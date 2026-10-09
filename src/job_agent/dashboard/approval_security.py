"""Loopback approval boundary with explicit local or trusted Serve identity policy."""
import fcntl
import hmac
import os
import re
import secrets
import stat

from starlette.responses import JSONResponse


CSP = (
    "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; "
    "img-src 'none'; font-src 'self'; object-src 'none'; frame-src 'none'; "
    "worker-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none';"
)
SECURITY_HEADERS = {
    "Cache-Control": "no-store",
    "Pragma": "no-cache",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
    "Content-Security-Policy": CSP,
}
MAX_MUTATION_BODY_BYTES = 65_536


def supported_login(value):
    """Strict ASCII bytes only; no decoding/normalization or ambiguous lists."""
    return (isinstance(value, bytes) and 1 <= len(value) <= 512
            and all(33 <= byte <= 126 for byte in value)
            and not any(char in value for char in (b",", b"*", b"?", b"[", b"]"))
            and b"=?" not in value)


def approval_access(access, settings):
    """Validate private mode configuration before opening storage. Never echo it."""
    if access == "local":
        return None, None
    if access != "tailscale":
        raise ValueError("invalid_approval_access")
    try:
        login = settings.approval_tailscale_login.get_secret_value().encode("ascii")
        host = settings.approval_tailscale_host.get_secret_value().encode("ascii")
    except (AttributeError, UnicodeError):
        raise ValueError("invalid_approval_access_configuration") from None
    label = rb"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
    if (not supported_login(login) or len(host) > 253
            or re.fullmatch(label + rb"\." + label + rb"\.ts\.net", host) is None):
        raise ValueError("invalid_approval_access_configuration")
    return login, host


class ProcessCSRF:
    """One in-memory synchronizer token per approval app server instance.

    Generated from 32 random bytes at app construction/startup. No file, DB,
    cookie, URL, browser storage or logging. A restarted app gets a new token.
    """
    def __init__(self):
        self._token = secrets.token_urlsafe(32)

    def token(self):
        return self._token

    def accepts(self, headers, host, port, *, origin=None):
        origins = [value for name, value in headers if name.lower() == b"origin"]
        tokens = [value for name, value in headers if name.lower() == b"x-job-pilot-csrf"]
        allowed = {b"http://" + host}
        if port == 80:
            name = host.removesuffix(b":80")
            allowed = {b"http://" + name, b"http://" + name + b":80"}
        if origin is not None:
            allowed = {origin}
        return (len(origins) == 1 and origins[0] in allowed and len(tokens) == 1
                and hmac.compare_digest(tokens[0], self._token.encode("ascii")))


class AdapterError(ValueError):
    def __init__(self, code, status=409):
        self.code, self.status = code, status
        super().__init__(code)


def validate_port(port):
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError("invalid_approval_port")
    return port


def error_response(code, status):
    return JSONResponse({"error": {"code": code}}, status_code=status,
                        headers=SECURITY_HEADERS)


class LocalBoundaryMiddleware:
    """Check raw Host before routing/body reads; inspect actual ASGI endpoints.

    Uvicorn must also disable proxy_headers. Forwarded headers are ignored here.
    Exact scope server/client checks fail closed for alternate broad invocation.
    """
    def __init__(self, app, *, port, csrf=None, access="local", settings=None):
        self.app, self.port = app, validate_port(port)
        self.login, self.tailnet_host = approval_access(access, settings)
        self.access = access
        self.csrf = csrf if csrf is not None else ProcessCSRF()
        self.authorities = {f"127.0.0.1:{port}".encode(), f"localhost:{port}".encode()}
        if port == 80:
            self.authorities.update({b"127.0.0.1", b"localhost"})
        if access == "tailscale":
            # Canonical HTTPS authority only; explicit ports are refused.
            self.authorities = {self.tailnet_host}

    def loopback_boundary(self, scope):
        server, client = scope.get("server"), scope.get("client")
        return (server == ("127.0.0.1", self.port) and client
                and client[0] == "127.0.0.1" and scope.get("scheme") == "http")

    async def __call__(self, scope, receive, send):
        if scope["type"] == "lifespan":
            await self.app(scope, receive, send)
            return
        if scope["type"] != "http":
            await send({"type": "websocket.close", "code": 1008})
            return
        if self.access == "tailscale" and not self.loopback_boundary(scope):
            await error_response("local_only", 403)(scope, receive, send)
            return
        hosts = [value for name, value in scope.get("headers", []) if name.lower() == b"host"]
        if len(hosts) != 1 or hosts[0] not in self.authorities:
            await error_response("invalid_host", 400)(scope, receive, send)
            return
        if not self.loopback_boundary(scope):
            await error_response("local_only", 403)(scope, receive, send)
            return
        if self.access == "tailscale":
            identities = [v for k, v in scope.get("headers", []) if k.lower() == b"tailscale-user-login"]
            if len(identities) != 1 or not supported_login(identities[0]):
                await error_response("authentication_required", 401)(scope, receive, send)
                return
            if not hmac.compare_digest(identities[0], self.login):
                await error_response("authorization_failed", 403)(scope, receive, send)
                return
        if scope["method"] not in {"GET", "HEAD", "OPTIONS"}:
            # Origin + token are checked BEFORE receiving/parsing private bodies.
            origin = b"https://" + self.tailnet_host if self.access == "tailscale" else None
            if not self.csrf.accepts(scope.get("headers", []), hosts[0], self.port, origin=origin):
                await error_response("csrf_failed", 403)(scope, receive, send)
                return
            try:
                receive = await bounded_json_receive(scope, receive)
            except AdapterError as exc:
                await error_response(exc.code, exc.status)(scope, receive, send)
                return
        started = False

        async def secured_send(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
                names = {key.lower().encode() for key in SECURITY_HEADERS}
                headers = [(k, v) for k, v in message.get("headers", []) if k.lower() not in names]
                headers.extend((k.lower().encode(), v.encode()) for k, v in SECURITY_HEADERS.items())
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, secured_send)
        except Exception:
            # Never expose/log repr, SQL, private inputs or traceback.
            if not started:
                await error_response("internal_error", 500)(scope, receive, secured_send)


async def bounded_json_receive(scope, receive):
    """Capture a bounded JSON request before FastAPI's parser can buffer it.

    Content-Length alone is not authority: streamed/chunked bytes are bounded too.
    No private values appear in failures. FastAPI still owns JSON/DTO validation.
    """
    headers = scope.get("headers", [])
    types = [v.lower() for k, v in headers if k.lower() == b"content-type"]
    if len(types) != 1 or types[0] not in {b"application/json", b"application/json; charset=utf-8"}:
        raise AdapterError("invalid_request", 422)
    encodings = [v.lower() for k, v in headers if k.lower() == b"content-encoding"]
    if encodings and encodings != [b"identity"]:
        raise AdapterError("invalid_request", 422)
    lengths = [v for k, v in headers if k.lower() == b"content-length"]
    if lengths:
        if len(lengths) != 1 or not lengths[0].isdigit() or len(lengths[0]) > 10:
            raise AdapterError("invalid_request", 422)
        if int(lengths[0]) > MAX_MUTATION_BODY_BYTES:
            raise AdapterError("invalid_request", 413)
    body = bytearray()
    while True:
        message = await receive()
        if message["type"] != "http.request":
            raise AdapterError("invalid_request", 422)
        chunk = message.get("body", b"")
        if len(body) + len(chunk) > MAX_MUTATION_BODY_BYTES:
            raise AdapterError("invalid_request", 413)
        body.extend(chunk)
        if not message.get("more_body", False):
            break
    if lengths and len(body) != int(lengths[0]):
        raise AdapterError("invalid_request", 422)
    captured = bytes(body)
    delivered = False

    async def replay():
        nonlocal delivered
        if not delivered:
            delivered = True
            return {"type": "http.request", "body": captured, "more_body": False}
        return {"type": "http.disconnect"}
    return replay


def probe_packet_lock(settings):
    """UX-only nonblocking probe; the domain takes its own authoritative lock.

    Releasing this probe does not eliminate a subsequent cooperating-process race.
    Never creates or resets a lock or packet directory.
    """
    root = settings.data_dir.resolve() / "packets"
    descriptor = None
    try:
        if root.is_symlink() or not root.is_dir():
            raise AdapterError("storage_unavailable", 503)
        descriptor = os.open(root / ".build.lock", os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK)
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise AdapterError("storage_unavailable", 503)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise AdapterError("packet_busy", 503) from None
    except OSError:
        raise AdapterError("storage_unavailable", 503) from None
    finally:
        if descriptor is not None:
            os.close(descriptor)
