from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import hashlib
import os
import re
import shutil
import subprocess

from django.db import connection
from django.db.migrations.loader import MigrationLoader


POSTGRES_VERSION_PATTERN = re.compile(
    r"PostgreSQL\)?\s+(?P<major>\d+)(?:\.(?P<minor>\d+))?",
    re.IGNORECASE,
)
POSTGRES_URL_PATTERN = re.compile(
    r"postgres(?:ql)?://[^\s'\"]+",
    re.IGNORECASE,
)
PGPASSWORD_PATTERN = re.compile(r"PGPASSWORD=[^\s]+", re.IGNORECASE)


class DatabaseBackupError(RuntimeError):
    pass


class PostgresCompatibilityError(DatabaseBackupError):
    pass


@dataclass(frozen=True)
class DatabaseDumpResult:
    filename: str
    byte_size: int
    sha256: str
    metadata: dict


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def redact_backup_error(text: str, *, secrets=()) -> str:
    redacted = str(text or "")
    for secret in secrets:
        value = str(secret or "")
        if value:
            redacted = redacted.replace(value, "[redacted]")
    redacted = POSTGRES_URL_PATTERN.sub("postgresql://[redacted]", redacted)
    redacted = PGPASSWORD_PATTERN.sub("PGPASSWORD=[redacted]", redacted)
    return redacted.strip()[:4000]


def parse_postgres_version(output: str, *, tool_name: str) -> dict:
    match = POSTGRES_VERSION_PATTERN.search(str(output or ""))
    if not match:
        raise DatabaseBackupError(
            f"无法识别 {tool_name} 版本：{redact_backup_error(output)}"
        )
    major = int(match.group("major"))
    minor = match.group("minor")
    version = str(major) if minor is None else f"{major}.{minor}"
    return {"version": version, "major": major}


def postgres_tool_version(executable: str, *, tool_name: str) -> dict:
    try:
        completed = subprocess.run(
            [executable, "--version"],
            capture_output=True,
            check=False,
            text=True,
            timeout=30,
        )
    except FileNotFoundError as exc:
        raise DatabaseBackupError(
            f"PostgreSQL {tool_name} executable missing: {executable}"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise DatabaseBackupError(
            f"PostgreSQL {tool_name} version check timed out."
        ) from exc
    output = (completed.stdout or completed.stderr or "").strip()
    if completed.returncode != 0:
        raise DatabaseBackupError(
            f"PostgreSQL {tool_name} version check failed: "
            f"exit_code={completed.returncode}; {redact_backup_error(output)}"
        )
    parsed = parse_postgres_version(output, tool_name=tool_name)
    parsed["raw"] = output
    return parsed


def postgres_server_version(database_connection=connection) -> dict:
    if database_connection.vendor != "postgresql":
        raise DatabaseBackupError("PostgreSQL version preflight requires PostgreSQL.")
    with database_connection.cursor() as cursor:
        cursor.execute(
            "SELECT current_setting('server_version'), "
            "current_setting('server_version_num')"
        )
        version, version_number = cursor.fetchone()
    numeric = int(version_number)
    major = numeric // 10000
    return {"version": str(version), "major": major}


def _assert_client_compatible(*, server: dict, client: dict, operation: str) -> None:
    if client["major"] < server["major"]:
        raise PostgresCompatibilityError(
            f"PostgreSQL {operation} client incompatible: "
            f"server={server['version']} "
            f"{operation}={client['version']}"
        )


def inspect_postgres_backup_runtime(database_connection=connection) -> dict:
    server = postgres_server_version(database_connection)
    dump_client = postgres_tool_version("pg_dump", tool_name="pg_dump")
    restore_client = postgres_tool_version("pg_restore", tool_name="pg_restore")
    _assert_client_compatible(
        server=server,
        client=dump_client,
        operation="pg_dump",
    )
    _assert_client_compatible(
        server=server,
        client=restore_client,
        operation="pg_restore",
    )
    return {
        "server_version": server["version"],
        "server_major": server["major"],
        "pg_dump_version": dump_client["version"],
        "pg_dump_major": dump_client["major"],
        "pg_restore_version": restore_client["version"],
        "pg_restore_major": restore_client["major"],
    }


def inspect_postgres_restore_runtime(
    database_connection=connection,
    *,
    dump_client_major: int | None = None,
) -> dict:
    server = postgres_server_version(database_connection)
    restore_client = postgres_tool_version("pg_restore", tool_name="pg_restore")
    _assert_client_compatible(
        server=server,
        client=restore_client,
        operation="pg_restore",
    )
    if dump_client_major and restore_client["major"] < int(dump_client_major):
        raise PostgresCompatibilityError(
            "PostgreSQL restore client incompatible with dump format: "
            f"dump_client={int(dump_client_major)} "
            f"pg_restore={restore_client['version']}"
        )
    return {
        "server_version": server["version"],
        "server_major": server["major"],
        "pg_restore_version": restore_client["version"],
        "pg_restore_major": restore_client["major"],
    }


def _postgres_environment(configuration: dict) -> tuple[dict, tuple[str, ...]]:
    environment = os.environ.copy()
    password = str(configuration.get("PASSWORD") or "")
    if password:
        environment["PGPASSWORD"] = password
    else:
        environment.pop("PGPASSWORD", None)
    return environment, (password,)


def _postgres_connection_arguments(configuration: dict) -> list[str]:
    return [
        "--host",
        str(configuration.get("HOST") or "localhost"),
        "--port",
        str(configuration.get("PORT") or "5432"),
        "--username",
        str(configuration.get("USER") or ""),
    ]


def create_database_dump(destination: Path, database_connection=connection) -> DatabaseDumpResult:
    engine = str(database_connection.settings_dict.get("ENGINE") or "")
    if engine.endswith("sqlite3"):
        source = Path(database_connection.settings_dict["NAME"]).resolve()
        target = destination / "database.sqlite3"
        shutil.copy2(source, target)
        return DatabaseDumpResult(
            filename=target.name,
            byte_size=target.stat().st_size,
            sha256=file_sha256(target),
            metadata={"engine": "sqlite3"},
        )
    if not engine.endswith("postgresql"):
        raise DatabaseBackupError(f"暂不支持备份数据库引擎：{engine}")

    runtime = inspect_postgres_backup_runtime(database_connection)
    configuration = database_connection.settings_dict
    target = destination / "database.dump"
    environment, secrets = _postgres_environment(configuration)
    command = [
        "pg_dump",
        "--format=custom",
        "--no-owner",
        "--file",
        str(target),
        *_postgres_connection_arguments(configuration),
        str(configuration.get("NAME") or ""),
    ]
    try:
        completed = subprocess.run(
            command,
            env=environment,
            capture_output=True,
            check=False,
            text=True,
            timeout=60 * 60,
        )
    except FileNotFoundError as exc:
        raise DatabaseBackupError(
            "PostgreSQL pg_dump executable missing: pg_dump"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        target.unlink(missing_ok=True)
        raise DatabaseBackupError("PostgreSQL backup command timed out.") from exc
    if completed.returncode != 0:
        target.unlink(missing_ok=True)
        detail = redact_backup_error(completed.stderr or completed.stdout, secrets=secrets)
        raise DatabaseBackupError(
            "PostgreSQL backup command failed: "
            f"exit_code={completed.returncode}; {detail}"
        )
    if not target.is_file() or target.stat().st_size <= 0:
        target.unlink(missing_ok=True)
        raise DatabaseBackupError("PostgreSQL backup command produced an empty artifact.")
    checksum = file_sha256(target)
    return DatabaseDumpResult(
        filename=target.name,
        byte_size=target.stat().st_size,
        sha256=checksum,
        metadata={
            "engine": "postgresql",
            **runtime,
        },
    )


def restore_database_dump(
    dump_path: Path,
    database_connection=connection,
    *,
    dump_client_major: int | None = None,
) -> dict:
    if database_connection.vendor != "postgresql":
        raise DatabaseBackupError("Restore rehearsal requires PostgreSQL.")
    runtime = inspect_postgres_restore_runtime(
        database_connection,
        dump_client_major=dump_client_major,
    )
    configuration = database_connection.settings_dict
    environment, secrets = _postgres_environment(configuration)
    command = [
        "pg_restore",
        "--exit-on-error",
        "--no-owner",
        "--no-privileges",
        *_postgres_connection_arguments(configuration),
        "--dbname",
        str(configuration.get("NAME") or ""),
        str(dump_path),
    ]
    database_connection.close()
    try:
        completed = subprocess.run(
            command,
            env=environment,
            capture_output=True,
            check=False,
            text=True,
            timeout=60 * 60,
        )
    except FileNotFoundError as exc:
        raise DatabaseBackupError(
            "PostgreSQL pg_restore executable missing: pg_restore"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise DatabaseBackupError("PostgreSQL restore command timed out.") from exc
    if completed.returncode != 0:
        detail = redact_backup_error(completed.stderr or completed.stdout, secrets=secrets)
        raise DatabaseBackupError(
            "PostgreSQL restore command failed: "
            f"exit_code={completed.returncode}; {detail}"
        )
    return runtime


def applied_migration_heads(database_connection=connection) -> list[str]:
    loader = MigrationLoader(database_connection, ignore_no_migrations=True)
    applied = set(loader.applied_migrations)
    heads = []
    for node in sorted(applied):
        graph_node = loader.graph.node_map.get(node)
        if graph_node is None:
            continue
        same_app_child_applied = any(
            child.key[0] == node[0] and child.key in applied
            for child in graph_node.children
        )
        if not same_app_child_applied:
            heads.append(f"{node[0]}.{node[1]}")
    return heads
