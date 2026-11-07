"""Conservatively compact a paused Redis queue, with WATCH and a durable backup.

Load through Django's management shell. Default is read-only. Unique business
messages and unacked deliveries are never removed; no task-body data is logged.
"""
import base64
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
from uuid import uuid4

MAX_MESSAGES = 20000

PERIODIC = {
    "catalog.tasks.heartbeat_claim_executor", "ingestion.tasks.record_ingestion_worker_heartbeat",
    "catalog.tasks.recover_knowledge_publication_events", "distribution.storage_tasks.dispatch_due_backups",
    "catalog.tasks.recover_query_lexicon_events", "catalog.tasks.recover_projection_queue",
    "ingestion.tasks.recover_ingestion_queue", "catalog.tasks.run_scheduled_health_probes",
    "reading.tasks.recover_private_research_tasks", "catalog.tasks.recover_semantic_index_queue",
}


def plan(messages):
    keep, seen, periodic, counts = [], set(), set(), Counter()
    for raw in messages:  # Redis LPUSH makes index zero the newest delivery.
        try:
            message = json.loads(raw)
            headers = message.get("headers") or {}
            task, task_id = headers.get("task"), headers.get("id")
            body = message.get("body")
            decoded = json.loads(base64.b64decode(body))
            is_periodic = task in PERIODIC and decoded[0] == [] and decoded[1] == {}
            identity = (task, task_id, body, headers.get("eta"), headers.get("retries"))
            if is_periodic and task in periodic:
                counts["superseded_periodic"] += 1
                continue
            if task_id and identity in seen:
                counts["same_delivery"] += 1
                continue
            if is_periodic:
                periodic.add(task)
            if task_id:
                seen.add(identity)
        except (ValueError, TypeError, KeyError, IndexError):
            counts["unparsed_preserved"] += 1
        keep.append(raw)
    return keep, dict(counts)


def compact(*, apply=False, backup_dir=None):
    from config.celery import app
    with app.connection_for_read(connect_timeout=2) as connection, connection.channel() as channel:
        if connection.transport.driver_type != "redis":
            raise ValueError("Redis transport required")
        client = channel.client
        keys = [channel._q_for_pri("celery", p) for p in channel.priority_steps]
        with client.pipeline() as transaction:
            transaction.watch(*keys)
            if sum(client.llen(key) for key in keys) > MAX_MESSAGES:
                raise ValueError("Queue exceeds snapshot bound")
            originals = {key: transaction.lrange(key, 0, MAX_MESSAGES) for key in keys}
            plans = {key: plan(rows) for key, rows in originals.items()}
            summary = {key: {"before": len(originals[key]), "after": len(kept), **counts}
                       for key, (kept, counts) in plans.items()}
            if apply:
                folder = Path(backup_dir)
                folder.mkdir(parents=True, exist_ok=True, mode=0o700)
                backup = folder / ("celery-before-" + uuid4().hex + ".json")
                payload = json.dumps({key: [base64.b64encode(raw).decode() for raw in rows]
                                      for key, rows in originals.items()}).encode()
                with backup.open("xb") as handle:
                    os.chmod(backup, 0o600)
                    handle.write(payload)
                    handle.flush()
                    os.fsync(handle.fileno())
                assert hashlib.sha256(backup.read_bytes()).digest() == hashlib.sha256(payload).digest()
                transaction.multi()
                for key, (kept, _counts) in plans.items():
                    if len(kept) == len(originals[key]):
                        continue
                    transaction.delete(key)
                    if kept:
                        transaction.rpush(key, *kept)
                transaction.execute()  # Abort if any watched list changed since the snapshot.
                summary["backup"] = {"path": str(backup), "sha256": hashlib.sha256(payload).hexdigest()}
            return summary
