"""Explicit protection of saved catalog fields, using the existing FieldLock rows."""
from uuid import UUID
from django.db.models import Q

from catalog.contracts.fields import FIELDS
from catalog.services.field_decisions import formal_field_values
from catalog.services.work_editor import WorkflowEditError, _json_safe
from common.capabilities import Capability, has_capability
from rest_framework.exceptions import PermissionDenied
from ingestion.models import FieldLock

FIELDS_BY_NAME = {field.name: field for field in FIELDS
                 if field.section in {"work", "bibliography", "contributors", "classification", "knowledge"}
                 and "compatibility_alias" not in field.publication_rules}
WORK_FIELDS = [field.name for field in FIELDS if field.domain_object == "work"]


def display_values(values, locks):
    from catalog.models import Person, Work, Discipline, Subdiscipline, Topic, KnowledgeNode
    sources = {name: (Person, "preferred_name") for name, field in FIELDS_BY_NAME.items() if field.section == "contributors"}
    sources.update(translation_of=(Work, "title"), disciplines=(Discipline, "name"), subdisciplines=(Subdiscipline, "name"),
                   topics=(Topic, "name"), theories=(KnowledgeNode, "canonical_name_zh"))
    maps = {}
    for name, (model, label) in sources.items():
        candidates = [values.get(name), *[lock.locked_value for lock in locks if lock.field_name == name]]
        ids = set()
        for candidate in candidates:
            for value in candidate if isinstance(candidate, list) else [candidate]:
                try: ids.add(UUID(str(value)))
                except (ValueError, TypeError): pass
        maps[name] = {str(pk): text for pk, text in model.objects.filter(pk__in=ids).values_list("pk", label)} if ids else {}
    def display(name, value):
        if isinstance(value, list): return [display(name, item) for item in value]
        if name not in sources: return value
        try: key = str(UUID(str(value)))
        except (ValueError, TypeError): return value
        return maps[name].get(key, "关联记录暂不可用")
    return display


def scoped_locks(edition):
    return FieldLock.objects.filter(Q(edition=edition) | Q(edition__work_id=edition.work_id, field_name__in=WORK_FIELDS))


def saved_values(edition):
    from catalog.models import EditorialRevision
    values, _ = formal_field_values(edition)
    revision = EditorialRevision.objects.filter(target_type="edition", target_id=edition.pk, status="draft").order_by("-revision").first()
    if revision:
        # The editing page overlays only explicit Edition changes, after the Work draft.
        values.update({name: value for name, value in (revision.patch or {}).items()
                       if name in FIELDS_BY_NAME and FIELDS_BY_NAME[name].domain_object == "edition"})
    return values


def state(edition, actor):
    values = saved_values(edition)
    locks = list(scoped_locks(edition).select_related("edition", "locked_by").order_by("field_name", "edition_id"))
    display = display_values(values, locks)
    return [{"name": name, "label": field.label, "scope": "work" if name in WORK_FIELDS else "edition", "value": values[name],
             "display_value": display(name, values[name]),
             "can_edit": field.section != "knowledge" or has_capability(actor, Capability.EDIT_DRAFT_AUTHORITY),
             "locks": [{"id": str(lock.pk), "edition_id": str(lock.edition_id), "version_label": lock.edition.version_label,
                        "value": lock.locked_value, "display_value": display(name, lock.locked_value), "reason": lock.reason, "updated_at": lock.updated_at,
                        "actor": lock.locked_by.display_name or "编目人员"} for lock in locks if lock.field_name == name]}
            for name, field in FIELDS_BY_NAME.items() if name in values]


def apply(edition, changes, actor):
    values = saved_values(edition)
    seen, output = set(), []
    for change in changes:
        name, action = change["field"], change["action"]
        if name not in FIELDS_BY_NAME or name not in values or name in seen or action not in {"lock", "unlock"}:
            raise WorkflowEditError("请选择可管理的字段，每个字段仅能作出一次决定。")
        if FIELDS_BY_NAME[name].section == "knowledge" and not has_capability(actor, Capability.EDIT_DRAFT_AUTHORITY):
            raise PermissionDenied("当前账户不能更改关联知识的人工锁。")
        seen.add(name)
        query = scoped_locks(edition).filter(field_name=name)
        previous = list(query.select_for_update(of=("self",)).order_by("edition_id").values("id", "edition_id", "locked_value", "reason"))
        if action == "unlock":
            if not previous:
                raise WorkflowEditError("此字段已经没有人工锁，请重新读取后核对。")
            query.delete()
        else:
            if previous:
                raise WorkflowEditError("此字段已有人工锁，请先查看已有保护记录。")
            value = values[name]
            FieldLock.objects.create(edition=edition, field_name=name, locked_by=actor,
                                     locked_value=_json_safe(value) if value is not None else {"confirmed_null": True}, reason=change["reason"])
        output.append({"field": name, "action": action, "scope": "work" if name in WORK_FIELDS else "edition",
                       "reason": change["reason"], "previous": _json_safe(previous)})
    return output
