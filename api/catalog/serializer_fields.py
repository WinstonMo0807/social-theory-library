from rest_framework import serializers


class PreservedSlugField(serializers.SlugField):
    """Keep an existing legacy address without accepting a new invalid slug."""

    def run_validators(self, value):
        instance = getattr(self.parent, "instance", None)
        if instance is not None and value == getattr(instance, self.source_attrs[0], None):
            return
        super().run_validators(value)
