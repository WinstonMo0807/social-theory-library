"""Root-owned NAS service: fixed allowlist, Redis demand, bounded idle shutdown.

No HTTP endpoint or user-supplied Docker commands. Requires the combined heavy
worker to consume ingestion and discovery_index with late ACKs; reader queries
keep their own on-demand worker so indexing cannot block an interactive query.
"""
import argparse
import json
import subprocess
import time

PREFIX = "social-science-library-"
CONTAINERS = {"inference": PREFIX + "discovery-inference-1", "docx": PREFIX + "docx-preview-1",
              "searxng": PREFIX + "searxng-1", "heavy": PREFIX + "ingestion-worker-1",
              "query": PREFIX + "discovery-query-worker-1", "ocr": PREFIX + "rapidocr-1"}
QUEUES = ("ingestion", "discovery_query", "discovery_index")
DEMANDS = ("inference", "docx", "searxng", "ocr")


def command(args, timeout=20):
    result = subprocess.run(args, capture_output=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError("Command failed: " + args[0])
    return result.stdout


def redis(*args):
    raw = command(["docker", "exec", PREFIX + "redis-1", "sh", "-c",
        'export REDISCLI_AUTH="$REDIS_PASSWORD"; exec redis-cli --no-auth-warning --json -n 2 "$@"',
        "redis-cli", *args])
    return json.loads(raw)


def snapshot():
    # One read-only Redis round trip. Never put authentication in process args.
    lua = "local r={} for _,k in ipairs(KEYS) do r[#r+1]=redis.call('GET',k) or '' end "
    lua += "for _,q in ipairs(ARGV) do local n=0 for _,p in ipairs({'','\\006\\0223','\\006\\0226','\\006\\0229'}) do n=n+redis.call('LLEN',q..p) end r[#r+1]=n end "
    lua += "if redis.call('HLEN','unacked')>20000 then return redis.error_reply('snapshot bound') end r[#r+1]=redis.call('HVALS','unacked') return r"
    keys = ["stl:service-demand:" + name for name in DEMANDS]
    rows = redis("EVAL", lua, str(len(keys)), *keys, *QUEUES)
    if not isinstance(rows, list) or len(rows) != len(DEMANDS) + len(QUEUES) + 1:
        raise ValueError("Invalid broker snapshot")
    demand = {name: bool(rows[i]) for i, name in enumerate(DEMANDS)}
    queued = dict(zip(QUEUES, rows[len(DEMANDS):-1]))
    for raw in rows[-1]:
        message, _exchange, routing = json.loads(raw)
        if routing in queued:
            queued[routing] += 1
    demand["heavy"] = bool(queued["ingestion"] or queued["discovery_index"])
    demand["query"] = bool(queued["discovery_query"])
    return demand


def tick(last_busy, *, now=None, inspect=None, run=command, demand=None):
    now = time.monotonic() if now is None else now
    demand = snapshot() if demand is None else demand
    inspect = json.loads(run(["docker", "inspect", *CONTAINERS.values()])) if inspect is None else inspect
    by_name = {row["Name"].lstrip("/"): row for row in inspect}
    for container in CONTAINERS.values():
        row = by_name[container]
        labels = row["Config"].get("Labels") or {}
        if labels.get("com.docker.compose.project") != "social-science-library":
            raise ValueError("Unexpected container ownership")
    for name, container in CONTAINERS.items():
        row = by_name[container]
        if demand[name]:
            last_busy[name] = now
            if not row["State"]["Running"]:
                run(["docker", "start", container])
                print(json.dumps({"started": name}), flush=True)
        elif row["State"]["Running"]:
            last_busy.setdefault(name, now)
            if now - last_busy[name] >= (90 if name in {"heavy", "query"} else 300):
                # A queued/reserved/active late-ACK heavy task blocks shutdown.
                # HTTP demands already have a 900-second lifetime before this grace.
                if name in DEMANDS:
                    claimed = redis("EVAL", "if redis.call('EXISTS',KEYS[1])==1 then return 0 end return redis.call('SET',KEYS[2],'1','NX','EX',75)",
                                    "2", "stl:service-demand:" + name, "stl:service-stopping:" + name)
                    if not claimed:
                        continue
                # Warm TERM only: a delivery arriving after the queue snapshot
                # must finish; never escalate to SIGKILL on a fixed deadline.
                run(["docker", "kill", "--signal", "TERM", container])
                if name in DEMANDS:
                    run(["docker", "wait", container], timeout=70)
                    redis("DEL", "stl:service-stopping:" + name)
                last_busy.pop(name, None)
                print(json.dumps({"stopped_idle": name}), flush=True)


if __name__ == "__main__":
    import fcntl
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    with open("/run/stl-on-demand.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        last_busy = {}
        while True:
            try:
                tick(last_busy)
            except Exception as exc:
                print(json.dumps({"error": type(exc).__name__, "action": "deferred"}), flush=True)
                # An unknown broker/container state never authorizes a stop.
                last_busy.clear()
            if args.once:
                break
            time.sleep(5)
