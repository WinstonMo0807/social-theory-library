"""Explicit field refresh adapter for the existing ResearchOrchestrator."""
from dataclasses import asdict, dataclass, replace
from copy import deepcopy
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

from catalog.contracts.fields import FIELDS

for _field in FIELDS:
    try:
        RESEARCH_CONTRACTS.get(_field.section, _field.name)
    except ValueError:
        continue
    else:
        FIELD_RESEARCH.setdefault(_field.name, (_field.section, _field.name))


def field_research_context(edition, policy, query="", form_context=None, *, version=2):
    from .service import _edition_section_values
    from catalog.models import Person

    values, _confirmed = formal_field_values(edition, include_editorial_draft=True)
    contributions = _edition_section_values(edition, "contributors").get("contributors", [])
    people = {str(person.pk): person.preferred_name for person in Person.objects.filter(pk__in=[row["person_id"] for row in contributions])}
    draft = {
        "work": {field.name: values.get(field.name) for field in FIELDS if field.section == "work" and field.data_type in {"string", "text", "integer", "date", "identifier", "enum"}},
        "bibliography": {field.name: values.get(field.name) for field in FIELDS if field.section == "bibliography" and field.data_type in {"string", "text", "integer", "date", "identifier"}},
        "contributors": {"items": [{**row, "display_name": people.get(str(row["person_id"]), "")} for row in contributions]},
        "knowledge": {"topics": values.get("topics", []), "theories": values.get("theories", [])},
    }
    if version == 1:
        # Existing run markers keep their original fingerprint contract.
        draft["work"] = {key: values.get(key) for key in ("title", "subtitle", "original_title", "document_type", "language", "abstract")}
        draft["bibliography"] = {key: values.get(key) for key in ("isbn", "isbn10", "isbn13", "doi", "publisher", "publication_year", "publication_date", "responsibility_statement")}
    if version == 2:
        form = form_context if isinstance(form_context, dict) else {}
        for section in ("work", "bibliography"):
            for key, value in draft[section].items():
                selected = form.get(key, value)
                draft[section][key] = str(selected or "").strip() if not isinstance(selected, (dict, list)) else str(value or "").strip()
        if "isbn10" in form or "isbn13" in form:
            draft["bibliography"]["isbn"] = draft["bibliography"].get("isbn13") or draft["bibliography"].get("isbn10") or ""
        for row in draft["contributors"]["items"]:
            if row.get("credited_name"):
                row["display_name"] = row["credited_name"]
        # Only public bibliographic fields enter research. No reader notes,
        # arbitrary form keys, or user-supplied confirmation flags are copied.
        for field, role in (("authors", "author"), ("translators", "translator")):
            if field in form and isinstance(form[field], list):
                others = [row for row in draft["contributors"]["items"] if row.get("role") != role]
                draft["contributors"]["items"] = [*others, *[{"role": role, "display_name": str(name).strip()} for name in form[field][:50] if isinstance(name, str) and name.strip()]]
        # Identity IDs are authoritative only after an explicit save. Matching
        # research inputs uses the actual names/roles, not a client ID claim.
        draft["contributors"]["items"] = [{"role": str(row.get("role") or "author"), "display_name": str(row.get("display_name") or "").strip()} for row in draft["contributors"]["items"]]
    comparable = deepcopy(draft)
    if version == 2:
        # Depend on the field's declared upstream inputs, not unrelated edits.
        # A manual change to its own proposed value is recorded at save time.
        dependencies = set(policy.query_context_fields) | {"document_type"}
        _section, target = FIELD_RESEARCH.get(policy.key, ("", policy.key))
        dependencies.discard(target)
        if target in {"isbn", "isbn10", "isbn13"}:
            dependencies -= {"isbn", "isbn10", "isbn13"}
        comparable = {key: draft[section].get(key) for section in ("work", "bibliography", "knowledge") for key in dependencies if key in draft[section]}
        for field, role in (("authors", "author"), ("translators", "translator")):
            if field in dependencies:
                comparable[field] = [row["display_name"] for row in draft["contributors"]["items"] if row["role"] == role]
    fingerprint = sha256(json.dumps([policy.key, query, comparable], ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()
    draft["field_assistant"] = {"field": policy.key, "query": query, "fingerprint": fingerprint, "version": version, "input_scope": "lookup_only_not_saved"}
    return draft, fingerprint


def research_context_is_current(run, edition, policy, form_context=None) -> bool:
    if run is None or not run.is_current or run.status in {"canceled", "superseded"}:
        return False
    marker = ((run.context_snapshot or {}).get("draft_data") or {}).get("field_assistant")
    if form_context and (not marker or marker.get("version", 1) != 2):
        # Old runs never saw unsaved inputs. Preserve their saved-context
        # compatibility, but do not present them as advice for changed inputs.
        _saved, saved_fingerprint = field_research_context(edition, policy)
        _form, form_fingerprint = field_research_context(edition, policy, form_context=form_context)
        if saved_fingerprint != form_fingerprint:
            return False
    if not marker:
        # Legacy runs have no field-session marker. Still compare substantive
        # book/version inputs so a new title or ISBN cannot revive old advice.
        current, _fingerprint = field_research_context(edition, policy, form_context=form_context)
        saved = run.context_snapshot or {}
        for section, fields in (("work", ("title", "original_title")), ("bibliography", ("isbn", "isbn10", "isbn13", "publisher", "publication_year"))):
            previous = {**((saved.get("persisted_data") or {}).get(section) or {}), **((saved.get("draft_data") or {}).get(section) or {})}
            if any(str(previous[field] or "") != str(current[section].get(field) or "") for field in fields if field in previous):
                return False
        return True
    if marker.get("field") != policy.key:
        return False
    _draft, fingerprint = field_research_context(edition, policy, marker.get("query", ""), form_context, version=marker.get("version", 1))
    return fingerprint == marker.get("fingerprint")


def form_context_for_edits(edition, sections):
    """Build save-time context from validated sections, never a free-form flag."""
    from catalog.models import Person

    context = {**sections.get("work", {}), **sections.get("bibliography", {})}
    contributors = sections.get("contributors", {}).get("contributors")
    if contributors is not None:
        people = {str(person.pk): person.preferred_name for person in Person.objects.filter(pk__in=[row["person_id"] for row in contributors])}
        for field, role in (("authors", "author"), ("translators", "translator")):
            context[field] = [str(row.get("credited_name") or people.get(str(row["person_id"]), "")) for row in contributors if row["role"] == role]
    return context


@dataclass(frozen=True)
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
    identity = {"run_id": str(run.pk), "updated_at": run.updated_at.isoformat(), "reused": reused}
    if not run.plan:
        return {**identity, "state": "not_applicable", "message": "当前字段没有可执行的查找来源，可以继续手工填写。"}
    preparing = run.status in {"queued", "running"}
    outcomes = (run.external_results or {}).get("field_outcomes") or []
    if not preparing and not any(row.get("status") == "candidates_available" for row in outcomes):
        codes = {str(row.get("code") or "") for row in (run.diagnostics or {}).get("errors", [])}
        if any("not_configured" in code for code in codes):
            return {**identity, "state": "not_configured", "message": "部分查找来源尚未配置，不能据此判断没有匹配资料。可使用馆内已有记录，或请管理员配置来源。"}
        if any(row.get("status") == "producer_unavailable" for row in outcomes):
            return {**identity, "state": "unavailable", "message": "当前字段的查找服务不可用，暂未取得新建议。你的填写保持不变。"}
        if run.status == "failed" or any(code.endswith("failed") or code in {"authority_unavailable", "fetch_blocked"} for code in codes):
            return {**identity, "state": "failed", "message": "这次查找有来源失败或无法访问，不能当作没有结果。可以稍后重试，或继续手工填写。"}
        if run.status in {"completed", "degraded"}:
            return {**identity, "state": "no_suggestion", "message": "这次查找没有找到新建议，可以使用馆内已有记录或继续手工填写。"}
    return {
        **identity,
        "state": "preparing" if preparing else "unavailable" if run.status in {"failed", "canceled", "superseded"} else "ready",
        "message": "正在按本页填写查找建议，结果会自动出现在这里；不会保存或替换你的输入。" if preparing else "部分来源暂时不可用，可以继续手工填写或稍后再查找。" if run.status in {"failed", "degraded", "canceled", "superseded"} else "已读取与本页填写相符的最新建议，请核对后填入。",
    }


def current_field_refresh(request):
    from .service import _edition_for_request

    policy = get_field_policy(request.field_name)
    edition = _edition_for_request(request)
    _draft, fingerprint = field_research_context(edition, policy, request.query, request.confirmed_context)
    run = ResearchRun.objects.filter(edition=edition, draft_session_id=f"field-assistant:{edition.pk}:{policy.key}", is_current=True).order_by("-created_at").first()
    marker = (((run.context_snapshot or {}).get("draft_data") or {}).get("field_assistant") or {}) if run else {}
    if run and marker.get("fingerprint") == fingerprint:
        return refresh_state(run, reused=True)
    return {"state": "not_started", "message": "已按本页填写核对馆内记录和已有依据。需要新的外部建议时，请点击查找；本次没有启动外部服务。"}


def request_field_refresh(request, *, actor):
    from .service import _edition_for_request, _upload_item

    policy = get_field_policy(request.field_name)
    if not request.allow_external or not (policy.allow_authority or policy.allow_web):
        return {"state": "local", "message": "当前字段只使用馆内记录和已有依据。"}
    if policy.key not in FIELD_RESEARCH:
        return {"state": "local", "message": "此字段暂只支持人工填写与已有依据，外部研究尚未接通。"}
    edition = _edition_for_request(request)
    edition = Edition.objects.select_related("work").get(pk=edition.pk)
    item = _upload_item(edition, request.upload_item_id)
    draft, fingerprint = field_research_context(edition, policy, request.query, request.confirmed_context)
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
