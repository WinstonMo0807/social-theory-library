"""Explicit field refresh adapter for the existing ResearchOrchestrator."""
from dataclasses import asdict, dataclass, replace
from hashlib import sha256
import json

from django.utils import timezone

from catalog.models import Edition, ResearchRun
from catalog.services.field_decisions import formal_field_values
from catalog.services.research.contracts import RESEARCH_CONTRACTS
from catalog.services.research.orchestrator import ResearchOrchestrator
from catalog.services.research.planner import ResearchPlanner, ResearchTask

from .policies import get_field_policy


FIELD_RESEARCH = {
    "author": ("contributors", "authors"),
    "translator": ("contributors", "translators"),
    "publisher": ("bibliography", "publisher"),
    "publication_year": ("bibliography", "publication_year"),
    "abstract": ("work", "abstract"),
    "topic": ("knowledge", "topics"),
    "theory": ("knowledge", "theories"),
}


def field_research_context(edition, policy, query=""):
    from .service import _edition_section_values
    from catalog.models import Person

    values, _confirmed = formal_field_values(edition, include_editorial_draft=True)
    contributions = _edition_section_values(edition, "contributors").get("contributors", [])
    people = {str(person.pk): person.preferred_name for person in Person.objects.filter(pk__in=[row["person_id"] for row in contributions])}
    draft = {
        "work": {key: values.get(key) for key in ("title", "subtitle", "original_title", "document_type", "language", "abstract")},
        "bibliography": {key: values.get(key) for key in ("isbn", "isbn10", "isbn13", "doi", "publisher", "publication_year", "publication_date", "responsibility_statement")},
        "contributors": {"items": [{**row, "display_name": people.get(str(row["person_id"]), "")} for row in contributions]},
        "knowledge": {"topics": values.get("topics", []), "theories": values.get("theories", [])},
    }
    fingerprint = sha256(json.dumps([policy.key, query, draft], ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()
    draft["field_assistant"] = {"field": policy.key, "query": query, "fingerprint": fingerprint}
    return draft, fingerprint


def research_context_is_current(run, edition, policy) -> bool:
    if run is None or not run.is_current or run.status in {"canceled", "superseded"}:
        return False
    marker = ((run.context_snapshot or {}).get("draft_data") or {}).get("field_assistant")
    if not marker:
        # Legacy runs have no field-session marker. Still compare substantive
        # book/version inputs so a new title or ISBN cannot revive old advice.
        current, _fingerprint = field_research_context(edition, policy)
        saved = run.context_snapshot or {}
        for section, fields in (("work", ("title", "original_title")), ("bibliography", ("isbn", "isbn10", "isbn13", "publisher", "publication_year"))):
            previous = {**((saved.get("persisted_data") or {}).get(section) or {}), **((saved.get("draft_data") or {}).get(section) or {})}
            if any(str(previous[field] or "") != str(current[section].get(field) or "") for field in fields if field in previous):
                return False
        return True
    if marker.get("field") != policy.key:
        return False
    _draft, fingerprint = field_research_context(edition, policy, marker.get("query", ""))
    return fingerprint == marker.get("fingerprint")


@dataclass
class FieldResearchTask(ResearchTask):
    allow_external: bool = True
    allow_web: bool = True
    allow_authority: bool = True


class FieldScopedPlanner(ResearchPlanner):
    def __init__(self, policy, query):
        super().__init__()
        self.policy = policy
        self.query = query

    def plan(self, context, **kwargs):
        context, tasks = super().plan(context, **kwargs)
        step, field = FIELD_RESEARCH[self.policy.key]
        contract = RESEARCH_CONTRACTS.get(step, field)
        base = next((task for task in tasks if task.step == step and task.field == contract.canonical_field), None)
        if base is None:
            return context, []
        query = self.query or base.query
        if self.policy.contribution_role:
            people = (context.draft_data.get("contributors") or {}).get("items") or []
            names = [row.get("display_name", "") for row in people if row.get("role") == self.policy.contribution_role and row.get("display_name")]
            query = self.query or (names[0] if names else f"{context.draft_value('work', 'title', '')} {self.policy.label}")
        task = replace(base, field=field, entity_types=contract.entity_types, query=query, reason=f"管理员在{self.policy.label}字段请求查找",
                       trigger_input_values={**base.trigger_input_values, "field_assistant.context": context.draft_data.get("field_assistant", {}).get("fingerprint")})
        return context, [FieldResearchTask(**asdict(task), allow_external=True, allow_authority=self.policy.allow_authority, allow_web=self.policy.allow_web)]


def refresh_state(run, *, reused=False):
    if not run.plan:
        return {"state": "unavailable", "message": "当前字段暂时没有可执行的查找来源，可以继续手工填写。", "reused": reused}
    preparing = run.status in {"queued", "running"}
    outcomes = (run.external_results or {}).get("field_outcomes") or []
    if not preparing and run.status in {"completed", "degraded"} and not any(row.get("status") == "candidates_available" for row in outcomes):
        return {"state": "no_suggestion", "message": "这次查找没有找到新的可靠建议，可以使用馆内已有记录或继续手工填写。", "reused": reused}
    return {
        "state": "preparing" if preparing else "unavailable" if run.status in {"failed", "canceled", "superseded"} else "ready",
        "message": "正在准备新的建议，稍后重新查找即可。" if preparing else "部分来源暂时不可用，可以继续手工填写或稍后再查找。" if run.status in {"failed", "degraded", "canceled", "superseded"} else "已读取当前字段的最新准备结果。",
        "reused": reused,
    }


def request_field_refresh(request, *, actor):
    from .service import _edition_for_request, _upload_item

    policy = get_field_policy(request.field_name)
    if not request.allow_external or not (policy.allow_authority or policy.allow_web):
        return {"state": "local", "message": "当前字段只使用馆内记录和已有依据。"}
    edition = _edition_for_request(request)
    edition = Edition.objects.select_related("work").get(pk=edition.pk)
    item = _upload_item(edition, request.upload_item_id)
    draft, fingerprint = field_research_context(edition, policy, request.query)
    session = f"field-assistant:{edition.pk}:{policy.key}"
    previous = ResearchRun.objects.filter(edition=edition, draft_session_id=session, is_current=True).order_by("-created_at").first()
    same = bool(previous and ((previous.context_snapshot or {}).get("draft_data") or {}).get("field_assistant", {}).get("fingerprint") == fingerprint)
    if same:
        age = (timezone.now() - previous.updated_at).total_seconds()
        if previous.status in {"queued", "running"} or age < (30 if previous.status in {"failed", "canceled", "superseded"} else 300):
            return refresh_state(previous, reused=True)
    step, field = FIELD_RESEARCH[policy.key]
    # A deterministic retry window retains the orchestrator's unique-key
    # deduplication without locking Edition ahead of its ResearchRun locks.
    # The marker's content fingerprint excludes this scheduling-only value.
    draft["field_assistant"]["refresh_window"] = int(timezone.now().timestamp() // 30)
    run, created = ResearchOrchestrator(planner=FieldScopedPlanner(policy, request.query)).prepare(
        edition, item=item, active_step=step, draft_data=draft, changed_fields=[f"{step}.{field}"],
        trigger=ResearchRun.Trigger.MANUAL, mode="full" if policy.allow_web else "structured",
        actor=actor, force=False, dispatch=True, include_background=False, draft_session_id=session,
    )
    return refresh_state(run, reused=not created)
