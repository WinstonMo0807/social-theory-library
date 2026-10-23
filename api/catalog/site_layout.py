"""Homepage references carried by the existing site-content revision.

Only published source projections leave this module. A missing source remains
editable in a saved draft, but never becomes an anonymous card or a new object.
"""
from copy import deepcopy
from django.core.paginator import Paginator
from django.db.models import Case, F, JSONField, Q, When
from django.db.models.fields.json import KeyTextTransform
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from catalog.services import editorial_issues as ledger
from catalog.services.shared_curation import identifier

AREAS = ("featured", "scholars", "topics")
KINDS = ("issue", "scholar", "topic", "edition")
LABELS = {"issue": "特别策划", "scholar": "学者", "topic": "主题", "edition": "馆藏"}


class HomeTargetSerializer(serializers.Serializer):
    type = serializers.ChoiceField(choices=KINDS)
    id = serializers.UUIDField()


class HomeSlotSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    target = HomeTargetSerializer()
    title = serializers.CharField(max_length=40, allow_blank=True)
    description = serializers.CharField(max_length=80, allow_blank=True)
    cover_rendition_id = serializers.UUIDField(allow_null=True)
    visible = serializers.BooleanField()


class HomeLayoutSerializer(serializers.Serializer):
    featured = HomeSlotSerializer(many=True, max_length=5, allow_null=True)
    scholars = HomeSlotSerializer(many=True, max_length=5, allow_null=True)
    topics = HomeSlotSerializer(many=True, max_length=5, allow_null=True)


class HomeCardSerializer(serializers.Serializer):
    id = serializers.CharField()
    title = serializers.CharField(allow_blank=True)
    description = serializers.CharField(allow_blank=True)
    href = serializers.CharField(allow_blank=True)
    image_url = serializers.CharField(allow_blank=True)
    label = serializers.CharField()
    available = serializers.BooleanField()
    visible = serializers.BooleanField()
    source_title = serializers.CharField(allow_blank=True, required=False)
    source_description = serializers.CharField(allow_blank=True, required=False)
    source_image_url = serializers.CharField(allow_blank=True, required=False)


class HomeLayoutPreviewSerializer(serializers.Serializer):
    featured = HomeCardSerializer(many=True, allow_null=True)
    scholars = HomeCardSerializer(many=True, allow_null=True)
    topics = HomeCardSerializer(many=True, allow_null=True)


class HomeSourceQuerySerializer(serializers.Serializer):
    type = serializers.ChoiceField(choices=KINDS, default="issue")
    q = serializers.CharField(max_length=200, allow_blank=True, default="")
    page = serializers.IntegerField(min_value=1, max_value=100000, default=1)


class HomeSourceChoiceSerializer(serializers.Serializer):
    target = HomeTargetSerializer()
    source = HomeCardSerializer()


class HomeSourcePageSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    page = serializers.IntegerField()
    total_pages = serializers.IntegerField()
    results = HomeSourceChoiceSerializer(many=True)


def source_rows(kind, query=""):
    if kind == "issue":
        rows = ledger.published_issues().annotate(home_snapshot=Case(
            When(scheduled_revision__status="published", scheduled_for__lte=timezone.now(), then=F("scheduled_revision__materialized_preview")),
            default=F("active_revision__materialized_preview"), output_field=JSONField())).annotate(
                home_name=KeyTextTransform("title", "home_snapshot"))
        return rows.filter(home_name__icontains=query).order_by("-effective_display_from", "pk")
    if kind == "scholar":
        from catalog.services.public_scholars import _base
        return _base().filter(Q(public_name__icontains=query) | Q(public_original__icontains=query)).order_by("public_name", "pk")
    if kind == "topic":
        from catalog.services.public_topics import _base
        return _base(counts=False).filter(public_name__icontains=query).order_by("public_name", "pk")
    if kind == "edition":
        from catalog.services.publication_eligibility import public_editions
        return public_editions().filter(active_catalog_revision__snapshot__work__title__icontains=query).order_by("-first_published_at", "pk")
    raise ValidationError("请选择策划、学者、主题或馆藏。")


def source_card(target, row=None):
    kind = target["type"]
    row = row if row is not None else get_object_or_404(source_rows(kind), pk=identifier(target["id"]))
    card = {"id": str(row.pk), "label": LABELS[kind], "available": True, "visible": True}
    if kind == "issue":
        raw = ledger.public_issue_revision(row).materialized_preview
        image = f"/api/catalog/editorial-media/{raw['cover_rendition_id']}/" if raw.get("cover_rendition_id") else raw.get("cover_url", "")
        card.update(title=raw.get("title", ""), description=raw.get("introduction", ""), image_url=image, href=f"/recommendations/{row.slug}")
    elif kind == "scholar":
        from catalog.services.public_scholars import _formal_profile
        from catalog.serializers import PersonCompactSerializer
        row = _formal_profile(row, row.public_snapshot or {})
        card.update(title=row.person.preferred_name, description=row.short_description,
                    image_url=PersonCompactSerializer().get_portrait(row.person) or "", href=f"/scholars/{row.slug}")
    elif kind == "topic":
        from catalog.services.public_topics import _formal, _image
        row = _formal(row)
        card.update(title=row.name, description=row.description or row.problem_statement,
                    image_url=_image(row) or "", href=f"/topics/{row.slug}")
    else:
        from catalog.services.content_placements import _source
        _reference, source = _source(target, public=True)
        card.update(title=source["title"], description=source.get("edition_label", ""),
                    image_url=source["image_url"], href=source["work_url"])
    return card


def source_page(params):
    serializer = HomeSourceQuerySerializer(data=params)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    pages = Paginator(source_rows(data["type"], data["q"]), 20)
    page = pages.get_page(data["page"])
    return {"count": pages.count, "page": page.number, "total_pages": pages.num_pages,
            "results": [{"target": {"type": data["type"], "id": str(row.pk)},
                         "source": source_card({"type": data["type"], "id": str(row.pk)}, row)} for row in page]}


def normalize(value, *, retained=None):
    serializer = HomeLayoutSerializer(data=value)
    serializer.is_valid(raise_exception=True)
    old = {row["id"]: row for rows in (retained or {}).values() if isinstance(rows, list) for row in rows}
    result, seen = {}, set()
    for area, rows in serializer.validated_data.items():
        result[area] = None if rows is None else []
        targets = set()
        for row in rows or []:
            row = deepcopy(row)
            row["id"] = str(row["id"])
            row["target"]["id"] = str(row["target"]["id"])
            identity = (row["target"]["type"], row["target"]["id"])
            if row["id"] in seen or identity in targets:
                raise ValidationError("同一区域不能重复添加同一来源，条目编号也不能重复。")
            if area != "featured" and row["target"]["type"] != {"scholars": "scholar", "topics": "topic"}[area]:
                raise ValidationError("请为学者和主题栏目选择对应类型。")
            seen.add(row["id"])
            targets.add(identity)
            # Retain withdrawn references for correction, never silently rebind them.
            if old.get(row["id"], {}).get("target") != row["target"]:
                source_card(row["target"])
            rendition = ledger._rendition(row["cover_rendition_id"])
            row["cover_rendition_id"] = str(rendition.pk) if rendition else None
            result[area].append(row)
    return result


def present(layout, *, public=False, publishing=False):
    result = {}
    for area in AREAS:
        rows = (layout or {}).get(area)
        result[area] = None if rows is None else []
        for row in rows or []:
            if public and not row["visible"]:
                continue
            try:
                source = source_card(row["target"])
            except (Http404, ValidationError):
                if publishing and row["visible"]:
                    raise ValidationError("首页包含已撤回或不可公开的来源，请更换来源、移除条目或关闭显示后再发布。") from None
                if public:
                    continue
                source = {"title": "来源已撤回或不可用", "description": "请更换已公开的来源。", "href": "", "image_url": "", "label": LABELS.get(row["target"]["type"], "内容"), "available": False}
            image = source["image_url"]
            if row.get("cover_rendition_id"):
                image = f"/api/catalog/editorial-media/{row['cover_rendition_id']}/" if public else f"/api/catalog/admin/media/renditions/{row['cover_rendition_id']}/file/"
            card = {**source, "id": row["id"], "title": row["title"] or source["title"],
                "description": row["description"] or source["description"], "image_url": image, "visible": row["visible"]}
            if not public:
                card.update(source_title=source["title"], source_description=source["description"], source_image_url=source["image_url"])
            result[area].append(card)
    return result


def published_layout():
    from catalog.models import EditorialRevision, SiteSetting
    site = SiteSetting.objects.filter(key="site_config", public=True).first()
    revision = EditorialRevision.objects.filter(target_type="site_content", target_id=site.pk, status="published").order_by("-revision").first() if site else None
    return (revision.materialized_preview.get("home_layout") or {}) if revision else {}


def public_layout():
    return present(published_layout(), public=True)


def public_cover_used(rendition_id):
    # Old revisions and hidden/withdrawn cards do not grant public media access.
    for rows in published_layout().values():
        for row in rows or []:
            if row["visible"] and row.get("cover_rendition_id") == str(rendition_id):
                try:
                    source_card(row["target"])
                    return True
                except (Http404, ValidationError):
                    continue
    return False
