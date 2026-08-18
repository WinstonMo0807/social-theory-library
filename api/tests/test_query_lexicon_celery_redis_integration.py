from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
import subprocess
import sys
from time import monotonic, sleep
from urllib.parse import quote, urlsplit, urlunsplit

import pytest
import redis
from django.db import connection, transaction

from catalog.models import (
    Person,
    QueryLexiconChangeEvent,
    QueryLexiconEntry,
    QueryLexiconState,
)
from catalog.services.query_lexicon.normalization import normalize_term
from catalog.services.query_lexicon.resolver import PUBLIC_ACTIVE, resolve_term
from catalog.services.query_lexicon.sync import ensure_query_lexicon_state
from catalog.tasks import process_query_lexicon_events
from config.celery import app as celery_app


pytestmark = [
    pytest.mark.celery_redis_integration,
    pytest.mark.django_db(transaction=True),
]


def _wait_until(predicate, *, timeout=20, interval=0.2, message="condition timed out"):
    deadline = monotonic() + timeout
    last_error = None
    while monotonic() < deadline:
        try:
            value = predicate()
            if value:
                return value
        except Exception as exc:  # Service startup and reconnect are expected here.
            last_error = exc
        sleep(interval)
    if last_error is not None:
        raise AssertionError(f"{message}: {last_error}") from last_error
    raise AssertionError(message)


def _test_database_url() -> str:
    configured = os.environ["DATABASE_URL"]
    parsed = urlsplit(configured)
    database_name = quote(str(connection.settings_dict["NAME"]), safe="")
    return urlunsplit(
        (parsed.scheme, parsed.netloc, f"/{database_name}", parsed.query, parsed.fragment)
    )


@dataclass
class CeleryRedisRuntime:
    redis_server: Path
    redis_port: int
    temp_dir: Path
    environment: dict[str, str]
    redis_process: subprocess.Popen | None = None
    worker_process: subprocess.Popen | None = None
    beat_process: subprocess.Popen | None = None
    log_handles: list = field(default_factory=list)

    @property
    def redis_client(self):
        return redis.Redis(host="127.0.0.1", port=self.redis_port, db=15)

    def _popen(self, args, log_name):
        handle = (self.temp_dir / log_name).open("a", encoding="utf-8")
        self.log_handles.append(handle)
        return subprocess.Popen(
            args,
            cwd=Path(__file__).resolve().parents[1],
            env=self.environment,
            stdin=subprocess.DEVNULL,
            stdout=handle,
            stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

    @staticmethod
    def _stop_process(process):
        if process is None or process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)

    def start_redis(self):
        if self.redis_process is not None and self.redis_process.poll() is None:
            return
        self.redis_process = self._popen(
            [
                str(self.redis_server),
                "--bind",
                "127.0.0.1",
                "--port",
                str(self.redis_port),
                "--save",
                "",
                "--appendonly",
                "no",
                "--logfile",
                str(self.temp_dir / "redis.log"),
            ],
            "redis-process.log",
        )
        _wait_until(
            self.redis_client.ping,
            timeout=10,
            message="Redis did not start",
        )

    def stop_redis(self):
        self._stop_process(self.redis_process)
        self.redis_process = None
        _wait_until(
            lambda: not self._redis_available(),
            timeout=5,
            message="Redis port remained available",
        )

    def _redis_available(self):
        try:
            return bool(self.redis_client.ping())
        except redis.RedisError:
            return False

    def start_worker(self, *, wait_ready=True):
        if self.worker_process is None or self.worker_process.poll() is not None:
            self.worker_process = self._popen(
                [
                    sys.executable,
                    "-m",
                    "celery",
                    "-A",
                    "config",
                    "worker",
                    "--pool=solo",
                    "--concurrency=1",
                    "--prefetch-multiplier=1",
                    "--loglevel=INFO",
                    "--hostname=query-lexicon-test@%h",
                ],
                "worker.log",
            )
        if wait_ready:
            _wait_until(
                lambda: celery_app.control.ping(timeout=1),
                timeout=15,
                message="Celery worker did not answer ping",
            )

    def stop_worker(self):
        self._stop_process(self.worker_process)
        self.worker_process = None

    def start_beat(self):
        if self.beat_process is not None and self.beat_process.poll() is None:
            return
        schedule = self.temp_dir / "celerybeat-schedule"
        self.beat_process = self._popen(
            [
                sys.executable,
                "-m",
                "celery",
                "-A",
                "config",
                "beat",
                "--loglevel=INFO",
                f"--schedule={schedule}",
            ],
            "beat.log",
        )
        sleep(1)
        if self.beat_process.poll() is not None:
            raise AssertionError("Celery Beat exited during startup")

    def ensure_celery_after_broker_restart(self):
        celery_app.close()
        self.start_worker(wait_ready=False)
        self.start_beat()
        _wait_until(
            lambda: celery_app.control.ping(timeout=1),
            timeout=20,
            message="Celery worker did not reconnect after Redis restart",
        )

    def close(self):
        self.stop_worker()
        self._stop_process(self.beat_process)
        self.beat_process = None
        self._stop_process(self.redis_process)
        self.redis_process = None
        celery_app.close()
        for handle in self.log_handles:
            handle.close()


@pytest.fixture
def celery_redis_runtime(tmp_path):
    if connection.vendor != "postgresql":
        pytest.skip("requires PostgreSQL")
    redis_server = os.getenv("QUERY_LEXICON_TEST_REDIS_SERVER", "").strip()
    if not redis_server or not Path(redis_server).is_file():
        pytest.skip("QUERY_LEXICON_TEST_REDIS_SERVER is not available")
    redis_port = int(os.getenv("QUERY_LEXICON_TEST_REDIS_PORT", "56380"))
    environment = os.environ.copy()
    environment.update(
        {
            "DATABASE_URL": _test_database_url(),
            "CELERY_BROKER_URL": f"redis://127.0.0.1:{redis_port}/14",
            "CACHE_URL": f"redis://127.0.0.1:{redis_port}/15",
            "CELERY_TASK_ALWAYS_EAGER": "0",
            "PROCESS_INGESTION_INLINE": "0",
            "QUERY_LEXICON_EVENT_LEASE_SECONDS": "5",
            "QUERY_LEXICON_EVENT_RETRY_BASE_SECONDS": "1",
            "QUERY_LEXICON_EVENT_RETRY_MAX_SECONDS": "1",
            "QUERY_LEXICON_RECOVERY_INTERVAL_SECONDS": "2",
            "PYTHONUTF8": "1",
            "PYTHONIOENCODING": "utf-8",
        }
    )
    ensure_query_lexicon_state()
    runtime = CeleryRedisRuntime(
        redis_server=Path(redis_server),
        redis_port=redis_port,
        temp_dir=tmp_path,
        environment=environment,
    )
    runtime.start_redis()
    runtime.start_worker()
    runtime.start_beat()
    try:
        yield runtime
    finally:
        runtime.close()


def _person(name):
    return Person.objects.create(
        preferred_name=name,
        authority_status=Person.AuthorityStatus.VERIFIED,
    )


def _wait_for_event(person, *, timeout=25):
    def processed():
        event = QueryLexiconChangeEvent.objects.get(entity_id=person.pk)
        return event if event.processed_at is not None else None

    return _wait_until(
        processed,
        timeout=timeout,
        message=f"event for {person.pk} was not processed",
    )


def test_celery_redis_commit_wakeup_consumes_durable_event(celery_redis_runtime):
    revision = QueryLexiconState.objects.get(key="default").revision
    person = _person("真实 Celery 唤醒人物")

    event = _wait_for_event(person)
    state = QueryLexiconState.objects.get(key="default")
    assert event.applied_revision == state.revision == revision + 1
    assert resolve_term(person.preferred_name, scope=PUBLIC_ACTIVE)["matches"]


def test_celery_redis_periodic_sweep_recovers_lost_broker_notification(
    celery_redis_runtime,
):
    runtime = celery_redis_runtime
    revision = QueryLexiconState.objects.get(key="default").revision
    runtime.stop_redis()
    celery_app.close()

    person = _person("broker 丢失恢复人物")
    event = QueryLexiconChangeEvent.objects.get(entity_id=person.pk)
    assert event.processed_at is None
    assert event.last_error_code == "queue_unavailable"

    runtime.start_redis()
    runtime.ensure_celery_after_broker_restart()
    event = _wait_for_event(person, timeout=30)
    state = QueryLexiconState.objects.get(key="default")
    assert event.applied_revision == state.revision == revision + 1
    assert resolve_term(person.preferred_name, scope=PUBLIC_ACTIVE)["matches"]


def test_celery_redis_worker_crash_after_claim_recovers_after_lease(
    celery_redis_runtime,
):
    runtime = celery_redis_runtime
    revision = QueryLexiconState.objects.get(key="default").revision
    runtime.stop_worker()
    person = _person("真实 worker 崩溃恢复人物")
    event = QueryLexiconChangeEvent.objects.get(entity_id=person.pk)

    with transaction.atomic():
        QueryLexiconState.objects.select_for_update().get(key="default")
        runtime.start_worker(wait_ready=False)

        def claimed():
            event.refresh_from_db()
            return event.lease_token

        _wait_until(claimed, timeout=15, message="worker did not claim event")
        runtime.stop_worker()
        event.refresh_from_db()
        assert event.processed_at is None
        assert event.lease_token is not None

    runtime.start_worker()
    event = _wait_for_event(person, timeout=30)
    state = QueryLexiconState.objects.get(key="default")
    assert event.lease_token is None
    assert event.applied_revision == state.revision == revision + 1


def test_celery_redis_duplicate_wakeups_are_idempotent(celery_redis_runtime):
    runtime = celery_redis_runtime
    revision = QueryLexiconState.objects.get(key="default").revision
    runtime.stop_worker()
    person = _person("重复真实唤醒人物")
    for _index in range(4):
        process_query_lexicon_events.apply_async(ignore_result=True)

    runtime.start_worker()
    _wait_for_event(person)
    sleep(3)
    state = QueryLexiconState.objects.get(key="default")
    assert state.revision == revision + 1
    assert QueryLexiconEntry.objects.filter(
        generation=state.active_generation,
        entity_type=QueryLexiconEntry.EntityType.PERSON,
        entity_id=person.pk,
        normalized_term=normalize_term(person.preferred_name),
    ).count() == 1
