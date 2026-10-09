"""Source-owned fictional review evidence. No settings, DB or private files."""
import json
from pathlib import Path

from job_agent.dashboard.approval_models import PacketDetail

def history(index, version, **changes):
    result = dict(packet_id=f"{index:032x}", version=version, status="packet_ready",
        created_at="2026-10-01T14:00:00Z", updated_at="2026-10-01T14:05:00Z",
        ready_at="2026-10-01T14:05:00Z", decision=None, revision_decision_id=None,
        source_packet_id=None, lineage_kind="unlinked", is_latest_allocated=True,
        is_latest_ready=True)
    result.update(changes)
    return result

def packet(index, **changes):
    identity = f"{index:032x}"
    base = dict(packet_id=identity, version=2, company="Synthetic · Northstar Instruments",
        title="Software Engineer, Applied AI", location="Remote, United States", score=94, tier="A",
        status="packet_ready", ready_at="2026-10-01T14:05:00Z", expected_packet_fingerprint="a" * 64,
        decision=None, integrity="passed", current_authorization="not_approved",
        reasons=["The role asks for Python APIs and practical AI evaluation.", "The packet includes evidence of retrieval testing and review tooling."],
        matched_requirements=["Python API development", "Automated testing", "Human review of AI output"],
        missing_requirements=["Production experience with the employer's internal platform"],
        cover_letter_acceptance="yes", cover_text="Northstar Instruments builds tools for teams that need traceable evidence.\n\nMy synthetic project pairs a Python API with a review interface and tests every boundary before a decision. I built structured output checks and a manual review path for answers the system could not verify.\n\nI would bring that same evidence-first approach to your applied AI tooling.",
        cover_integrity="available", screening={"answers": [{"question": "Describe a relevant project.", "answer": "Synthetic project: evidence review with API contracts and keyboard navigation."}, {"question": "Can you work in the listed location?", "answer": True}], "manual_needed": []},
        company_facts=[{"text": "Fictional Northstar Instruments makes review tools for laboratory teams.", "source_title": "Synthetic company profile", "source_url": "https://northstar.invalid/company"}],
        history=[history(index, 2), history(90, 1, is_latest_ready=False, is_latest_allocated=False)],
        revision={"source_packet_id": identity, "decision_id": None, "state": "none", "label": "No revision requested"},
        artifacts=[{"kind": "resume_pdf", "available": True, "size": 18432}],
        application_destination={"url": "https://northstar.invalid/careers/synthetic-role", "domain": "northstar.invalid", "authorization": "not_approved"},
        approval_preview=None)
    base.update(changes)
    base['history'][0].update(version=base['version'], status=base['status'],
        decision=base['decision'], ready_at=base['ready_at'])
    if base['decision'] is None and base['integrity'] == 'passed' and base['application_destination']['url']:
        base['approval_preview'] = dict(packet_id=identity, packet_version=base['version'],
            expected_packet_fingerprint=base['expected_packet_fingerprint'],
            expected_approval_view_fingerprint='b' * 64,
            application_url=base['application_destination']['url'])
    return PacketDetail.model_validate(base).model_dump()

packets = [
    packet(1),
    packet(2, company="Synthetic · Meridian Field Systems", title="Associate Platform Engineer", score=78, tier="B",
        cover_letter_acceptance="unknown", screening={"answers": [{"question": "Preferred working hours", "answer": None}], "manual_needed": ["Confirm travel availability", "Provide an authorized salary expectation"]}),
    packet(3, company="Synthetic · Lantern Archive", title="Frontend Engineer, Accessible Research Collections and Long-Form Evidence Review", location=None, score=58, tier="C", missing_requirements=["Five years of frontend experience", "Native mobile delivery"], cover_letter_acceptance="no", cover_text=None, cover_integrity="unavailable", company_facts=[], artifacts=[{"kind": "resume_pdf", "available": False}], application_destination={"url": None, "domain": None, "authorization": "not_checked"}, integrity="not_checked"),
    packet(4, company="Synthetic · Harbor Tools", status="building", ready_at=None, integrity="not_checked", cover_text=None, cover_integrity="unavailable", decision="revise", revision={"source_packet_id": f"{4:032x}", "decision_id": "synthetic-revision", "state": "queued", "label": "Revision queued; awaiting worker"}),
    packet(5, company="Synthetic · Cedar Signal", status="recovery_required", integrity="failed", current_authorization="integrity_failed", decision="revise", cover_text=None, cover_integrity="integrity_failed", revision={"source_packet_id": f"{5:032x}", "decision_id": "synthetic-revision-2", "state": "blocked", "label": "Revision needs attention", "failure_category": "source_evidence"}),
    packet(6, company="Synthetic · Northstar Historical", decision="approve", current_authorization="evidence_changed", application_destination={"url": None, "domain": None, "authorization": "evidence_changed"}),
    packet(7, company="Synthetic · Alder Current", decision="approve", current_authorization="currently_valid", application_destination={"url": "https://alder.invalid/synthetic-job", "domain": "alder.invalid", "authorization": "currently_valid"}),
    packet(8, company="Synthetic · Elm Research", decision="reject", reasons=[], matched_requirements=[], missing_requirements=[], current_authorization="not_approved"),
    packet(9, company="Synthetic · Long Content Laboratory", cover_text=("Synthetic evidence paragraph. The review preserves the exact packet text, including long content and line breaks.\n\n" * 18), screening={"answers": [{"question": "Explain the architecture " + "in detail " * 12, "answer": "Synthetic structured answer. " * 30}], "manual_needed": ["Resolve this deliberately long synthetic question about a requirement that was not supplied in the packet. " * 5]}),
    packet(90, company="Synthetic · Northstar Instruments", version=1, history=[history(90, 1)]),
]
data = {"synthetic": True, "packets": packets, "sections": {"needs-review": [1, 2, 3, 9], "processing": [4], "needs-attention": [5], "history": [6, 7, 8]}}
target = Path(__file__).resolve().parents[1] / "src/fixtures/review.json"
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text(json.dumps(data, indent=2) + "\n")
