"""Refresh public read DTO schema snapshots; never loads settings or storage."""
import json
from pathlib import Path

from job_agent.dashboard.approval_models import (
    BootstrapResponse, TailscaleBootstrapResponse, DecisionResult,
    DecisionDetail, PacketDetail, PacketDiffResult, QueueResponse, RevisionComparison, RevisionStatus,
)

target = Path(__file__).resolve().parents[1] / "src/lib/contracts.json"
target.write_text(json.dumps({model.__name__: model.model_json_schema()
    for model in (QueueResponse, PacketDetail, DecisionDetail, PacketDiffResult,
                  BootstrapResponse, TailscaleBootstrapResponse, DecisionResult, RevisionComparison, RevisionStatus)}, indent=2) + "\n")
