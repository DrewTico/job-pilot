"""ATS source implementations and a small factory."""

from __future__ import annotations

from job_agent.sources.ashby import AshbySource
from job_agent.sources.base import JobSource
from job_agent.sources.freehire import FreeHireSource, FreeHireRelocationSource
from job_agent.sources.greenhouse import GreenhouseSource
from job_agent.sources.lever import LeverSource
from job_agent.sources.remoteok import RemoteOKSource
from job_agent.sources.remotive import RemotiveSource
from job_agent.sources.smartrecruiters import SmartRecruitersSource
from job_agent.sources.sr_search import SmartRecruitersSearchSource

_REGISTRY: dict[str, type[JobSource]] = {
    GreenhouseSource.ats: GreenhouseSource,
    LeverSource.ats: LeverSource,
    AshbySource.ats: AshbySource,
    SmartRecruitersSource.ats: SmartRecruitersSource,
    # Cross-company discovery: ``board`` is a keyword query / tag, not a company.
    SmartRecruitersSearchSource.ats: SmartRecruitersSearchSource,
    RemotiveSource.ats: RemotiveSource,
    RemoteOKSource.ats: RemoteOKSource,
    FreeHireSource.ats: FreeHireSource,
    FreeHireRelocationSource.ats: FreeHireRelocationSource,
}


def build_source(ats: str, board: str) -> JobSource:
    """Construct a source for ``ats``. Raises KeyError for unknown ATS names."""
    return _REGISTRY[ats](board)


__all__ = [
    "JobSource",
    "GreenhouseSource",
    "LeverSource",
    "AshbySource",
    "SmartRecruitersSource",
    "SmartRecruitersSearchSource",
    "RemotiveSource",
    "RemoteOKSource",
    "FreeHireSource",
    "FreeHireRelocationSource",
    "build_source",
]
