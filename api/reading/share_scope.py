"""Project a deliberately selected summary; never accept client-provided source text."""
from hashlib import sha256
import json

from django.contrib.auth.models import AnonymousUser
from rest_framework.exceptions import NotFound, ValidationError

from catalog.models import Asset
from . import booklists, notebook, privacy, research, reader_groups
from .models import Annotation, ReadingList, ResearchProject, ResearchTurn
from .services import decrypt_private_text

SECTIONS = ("questions", "materials", "notes")
SOURCE_FIELDS = ('source_kind', 'source_id', 'expected_version', *SECTIONS)


def source_specs(data):
    specs = [{key:data[key] for key in SOURCE_FIELDS}, *data.get('additional_sources', [])]
    identities = [(item['source_kind'], str(item['source_id'])) for item in specs]
    if len(specs) > 5 or len(identities) != len(set(identities)):
        raise ValidationError('一次最多组合5个本人研究或书单，同一对象不能重复。')
    if any(sum(len(item[section]) for item in specs) > 20 for section in SECTIONS):
        raise ValidationError('跨对象合计每类最多选择20项，请缩小本次分享范围。')
    return specs


def lock_sources(user, data):
    for spec in sorted(source_specs(data), key=lambda item:(item['source_kind'], str(item['source_id']))):
        model = ResearchProject if spec['source_kind'] == 'research' else ReadingList
        if model.objects.select_for_update().filter(user=user,pk=spec['source_id']).first() is None:
            raise NotFound('所选本人研究或书单已不存在。')


def specification(data):
    # Retain the original single-source encoding, so existing hashes and receipts stay valid.
    values = {key:data[key] for key in (*SOURCE_FIELDS, 'message')}
    values['source_id'] = str(values['source_id'])
    if data.get('additional_sources'):
        values['additional_sources'] = [{**item,'source_id':str(item['source_id'])} for item in source_specs(data)[1:]]
    return values


def content_fields(value):
    return {key:value[key] for key in ('source','sections','message','excluded','sources') if key in value}


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def source(user, kind, pk, expected=None):
    model = ResearchProject if kind == "research" else ReadingList
    row = model.objects.filter(user=user, pk=research.identifier(pk)).first()
    if row is None:
        raise NotFound("待分享的本人研究或书单已不存在。")
    if expected is not None and privacy.version(row) != expected:
        raise research.ResearchConflict("原研究或书单已修改，请重新选择和预览分享范围。")
    payload = research.unpack(row) if kind == "research" else {}
    refs = payload.get("selections", []) if kind == "research" else []
    if kind == "research":
        if len(refs) > 400:
            raise ValidationError("请先整理本研究的材料，再明确选择分享范围。")
        asset_ids = [value.get("asset_id") for value in refs if value.get("asset_id")]
        asset_ids.extend(anchor.get("asset_id") for value in refs for anchor in value.get("anchors", []) if anchor.get("asset_id"))
        works = set(str(value) for value in Asset.objects.filter(pk__in=asset_ids).values_list("edition__work_id", flat=True))
        works.update(str(value["work_id"]) for value in refs if value.get("work_id"))
    else:
        works = set(str(value) for value in row.items.filter(removed_at__isnull=True).values_list("work_id", flat=True))
    return row, payload, refs, works


def description(row, kind, payload):
    return {"id": str(row.pk), "kind": kind, "title": payload.get("title", "未命名研究") if kind == "research" else row.title,
        "version": privacy.version(row)}


def directory_source(row, kind):
    """Owner-only card metadata; never changes the original signed share projection."""
    payload = research.unpack(row) if kind == 'research' else {}
    if kind == 'research':
        refs = payload.get('selections', [])
        count = len(refs)
        first = material(row, kind, research.reference_identity(refs[0]), refs) if refs else None
        work = first['work'] if first and first['available'] else None
    else:
        items = row.items.filter(removed_at__isnull=True).order_by('order', 'created_at', 'id')
        count, first = items.count(), items.first()
        work = notebook.published_work(first.work_id) if first else None
        if work and not work['href']:
            work = None
    return {**description(row, kind, payload), 'material_count':count, 'first_material':work}


def question(row, key, payload):
    if key == "project":
        value, version = payload.get("question", ""), str(row.revision)
    else:
        turn = ResearchTurn.objects.filter(project=row, pk=research.identifier(key)).first()
        if turn is None:
            raise NotFound("这条研究问题已经删除。")
        value, version = research.unpack(turn).get("question", ""), str(turn.revision)
    if not value.strip():
        raise ValidationError("所选问题没有可分享的文字。")
    return {"id": key, "version": version, "title": "研究问题", "text": value[:2000], "truncated": len(value) > 2000, "available": True}


def material(row, kind, key, refs):
    if kind == "booklist":
        item = row.items.filter(pk=research.identifier(key), removed_at__isnull=True).first()
        if item is None:
            raise NotFound("书目已经从原书单移除。")
        work = notebook.published_work(item.work_id)
        return {"id": key, "version": privacy.version(item), "title": work["title"], "text": "",
            "available": bool(work["href"]), "work": work, "reference": None, "truncated": False}
    raw = next((value for value in refs if research.reference_identity(value) == key), None)
    if raw is None:
        raise NotFound("这条材料已经不在原研究中。")
    current = research.resolve_reference(raw, AnonymousUser())
    quote = current.get("quote", "")
    return {"id": key, "version": digest(research.compact_reference(current)), "title": current.get("title") or "来源当前不可用",
        "text": quote[:2000], "available": current["source_status"] == "available", "truncated": len(quote) > 2000,
        "reference": {**research.compact_reference(current), "reader_url": current.get("reader_url"),
            "printed_label": current.get("printed_label"), "citation": current.get("citation"), "cover_url": current.get("cover_url"), "cover_media": current.get("cover_media")},
        "work": {"title": current.get("title"), "authors": current.get("authors", []), "year": current.get("publication_year"), "cover_url": current.get("cover_url"), "cover_media": current.get("cover_media")}}


def note(user, key, works, project=None, payload=None):
    if key == "project-notes" or key.startswith("turn-note:"):
        if not isinstance(project, ResearchProject):
            raise NotFound("该对象没有此条研究笔记。")
        if key == "project-notes":
            body, version, title = (payload or {}).get("notes", ""), str(project.revision), "本人研究笔记"
        else:
            turn = ResearchTurn.objects.filter(project=project, pk=research.identifier(key.removeprefix("turn-note:"))).first()
            if turn is None:
                raise NotFound("这条回放笔记已不存在。")
            saved = research.unpack(turn)
            body, version, title = saved.get("replay_note", ""), str(turn.revision), saved.get("replay_title") or "本人回放笔记"
        if not body.strip():
            raise ValidationError("此处没有本人撰写的笔记。")
        return {"id": key, "version": version, "title": title, "text": body[:2000], "tags": [],
            "truncated": len(body) > 2000, "available": True}
    row = Annotation.objects.select_related("asset__edition", "page").filter(user=user, pk=research.identifier(key), asset__edition__work_id__in=works).first()
    if row is None:
        raise NotFound("这条本人笔记已不存在，或不属于所选研究/书单的文献。")
    body = decrypt_private_text(row.body_ciphertext)
    if not body.strip():
        raise ValidationError("所选记录只有原文摘录，没有本人笔记。请在材料中分享公开原文。")
    work = notebook.published_work(row.asset.edition.work_id, edition_id=row.asset.edition_id)
    # A note is explicit authored content. Saved quotations and manuscript bytes
    # are never included in this projection, even if their source has withdrawn.
    return {"id": str(row.pk), "version": privacy.version(row), "title": work["title"], "text": body[:2000],
        "tags": json.loads(decrypt_private_text(row.tags_ciphertext) or "[]"), "work": work,
        "truncated": len(body) > 2000, "available": True}


def candidates(user, data):
    row, payload, refs, works = source(user, data["source_kind"], data["source_id"], data.get("expected_version"))
    kind, section, page = data["source_kind"], data["section"], data["page"]
    start, end = (page - 1) * 20, page * 20
    if section == "questions":
        if kind == "booklist":
            count, values = 0, []
        else:
            has_question = bool(payload.get("question", "").strip())
            turns = ResearchTurn.objects.filter(project=row).order_by("-created_at", "-id")
            count = turns.count() + int(has_question)
            keys = (["project"] if has_question and start == 0 else []) + [str(pk) for pk in turns.values_list("pk", flat=True)[max(0, start - int(has_question)):max(0, end - int(has_question))]]
            values = []
            for key in keys:
                try:
                    values.append(question(row, key, payload))
                except ValidationError:
                    values.append({"id": key, "version": "", "title": "该轮没有可分享的问题", "text": "", "available": False})
    elif section == "materials":
        if kind == "research":
            count = len(refs)
            keys = [research.reference_identity(value) for value in refs[start:end]]
        else:
            items = row.items.filter(removed_at__isnull=True).order_by("order", "created_at", "id")
            count, keys = items.count(), [str(pk) for pk in items.values_list("pk", flat=True)[start:end]]
        values = [material(row, kind, key, refs) for key in keys]
    else:
        # Encrypted empty bodies cannot be SQL-filtered. Keep honest counts and
        # mark pure highlights unavailable instead of inventing authored notes.
        notes = Annotation.objects.filter(user=user, asset__edition__work_id__in=works).order_by("-updated_at", "-id")
        leading = int(kind == "research" and bool(payload.get("notes", "").strip()))
        turns = ResearchTurn.objects.filter(project=row).order_by("-created_at", "-id") if kind == "research" else None
        turn_count = turns.count() if turns is not None else 0
        count, values = notes.count() + leading + turn_count, []
        keys = ["project-notes"] if leading and start == 0 else []
        if turns is not None:
            keys.extend(f"turn-note:{pk}" for pk in turns.values_list("pk", flat=True)[max(0, start - leading):max(0, end - leading)])
        keys.extend(str(pk) for pk in notes.values_list("pk", flat=True)[max(0, start - leading - turn_count):max(0, end - leading - turn_count)])
        for key in keys:
            try:
                values.append(note(user, key, works, row, payload))
            except ValidationError:
                values.append({"id": key, "version": "", "title": "此记录未填写本人笔记", "text": "", "available": False})
    if page > 1 and start >= count:
        raise NotFound("此页没有内容，请返回第一页。")
    source(user, kind, row.pk, privacy.version(row))
    return {"owner_id": str(user.pk), "source": description(row, kind, payload), "section": section,
        "page": page, "count": count, "total_pages": max(1, (count + 19) // 20), "results": values}


def single_content(user, data):
    row, payload, refs, works = source(user, data["source_kind"], data["source_id"], data["expected_version"])
    selected, bindings = {}, {}
    for section in SECTIONS:
        items = data[section]
        if len(items) > 20 or len(set(items)) != len(items):
            raise ValidationError("每类最多选择20项，同一项不能重复选择。")
        if section == "questions" and data["source_kind"] != "research" and items:
            raise ValidationError("书单没有独立研究问题，请从研究中选择。")
        values = [question(row, key, payload) if section == "questions" else material(row, data["source_kind"], key, refs)
            if section == "materials" else note(user, key, works, row, payload) for key in items]
        if any(not value["available"] for value in values):
            raise ValidationError("所选内容有来源失效项，请重新选择；系统不会静默跳过。")
        selected[section] = values
        bindings[section] = [{"id": value["id"], "version": value["version"], "hash": digest(value)} for value in values]
    if not any(selected.values()):
        raise ValidationError("请明确选择至少一项内容。")
    source(user, data["source_kind"], row.pk, privacy.version(row))
    return {"source": description(row, data["source_kind"], payload), "sections": selected,
        "message": data.get("message", ""), "excluded": ["私人正文", "PDF原件", "未选中的笔记", "账户资料", "学术记忆授权"]}, bindings


def content(user, data):
    specs = source_specs(data)
    if len(specs) == 1:
        return single_content(user, data)
    projections = [single_content(user, spec) for spec in specs]
    sources = [value['source'] for value,_ in projections]
    sections = {section:[] for section in SECTIONS}
    for projected,_ in projections:
        for section in SECTIONS:
            sections[section].extend({**item,'origin_kind':projected['source']['kind'],'origin_title':projected['source']['title']}
                for item in projected['sections'][section])
    # A later source lookup must not let a change to an earlier source escape the final check.
    for spec in specs:
        source(user,spec['source_kind'],spec['source_id'],spec['expected_version'])
    result = {**projections[0][0], 'source':{**sources[0],'title':f'选定的 {len(sources)} 个研究与书单'},
        'sources':sources,'sections':sections,'message':data.get('message','')}
    return result, {'sources':[{'source':projected['source'],'sections':binding} for projected,binding in projections]}


def preview(user, data):
    projected, bindings = content(user, data)
    destination = {"kind": data["destination"], "title": {"public": "公开摘要链接", "proposal": "本站策划团队", "group": "指定小组成员"}[data["destination"]],
        "group_id": None, "members": []}
    if data["destination"] == "group":
        if not data.get("group_id") or not data.get("member_ids"):
            raise ValidationError("请选择小组和明确的接收成员。")
        group = reader_groups.group_for(user, data["group_id"])
        if group.revision != data.get("group_revision"):
            raise research.ResearchConflict("小组成员已变化，请重新选择接收范围。")
        members = reader_groups.member_bindings(group)
        chosen = set(data["member_ids"])
        selected = [value for value in members if value["user_id"] in chosen]
        sender = next((value for value in members if value["user_id"] == str(user.pk)), None)
        if len(selected) != len(chosen) or sender is None:
            raise research.ResearchConflict("所选接收者已不在当前小组，请重新核对。")
        destination.update(title=research.unpack(group).get("title", "小组"), group_id=str(group.pk), members=selected,
            sender_binding=sender)
    elif data.get("group_id") or data.get("member_ids"):
        raise ValidationError("当前目的地不接受小组或接收成员字段。")
    public = {"owner_id": str(user.pk), **projected, "destination": destination, "expires_days": data["expires_days"]}
    return {**public, "preview_hash": digest(public)}, bindings
