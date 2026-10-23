"""Bounded database reset; external stores require separate recovery steps."""
import hashlib
import json
from pathlib import Path

from django.apps import apps
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from distribution.database_backup import file_sha256


PRESERVED_TABLES = frozenset({
    "accounts_user", "accounts_readerprofile", "accounts_recoverycode", "accounts_accountavatar",
    "accounts_user_groups", "accounts_user_user_permissions", "auth_group",
    "auth_group_permissions", "auth_permission", "django_content_type",
    "django_migrations", "django_session",
    # Removing the blacklist would make some revoked refresh tokens valid again.
    "token_blacklist_outstandingtoken", "token_blacklist_blacklistedtoken",
    # Recovery audit and connection/budget configuration are not library content.
    "distribution_backupjob", "distribution_cloudprovider", "distribution_cloudbudgetpolicy",
    # This mixed table is retained only for the account rows described below.
    "ingestion_auditevent",
})
PARTIAL_PRESERVATION = {
    "ingestion_auditevent": (
        '(("object_type" = %s AND (left("action", 8) = %s OR "action" IN (%s, %s))) '
        'OR ("object_type" = %s AND "action" IN (%s, %s, %s)))',
        ("User", "account_", "admin_update_user", "admin_set_password", "AccountAvatar",
         "profile_avatar_set", "profile_avatar_remove", "profile_avatar_stop"),
    ),
}
BUSINESS_APPS = frozenset({"catalog", "ingestion", "reading", "distribution", "admin"})
PLAN_FORMAT = "stl4-database-reset-plan-v2"
BACKUP_FORMAT = "stl4-reset-backup-v1"
BACKUP_SCOPES = frozenset({"database", "files", "search", "cache", "environment"})


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def read_json(path):
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CommandError("Cannot read the required JSON evidence file.") from exc
    if not isinstance(value, dict):
        raise CommandError("Evidence must be a JSON object.")
    return value


def model_tables():
    """No name-prefix or 'everything except accounts' deletion policy."""
    return {
        model._meta.db_table
        for model in apps.get_models(include_auto_created=True)
        if model._meta.managed and not model._meta.proxy
        and not model._meta.swapped and model._meta.app_label in BUSINESS_APPS
    } - PRESERVED_TABLES


def quoted_table(table):
    return connection.ops.quote_name("public") + "." + connection.ops.quote_name(table)


def table_snapshot(cursor, table, where=None):
    """Stream canonical rows; never emit passwords, tokens or private content."""
    checksum, count = hashlib.sha256(), 0
    predicate, params = where if where else ("", ())
    cursor.execute(
        "DECLARE stl_reset_rows NO SCROLL CURSOR FOR "
        f"SELECT row_to_json(t)::text FROM {quoted_table(table)} t "
        + ("WHERE " + predicate + " " if predicate else "")
        + "ORDER BY row_to_json(t)::text", params,
    )
    try:
        while True:
            cursor.execute("FETCH FORWARD 32 FROM stl_reset_rows")
            rows = cursor.fetchall()
            if not rows:
                break
            for (row,) in rows:
                checksum.update(row.encode())
                checksum.update(b"\n")
                count += 1
    finally:
        cursor.execute("CLOSE stl_reset_rows")
    return {"rows": count, "sha256": checksum.hexdigest()}


def inspect_plan(cursor):
    cursor.execute(
        "SELECT current_database(), (SELECT oid FROM pg_database WHERE datname = current_database()), "
        "inet_server_addr()::text, inet_server_port(), current_user, "
        "current_setting('server_version_num'), pg_postmaster_start_time()::text"
    )
    identity = dict(zip(
        ("database", "database_oid", "server_address", "server_port", "role", "server_version", "server_started_at"),
        cursor.fetchone(),
    ))
    # Unix socket connections have no inet_server_addr. Hash their endpoint;
    # never copy a database URL, username or password into the report.
    identity["endpoint_sha256"] = digest({
        key: str(connection.settings_dict.get(key) or "") for key in ("HOST", "PORT")
    })
    cursor.execute(
        "SELECT c.relname, c.relkind FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p', 'f') ORDER BY c.relname"
    )
    relations = dict(cursor.fetchall())
    known = model_tables()
    targets = sorted(set(relations) & known)
    preserved = sorted(set(relations) & PRESERVED_TABLES)
    partial = sorted(set(relations) & set(PARTIAL_PRESERVATION))
    unknown = sorted(set(relations) - known - PRESERVED_TABLES)
    blockers = [f"Unclassified table: public.{table}" for table in unknown]
    blockers += [f"Missing preserved table: public.{table}" for table in sorted(PRESERVED_TABLES - set(relations))]
    blockers += [f"Unsupported relation kind: public.{table}" for table, kind in relations.items() if kind != "r"]

    cursor.execute(
        "SELECT sn.nspname, src.relname, tn.nspname, dst.relname, fk.conname, "
        "pg_get_constraintdef(fk.oid) FROM pg_constraint fk "
        "JOIN pg_class src ON src.oid = fk.conrelid JOIN pg_namespace sn ON sn.oid = src.relnamespace "
        "JOIN pg_class dst ON dst.oid = fk.confrelid JOIN pg_namespace tn ON tn.oid = dst.relnamespace "
        "WHERE fk.contype = 'f' AND (sn.nspname = 'public' OR tn.nspname = 'public') "
        "ORDER BY sn.nspname, src.relname, fk.conname"
    )
    foreign_keys = [list(row) for row in cursor.fetchall()]
    target_set = set(targets) | set(partial)
    for schema, table, target_schema, target, constraint, _ in foreign_keys:
        if target_schema == "public" and target in target_set and (schema != "public" or table not in target_set):
            blockers.append(f"Outside reference to reset table: {schema}.{table}.{constraint} -> public.{target}")

    # Inheritance and write triggers can affect rows outside the explicit list.
    cursor.execute(
        "SELECT c.relname FROM pg_inherits i JOIN pg_class c ON c.oid IN (i.inhrelid, i.inhparent) "
        "JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = 'public' ORDER BY c.relname"
    )
    blockers += [f"Inherited/partitioned reset table: public.{row[0]}" for row in cursor.fetchall() if row[0] in target_set]
    cursor.execute(
        "SELECT c.relname, t.tgname, t.tgtype FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid "
        "JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = 'public' "
        "AND NOT t.tgisinternal AND t.tgenabled <> 'D' AND (t.tgtype & 40) <> 0 ORDER BY c.relname, t.tgname"
    )
    for table, trigger, trigger_type in cursor.fetchall():
        if table in partial and trigger_type & 8:
            blockers.append(f"Unreviewed DELETE trigger: public.{table}.{trigger}")
        elif table in targets and trigger_type & 32:
            blockers.append(f"Unreviewed TRUNCATE trigger: public.{table}.{trigger}")
    cursor.execute(
        "SELECT c.relname, a.attname, format_type(a.atttypid, a.atttypmod), a.attnotnull "
        "FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid "
        "JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = 'public' "
        "AND c.relkind IN ('r', 'p', 'f') AND a.attnum > 0 AND NOT a.attisdropped ORDER BY c.relname, a.attnum"
    )
    columns = [list(row) for row in cursor.fetchall()]
    # Never contact an external store through an unreviewed foreign table.
    snapshots = {table: table_snapshot(cursor, table) for table, kind in relations.items() if kind == "r"}
    retained = {table: table_snapshot(cursor, table, PARTIAL_PRESERVATION[table])
                if table in partial and relations[table] == "r" else snapshots.get(table) for table in preserved}
    partial_resets = {}
    for table in partial:
        if relations[table] != "r":
            continue
        predicate, params = PARTIAL_PRESERVATION[table]
        partial_resets[table] = {"before": snapshots[table],
            "to_remove": table_snapshot(cursor, table, (f"NOT ({predicate})", params)),
            "retention_policy_sha256": digest({"predicate": predicate, "parameters": params}),
            "policy": "Keep account identity, invitation and avatar command receipts; remove other business audit rows."}
    plan = {
        "format": PLAN_FORMAT, "database_identity": identity,
        "targets": {table: snapshots.get(table) for table in targets},
        "preserved": retained, "partial_resets": partial_resets,
        "unknown": {table: snapshots.get(table) for table in unknown},
        "foreign_keys": foreign_keys, "columns": columns, "blockers": sorted(set(blockers)),
        "external_resources": "Not modified: files, object storage, Redis and search indexes.",
    }
    plan["preserved_fingerprint"] = digest(plan["preserved"])
    plan["fingerprint"] = digest(plan)
    return plan


def verify_plan(plan, confirmed):
    unsigned = {key: value for key, value in plan.items() if key != "fingerprint"}
    if plan.get("format") != PLAN_FORMAT or plan.get("fingerprint") != digest(unsigned) or confirmed != plan.get("fingerprint"):
        raise CommandError("The plan fingerprint is missing, altered or not explicitly confirmed.")
    if plan.get("blockers"):
        raise CommandError("Reset blocked by unknown tables, missing identity tables or unsafe dependencies.")


def verified_file(root, record):
    if not isinstance(record, dict) or not record.get("path"):
        raise CommandError("Backup evidence requires a path, positive byte size and SHA-256.")
    path = (root / str(record["path"])).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise CommandError("Backup artifact is missing or outside its evidence directory.")
    size = record.get("bytes")
    if type(size) is not int or size <= 0 or path.stat().st_size != size or file_sha256(path) != record.get("sha256"):
        raise CommandError("Backup artifact size/checksum verification failed.")
    return path


def verify_backup(path, plan):
    path = Path(path).resolve()
    backup = read_json(path)
    if (backup.get("format") != BACKUP_FORMAT or backup.get("plan_fingerprint") != plan["fingerprint"]
            or backup.get("database_identity") != plan["database_identity"]
            or backup.get("preserved_fingerprint") != plan["preserved_fingerprint"]
            or backup.get("writes_stopped") is not True):
        raise CommandError("Backup evidence must match this exact database, plan and preserved-account snapshot with writes stopped.")
    artifacts = backup.get("artifacts")
    if not isinstance(artifacts, dict) or set(artifacts) != BACKUP_SCOPES:
        raise CommandError("Backup evidence must cover database, files, search, cache and environment.")
    for artifact in artifacts.values():
        verified_file(path.parent, artifact)
    restore = read_json(verified_file(path.parent, backup.get("restore_report")))
    # Reuse rehearse_database_restore's report. It must describe the same archive,
    # not a different dump that was manually labelled as having been restored.
    if (restore.get("status") != "restored"
            or restore.get("archive_sha256") != artifacts["database"]["sha256"]
            or not restore.get("database")
            or restore["database"] == plan["database_identity"]["database"]
            or not restore.get("database_dump_sha256")):
        raise CommandError("A successful isolated restore of this exact database archive is required.")
    account_report = read_json(verified_file(path.parent, backup.get("account_verification")))
    if (account_report.get("status") != "verified"
            or account_report.get("restored_database") != restore["database"]
            or account_report.get("archive_sha256") != restore["archive_sha256"]
            or account_report.get("preserved") != plan["preserved"]):
        raise CommandError("Restored account/permission/session fingerprints must match the preview.")
    return file_sha256(path)


class Command(BaseCommand):
    help = "Default: read-only reset preview. Execution needs matching preview, verified recovery evidence and final approval."
    requires_system_checks = []
    requires_migrations_checks = False

    def add_arguments(self, parser):
        parser.add_argument("--execute", action="store_true")
        parser.add_argument("--dry-run", action="store_true", help="Explicit read-only preview (also the default).")
        parser.add_argument("--plan-output", type=Path, help="Write preview JSON to a new file; existing files are never overwritten.")
        parser.add_argument("--plan-file", type=Path)
        parser.add_argument("--confirm-plan", help="Exact fingerprint from the reviewed preview.")
        parser.add_argument("--backup-manifest", type=Path)
        parser.add_argument("--maintenance-confirmed", action="store_true", help="All API/worker/beat writers and producers are stopped.")
        parser.add_argument("--approval-reference", help="Reference to the user's final approval of this exact impact and backup report.")
        parser.add_argument("--confirm-public-reset", action="store_true", help="Acknowledge deletion of the listed business rows only.")

    def handle(self, *args, **options):
        execute = options["execute"]
        if options["dry_run"] and execute:
            raise CommandError("--dry-run and --execute are mutually exclusive.")
        if not execute and any(options.get(key) for key in (
            "confirm_public_reset", "plan_file", "confirm_plan", "backup_manifest", "maintenance_confirmed", "approval_reference"
        )):
            raise CommandError("Execution acknowledgements require --execute; the legacy confirmation flag alone no longer deletes data.")
        if execute and (options["plan_output"] or not all(options.get(key) for key in (
            "confirm_public_reset", "plan_file", "confirm_plan", "backup_manifest", "maintenance_confirmed", "approval_reference"
        )) or not str(options.get("approval_reference") or "").strip()):
            raise CommandError("Execution requires a plan, its fingerprint, verified backup manifest, maintenance acknowledgement and final approval reference.")
        if connection.vendor != "postgresql":
            raise CommandError("This bounded reset supports PostgreSQL only; no rows were changed.")
        if connection.in_atomic_block:
            raise CommandError("Run the reset outside any existing transaction.")
        if not execute:
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
                    cursor.execute("SET LOCAL statement_timeout = '300000'")
                    plan = inspect_plan(cursor)
            report = json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True)
            if options["plan_output"]:
                try:
                    with options["plan_output"].open("x", encoding="utf-8") as handle:
                        handle.write(report + "\n")
                except OSError as exc:
                    raise CommandError("Cannot create a new plan file; existing evidence is never overwritten.") from exc
            self.stdout.write(report)
            return

        plan = read_json(options["plan_file"])
        verify_plan(plan, options["confirm_plan"])
        backup_checksum = verify_backup(options["backup_manifest"], plan)
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL lock_timeout = '5000'")
                cursor.execute("SET LOCAL statement_timeout = '300000'")
                tables = sorted(set(plan["targets"]) | set(plan["preserved"]))
                cursor.execute("LOCK TABLE " + ", ".join(quoted_table(table) for table in tables) + " IN ACCESS EXCLUSIVE MODE NOWAIT")
                current = inspect_plan(cursor)
                if current["fingerprint"] != plan["fingerprint"]:
                    raise CommandError("Database identity, schema or rows changed since preview; obtain a new preview and backup.")
                verify_plan(current, options["confirm_plan"])
                targets = list(current["targets"])
                if targets:
                    cursor.execute("TRUNCATE TABLE " + ", ".join("ONLY " + quoted_table(table) for table in targets) + " CONTINUE IDENTITY RESTRICT")
                for table in current["partial_resets"]:
                    predicate, params = PARTIAL_PRESERVATION[table]
                    cursor.execute(f"DELETE FROM {quoted_table(table)} WHERE NOT ({predicate})", params)
                preserved_after = {table: table_snapshot(cursor, table, PARTIAL_PRESERVATION.get(table)) for table in current["preserved"]}
                if preserved_after != current["preserved"]:
                    raise CommandError("Preserved account/configuration rows changed; the entire reset has been rolled back.")
                for table in targets:
                    cursor.execute(f"SELECT COUNT(*) FROM {quoted_table(table)}")
                    if cursor.fetchone()[0] != 0:
                        raise CommandError("A business table is not empty; the entire reset has been rolled back.")
                for table in current["partial_resets"]:
                    predicate, params = PARTIAL_PRESERVATION[table]
                    cursor.execute(f"SELECT COUNT(*) FROM {quoted_table(table)} WHERE NOT ({predicate})", params)
                    if cursor.fetchone()[0] != 0:
                        raise CommandError("Business audit rows remain; the entire reset has been rolled back.")
        self.stdout.write(json.dumps({
            "status": "database_rows_reset", "plan_fingerprint": plan["fingerprint"],
            "backup_manifest_sha256": backup_checksum, "preserved_fingerprint": plan["preserved_fingerprint"],
            "reset_tables": targets, "approval_reference": options["approval_reference"],
            "partial_reset_tables": list(current["partial_resets"]),
            "external_resources": plan["external_resources"],
        }, ensure_ascii=False, sort_keys=True))
