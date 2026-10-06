"""Separate loopback approval app. Legacy dashboard/router are not mounted."""
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated
from urllib.parse import quote

from fastapi import FastAPI, Path as PathParam, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import Response
from sqlalchemy import event
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import create_engine
from starlette.exceptions import HTTPException

from job_agent.approvals import DecisionError
from job_agent.config import Settings
from job_agent.database import SCHEMA_VERSION
from job_agent.packet_history import HistoryError
from job_agent.packets import private_packet_logs
from job_agent.dashboard.approval_models import (ApproveRequest, BootstrapResponse,
    ApplicationDestination, DecisionDetail, DecisionResult, HistoryItem, PacketDetail, PacketDiffResult,
    QueueQuery, QueueResponse, RejectRequest, ReviseRequest, RevisionStatus, TailscaleBootstrapResponse)
from job_agent.dashboard.approval_security import (
    AdapterError, LocalBoundaryMiddleware, ProcessCSRF, approval_access, error_response, validate_port,
)
from job_agent.dashboard.approval_service import ApprovalQueueService

_STATIC = Path(__file__).resolve().parent / "static"
PacketID = Annotated[str, PathParam(pattern=r"^[0-9a-f]{32}$")]

DOMAIN_ERRORS = {
    "packet_not_found": (404, "not_found"),
    "invalid_packet_reference": (422, "invalid_request"),
    "stale_packet_fingerprint": (409, "stale_packet"),
    "stale_approval_view": (409, "stale_approval_view"),
    "packet_decision_conflict": (409, "decision_conflict"),
    "packet_integrity_failed": (409, "packet_integrity_failed"),
    "approval_evidence_changed": (409, "approval_not_current"),
    "packet_not_approved": (409, "approval_not_current"),
    "packet_lock_unavailable": (503, "storage_unavailable"),
    "decision_storage_failed": (503, "storage_unavailable"),
    "invalid_reject_reason": (422, "invalid_request"),
    "invalid_decision_detail": (422, "invalid_request"),
    "revision_feedback_required": (422, "invalid_request"),
    "invalid_history_reference": (422, "invalid_request"),
    "history_integrity_failed": (409, "packet_integrity_failed"),
    "history_storage_error": (503, "storage_unavailable"),
    "artifact_unavailable": (404, "artifact_unavailable"),
    "artifact_integrity_failed": (409, "artifact_integrity_failed"),
}


def _existing_engine(settings):
    """Open existing v9 only. No creation, migration, legacy import or schema DDL."""
    path = settings.data_dir.absolute() / "job_pilot.sqlite3"
    engine = create_engine(f"sqlite:///file:{quote(str(path), safe='/')}?mode=rw&uri=true",
                           connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")

    try:
        with engine.connect() as connection:
            if connection.exec_driver_sql("PRAGMA user_version").scalar() != SCHEMA_VERSION:
                raise ValueError("approval_schema_unavailable")
    except Exception:
        engine.dispose()
        raise ValueError("approval_storage_unavailable") from None
    return engine


def create_approval_app(*, settings: Settings | None = None, engine=None, port: int = 8643,
                        access: str = "local") -> FastAPI:
    """Factory binds request policy to the actual CLI/test server port.

    Alternate launchers must bind 127.0.0.1 with proxy_headers=False too. Broad
    server/client endpoints are refused by the request guard even with valid Host.
    """
    validate_port(port)
    settings = settings if settings is not None else Settings()
    approval_access(access, settings)
    owned = engine is None
    if owned:
        with private_packet_logs():
            engine = _existing_engine(settings)
    service = ApprovalQueueService(engine, settings)
    csrf = ProcessCSRF()

    @asynccontextmanager
    async def lifespan(app):
        try:
            yield
        finally:
            if owned:
                engine.dispose()

    app = FastAPI(title="Job Pilot approval", docs_url=None, redoc_url=None,
                  openapi_url=None, lifespan=lifespan)
    app.add_middleware(LocalBoundaryMiddleware, port=port, csrf=csrf, access=access, settings=settings)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request, exc):
        return error_response("invalid_request", 422)

    @app.exception_handler(AdapterError)
    async def adapter_error(request, exc):
        return error_response(exc.code, exc.status)

    @app.exception_handler(DecisionError)
    @app.exception_handler(HistoryError)
    async def domain_error(request, exc):
        status, code = DOMAIN_ERRORS.get(str(exc), (500, "internal_error"))
        return error_response(code, status)

    @app.exception_handler(SQLAlchemyError)
    async def storage_error(request, exc):
        return error_response("storage_unavailable", 503)

    @app.exception_handler(HTTPException)
    async def http_error(request, exc):
        code = "not_found" if exc.status_code == 404 else "invalid_request"
        return error_response(code, exc.status_code)

    @app.get("/", include_in_schema=False)
    def shell():
        return Response((_STATIC / "approval.html").read_bytes(), media_type="text/html")

    @app.get("/assets/{asset}", include_in_schema=False)
    def asset_file(asset: str):
        assets = {"approval.js": "text/javascript", "approval.css": "text/css"}
        if asset not in assets:
            raise AdapterError("not_found", 404)
        return Response((_STATIC / asset).read_bytes(), media_type=assets[asset])

    @app.get("/api/queue", response_model=QueueResponse)
    def queue(query: Annotated[QueueQuery, Query()]):
        return service.queue(query)

    @app.get("/api/bootstrap", response_model=BootstrapResponse | TailscaleBootstrapResponse)
    async def bootstrap(request: Request):
        if access == "tailscale":
            return TailscaleBootstrapResponse(csrf_token=csrf.token())
        # Host has already passed the raw boundary; no DB/provider access.
        authority = request.headers["host"]
        if port == 80:
            authority = authority.removesuffix(":80")
        return BootstrapResponse(csrf_token=csrf.token(), origin="http://" + authority)

    @app.get("/api/packets/{packet_id}", response_model=PacketDetail)
    def packet_detail(packet_id: PacketID):
        return service.detail(packet_id)

    @app.get("/api/packets/{packet_id}/history", response_model=list[HistoryItem])
    def history(packet_id: PacketID):
        return service.history(packet_id)

    @app.get("/api/packets/{packet_id}/revision-status", response_model=RevisionStatus)
    def revision_status(packet_id: PacketID):
        return service.revision_status(packet_id)

    @app.get("/api/packets/{packet_id}/decision-detail", response_model=DecisionDetail)
    def decision_detail(packet_id: PacketID):
        return service.decision_detail(packet_id)

    @app.get("/api/packets/{packet_id}/application-destination", response_model=ApplicationDestination)
    def destination(packet_id: PacketID):
        return service.application_destination(packet_id)

    @app.get("/api/packets/{left_id}/diff/resume/{right_id}", response_model=PacketDiffResult)
    def resume_diff(left_id: PacketID, right_id: PacketID):
        return service.packet_diff(left_id, right_id, "resume")

    @app.get("/api/packets/{left_id}/diff/cover/{right_id}", response_model=PacketDiffResult)
    def cover_diff(left_id: PacketID, right_id: PacketID):
        return service.packet_diff(left_id, right_id, "cover")

    @app.get("/api/packets/{packet_id}/artifacts/resume.pdf")
    def resume_pdf(packet_id: PacketID, request: Request):
        if request.query_params:
            raise AdapterError("invalid_request", 422)
        version, content = service.resume_pdf(packet_id)
        return Response(content, media_type="application/pdf", headers={
            "Content-Disposition": f'inline; filename="resume-v{version}.pdf"'})

    @app.post("/api/packets/{packet_id}/approve", response_model=DecisionResult)
    def approve_packet(packet_id: PacketID, body: ApproveRequest):
        return service.approve(packet_id, body)

    @app.post("/api/packets/{packet_id}/reject", response_model=DecisionResult)
    def reject_packet(packet_id: PacketID, body: RejectRequest):
        return service.reject(packet_id, body)

    @app.post("/api/packets/{packet_id}/revise", response_model=DecisionResult)
    def revise_packet(packet_id: PacketID, body: ReviseRequest):
        return service.revise(packet_id, body)

    return app
