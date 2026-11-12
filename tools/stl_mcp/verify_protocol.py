"""Real stdio MCP handshake and read probe, with no library mutation."""
import asyncio
import json
from pathlib import Path
import sys
import time

from mcp import Client, StdioServerParameters


async def main():
    parameters = StdioServerParameters(command=sys.executable, args=["-X", "utf8", str(Path(__file__).with_name("server.py"))])
    for mode in ("auto", "legacy"):
        started = time.monotonic()
        async with Client(parameters, mode=mode, read_timeout_seconds=120) as client:
            tools = await client.list_tools()
            names = sorted(tool.name for tool in tools.tools)
            assert len(names) == 9 and "stl_save_drafts" in names and "stl_prepare_uploads" in names
            result = await client.call_tool("stl_search_catalog", {"queries": ["经济与社会"], "limit": 3})
            data = result.structured_content
            assert not result.is_error and data and data["ok"], data
            print(json.dumps({"ok": True, "mode": mode, "tools": names, "matching_works": len(data["queries"][0]["results"]),
                              "elapsed_seconds": round(time.monotonic() - started, 3)}, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
