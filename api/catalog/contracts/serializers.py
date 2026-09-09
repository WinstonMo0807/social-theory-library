"""DRF adaptation of the shared catalog validation contract."""
from rest_framework import serializers

from catalog.contracts.fields import FIELD_CONTRACTS
from catalog.contracts.validation import field_error, normalize_field


class CatalogContractValidationMixin:
    def validate(self, attrs):
        attrs = super().validate(attrs)
        errors = {}
        for name, value in attrs.items():
            if name not in FIELD_CONTRACTS:
                continue
            error = field_error(name, value)
            if error:
                errors[name] = error["message"]
            else:
                attrs[name] = normalize_field(name, value)
        if errors:
            raise serializers.ValidationError(errors)
        publication_date = attrs.get("publication_date")
        publication_year = attrs.get("publication_year")
        if publication_date and publication_year and publication_date.year != publication_year:
            raise serializers.ValidationError({"publication_date": "本版本出版日期与兼容出版年份不一致。"})
        return attrs
