"""Execute a reviewed maintenance specification through real MCP tools.

The input specification and raw results live outside Git. This measures the
structured execution, not fresh model research or from-empty book curation.
"""
import asyncio
import hashlib
import json
from pathlib import Path
import sys
import time

from mcp import Client, StdioServerParameters


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


async def main(spec_path):
    spec_path = Path(spec_path)
    specification = json.loads(spec_path.read_text(encoding="utf-8"))
    directory = spec_path.parent / "trial"
    directory.mkdir(exist_ok=True)
    parameters = StdioServerParameters(command=sys.executable, args=["-X", "utf8", str(Path(__file__).with_name("server.py"))])
    report = {"scenario": "existing_holdings_maintenance", "source_selection_reviewed_before_timer": True,
              "fresh_semantic_research_measured": False, "started_at_epoch": time.time(), "books": []}

    async with Client(parameters, read_timeout_seconds=120) as client:
        for book in specification:
            started = time.monotonic()
            timings = []
            raw = {}

            async def call(name, arguments, *, label=None):
                then = time.monotonic()
                response = await client.call_tool(name, arguments)
                result = response.structured_content
                timings.append({"tool": name, "phase": label or name, "seconds": round(time.monotonic() - then, 3)})
                raw[label or name] = result
                write(directory / f"{book['key']}-raw.json", raw)
                if response.is_error or result is None or not result.get("ok"):
                    raise RuntimeError(f"{book['key']} {name}: {result}")
                return result

            await call("stl_search_catalog", {"queries": [book["title"]], "limit": 5})
            await call("stl_get_operation_status", {"work_ids": [book["work_id"]]}, label="background_before")
            targets = [{"type": "work", "id": book["work_id"], "edition_id": book["edition_id"]},
                       {"type": "scholar_profile", "id": book["scholar_id"]},
                       {"type": "evidence_curation", "kind": "scholar", "id": book["scholar_id"]},
                       {"type": "topic", "id": book["topic_id"]},
                       {"type": "evidence_curation", "kind": "topic", "id": book["topic_id"]}]
            before = await call("stl_get_curation_context", {"targets": targets, "include_candidates": True}, label="context_before")
            resolved = await call("stl_resolve_entities", {"queries": book["entity_queries"], "limit": 6})
            if not any(row.get("scholar_profile_id") == book["scholar_id"] for query in resolved["queries"] for row in query["results"]):
                raise RuntimeError("Expected author identity was not found; do not create a duplicate or count resolution complete")
            evidence = await call("stl_read_sources", {"requests": [{"edition_id": book["edition_id"], "pages": book["pages"], "limit": 8,
                                                                      "document_revision_id": book["document_revision_id"]}]})
            source = next((row for row in evidence["requests"][0]["results"] if row["span_id"] == book["span_id"]), None)
            if source is None or not source["valid_locator"]:
                raise RuntimeError("Reviewed exact source is no longer current; no substitute is permitted")
            operations = []
            for kind, identifier, position in [("scholar", book["scholar_id"], 2), ("topic", book["topic_id"], 4)]:
                current = before["results"][position]
                allowed = {"id", "source_type", "source_id", "group_title", "reason", "order"}
                items = [{key: value for key, value in row.items() if key in allowed} for row in current["items"]]
                if any(item["source_type"] == "span" and item["source_id"] == book["span_id"] for item in items):
                    raise RuntimeError("This exact maintenance increment already exists; query its original plan instead of creating another")
                items.append({"source_type": "span", "source_id": book["span_id"], "group_title": book["group_title"], "reason": book["reason"], "order": len(items)})
                operations.append({"key": kind + "_evidence", "kind": "evidence_curation", "work_id": book["work_id"],
                                   "target_type": kind, "target_id": identifier, "expected_version": current["edit_version"], "data": {"items": items}})
            prepared = await call("stl_prepare_changes", {"operations": operations, "requirements": book["requirements"]})
            plan = {"plan_id": prepared["plan_id"], "plan_digest": prepared["plan_digest"]}
            write(directory / f"{book['key']}-plan.json", plan)
            saved = await call("stl_save_drafts", plan)
            status = await call("stl_get_operation_status", {"plan_id": plan["plan_id"]})
            assert status["all_saved"] and not saved["published"]
            after = await call("stl_get_curation_context", {"targets": targets, "include_candidates": False}, label="context_after")
            await call("stl_get_operation_status", {"work_ids": [book["work_id"]]}, label="background_after")
            # Complete existing book content and editorial parents must match;
            # only the explicitly prepared EvidenceCuration drafts may change.
            for position in [0, 1, 3]:
                assert digest(before["results"][position]["data"]) == digest(after["results"][position]["data"])
            assert before["results"][0]["field_locks"] == after["results"][0]["field_locks"]
            for position in [2, 4]:
                assert len(after["results"][position]["items"]) == len(before["results"][position]["items"]) + 1
            report["books"].append({"key": book["key"], "title": book["title"], "pages": book["page_count"],
                "execution_seconds": round(time.monotonic() - started, 3), "timings": timings, "tool_calls": len(timings),
                "draft_operations": len(operations), "plan": plan, "existing_content_unchanged": True,
                "requirements": book["requirements"], "source_pdf_page": source["page"], "printed_label": source["printed_label"]})
            write(directory / "report.json", report)

    # A new MCP and SSH process must retrieve the original receipts and replay
    # the same requests, not create fresh revisions.
    restart_started = time.monotonic()
    async with Client(parameters, read_timeout_seconds=120) as client:
        for book in report["books"]:
            status = (await client.call_tool("stl_get_operation_status", {"plan_id": book["plan"]["plan_id"]})).structured_content
            assert status["ok"] and status["all_saved"]
            replay = (await client.call_tool("stl_save_drafts", book["plan"])).structured_content
            assert replay["ok"] and all(row["replayed"] for row in replay["results"])
            book["restart_receipts_verified"] = True
            book["retry_all_replayed"] = True
    report["restart_verification_seconds"] = round(time.monotonic() - restart_started, 3)
    report["finished_at_epoch"] = time.time()
    report["wall_seconds"] = round(report["finished_at_epoch"] - report["started_at_epoch"], 3)
    write(directory / "report.json", report)
    print(json.dumps({"ok": True, "scenario": report["scenario"], "wall_seconds": report["wall_seconds"],
                      "books": [{key: row[key] for key in ("title", "execution_seconds", "tool_calls", "draft_operations", "existing_content_unchanged", "retry_all_replayed")} for row in report["books"]]}, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1]))
