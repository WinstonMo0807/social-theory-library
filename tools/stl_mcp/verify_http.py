"""Authenticated HTTP MCP probe; no library writes or credential output.

Use --url through an SSH forward before exposing the service, then repeat on
the real HTTPS endpoint. Windows DPAPI supplies credentials only in memory.
"""
import argparse
import asyncio
import json
import os
from pathlib import Path
import sys
import time

import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

async def main(url, output, token_stdin=False):
    started = time.monotonic()
    if token_stdin:
        token = sys.stdin.readline().strip()
    else:
        from credentials import read_token
        token = read_token()
    headers = {"Authorization": "Bearer " + token, "Host": "books.winstonmo.com"}
    async with httpx2.AsyncClient(timeout=120, follow_redirects=False) as http:
        for extra, expected in (({}, 401), ({"Authorization": "Bearer invalid-test-token-0000000000"}, 401),
                                ({**headers, "Origin": "https://untrusted.example"}, 403)):
            response = await http.post(url, headers=extra, json={})
            assert response.status_code == expected, (response.status_code, expected)
    config_path = os.environ.get("STL_MCP_CONFIG")
    config = json.loads((Path(config_path) if config_path else Path(__file__).resolve().parents[2] / ".local/stl-mcp/config.json").read_text())
    results = []
    for mode in ("auto", "legacy"):
        async with httpx2.AsyncClient(headers=headers, timeout=120) as http:
            async with Client(streamable_http_client(url, http_client=http), mode=mode, read_timeout_seconds=120) as client:
                tools = await client.list_tools()
                names = sorted(tool.name for tool in tools.tools)
                assert len(names) == 7 and "stl_save_drafts" in names
                result = await client.call_tool("stl_search_catalog", {"queries": ["经济与社会", "国家的视角", "定县社会概况调查"], "limit": 3})
                data = result.structured_content
                assert not result.is_error and data and data["ok"], data
                assert all(row["results"] for row in data["queries"])
                result = await client.call_tool("stl_get_curation_context", {"targets": [{"type": "work", "id": key} for key in config["allowed_work_ids"]]})
                assert not result.is_error and result.structured_content["ok"], result.structured_content
                results.append({"mode": mode, "tool_count": len(names), "books": 3, "context_ok": True})
    report = {"url": url, "authentication_checks": 3, "protocols": results,
              "library_writes": 0, "elapsed_seconds": round(time.monotonic() - started, 3)}
    if output:
        Path(output).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="https://books.winstonmo.com/mcp")
    parser.add_argument("--output")
    parser.add_argument("--token-stdin", action="store_true", help="Trusted SSH pipe only; never pass a token in argv")
    args = parser.parse_args()
    asyncio.run(main(args.url, args.output, args.token_stdin))
