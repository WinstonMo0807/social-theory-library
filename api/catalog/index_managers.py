"""Separate existing semantic generations from discovery in the same ledger."""
from django.db import models


class SemanticVersionManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(index_family="semantic")


class DiscoveryVersionManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(index_family="discovery")
