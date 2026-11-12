"""Send PDF bytes outside model context using the existing protected MCP origin.

Example: python upload_client.py book.pdf --ocr skip
Resume:  python upload_client.py --resume <request UUID>
Credentials come from STL_MCP_TOKEN or the Windows DPAPI helper, never argv.
"""
import argparse
import asyncio
import json
import os
from pathlib import Path
import sys
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

from credentials import read_token

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / ".local/stl-mcp/upload-clients"


def file_spec(path):
    path = Path(path).resolve()
    return {"path": str(path), "name": path.name, "size": path.stat().st_size}


def load_state(args):
    STATE.mkdir(parents=True, exist_ok=True)
    request_id = str(UUID(args.resume or args.request_id)) if args.resume or args.request_id else str(uuid4())
    path = STATE / f"{request_id}.json"
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
    else:
        if args.resume:
            raise ValueError("此电脑没有该上传记录，请核对原请求编号。")
        policy = {}
        for name, value in (("access_policy", args.access), ("ocr_strategy", args.ocr), ("duplicate_policy", args.duplicates)):
            if value is not None:
                policy[name] = value
        data = {"request_id": request_id, "files": [file_spec(name) for name in args.files], "policy": policy}
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        if os.name != "nt":
            path.chmod(0o600)
    return path, data


def upload_url(endpoint, relative):
    origin = urlsplit(endpoint)
    if origin.scheme != "https" or origin.hostname != "books.winstonmo.com" or origin.username or origin.password:
        raise ValueError("凭据只能发送到已配置的书库HTTPS域名。")
    if origin.port not in {None, 443} or origin.path != "/mcp" or origin.query or origin.fragment:
        raise ValueError("需要标准HTTPS MCP入口。")
    if not relative.startswith("/mcp/uploads/") or any(c in relative for c in ("?", "#", "\\", ".")):
        raise ValueError("服务端返回了非上传路径。")
    return f"{origin.scheme}://{origin.netloc}{relative}"


async def transfer(http, endpoint, state, prepared):
    completed = []
    for local, remote in zip(state["files"], prepared["files"], strict=True):
        url = upload_url(endpoint, remote["upload_path"])
        response = await http.get(url)
        response.raise_for_status()
        current = response.json()
        if not current.get("ok"):
            raise ValueError("无法读取原分片状态。")
        if not current["transfer_complete"]:
            chunk_bytes = prepared["chunk_bytes"]
            received = set(current["received_indices"])
            total = (local["size"] + chunk_bytes - 1) // chunk_bytes
            with Path(local["path"]).open("rb") as source:
                for index in range(total):
                    if index in received:
                        continue
                    source.seek(index * chunk_bytes)
                    content = source.read(chunk_bytes)
                    for attempt in range(4):
                        try:
                            response = await http.put(url + f"/{index}", content=content,
                                                      headers={"Content-Type": "application/octet-stream"})
                            if response.status_code in {429, 502, 503, 504} and attempt < 3:
                                await asyncio.sleep(2 ** attempt)
                                continue
                            response.raise_for_status()
                            current = response.json()
                            if not current.get("ok"):
                                raise ValueError("分片未被接收，保留原请求编号续传。")
                            break
                        except httpx2.TransportError:
                            if attempt == 3:
                                raise
                            await asyncio.sleep(2 ** attempt)
        completed.append({"name": local["name"], **current})
    return completed


async def run(args):
    # Validate the origin before starting any credential-bearing request.
    upload_url(args.endpoint, "/mcp/uploads/")
    path, state = load_state(args)
    print(json.dumps({"request_id": state["request_id"], "files": len(state["files"]), "resume_record": str(path)}, ensure_ascii=False), flush=True)
    async with httpx2.AsyncClient(headers={"Authorization": "Bearer " + read_token()}, timeout=180,
                                  follow_redirects=False) as http:
        async with Client(streamable_http_client(args.endpoint, http_client=http), mode="legacy", read_timeout_seconds=180) as client:
            result = await client.call_tool("stl_prepare_uploads", {
                "request_id": state["request_id"], "files": [{k: row[k] for k in ("name", "size")} for row in state["files"]],
                "policy": state["policy"]})
            prepared = result.structured_content
            if result.is_error or not prepared or not prepared.get("ok"):
                raise ValueError(str(prepared))
            rows = await transfer(http, args.endpoint, state, prepared)
            result = await client.call_tool("stl_get_ingestion_status", {"request_id": state["request_id"]})
            if result.is_error or not result.structured_content or not result.structured_content.get("ok"):
                raise ValueError("上传后回执查询失败，请用原请求编号续查。")
    report = {"request_id": state["request_id"], "batch_id": prepared["batch_id"], "files": rows,
              "ingestion": result.structured_content, "published_by_this_client": False}
    path.with_suffix(".receipt.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("files", nargs="*")
    parser.add_argument("--request-id")
    parser.add_argument("--resume")
    parser.add_argument("--access", help="网站访问策略，不填沿用网站默认")
    parser.add_argument("--ocr", help="网站OCR策略，不填沿用网站默认")
    parser.add_argument("--duplicates", help="网站重复处理策略，不填沿用网站默认")
    parser.add_argument("--endpoint", default="https://books.winstonmo.com/mcp")
    try:
        asyncio.run(run(parser.parse_args()))
    except Exception as error:
        print("上传未完成：" + str(error)[:1200] + "；本机记录已保留，请用--resume原请求编号续传。", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
