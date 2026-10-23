"""Deferred PostgreSQL-only account retention coverage; never run in development."""
import pytest
from django.core.management.base import CommandError
from django.db import connection

from catalog.management.commands.reset_public_library import (
    PARTIAL_PRESERVATION, PLAN_FORMAT, PRESERVED_TABLES, digest, model_tables,
    quoted_table, table_snapshot, verify_plan,
)
from ingestion.models import AuditEvent


def test_account_tables_are_excluded_and_old_approval_plan_is_rejected():
    assert "accounts_accountavatar" in PRESERVED_TABLES
    assert "ingestion_auditevent" not in model_tables()
    assert "accounts_accountavatar" not in model_tables()
    old = {"format": "stl4-database-reset-plan-v1", "blockers": []}
    old["fingerprint"] = digest(old)
    with pytest.raises(CommandError):
        verify_plan(old, old["fingerprint"])
    assert PLAN_FORMAT == "stl4-database-reset-plan-v2"


@pytest.mark.django_db
def test_mixed_audit_reset_preserves_only_account_receipts_in_test_database(admin_user):
    if connection.vendor != "postgresql":
        pytest.skip("This acceptance scenario requires the isolated PostgreSQL test database.")
    kept = [AuditEvent.objects.create(actor=admin_user, object_type=kind, object_id=str(admin_user.pk), action=action)
        for kind, action in [("User", "account_create"), ("User", "account_stop"), ("User", "account_activate"),
            ("User", "admin_set_password"), ("AccountAvatar", "profile_avatar_set"), ("AccountAvatar", "profile_avatar_stop")]]
    removed = [AuditEvent.objects.create(actor=admin_user, object_type=kind, object_id="fixture", action=action)
        for kind, action in [("Work", "account_create"), ("User", "accountXunrelated"), ("Work", "publish"), ("AccountAvatar", "unrelated")]]
    predicate, params = PARTIAL_PRESERVATION["ingestion_auditevent"]
    with connection.cursor() as cursor:
        before = table_snapshot(cursor, "ingestion_auditevent", (predicate, params))
        cursor.execute(f"DELETE FROM {quoted_table('ingestion_auditevent')} WHERE NOT ({predicate})", params)
        after = table_snapshot(cursor, "ingestion_auditevent", (predicate, params))
    assert before == after
    assert set(AuditEvent.objects.filter(pk__in=[row.pk for row in kept]).values_list("pk", flat=True)) == {row.pk for row in kept}
    assert not AuditEvent.objects.filter(pk__in=[row.pk for row in removed]).exists()
