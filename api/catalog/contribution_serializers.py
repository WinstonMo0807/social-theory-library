from rest_framework import serializers


class ContributionChapterInputSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=600)
    asset_id = serializers.UUIDField()
    document_revision_id = serializers.UUIDField()
    outline_revision_id = serializers.UUIDField()
    outline_node_id = serializers.UUIDField()
    page_start = serializers.IntegerField(min_value=1)
    page_end = serializers.IntegerField(min_value=1)


class ContributionScopeInputSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=["edition", "chapter"], default="edition")
    chapters = ContributionChapterInputSerializer(many=True, required=False, max_length=100)

    def validate(self, attrs):
        from catalog.services.contribution_scope import ContributionScopeError, normalize_contribution_scope
        try:
            return normalize_contribution_scope(attrs)
        except ContributionScopeError as error:
            raise serializers.ValidationError(str(error)) from error


class PublicContributionChapterSerializer(ContributionChapterInputSerializer):
    reader_href = serializers.CharField()


class PublicContributionScopeSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=["edition", "chapter"])
    status = serializers.ChoiceField(choices=["available", "unavailable"])
    chapters = PublicContributionChapterSerializer(many=True)
    notice = serializers.CharField(allow_blank=True)
