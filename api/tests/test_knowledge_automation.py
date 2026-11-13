"""Synthetic lifecycle checks, not claims of real model or corpus validation."""
from datetime import timedelta
from types import SimpleNamespace
import pytest
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError
from tests.test_knowledge_core import source
from catalog import models as m
from catalog.services import knowledge_automation as automation, knowledge_compilation as compilation

pytestmark = pytest.mark.django_db


def publish_fixture(source, *, when=None):
    asset, edition = source.asset, source.asset.edition
    asset.sha256 = source.source_checksum
    asset.file, asset.validation_status = "fixture.pdf", "valid"
    asset.save()
    revision = m.CatalogPublicationRevision.objects.create(edition=edition, revision=1,
        document_revision=source, reader_asset=asset, status="active", metadata_ready=True, fulltext_ready=True)
    edition.active_catalog_revision = revision
    edition.state, edition.first_published_at = "published", when or timezone.now()
    edition.save()
    return edition


def enable(admin_user):
    return automation.save_policy(admin_user, version=0, mode="draft")


def test_enrollment_requires_new_published_source_and_never_unpauses(source, admin_user):
    policy = enable(admin_user)
    assert policy["profile_key"] and policy["applies_after"]
    assert automation.enroll(source.asset.edition_id) is None  # draft/private imports
    edition = publish_fixture(source, when=timezone.now()-timedelta(days=1))
    assert automation.enroll(edition.pk) is None  # no historical mass enrollment
    edition.first_published_at = timezone.now(); edition.save()
    row = automation.enroll(edition.pk)
    assert row.pending_refresh and row.execution_mode == "provider" and row.latest_run_id is None
    assert not m.CurationRun.objects.exists()  # no model or structure work on publication
    assert automation.enroll(edition.pk) is None
    row.enabled = False; row.save()
    automation.recover_new_sources()
    row.refresh_from_db()
    assert not row.enabled and m.KnowledgeCompilation.objects.count() == 1


def test_policy_access_concurrency_and_missing_models_wait(source, admin_user, reader_user, monkeypatch):
    from catalog.services import intelligence as runner
    from catalog.services.intelligence_provider import configuration
    with pytest.raises(PermissionDenied):
        automation.save_policy(reader_user, version=0, mode="draft")
    policy = enable(admin_user)
    with pytest.raises(ValidationError):
        automation.save_policy(admin_user, version=0, mode="retrieval")
    edition = publish_fixture(source)
    row = automation.enroll(edition.pk)
    monkeypatch.setattr(runner, "schedule", lambda run: None)
    assert not configuration(policy["profile_key"]).enabled
    compilation.reconcile_pending()
    row.refresh_from_db()
    assert row.latest_run.status == "waiting_configuration"
    assert not row.latest_run.artifacts.exists()
    automation.save_policy(admin_user, version=1, mode="retrieval")
    assert m.KnowledgeCompilation.objects.get(pk=row.pk).enabled  # individual settings retained


def test_configured_model_wakes_only_its_waiting_enabled_subscriptions(source, admin_user, monkeypatch):
    from catalog.services import intelligence as runner, intelligence_provider
    from ingestion.services.ai_client import AIConfigurationError
    monkeypatch.setattr(runner, "schedule", lambda run: None)
    subscription = compilation.configure(source, admin_user)
    assert subscription.latest_run.status == "waiting_configuration"
    assert not subscription.pending_refresh
    def unavailable(key):
        raise AIConfigurationError("removed profile")
    monkeypatch.setattr(intelligence_provider, "configuration", unavailable)
    automation.resume_configured_sources()
    subscription.refresh_from_db()
    assert not subscription.pending_refresh and subscription.last_error["code"] == "configuration_missing"
    monkeypatch.setattr(intelligence_provider, "configuration", lambda key: SimpleNamespace(enabled=True))
    automation.resume_configured_sources()
    subscription.refresh_from_db()
    assert subscription.pending_refresh
    subscription.pending_refresh, subscription.enabled = False, False; subscription.save()
    automation.resume_configured_sources()
    subscription.refresh_from_db()
    assert not subscription.pending_refresh


def test_publication_notification_enrolls_even_with_search_disabled(source, admin_user, monkeypatch, django_capture_on_commit_callbacks):
    from catalog.services.retrieval.source_schedule import publication_changed
    from catalog.services import discovery_indexing
    from catalog.intelligence_tasks import refresh_compilations
    enable(admin_user)
    edition = publish_fixture(source)
    calls = []
    monkeypatch.setattr(discovery_indexing, "enabled", lambda: False)
    monkeypatch.setattr(refresh_compilations, "apply_async", lambda **kwargs: calls.append(kwargs))
    with django_capture_on_commit_callbacks(execute=True):
        publication_changed(edition.pk)
    assert m.KnowledgeCompilation.objects.get(edition=edition).pending_refresh
    assert calls == [{"queue": "intelligence"}]


def test_automation_api_keeps_secrets_out_and_denies_editors(api_client, admin_user):
    api_client.force_authenticate(admin_user)
    read = api_client.get("/api/knowledge/automation/")
    assert read.status_code == 200 and read.data["mode"] == "retrieval"
    assert set(read.data["profiles"][0]) == {"key", "model", "enabled"}
    admin_user.role = "editor"; admin_user.save()
    response = api_client.post("/api/knowledge/automation/", {"version": 0, "mode": "draft"}, format="json")
    assert response.status_code == 403
