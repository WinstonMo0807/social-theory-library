"""Real PostgreSQL migration and concurrent recovery checks, with fixture data only."""
from concurrent.futures import ThreadPoolExecutor
from time import perf_counter
from uuid import uuid4

import pytest
from django.db import connection, connections, transaction
from django.db.migrations.executor import MigrationExecutor

from catalog import models as m

pytestmark = [pytest.mark.postgres_integration, pytest.mark.django_db(transaction=True)]


@pytest.fixture(autouse=True)
def require_postgres():
    if connection.vendor != "postgresql":
        pytest.skip("requires PostgreSQL")


def test_0103_0104_preserve_existing_sources_decisions_and_empty_receipts(admin_user):
    executor = MigrationExecutor(connection)
    latest = executor.loader.graph.leaf_nodes()
    old = [("catalog", "0102_merge_citation_name_and_retrieval")]
    executor.migrate(old)
    try:
        apps = executor.loader.project_state(old).apps
        model = lambda name: apps.get_model("catalog", name)
        actor = apps.get_model("accounts", "User").objects.get(pk=admin_user.pk)
        work = model("Work").objects.create(title="Synthetic migration source")
        edition = model("Edition").objects.create(work=work)
        asset = model("Asset").objects.create(edition=edition, kind="normalized", status="ready")
        revision = model("DocumentRevision").objects.create(asset=asset, revision=1,
            source_checksum="a"*64, text_checksum="b"*64)
        run = model("CurationRun").objects.create(work=work, edition=edition, document_revision=revision,
            request_id=uuid4(), created_by=actor, input_hash="c"*64, status="empty", execution_mode="agent")
        receipt = model("CurationArtifact").objects.create(run=run, stage=2, unit="fixture-window",
            status="empty", output={"entities":[], "assertions":[]}, output_hash="d"*64,
            usage={"agent_responses":1, "model_calls":0})
        changes = model("ChangeSet").objects.create(run=run, document_revision=revision,
            request_id=uuid4(), created_by=actor)
        decision = model("ChangeItem").objects.create(changeset=changes, kind="entity",
            fingerprint="e"*64, decision="rejected", reviewed_by=actor, decision_note="Keep this decision")
        page = model("KnowledgePage").objects.create(work=work, title=work.title, slug="migration-fixture",
            body_blocks=[{"id":str(uuid4()), "text":"Preserved human content"}], status="published")
        subscription = model("KnowledgeCompilation").objects.create(edition=edition, updated_by=actor,
            latest_run=run, pending_refresh=True, execution_mode="agent")
        subscription.target_pages.add(page)
        rows = {obj.__class__.__name__: (obj.pk, model(obj.__class__.__name__).objects.filter(pk=obj.pk).values().get())
            for obj in (work, edition, asset, revision, run, receipt, changes, decision, page, subscription)}
        started = perf_counter()
        MigrationExecutor(connection).migrate(latest)
        elapsed = perf_counter()-started
        apps = MigrationExecutor(connection).loader.project_state(latest).apps
        for name, (pk, original) in rows.items():
            current = apps.get_model("catalog", name).objects.filter(pk=pk).values().get()
            if name == "CurationRun":
                assert current.pop("plan_version") == 1
            elif name == "KnowledgeCompilation":
                assert current.pop("next_refresh_at") is None
                assert current.pop("refresh_failures") == 0
            assert current == original
        assert list(m.KnowledgeCompilation.objects.get(pk=subscription.pk).target_pages.values_list("pk", flat=True)) == [page.pk]
        assert not MigrationExecutor(connection).migration_plan(latest)
        print(f"PostgreSQL 0102 -> latest: {elapsed:.3f}s; 10 existing rows and target-page link preserved")
    finally:
        MigrationExecutor(connection).migrate(latest)


def _pending(actor):
    work = m.Work.objects.create(title="Concurrent recovery fixture")
    edition = m.Edition.objects.create(work=work)
    asset = m.Asset.objects.create(edition=edition, kind="normalized", status="ready", sha256=uuid4().hex*2)
    revision = m.DocumentRevision.objects.create(asset=asset, revision=1,
        source_checksum="a"*64, text_checksum="b"*64)
    run = m.CurationRun.objects.create(work=work, edition=edition, document_revision=revision,
        created_by=actor, request_id=uuid4(), input_hash="c"*64)
    return m.KnowledgeCompilation.objects.create(edition=edition, latest_run=run,
        updated_by=actor, pending_refresh=True)


def test_busy_subscription_does_not_block_other_sources(admin_user, monkeypatch):
    from catalog.services import knowledge_compilation as compilation, knowledge_automation as automation
    for name in ("recover_new_sources", "resume_configured_sources", "resume_resource_waiters"):
        monkeypatch.setattr(automation, name, lambda:None)
    busy, available = _pending(admin_user), _pending(admin_user)
    processed = []
    monkeypatch.setattr(compilation, "reconcile", lambda revision, **kw:processed.append(revision.pk))
    def recover():
        try:
            with connection.cursor() as cursor:
                cursor.execute("SET lock_timeout = '300ms'")
            compilation.reconcile_pending()
        finally:
            connections.close_all()
    with ThreadPoolExecutor(max_workers=1) as pool:
        with transaction.atomic():
            m.KnowledgeCompilation.objects.select_for_update().get(pk=busy.pk)
            pool.submit(recover).result(timeout=5)
    busy.refresh_from_db(); available.refresh_from_db()
    assert busy.pending_refresh and not busy.refresh_failures
    assert not available.pending_refresh
    assert processed == [available.latest_run.document_revision_id]
