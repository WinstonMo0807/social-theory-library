"""Website review/history on the existing site_content revision ledger."""
from hashlib import sha256
import json

from django.core.serializers.json import DjangoJSONEncoder
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.editorial_issue_serializers import SiteContentSerializer
from catalog.editorial_issue_views import EditorialErrorMixin
from catalog.editorial_read import AdminPrivateResponseMixin
from catalog.models import AboutPageBlock, MediaRendition, SiteSetting
from catalog.services import editorial_issues as ledger
from catalog.site_layout import AREAS, present
from common.permissions import IsLibraryAdmin

AREA_LABELS = {"featured": "首页主推", "scholars": "学者聚焦", "topics": "探索主题"}
SECTION_LABELS = {"about": "关于书库", "about_why": "建库缘起", "about_feature_search": "寻找原始出处",
    "about_feature_read": "阅读与整理", "about_feature_knowledge": "知识关系", "about_ingestion": "入库说明",
    "about_access": "开放原则", "about_rights": "版权说明", "about_privacy": "隐私说明", "about_warning": "使用提示"}


def checks(payload):
    rows = []
    def add(code, severity, title, detail, section="home", slot_id=""):
        rows.append(dict(code=code, severity=severity, title=title, detail=detail, section=section, slot_id=slot_id))
    layout = present(payload.get("home_layout", {}))
    media = []
    config = payload.get("config", {})
    if not str(config.get("site_name") or "").strip():
        add("site_name", "blocking", "书库名称未填写", "请填写品牌与导航中的书库名称。", "brand")
    if config.get("home_hero_rendition_id"):
        media.append((str(config["home_hero_rendition_id"]), "首页主图", "home", ""))
    elif config.get("home_hero_image"):
        add("legacy_hero", "warning", "旧主图出处待核对", "旧图片链接缺少可核对的媒体快照，请确认权利或重新选图。")
    for area in AREAS:
        for item in layout[area] or []:
            if item["visible"] and not item["available"]:
                add("source_unavailable", "blocking", f"{AREA_LABELS[area]}有不可公开的来源", "更换来源、移除条目或关闭本页显示后再发布。", area, item["id"])
        for slot in payload.get("home_layout", {}).get(area) or []:
            if slot.get("visible") and slot.get("cover_rendition_id"):
                media.append((str(slot["cover_rendition_id"]), AREA_LABELS[area], area, slot["id"]))
    for block in payload.get("about_blocks", []):
        key = block.get("key", "")
        if key.startswith("announcement-") and block.get("visible") and (not str(block.get("title") or "").strip() or not str(block.get("body") or "").strip() or not block.get("configuration", {}).get("published_date")):
            add("announcement_incomplete", "blocking", "公告信息未填完整", "请填写公告标题、正文与公告日期，或关闭显示后再发布。", key)
        if AboutPageBlock.all_objects.filter(key=key).exclude(pk__in=AboutPageBlock.objects.values("pk")).exists():
            add("recycled_block", "blocking", "草稿仍包含已回收模块", "请移除旧模块或从回收站明确恢复后再发布。", key)
        if block.get("visible") and not str(block.get("title") or "").strip() and not str(block.get("body") or "").strip():
            add("empty_block", "warning", "可见说明模块没有文字", "核对这个模块是否应显示，或补充真实内容。", key)
    assets = {str(row.pk): row for row in MediaRendition.objects.filter(pk__in=[item[0] for item in media])}
    for identifier, label, section, slot in media:
        item = assets.get(identifier)
        if not item:
            add("media_missing", "blocking", f"{label}图片版本不可用", "请重新选用已有图片版本。", section, slot)
        elif not any(str(item.metadata_snapshot.get(key) or "").strip() for key in ("license", "rights")):
            add("media_rights", "warning", f"{label}图片许可待核对", "所选不可变图片版本尚无权利说明，请补充出处后重新选用新版本。", section, slot)
    return rows


def changes(before, after):
    rows = []
    def display(value):
        if value is None: return "未设置"
        if isinstance(value, (dict, list)): return json.dumps(value, ensure_ascii=False, indent=2)
        return str(value)
    def add(field, label, old, new):
        if old == new: return
        def human(value):
            if field.startswith("home_layout."):
                if value is None: return "沿用公开推荐"
                if not value: return "手动编排，当前为空"
                return "\n".join(f"{index+1}. {item.get('title') or '沿用来源题名'} · {'显示' if item.get('visible') else '不显示'}\n{item.get('description') or '沿用来源导语'}\n{'独立配图' if item.get('cover_rendition_id') else '沿用来源配图'}" for index, item in enumerate(value))
            if field in {"config.home_hero_rendition_id", "config.home_hero_image"}:
                return "已选图片" if value else "未单独设置"
            if field.startswith("about_blocks.") and isinstance(value, dict):
                configuration = value.get("configuration")
                date = configuration.get("published_date") if isinstance(configuration, dict) else None
                return "\n".join(str(part) for part in (value.get("title"), f"公告日期：{date}" if date else "", value.get("body"), "显示" if value.get("visible") else "不显示", value.get("action_label"), value.get("action_href")) if part)
            return display(value)
        old_display, new_display = human(old), human(new)
        if old_display == new_display:
            new_display += "\n关联来源、图片版本或显示顺序有变化，请结合页面预览核对。"
        rows.append(dict(field=field, label=label, before_display=old_display, after_display=new_display,
            change="added" if old is None else "removed" if new is None else "changed"))
    labels = {"site_name": "书库名称", "wordmark_lines": "品牌文字", "navigation": "导航文字", "intro_lines": "首页导语",
        "home_title_left_lines": "首页标题第一行", "home_title_right_lines": "首页标题第二行", "home_hero_alt": "主图说明",
        "home_hero_image": "主图地址", "home_hero_rendition_id": "主图版本", "copyright_text": "页脚版权", "about_label": "关于入口"}
    for prefix, label in SECTION_LABELS.items():
        labels.update({f"{prefix}_title": f"{label}标题", f"{prefix}_body": f"{label}正文"})
    for key in dict.fromkeys([*before.get("config", {}), *after.get("config", {})]):
        if key == "home_hero_image" and before.get("config", {}).get("home_hero_rendition_id") == after.get("config", {}).get("home_hero_rendition_id") and after.get("config", {}).get("home_hero_rendition_id"):
            continue  # Public and private URLs refer to the same immutable image.
        add(f"config.{key}", labels.get(key, "其他网站文字"), before.get("config", {}).get(key), after.get("config", {}).get(key))
    old_blocks = {row["key"]: row for row in before.get("about_blocks", [])}
    new_blocks = {row["key"]: row for row in after.get("about_blocks", [])}
    for key in dict.fromkeys([*new_blocks, *old_blocks]):
        def content(value):
            return {name: value.get(name) for name in ("title", "body", "visible", "action_label", "action_href", "sort_order", "configuration")} if value else None
        add(f"about_blocks.{key}", (new_blocks.get(key) or old_blocks[key]).get("title") or "公共说明模块", content(old_blocks.get(key)), content(new_blocks.get(key)))
    for area in AREAS:
        add(f"home_layout.{area}", f"{AREA_LABELS[area]}顺序与内容", before.get("home_layout", {}).get(area), after.get("home_layout", {}).get(area))
    return rows


def review(expected):
    target = get_object_or_404(SiteSetting, key="site_config")
    ledger._check_version("site_content", target.pk, expected)
    saved = ledger.site_payload()
    before = ledger.site_public_payload()
    findings = checks(saved)
    differences = changes(before, saved)
    signature = sha256(json.dumps({"version": expected, "saved": {key: saved[key] for key in ("config", "about_blocks", "home_layout", "home_preview")},
        "public": before, "checks": findings}, cls=DjangoJSONEncoder, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    ledger._check_version("site_content", target.pk, expected)
    return dict(edit_version=expected, fingerprint=signature, checked_at=timezone.now(), snapshot=saved,
        changes=differences, checks=findings, can_publish=saved["has_unpublished_changes"] and not any(row["severity"] == "blocking" for row in findings))


class SiteReviewCheckSerializer(serializers.Serializer):
    code = serializers.CharField()
    severity = serializers.CharField()
    title = serializers.CharField()
    detail = serializers.CharField()
    section = serializers.CharField()
    slot_id = serializers.CharField(allow_blank=True)


class SiteReviewChangeSerializer(serializers.Serializer):
    field = serializers.CharField()
    label = serializers.CharField()
    before_display = serializers.CharField()
    after_display = serializers.CharField()
    change = serializers.CharField()


class SiteReviewSerializer(serializers.Serializer):
    edit_version = serializers.CharField()
    fingerprint = serializers.CharField()
    checked_at = serializers.DateTimeField()
    snapshot = SiteContentSerializer()
    checks = SiteReviewCheckSerializer(many=True)
    changes = SiteReviewChangeSerializer(many=True)
    can_publish = serializers.BooleanField()


class SiteReviewView(EditorialErrorMixin, AdminPrivateResponseMixin, APIView):
    permission_classes = [IsLibraryAdmin]

    @extend_schema(parameters=[OpenApiParameter("edit_version", required=True)], responses=SiteReviewSerializer)
    def get(self, request):
        if request.headers.get("X-Editor-Owner") != str(request.user.pk):
            raise PermissionDenied("请从当前管理账户核对网站内容。")
        version = request.query_params.get("edit_version")
        if not version or len(request.query_params.getlist("edit_version")) != 1:
            raise ValidationError("请指定一个已保存的网站版本。")
        return Response(review(version))
