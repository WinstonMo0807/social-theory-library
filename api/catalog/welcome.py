"""Welcome content on the existing site-content draft/publication ledger."""
from django.http import Http404
from rest_framework import serializers


class WelcomeCopySerializer(serializers.Serializer):
    id = serializers.ChoiceField(choices=("source", "question", "debate"))
    label = serializers.CharField(max_length=12)
    title = serializers.ListField(child=serializers.CharField(max_length=24), min_length=2, max_length=2)
    lead = serializers.CharField(max_length=160)
    question = serializers.CharField(max_length=60)
    results = serializers.CharField(max_length=24)
    reader = serializers.CharField(max_length=24)
    saved = serializers.CharField(max_length=40)


class WelcomeChapterSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=40)
    text = serializers.CharField(max_length=240)
    action = serializers.CharField(max_length=16)


TEXT_KEYS = frozenset("history_title history_subjects history_scholars history_theories history_works philosophy_title philosophy_body features_title features_body discovery_theory_title discovery_theory_body discovery_issue_title discovery_issue_body principles_title principle_source_title principle_source_body principle_context_title principle_context_body principle_debate_title principle_debate_body principle_judgment_title principle_judgment_body invitation_title invitation_body faq_title faq_read_title faq_read_body faq_cite_title faq_cite_body faq_private_title faq_private_body closing_title enter_label".split())


class WelcomeConfigSerializer(serializers.Serializer):
    copies = WelcomeCopySerializer(many=True, min_length=3, max_length=3, required=False)
    chapters = WelcomeChapterSerializer(many=True, min_length=4, max_length=4, required=False)
    texts = serializers.DictField(child=serializers.CharField(max_length=600), required=False)
    edition_ids = serializers.ListField(child=serializers.UUIDField(), max_length=3, allow_null=True, required=False)

    def validate_copies(self, value):
        if {row["id"] for row in value} != {"source", "question", "debate"}:
            raise serializers.ValidationError("请分别保留原文优先、问题出发和思想交锋三版。")
        return value

    def validate_texts(self, value):
        if value.keys() - TEXT_KEYS:
            raise serializers.ValidationError("包含不支持的欢迎页文字。")
        if "history_subjects" in value:
            subjects = value["history_subjects"].split("、")
            if not 1 <= len(subjects) <= 3 or any(not word.strip() or len(word.strip()) > 8 for word in subjects):
                raise serializers.ValidationError("演示学科请填写1至3项，以顿号分隔，每项不超过8字。")
        return value

    def validate_edition_ids(self, value):
        if value is None:
            return None
        if len(set(value)) != len(value):
            raise serializers.ValidationError("同一版本只能选择一次。")
        return [str(identifier) for identifier in value]


def welcome_books(config, *, include_missing=False):
    """Resolve only activated public editions. Stored IDs never authorize access."""
    from catalog.services.content_placements import _source
    rows = []
    for identifier in (config.get("welcome") or {}).get("edition_ids") or []:
        try:
            _, source = _source({"type": "edition", "id": identifier}, public=True)
        except Http404:
            if include_missing:
                rows.append(dict(id=str(identifier), title="来源已撤回或不可用", author="", coverImage="", available=False))
            continue
        authors = source.get("authors", [])
        rows.append(dict(id=str(identifier), title=source["title"], author="、".join(authors),
                         coverImage=source.get("image_url", ""), available=True))
    return rows
