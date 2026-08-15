#!/usr/bin/env python3
"""Read-only acceptance check for one PDF through public and LAN entry points.

The script never uploads or changes data. It proves that both host names reach
the same account, upload record, catalog record and PDF asset after an admin has
uploaded/reviewed the document through either entry point.
"""

from __future__ import annotations

import argparse
import http.cookiejar
import json
import os
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any


TERMINAL_PUBLIC_STATUS = "published"
REVIEWABLE_STATUSES = {"needs_review", "ready", "published"}


class AcceptanceError(RuntimeError):
    pass


def _api_root(base: str) -> str:
    base = base.strip().rstrip("/")
    if not base:
        raise AcceptanceError("入口地址不能为空。")
    parsed = urllib.parse.urlparse(base)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise AcceptanceError(f"入口地址格式不正确：{base}")
    return base if parsed.path.rstrip("/").endswith("/api") else f"{base}/api"


def _safe_excerpt(value: bytes, limit: int = 500) -> str:
    return value.decode("utf-8", errors="replace")[:limit].replace("\n", " ")


@dataclass
class EntryClient:
    label: str
    base: str
    timeout: float
    insecure_tls: bool = False
    opener: urllib.request.OpenerDirector = field(init=False)
    api: str = field(init=False)

    def __post_init__(self) -> None:
        self.base = self.base.strip().rstrip("/")
        self.api = _api_root(self.base)
        cookie_jar = http.cookiejar.CookieJar()
        handlers: list[Any] = [urllib.request.HTTPCookieProcessor(cookie_jar)]
        if self.insecure_tls:
            context = ssl.create_default_context()
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            handlers.append(urllib.request.HTTPSHandler(context=context))
        self.opener = urllib.request.build_opener(*handlers)

    def request(
        self,
        path_or_url: str,
        *,
        method: str = "GET",
        payload: dict | None = None,
        headers: dict[str, str] | None = None,
        expect_json: bool = True,
    ) -> tuple[int, Any, dict[str, str]]:
        if path_or_url.startswith(("http://", "https://")):
            url = path_or_url
        else:
            url = f"{self.api}/{path_or_url.lstrip('/')}"
        body = None
        request_headers = {
            "Accept": "application/json" if expect_json else "application/pdf,*/*;q=0.8",
            "User-Agent": "social-theory-library-acceptance/2.5.3",
        }
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            request_headers["Content-Type"] = "application/json"
        request_headers.update(headers or {})
        request = urllib.request.Request(url, data=body, headers=request_headers, method=method)
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                raw = response.read()
                status = int(response.status)
                response_headers = {key.lower(): value for key, value in response.headers.items()}
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            detail = _safe_excerpt(raw)
            raise AcceptanceError(f"{self.label} {method} {url} 返回 {exc.code}：{detail}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise AcceptanceError(f"{self.label} 无法访问 {url}：{exc}") from exc
        if not expect_json:
            return status, raw, response_headers
        try:
            return status, json.loads(raw.decode("utf-8")), response_headers
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise AcceptanceError(
                f"{self.label} {url} 没有返回 JSON：{_safe_excerpt(raw)}"
            ) from exc

    def login(self, email: str, password: str) -> dict:
        _status, payload, _headers = self.request(
            "auth/login/",
            method="POST",
            payload={"email": email, "password": password},
        )
        _status, me, _headers = self.request("auth/me/")
        role = str(me.get("role", ""))
        if role not in {"admin", "editor", "reviewer"}:
            raise AcceptanceError(f"{self.label} 登录账户没有书库管理权限：{role or '未知角色'}")
        return {"login": payload.get("session", ""), "user": me}

    def find_item(self, item_id: str, source_filename: str) -> dict:
        if item_id:
            _status, payload, _headers = self.request(f"ingestion/items/{item_id}/")
            return payload
        query = urllib.parse.urlencode(
            {"search": source_filename, "include_deleted": "true", "ordering": "-created_at"}
        )
        _status, payload, _headers = self.request(f"ingestion/items/?{query}")
        rows = payload.get("results", []) if isinstance(payload, dict) else payload
        if not isinstance(rows, list):
            raise AcceptanceError(f"{self.label} 上传记录接口返回格式不正确。")
        exact = [row for row in rows if row.get("source_filename") == source_filename]
        candidates = exact or rows
        if not candidates:
            raise AcceptanceError(f"{self.label} 没有找到上传记录：{source_filename}")
        return candidates[0]


def _item_identity(item: dict) -> dict:
    review = item.get("review_data") or {}
    return {
        "id": str(item.get("id", "")),
        "source_filename": item.get("source_filename", ""),
        "status": item.get("status", ""),
        "progress": item.get("stage_progress", 0),
        "updated_at": item.get("updated_at", ""),
        "edition": str(item.get("edition") or ""),
        "asset": str(item.get("asset") or ""),
        "work_id": str(review.get("work_id") or ""),
        "public_slug": review.get("public_slug") or "",
        "normalized_asset_id": str(review.get("normalized_asset_id") or ""),
        "page_count": int(review.get("page_count") or 0),
        "title": review.get("title") or item.get("title") or "",
    }


def _check(condition: bool, message: str) -> None:
    if not condition:
        raise AcceptanceError(message)


def _verify_publication(client: EntryClient, identity: dict) -> dict:
    slug = identity["public_slug"]
    asset_id = identity["normalized_asset_id"]
    title = identity["title"]
    _check(bool(slug), f"{client.label} 已发布记录缺少公开 slug。")
    _check(bool(asset_id), f"{client.label} 已发布记录缺少规范阅读副本。")

    _status, work, _headers = client.request(f"catalog/works/{urllib.parse.quote(slug)}/")
    work_title = work.get("title") or (work.get("work") or {}).get("title") or ""
    _check(not title or work_title == title, f"{client.label} 公开详情页题名与入库记录不一致。")

    search_query = urllib.parse.urlencode({"q": title, "mode": "exact"})
    _status, search, _headers = client.request(f"catalog/search/?{search_query}")
    serialized_search = json.dumps(search, ensure_ascii=False)
    _check(slug in serialized_search or title in serialized_search, f"{client.label} 全局搜索未返回该文献。")

    _status, manifest, _headers = client.request(f"catalog/assets/{asset_id}/manifest/")
    manifest_pages = int(manifest.get("page_count") or 0)
    _check(manifest_pages > 0, f"{client.label} 阅读器清单没有页数。")
    if identity["page_count"]:
        _check(
            manifest_pages == identity["page_count"],
            f"{client.label} 阅读器页数与后台记录不一致。",
        )

    _status, access, _headers = client.request(f"distribution/assets/{asset_id}/access/")
    _check(bool(access.get("url")), f"{client.label} 未返回 PDF 阅读地址。")
    _check(bool(access.get("supports_range")), f"{client.label} PDF 地址未声明 Range 支持。")
    status, first_bytes, headers = client.request(
        access["url"],
        headers={"Range": "bytes=0-1023"},
        expect_json=False,
    )
    _check(status == 206, f"{client.label} PDF Range 请求应返回 206，实际为 {status}。")
    _check(first_bytes.startswith(b"%PDF-"), f"{client.label} PDF 首段内容不是有效 PDF。")
    _check("content-range" in headers, f"{client.label} PDF Range 响应缺少 Content-Range。")
    return {
        "work_title": work_title,
        "manifest_pages": manifest_pages,
        "asset_source": access.get("source", ""),
        "range_status": status,
        "range_bytes": len(first_bytes),
    }


def verify(args: argparse.Namespace) -> dict:
    password = os.environ.get(args.password_env, "")
    if not password:
        raise AcceptanceError(f"请通过环境变量 {args.password_env} 提供管理员密码。")
    clients = [
        EntryClient("公网", args.public_base, args.timeout, args.insecure_tls),
        EntryClient("内网", args.lan_base, args.timeout, args.insecure_tls),
    ]
    entry_results: dict[str, Any] = {}
    identities: list[dict] = []
    for client in clients:
        _status, health, _headers = client.request("health/")
        _status, ready, _headers = client.request("ready/")
        auth = client.login(args.email, password)
        _status, queue, _headers = client.request("ingestion/queue-health/")
        item = client.find_item(args.item_id, args.source_filename)
        identity = _item_identity(item)
        if args.expect_status:
            _check(
                identity["status"] == args.expect_status,
                f"{client.label} 入库状态应为 {args.expect_status}，实际为 {identity['status']}。",
            )
        _check(identity["status"] in REVIEWABLE_STATUSES, f"{client.label} 该 PDF 尚未进入可复核或已发布状态。")
        _check(identity["edition"], f"{client.label} 该 PDF 尚未建立书目版本。")
        _check(identity["normalized_asset_id"], f"{client.label} 该 PDF 尚未建立规范阅读副本。")
        _check(identity["page_count"] > 0, f"{client.label} 该 PDF 尚未生成页文本。")
        publication = None
        if identity["status"] == TERMINAL_PUBLIC_STATUS:
            publication = _verify_publication(client, identity)
        entry_results[client.label] = {
            "base": client.base,
            "version": health.get("version", ""),
            "ready": ready,
            "authenticated_user": {
                "id": str(auth["user"].get("id", "")),
                "email": auth["user"].get("email", ""),
                "role": auth["user"].get("role", ""),
            },
            "queue": queue,
            "item": identity,
            "publication": publication,
        }
        identities.append(identity)

    public_identity, lan_identity = identities
    for field_name in (
        "id",
        "source_filename",
        "status",
        "progress",
        "updated_at",
        "edition",
        "work_id",
        "public_slug",
        "normalized_asset_id",
        "page_count",
    ):
        _check(
            public_identity[field_name] == lan_identity[field_name],
            f"公网与内网的 {field_name} 不一致。",
        )
    public_user = entry_results["公网"]["authenticated_user"]
    lan_user = entry_results["内网"]["authenticated_user"]
    _check(public_user["id"] == lan_user["id"], "公网与内网没有登录到同一个管理员账户。")
    _check(entry_results["公网"]["version"] == entry_results["内网"]["version"], "公网与内网版本不一致。")
    return {
        "ok": True,
        "message": "同一 PDF 已通过公网与内网一致性核验。",
        "entries": entry_results,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="核验一份 PDF 在公网与内网的入库、策展和阅读状态。")
    parser.add_argument("--public-base", default="https://books.winstonmo.com")
    parser.add_argument("--lan-base", default="http://192.168.5.6:18080")
    parser.add_argument("--email", default=os.environ.get("LIBRARY_ACCEPTANCE_ADMIN_EMAIL", "admin@example.com"))
    selector = parser.add_mutually_exclusive_group(required=True)
    selector.add_argument("--item-id", default="")
    selector.add_argument("--source-filename", default="")
    parser.add_argument("--expect-status", choices=sorted(REVIEWABLE_STATUSES), default="")
    parser.add_argument("--password-env", default="LIBRARY_ACCEPTANCE_ADMIN_PASSWORD")
    parser.add_argument("--timeout", type=float, default=45.0)
    parser.add_argument("--insecure-tls", action="store_true", help="仅用于自签名测试入口。")
    parser.add_argument("--output", default="", help="可选的 JSON 报告路径。")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = verify(args)
    except AcceptanceError as exc:
        print(f"验收失败：{exc}", file=sys.stderr)
        return 1
    rendered = json.dumps(result, ensure_ascii=False, indent=2, default=str)
    if args.output:
        from pathlib import Path

        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
