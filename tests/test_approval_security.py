"""Direct ASGI boundary tests, no sockets/TestClient/Chromium required."""
import asyncio
import json

import pytest

from job_agent.dashboard.approval_security import LocalBoundaryMiddleware, SECURITY_HEADERS, validate_port


def request(app, path="/", *, method="GET", headers=None, port=8643,
            server=None, client=("127.0.0.1", 1234), scheme="http", query="", body=b""):
    messages, reads = [], []
    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
        "method": method, "scheme": scheme, "path": path, "raw_path": path.encode(),
        "query_string": query.encode(), "root_path": "",
        "server": server if server is not None else ("127.0.0.1", port), "client": client,
        "headers": headers if headers is not None else [(b"host", f"127.0.0.1:{port}".encode())]}

    async def run():
        async def receive():
            reads.append(True)
            return {"type": "http.request", "body": body, "more_body": False}
        async def send(message):
            messages.append(message)
        await asyncio.wait_for(app(scope, receive, send), timeout=15)
    asyncio.run(run())
    start = next(m for m in messages if m["type"] == "http.response.start")
    content = b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")
    return start["status"], dict(start["headers"]), content, len(reads)


async def private_app(scope, receive, send):
    from starlette.responses import JSONResponse
    await JSONResponse({"private": "served"})(scope, receive, send)


@pytest.mark.parametrize("host", [
    b"attacker.example:8643", b"*.localhost:8643", b"localhost.:8643",
    b"127.0.0.1.attacker.example:8643", b"user@localhost:8643", b"localhost:0",
    b"localhost:8642", b"localhost:08643", b"LOCALHOST:8643", b"localhost",
    b"localhost:8643 ", b" localhost:8643", b"localhost:8643/path", b"[::1]:8643",
    b"0.0.0.0:8643", b"localhost:8643,attacker.example", b"localhost:8643\x00",
    b"http://localhost:8643", b"localhost:8643#fragment", b"localhost:8643?query",
])
def test_host_rejected_before_body(host):
    status, headers, body, reads = request(LocalBoundaryMiddleware(private_app, port=8643),
        method="POST", headers=[(b"host", host)], body=b"PRIVATE_REQUEST")
    assert status == 400 and json.loads(body) == {"error": {"code": "invalid_host"}}
    assert reads == 0 and b"PRIVATE_REQUEST" not in body
    assert headers[b"cache-control"] == b"no-store"


@pytest.mark.parametrize("headers", [[], [(b"host", b"localhost:8643"), (b"Host", b"localhost:8643")]])
def test_host_missing_duplicate(headers):
    assert request(LocalBoundaryMiddleware(private_app, port=8643), headers=headers)[0] == 400


@pytest.mark.parametrize("host", [b"127.0.0.1:8643", b"localhost:8643"])
def test_exact_local_host_and_headers(host):
    status, headers, body, _ = request(LocalBoundaryMiddleware(private_app, port=8643), headers=[(b"host", host)])
    assert status == 200 and b"served" in body
    for name, value in SECURITY_HEADERS.items():
        assert headers[name.lower().encode()] == value.encode()
    assert not any(b"access-control" in name for name in headers)


@pytest.mark.parametrize("host", [b"127.0.0.1", b"localhost", b"127.0.0.1:80", b"localhost:80"])
def test_port_80_browser_authority(host):
    assert request(LocalBoundaryMiddleware(private_app, port=80), port=80, headers=[(b"host", host)])[0] == 200


@pytest.mark.parametrize("change", [
    {"server": ("0.0.0.0", 8643)}, {"server": ("::", 8643)},
    {"server": ("192.168.1.2", 8643)}, {"server": ("127.0.0.1", 8642)},
    {"client": ("192.168.1.2", 1234)}, {"client": None}, {"scheme": "https"},
])
def test_alternate_invocation_fails_closed(change):
    assert request(LocalBoundaryMiddleware(private_app, port=8643), **change)[0] == 403


def test_forwarded_headers_never_replace_host_or_peer():
    forwarded = [(b"forwarded", b"for=127.0.0.1;host=localhost:8643;proto=http"),
        (b"x-forwarded-for", b"127.0.0.1"), (b"x-forwarded-host", b"localhost:8643"),
        (b"x-forwarded-proto", b"http")]
    guard = LocalBoundaryMiddleware(private_app, port=8643)
    assert request(guard, headers=[(b"host", b"attacker.example:8643"), *forwarded])[0] == 400
    assert request(guard, headers=[(b"host", b"localhost:8643"), *forwarded], client=("10.0.0.1", 1234))[0] == 403
    assert request(guard, headers=[(b"host", b"localhost:8643"), (b"x-forwarded-host", b"attacker.example")])[0] == 200


@pytest.mark.parametrize("port", [0, -1, 65536, True, "8643", None])
def test_invalid_factory_ports(port):
    with pytest.raises(ValueError, match="invalid_approval_port"):
        validate_port(port)


def test_unexpected_errors_are_sanitized_and_secured():
    async def failing(scope, receive, send):
        raise RuntimeError("PRIVATE_SQL_PATH_TOKEN")
    status, headers, body, _ = request(LocalBoundaryMiddleware(failing, port=8643))
    assert status == 500 and json.loads(body) == {"error": {"code": "internal_error"}}
    assert b"PRIVATE" not in body and headers[b"x-frame-options"] == b"DENY"


def mutation_headers(csrf, *, origin=b"http://127.0.0.1:8643", host=b"127.0.0.1:8643"):
    return [(b"host", host), (b"origin", origin), (b"x-job-pilot-csrf", csrf.token().encode()),
            (b"content-type", b"application/json")]


@pytest.mark.parametrize("origin", [None, b"null", b"https://127.0.0.1:8643", b"http://attacker.example",
    b"http://localhost:8643", b"http://127.0.0.1:8642", b"http://127.0.0.1:8643/",
    b"http://127.0.0.1:8643.attacker.example", b"http://user@127.0.0.1:8643", b" http://127.0.0.1:8643",
    b"http://127.0.0.1.:8643", b"http://127.0.0.1:08643", b"http://127.0.0.1:8643 http://localhost:8643"])
def test_origin_required_exact_before_body(origin):
    from job_agent.dashboard.approval_security import ProcessCSRF
    csrf = ProcessCSRF()
    headers = mutation_headers(csrf)
    headers = [(k, v) for k, v in headers if k != b"origin"]
    if origin is not None:
        headers.append((b"origin", origin))
    status, _, body, reads = request(LocalBoundaryMiddleware(private_app, port=8643, csrf=csrf),
        method="POST", headers=headers, body=b"PRIVATE_FEEDBACK")
    assert status == 403 and json.loads(body) == {"error": {"code": "csrf_failed"}}
    assert reads == 0


@pytest.mark.parametrize("change", ["missing", "bad", "duplicate_token", "duplicate_origin", "old_process", "non_ascii"])
def test_csrf_missing_bad_duplicates_restart(change):
    from job_agent.dashboard.approval_security import ProcessCSRF
    csrf = ProcessCSRF()
    headers = mutation_headers(csrf)
    if change == "duplicate_token":
        headers.append((b"x-job-pilot-csrf", csrf.token().encode()))
    elif change == "duplicate_origin":
        headers.append((b"origin", b"http://127.0.0.1:8643"))
    else:
        headers = [(k, v) for k, v in headers if k != b"x-job-pilot-csrf"]
        if change != "missing":
            value = {"bad": b"BAD", "old_process": ProcessCSRF().token().encode(), "non_ascii": b"\xff"}[change]
            headers.append((b"x-job-pilot-csrf", value))
    status, _, body, reads = request(LocalBoundaryMiddleware(private_app, port=8643, csrf=csrf),
        method="POST", headers=headers, body=b"PRIVATE_FEEDBACK")
    assert status == 403 and reads == 0 and b"PRIVATE" not in body


@pytest.mark.parametrize("host,origin,port", [
    (b"127.0.0.1:8643", b"http://127.0.0.1:8643", 8643),
    (b"localhost:8643", b"http://localhost:8643", 8643),
    (b"localhost:80", b"http://localhost", 80),
    (b"localhost", b"http://localhost:80", 80),
])
def test_matching_origin_token_json_accepted(host, origin, port):
    import base64
    from job_agent.dashboard.approval_security import ProcessCSRF
    csrf = ProcessCSRF()
    assert len(base64.urlsafe_b64decode(csrf.token() + "=")) >= 32
    guard = LocalBoundaryMiddleware(private_app, port=port, csrf=csrf)
    assert request(guard, method="POST", port=port, headers=mutation_headers(csrf, host=host, origin=origin), body=b"{}")[0] == 200


@pytest.mark.parametrize("extra,body,status", [
    ([(b"content-type", b"text/plain")], b"{}", 422),
    ([(b"content-encoding", b"gzip")], b"{}", 422),
    ([(b"content-length", b"65537")], b"{}", 413),
    ([(b"content-length", b"-1")], b"{}", 422),
    ([(b"content-length", b"3")], b"{}", 422),
    ([], b"x" * 65537, 413),
], ids=["wrong_content_type", "compressed", "declared_oversize", "negative_length", "length_mismatch", "actual_oversize"])
def test_mutation_body_policy(extra, body, status):
    from job_agent.dashboard.approval_security import ProcessCSRF
    csrf = ProcessCSRF()
    headers = mutation_headers(csrf)
    if any(k == b"content-type" for k, v in extra):
        headers = [(k, v) for k, v in headers if k != b"content-type"]
    actual, secured, result, _ = request(LocalBoundaryMiddleware(private_app, port=8643, csrf=csrf),
        method="POST", headers=[*headers, *extra], body=body)
    assert actual == status and json.loads(result) == {"error": {"code": "invalid_request"}}
    assert secured[b"cache-control"] == b"no-store"


def test_streamed_body_bound_without_content_length():
    from job_agent.dashboard.approval_security import bounded_json_receive, AdapterError
    chunks = iter([{"type": "http.request", "body": b"x" * 40000, "more_body": True},
        {"type": "http.request", "body": b"y" * 40000, "more_body": False}])
    async def receive():
        return next(chunks)
    with pytest.raises(AdapterError) as exc:
        asyncio.run(bounded_json_receive({"headers": [(b"content-type", b"application/json")]}, receive))
    assert exc.value.status == 413



def test_streamed_mutation_body_is_bounded_without_content_length():
    from job_agent.dashboard.approval_security import ProcessCSRF
    csrf = ProcessCSRF()
    reached, messages = [], []
    async def downstream(scope, receive, send): reached.append(True)
    scope = {"type": "http", "method": "POST", "scheme": "http",
        "server": ("127.0.0.1", 8643), "client": ("127.0.0.1", 1),
        "headers": mutation_headers(csrf)}
    chunks = iter([{"type": "http.request", "body": b"PRIVATE" + b"x" * 32761, "more_body": True},
                   {"type": "http.request", "body": b"x" * 32769, "more_body": False}])
    async def run():
        async def receive(): return next(chunks)
        async def send(message): messages.append(message)
        await LocalBoundaryMiddleware(downstream, port=8643, csrf=csrf)(scope, receive, send)
    asyncio.run(run())
    assert not reached and messages[0]["status"] == 413
    assert b"PRIVATE" not in messages[1]["body"]
    assert json.loads(messages[1]["body"]) == {"error": {"code": "invalid_request"}}
