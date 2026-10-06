"""Synthetic ASGI policy only. Real Serve observations remain Milestone B."""
import json
from io import StringIO

import pytest
from pydantic import SecretStr
from rich.console import Console

from job_agent.config import Settings, load_settings
from job_agent.cli import _build_parser, cmd_approval_queue
from job_agent.dashboard.approval_app import create_approval_app
from job_agent.dashboard.approval_security import (
    LocalBoundaryMiddleware, ProcessCSRF, SECURITY_HEADERS, approval_access,
)
from test_approval_security import request, private_app

HOST = b"pilot.tailtest.ts.net"
LOGIN = b"operator@example.test"


def settings(**values):
    return Settings(approval_tailscale_login=LOGIN.decode(),
                    approval_tailscale_host=HOST.decode(), **values)


def headers(csrf=None):
    result = [(b"host", HOST), (b"tailscale-user-login", LOGIN)]
    if csrf:
        result += [(b"origin", b"https://" + HOST),
                   (b"x-job-pilot-csrf", csrf.token().encode()),
                   (b"content-type", b"application/json")]
    return result


def guard(csrf=None):
    return LocalBoundaryMiddleware(private_app, port=8643, csrf=csrf,
                                   access="tailscale", settings=settings())


@pytest.mark.parametrize("field,value", [
    ("login", None), ("host", None), ("login", ""), ("host", ""),
    *[("login", v) for v in ("*", "a?b", "a[b]", "a,b", " a", "a ", "a\tb", "a\nb", "a\x00b", "a\x7fb", "é", "=?UTF-8?B?YWJj?=", "x" * 513)],
    *[("host", v) for v in ("localhost", "127.0.0.1", "100.64.0.1", "::1", "*.ts.net", "https://pilot.tailtest.ts.net", "pilot.tailtest.ts.net/", "pilot.tailtest.ts.net:443", "pilot.tailtest.ts.net.", "PILOT.tailtest.ts.net", " pilot.tailtest.ts.net", "user@pilot.tailtest.ts.net", "attacker.ts.net", "a..ts.net", "-a.tailtest.ts.net", "a._tail.ts.net")],
])
def test_invalid_config_refuses_before_storage(field, value, monkeypatch):
    configured = settings().model_copy(update={"approval_tailscale_" + field:
        SecretStr(value) if value is not None else None})
    monkeypatch.setattr("job_agent.dashboard.approval_app._existing_engine",
                        lambda *a: pytest.fail("invalid config must precede storage"))
    with pytest.raises(ValueError, match="^invalid_approval_access_configuration$") as failure:
        create_approval_app(settings=configured, access="tailscale")
    assert str(failure.value) == "invalid_approval_access_configuration"
    assert approval_access("local", configured) == (None, None)


def test_config_environment_private_exact(monkeypatch):
    monkeypatch.setattr("job_agent.config.load_dotenv", lambda: None)
    monkeypatch.setenv("JOB_AGENT_APPROVAL_TAILSCALE_LOGIN", LOGIN.decode())
    monkeypatch.setenv("JOB_AGENT_APPROVAL_TAILSCALE_HOST", HOST.decode())
    configured = load_settings()
    assert approval_access("tailscale", configured) == (LOGIN, HOST)
    for output in (repr(configured), configured.model_dump_json()):
        assert LOGIN.decode() not in output and HOST.decode() not in output
    monkeypatch.setenv("JOB_AGENT_APPROVAL_TAILSCALE_LOGIN", " " + LOGIN.decode())
    with pytest.raises(ValueError): approval_access("tailscale", load_settings())


def test_modes_explicit_local_default_and_no_host_option():
    parser = _build_parser()
    assert parser.parse_args(["approval-queue"]).access == "local"
    assert parser.parse_args(["approval-queue", "--access", "tailscale"]).access == "tailscale"
    assert approval_access("local", Settings()) == (None, None)
    for name in ("0.0.0.0", "::", "192.168.1.2", "100.64.0.1", "127.0.0.1"):
        with pytest.raises(SystemExit): parser.parse_args(["approval-queue", "--host", name])
    with pytest.raises(ValueError): approval_access("other", settings())


@pytest.mark.parametrize("access", ["local", "tailscale"])
def test_cli_fixed_bind_private_output(access, monkeypatch):
    import uvicorn
    received = []
    monkeypatch.setattr("job_agent.cli.load_settings", settings)
    monkeypatch.setattr("job_agent.dashboard.approval_app.create_approval_app",
        lambda **kwargs: received.append(kwargs) or object())
    monkeypatch.setattr(uvicorn, "run", lambda *args, **kwargs: received.append(kwargs))
    out = StringIO()
    args = _build_parser().parse_args(["approval-queue", "--access", access])
    assert cmd_approval_queue(Console(file=out), args) == 0
    assert received[0]["access"] == access
    assert received[1] == dict(host="127.0.0.1", port=8643, proxy_headers=False,
                              forwarded_allow_ips="", access_log=False, log_level="warning")
    assert HOST.decode() not in out.getvalue() and LOGIN.decode() not in out.getvalue()


@pytest.mark.parametrize("field", ["login", "host"])
def test_cli_missing_config_never_launches(field, monkeypatch):
    import uvicorn
    configured = settings().model_copy(update={"approval_tailscale_" + field: None})
    monkeypatch.setattr("job_agent.cli.load_settings", lambda: configured)
    monkeypatch.setattr(uvicorn, "run", lambda *a, **k: pytest.fail("must refuse startup"))
    out = StringIO()
    assert cmd_approval_queue(Console(file=out), _build_parser().parse_args([
        "approval-queue", "--access", "tailscale"])) == 1
    assert HOST.decode() not in out.getvalue() and LOGIN.decode() not in out.getvalue()


@pytest.mark.parametrize("identity,status", [
    ([], 401), ([b""], 401), ([LOGIN, LOGIN], 401), ([LOGIN + b",other"], 401),
    ([b"x" * 513], 401), ([b"\xff"], 401), ([b"a\x00b"], 401), ([b"a\r\nb"], 401),
    ([b" a"], 401), ([b"a "], 401), ([b"a\x7fb"], 401), ([b"=?UTF-8?Q?operator?="], 401),
    ([b"shared@example.test"], 403), ([LOGIN.upper()], 403), ([b"operator"], 403),
    ([b"prefix" + LOGIN], 403), ([LOGIN + b"suffix"], 403),
])
def test_identity_raw_exact_private_before_body(identity, status, caplog):
    hs = [(b"host", HOST), *[(b"Tailscale-User-Login", v) for v in identity]]
    actual, secured, content, reads = request(guard(), method="POST", headers=hs, body=b"PRIVATE_BODY")
    assert actual == status and reads == 0
    code = "authentication_required" if status == 401 else "authorization_failed"
    assert json.loads(content) == {"error": {"code": code}}
    for name, value in SECURITY_HEADERS.items(): assert secured[name.lower().encode()] == value.encode()
    assert LOGIN.decode() not in caplog.text and HOST.decode() not in caplog.text


@pytest.mark.parametrize("extra", [
    [(b"tailscale-user-name", LOGIN)], [(b"tailscale-user-profile-pic", b"https://example.test/pic")],
    [(b"cookie", b"Tailscale-User-Login=" + LOGIN)], [(b"x-forwarded-user", LOGIN)],
    [(b"forwarded", b"for=127.0.0.1;user=" + LOGIN)],
])
def test_nonidentity_sources_cannot_authenticate(extra):
    assert request(guard(), headers=[(b"host", HOST), *extra],
                   query="Tailscale-User-Login=operator@example.test")[0] == 401


def test_wrong_identity_correct_display_name_fails():
    assert request(guard(), headers=[(b"host", HOST), (b"tailscale-user-login", b"other@example.test"),
                                    (b"tailscale-user-name", LOGIN)])[0] == 403


@pytest.mark.parametrize("change", [
    {"client": ("192.168.1.2", 1234)}, {"client": ("100.64.0.1", 1234)},
    {"client": ("::1", 1234)}, {"client": None}, {"server": ("0.0.0.0", 8643)},
    {"server": ("::", 8643)}, {"server": ("192.168.1.2", 8643)},
    {"server": ("100.64.0.1", 8643)}, {"server": ("127.0.0.1", 8642)}, {"scheme": "https"},
])
def test_loopback_precedes_host_auth_body(change):
    hs = [(b"host", b"bad"), (b"tailscale-user-login", LOGIN),
          (b"x-forwarded-for", b"127.0.0.1"), (b"x-forwarded-host", HOST),
          (b"x-forwarded-proto", b"http"), (b"forwarded", b"for=127.0.0.1")]
    status, _, body, reads = request(guard(), method="POST", headers=hs, **change)
    assert status == 403 and json.loads(body)["error"]["code"] == "local_only" and reads == 0


@pytest.mark.parametrize("host", [b"localhost:8643", b"127.0.0.1:8643", b"localhost", b"127.0.0.1",
    b"*.ts.net", b"attacker.ts.net", HOST + b".evil.test", b"prefix" + HOST, HOST + b".",
    HOST + b":443", HOST + b":8643", HOST.upper(), b"user@" + HOST, b"https://" + HOST,
    HOST + b"/", b" " + HOST, HOST + b"\x00", HOST + b"," + HOST])
def test_host_exact_before_identity(host):
    status, _, body, reads = request(guard(), method="POST", headers=[(b"host", host),
        (b"x-forwarded-host", HOST), (b"forwarded", b"host=" + HOST)])
    assert status == 400 and json.loads(body)["error"]["code"] == "invalid_host" and reads == 0


def test_duplicate_host_and_forwarded_ignored():
    assert request(guard(), headers=[*headers(), (b"Host", HOST)])[0] == 400
    assert request(guard(), headers=[*headers(), (b"x-forwarded-host", b"evil"),
        (b"x-forwarded-proto", b"https"), (b"x-forwarded-for", b"10.0.0.1")])[0] == 200


@pytest.mark.parametrize("change", ["no_auth", "wrong_auth", "no_origin", "null", "http", "foreign",
    "duplicate_origin", "malformed", "no_csrf", "bad_csrf", "duplicate_csrf", "restart"])
def test_mutation_independent_auth_origin_csrf_no_body(change):
    csrf = ProcessCSRF()
    hs = headers(csrf)
    replacements = {"no_auth": (b"tailscale-user-login", None), "wrong_auth": (b"tailscale-user-login", b"other@example.test"),
        "no_origin": (b"origin", None), "null": (b"origin", b"null"), "http": (b"origin", b"http://" + HOST),
        "foreign": (b"origin", b"https://foreign.example.test"), "malformed": (b"origin", b"https://" + HOST + b"/"),
        "no_csrf": (b"x-job-pilot-csrf", None), "bad_csrf": (b"x-job-pilot-csrf", b"bad"),
        "restart": (b"x-job-pilot-csrf", ProcessCSRF().token().encode())}
    if change.startswith("duplicate_"):
        name = b"origin" if change == "duplicate_origin" else b"x-job-pilot-csrf"
        hs.append(next(pair for pair in hs if pair[0] == name))
    else:
        name, value = replacements[change]
        hs = [(k, v) for k, v in hs if k != name]
        if value is not None: hs.append((name, value))
    status, _, body, reads = request(guard(csrf), method="POST", headers=hs, body=b"PRIVATE")
    assert status == (401 if change == "no_auth" else 403) and reads == 0
    assert b"PRIVATE" not in body


@pytest.mark.parametrize("port", [80, 8643])
def test_https_origin_does_not_follow_backend_port(port):
    csrf = ProcessCSRF()
    boundary = LocalBoundaryMiddleware(private_app, port=port, csrf=csrf, access="tailscale", settings=settings())
    assert request(boundary, port=port, method="POST", headers=headers(csrf), body=b"{}")[0] == 200


@pytest.mark.parametrize("extra,body,status", [
    ([(b"content-type", b"text/plain")], b"{}", 422),
    ([(b"content-encoding", b"gzip")], b"{}", 422),
    ([(b"content-length", b"65537")], b"{}", 413), ([], b"x" * 65537, 413),
])
def test_authenticated_body_policy_preserved(extra, body, status):
    csrf = ProcessCSRF(); hs = headers(csrf)
    if any(k == b"content-type" for k, _ in extra): hs = [(k, v) for k, v in hs if k != b"content-type"]
    assert request(guard(csrf), method="POST", headers=[*hs, *extra], body=body)[0] == status
