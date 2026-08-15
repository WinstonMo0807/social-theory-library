"""Verify public, reader, and admin linkage for the four-document corpus."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx


PROBES = {
    "book_veblen_1899": "pecuniary emulation",
    "book_cooley_1902": "separate individual",
    "article_patel_2023": "anti-colonial social theory",
    "article_vrooman_2024": "person capital",
}


class Verification:
    def __init__(self) -> None:
        self.checks: list[dict[str, Any]] = []

    def check(self, name: str, condition: bool, evidence: Any = None) -> None:
        self.checks.append(
            {
                "name": name,
                "passed": bool(condition),
                "evidence": evidence,
            }
        )

    @property
    def failures(self) -> list[dict[str, Any]]:
        return [row for row in self.checks if not row["passed"]]


def api_json(
    client: httpx.Client,
    method: str,
    path: str,
    *,
    token: str | None = None,
    expected_status: int = 200,
    **kwargs: Any,
) -> Any:
    headers = dict(kwargs.pop("headers", {}))
    if token:
        headers["Authorization"] = f"Bearer {token}"
    response = client.request(method, path, headers=headers, **kwargs)
    try:
        payload = response.json()
    except ValueError:
        payload = {"body": response.text[:1000]}
    if response.status_code != expected_status:
        raise RuntimeError(
            f"{method} {path} 预期 {expected_status}，实际 {response.status_code}: {payload}"
        )
    return payload


def save(path: Path, report: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def results(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return payload.get("results", [])


def locate_by_name(rows: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
    return next((row for row in rows if row.get("name") == name), None)


def verify(
    api_base: str,
    web_base: str,
    ingestion_report_path: Path,
    admin_email: str,
    admin_password: str,
    reader_email: str,
    reader_password: str,
) -> dict[str, Any]:
    ingestion = json.loads(ingestion_report_path.read_text(encoding="utf-8"))
    verification = Verification()
    report: dict[str, Any] = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "api_base": api_base,
        "web_base": web_base,
        "checks": verification.checks,
        "documents": [],
        "reader": {},
        "withdrawal_restore": {},
    }

    with httpx.Client(base_url=api_base, timeout=httpx.Timeout(120)) as client:
        admin_login = api_json(
            client,
            "POST",
            "/api/auth/login/",
            json={"email": admin_email, "password": admin_password},
        )
        admin_token = admin_login["access"]
        dashboard = api_json(
            client,
            "GET",
            "/api/ingestion/dashboard/",
            token=admin_token,
        )
        verification.check(
            "后台文献总数为 4",
            dashboard["documents"]["total"] == 4,
            dashboard["documents"],
        )
        verification.check(
            "后台已发布文献为 4",
            dashboard["documents"]["published"] == 4,
            dashboard["documents"],
        )
        verification.check(
            "后台规范 PDF 数为 4",
            dashboard["pdf_assets"] == 4,
            dashboard["pdf_assets"],
        )
        verification.check(
            "复核队列已经清空",
            dashboard["needs_review"] == 0,
            dashboard["needs_review"],
        )

        work_list = api_json(client, "GET", "/api/catalog/works/")
        theory_list = api_json(client, "GET", "/api/catalog/theory-schools/")
        topic_list = api_json(client, "GET", "/api/catalog/topics/")
        scholar_list = api_json(client, "GET", "/api/catalog/scholars/")
        verification.check(
            "公开作品列表只有四份验收文献",
            len(results(work_list)) == 4,
            [row["title"] for row in results(work_list)],
        )
        verification.check(
            "公开流派没有未确认空对象",
            len(results(theory_list)) == 4
            and all(row["work_count"] >= 1 for row in results(theory_list)),
            [(row["name"], row["work_count"]) for row in results(theory_list)],
        )
        verification.check(
            "公开主题没有未确认空对象",
            len(results(topic_list)) == 4
            and all(row["work_count"] >= 1 for row in results(topic_list)),
            [(row["name"], row["work_count"]) for row in results(topic_list)],
        )
        verification.check(
            "六位作者均生成公开学者页",
            len(results(scholar_list)) == 6,
            [row["person"]["preferred_name"] for row in results(scholar_list)],
        )

        for source_record in ingestion["records"]:
            expected = source_record["expected"]
            item_id = source_record["final_item"]["id"]
            item = api_json(
                client,
                "GET",
                f"/api/ingestion/items/{item_id}/",
                token=admin_token,
            )
            slug = item["review_data"]["public_slug"]
            asset_id = item["review_data"]["normalized_asset_id"]
            edition_id = item["edition"]
            work_detail = api_json(
                client,
                "GET",
                f"/api/catalog/works/{quote(slug)}/",
            )
            title_search = api_json(
                client,
                "GET",
                "/api/catalog/search/",
                params={"q": expected["title"]},
            )
            probe = PROBES[source_record["record_id"]]
            fulltext = api_json(
                client,
                "GET",
                "/api/catalog/search/",
                params={"q": probe},
            )
            hit = next(
                (
                    row
                    for row in fulltext["passages"]
                    if row["asset_id"] == asset_id
                ),
                None,
            )
            document_search = api_json(
                client,
                "GET",
                f"/api/catalog/assets/{asset_id}/search/",
                params={"q": probe},
            )
            manifest = api_json(
                client,
                "GET",
                f"/api/catalog/assets/{asset_id}/manifest/",
            )
            access = api_json(
                client,
                "GET",
                f"/api/distribution/assets/{asset_id}/access/",
            )
            pdf = httpx.get(access["url"], timeout=120)
            citation = api_json(
                client,
                "GET",
                f"/api/catalog/editions/{edition_id}/citations/",
                params={"page": str((hit or {}).get("page_index", 1))},
            )

            verification.check(
                f"{expected['title']} 后台文件名仍为随机原名",
                item["source_filename"] == source_record["opaque_filename"],
                item["source_filename"],
            )
            verification.check(
                f"{expected['title']} 最终书目准确",
                item["title"] == expected["title"]
                and item["status"] == "published",
                {"title": item["title"], "status": item["status"]},
            )
            verification.check(
                f"{expected['title']} 详情页可访问",
                work_detail["title"] == expected["title"],
                slug,
            )
            verification.check(
                f"{expected['title']} 题名检索命中",
                title_search["counts"]["works"] >= 1
                and any(row["title"] == expected["title"] for row in title_search["works"]),
                title_search["counts"],
            )
            verification.check(
                f"{expected['title']} 全文检索命中具体页",
                hit is not None
                and hit["page_index"] >= 1
                and bool(hit["bbox"]),
                hit,
            )
            verification.check(
                f"{expected['title']} 文档内搜索返回高亮坐标",
                bool(document_search["matches"])
                and any(match["blocks"] for match in document_search["matches"]),
                {
                    "query": probe,
                    "pages": [row["page_index"] for row in document_search["matches"][:8]],
                },
            )
            verification.check(
                f"{expected['title']} 阅读器清单与关系一致",
                manifest["work"]["title"] == expected["title"]
                and {row["name"] for row in manifest["related_theories"]}
                == set(expected["theory_schools"])
                and {row["name"] for row in manifest["related_topics"]}
                == set(expected["topics"]),
                {
                    "theories": manifest["related_theories"],
                    "topics": manifest["related_topics"],
                },
            )
            verification.check(
                f"{expected['title']} 访客可取得 PDF",
                pdf.status_code == 200 and pdf.content.startswith(b"%PDF-"),
                {
                    "status": pdf.status_code,
                    "bytes": len(pdf.content),
                    "source": access["source"],
                    "download_filename": access["download_filename"],
                },
            )
            verification.check(
                f"{expected['title']} 下载名已经规范化",
                access["download_filename"] != source_record["opaque_filename"]
                and expected["title"].split(":")[0] in access["download_filename"],
                access["download_filename"],
            )
            verification.check(
                f"{expected['title']} GB/T 7714—2025 引用使用真实数据",
                expected["title"] in citation["gbt7714-2025"]
                and expected["authors"][0] in citation["gbt7714-2025"]
                and (
                    not expected.get("doi")
                    or expected["doi"] in citation["gbt7714-2025"]
                ),
                citation["gbt7714-2025"],
            )

            for author in expected["authors"]:
                author_search = api_json(
                    client,
                    "GET",
                    "/api/catalog/search/",
                    params={"q": author},
                )
                profile = next(
                    (
                        row
                        for row in results(scholar_list)
                        if row["person"]["preferred_name"] == author
                    ),
                    None,
                )
                scholar_detail = (
                    api_json(
                        client,
                        "GET",
                        f"/api/catalog/scholars/{quote(profile['slug'])}/",
                    )
                    if profile
                    else None
                )
                verification.check(
                    f"{author} 搜索命中学者和作品",
                    author_search["counts"]["scholars"] >= 1
                    and author_search["counts"]["works"] >= 1,
                    author_search["counts"],
                )
                verification.check(
                    f"{author} 学者页显示馆藏作品",
                    bool(scholar_detail)
                    and any(
                        row["title"] == expected["title"]
                        for row in scholar_detail["works"]
                    ),
                    profile,
                )

            if "Mérove Gijsberts" in expected["authors"]:
                transliterated = api_json(
                    client,
                    "GET",
                    "/api/catalog/search/",
                    params={"q": "Merove Gijsberts"},
                )
                verification.check(
                    "外文姓名去音符检索命中",
                    transliterated["counts"]["scholars"] >= 1,
                    transliterated["counts"],
                )

            for theory_name in expected["theory_schools"]:
                theory = locate_by_name(results(theory_list), theory_name)
                detail = (
                    api_json(
                        client,
                        "GET",
                        f"/api/catalog/theory-schools/{quote(theory['slug'])}/",
                    )
                    if theory
                    else None
                )
                verification.check(
                    f"{theory_name} 流派页联动作品和学者",
                    bool(detail)
                    and any(row["title"] == expected["title"] for row in detail["works"])
                    and bool(detail["scholars"]),
                    theory,
                )

            for topic_name in expected["topics"]:
                topic = locate_by_name(results(topic_list), topic_name)
                detail = (
                    api_json(
                        client,
                        "GET",
                        f"/api/catalog/topics/{quote(topic['slug'])}/",
                    )
                    if topic
                    else None
                )
                verification.check(
                    f"{topic_name} 主题页联动作品、学者和全文",
                    bool(detail)
                    and any(row["title"] == expected["title"] for row in detail["works"])
                    and bool(detail["scholars"])
                    and bool(detail["passages"]),
                    topic,
                )

            report["documents"].append(
                {
                    "record_id": source_record["record_id"],
                    "title": expected["title"],
                    "item_id": item_id,
                    "work_id": work_detail["id"],
                    "edition_id": edition_id,
                    "asset_id": asset_id,
                    "slug": slug,
                    "page_count": manifest["page_count"],
                    "fulltext_query": probe,
                    "fulltext_page": (hit or {}).get("page_index"),
                    "reader_url": (
                        f"{web_base}/reader/{asset_id}?"
                        f"page={(hit or {}).get('page_index', 1)}&q={quote(probe)}"
                    ),
                }
            )

        clean_copy = api_json(
            client,
            "POST",
            "/api/catalog/clean-copy/",
            json={"text": "A hyphen-\nated line.\nThe next sentence.\n\nSecond paragraph。"},
        )
        verification.check(
            "访客干净复制会合并断词和普通换行",
            clean_copy["text"].startswith("A hyphenated line.")
            and "hyphen-\nated" not in clean_copy["text"],
            clean_copy,
        )

        guest_progress = client.get("/api/reading/progress/")
        verification.check(
            "访客不能读取私人阅读资料",
            guest_progress.status_code == 401,
            guest_progress.status_code,
        )

        register = client.post(
            "/api/auth/register/",
            json={
                "email": reader_email,
                "display_name": "联动验收读者",
                "password": reader_password,
            },
        )
        verification.check(
            "读者注册接口可用",
            register.status_code in {201, 400},
            {"status": register.status_code, "body": register.json()},
        )
        reader_login = api_json(
            client,
            "POST",
            "/api/auth/login/",
            json={"email": reader_email, "password": reader_password},
        )
        reader_token = reader_login["access"]
        first_doc = report["documents"][0]
        page = api_json(
            client,
            "GET",
            f"/api/catalog/assets/{first_doc['asset_id']}/pages/{first_doc['fulltext_page']}/",
        )
        progress = api_json(
            client,
            "POST",
            "/api/reading/progress/",
            token=reader_token,
            expected_status=201,
            json={
                "asset": first_doc["asset_id"],
                "current_page": first_doc["fulltext_page"],
                "progress_ratio": 0.25,
                "last_position": {"source": "acceptance"},
            },
        )
        annotation = api_json(
            client,
            "POST",
            "/api/reading/annotations/",
            token=reader_token,
            expected_status=201,
            json={
                "asset": first_doc["asset_id"],
                "page": page["page_id"],
                "kind": "highlight",
                "selector": {
                    "type": "TextQuoteSelector",
                    "exact": PROBES["book_veblen_1899"],
                },
                "quote": PROBES["book_veblen_1899"],
                "body": "这是一条只向当前读者返回的验收笔记。",
                "color": "yellow",
            },
        )
        bookmark = api_json(
            client,
            "POST",
            "/api/reading/bookmarks/",
            token=reader_token,
            expected_status=201,
            json={
                "asset": first_doc["asset_id"],
                "page": page["page_id"],
                "label": "验收书签",
            },
        )
        saved = api_json(
            client,
            "POST",
            "/api/reading/saved/",
            token=reader_token,
            expected_status=201,
            json={"work": first_doc["work_id"]},
        )
        reading_list = api_json(
            client,
            "POST",
            "/api/reading/lists/",
            token=reader_token,
            expected_status=201,
            json={
                "title": "联动验收书单",
                "description": "验证作品与读者书单关系",
                "is_default": False,
            },
        )
        list_item = api_json(
            client,
            "POST",
            f"/api/reading/lists/{reading_list['id']}/add_item/",
            token=reader_token,
            expected_status=201,
            json={"work": first_doc["work_id"], "order": 0},
        )
        history = api_json(
            client,
            "POST",
            "/api/reading/history/",
            token=reader_token,
            expected_status=201,
            json={
                "asset": first_doc["asset_id"],
                "page_index": first_doc["fulltext_page"],
                "session_seconds": 180,
            },
        )
        exported = api_json(
            client,
            "GET",
            "/api/reading/export/",
            token=reader_token,
        )
        verification.check(
            "登录后进度、批注、书签、收藏、书单和历史均可保存并导出",
            progress["current_page"] == first_doc["fulltext_page"]
            and annotation["body_text"] == "这是一条只向当前读者返回的验收笔记。"
            and bookmark["label"] == "验收书签"
            and saved["title"] == first_doc["title"]
            and list_item["title"] == first_doc["title"]
            and history["session_seconds"] == 180
            and len(exported["progress"]) >= 1
            and len(exported["annotations"]) >= 1
            and len(exported["bookmarks"]) >= 1
            and len(exported["saved_items"]) >= 1
            and len(exported["reading_lists"]) >= 1
            and len(exported["reading_history"]) >= 1,
            {
                "progress": len(exported["progress"]),
                "annotations": len(exported["annotations"]),
                "bookmarks": len(exported["bookmarks"]),
                "saved": len(exported["saved_items"]),
                "lists": len(exported["reading_lists"]),
                "history": len(exported["reading_history"]),
            },
        )
        report["reader"] = {
            "email": reader_email,
            "progress_id": progress["id"],
            "annotation_id": annotation["id"],
            "bookmark_id": bookmark["id"],
            "saved_id": saved["id"],
            "reading_list_id": reading_list["id"],
            "history_id": history["id"],
        }

        withdraw_doc = report["documents"][0]
        withdraw_item = next(
            row
            for row in ingestion["records"]
            if row["record_id"] == "book_veblen_1899"
        )["final_item"]["id"]
        withdrawn = False
        try:
            api_json(
                client,
                "POST",
                f"/api/ingestion/items/{withdraw_item}/withdraw/",
                token=admin_token,
                json={"reason": "真实验收中的临时下架测试"},
            )
            withdrawn = True
            hidden_search = api_json(
                client,
                "GET",
                "/api/catalog/search/",
                params={"q": withdraw_doc["title"]},
            )
            hidden_work = client.get(
                f"/api/catalog/works/{quote(withdraw_doc['slug'])}/"
            )
            hidden_asset = client.get(
                f"/api/distribution/assets/{withdraw_doc['asset_id']}/access/"
            )
            admin_item = api_json(
                client,
                "GET",
                f"/api/ingestion/items/{withdraw_item}/",
                token=admin_token,
            )
            verification.check(
                "下架后前台作品、搜索和 PDF 立即不可用",
                hidden_search["counts"]["works"] == 0
                and hidden_work.status_code == 404
                and hidden_asset.status_code == 404,
                {
                    "search": hidden_search["counts"],
                    "work_status": hidden_work.status_code,
                    "asset_status": hidden_asset.status_code,
                },
            )
            verification.check(
                "下架后后台记录和处理日志仍可查看",
                admin_item["status"] == "withdrawn"
                and len(admin_item["attempts"]) >= 1,
                {
                    "status": admin_item["status"],
                    "attempts": len(admin_item["attempts"]),
                },
            )
        finally:
            if withdrawn:
                api_json(
                    client,
                    "POST",
                    f"/api/ingestion/items/{withdraw_item}/publish/",
                    token=admin_token,
                    json={},
                )
        restored_search = api_json(
            client,
            "GET",
            "/api/catalog/search/",
            params={"q": withdraw_doc["title"]},
        )
        verification.check(
            "临时下架测试后已经恢复公开",
            restored_search["counts"]["works"] == 1,
            restored_search["counts"],
        )
        report["withdrawal_restore"] = {
            "item_id": withdraw_item,
            "title": withdraw_doc["title"],
            "restored": restored_search["counts"]["works"] == 1,
        }

    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    report["summary"] = {
        "total": len(verification.checks),
        "passed": len(verification.checks) - len(verification.failures),
        "failed": len(verification.failures),
        "failures": verification.failures,
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-base", default="http://127.0.0.1:8001")
    parser.add_argument("--web-base", default="http://localhost:3100")
    parser.add_argument(
        "--ingestion-report",
        type=Path,
        default=Path(
            "data/literature_runs/library_acceptance_20260728/ingestion_run.json"
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "data/literature_runs/library_acceptance_20260728/linkage_verification.json"
        ),
    )
    parser.add_argument("--admin-email", default="acceptance-admin@local.test")
    parser.add_argument("--reader-email", default="acceptance-reader@local.test")
    args = parser.parse_args()
    admin_password = os.getenv("ACCEPTANCE_ADMIN_PASSWORD", "")
    reader_password = os.getenv(
        "ACCEPTANCE_READER_PASSWORD",
        "Library-Reader-2026!",
    )
    if not admin_password:
        raise SystemExit("请通过 ACCEPTANCE_ADMIN_PASSWORD 提供管理员密码。")
    if args.output.exists():
        raise SystemExit(f"{args.output} 已存在，本脚本不会覆盖验收证据。")
    try:
        report = verify(
            args.api_base,
            args.web_base,
            args.ingestion_report.resolve(),
            args.admin_email,
            admin_password,
            args.reader_email,
            reader_password,
        )
    except Exception as exc:
        report = {
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "summary": {
                "total": 0,
                "passed": 0,
                "failed": 1,
                "failures": [
                    {
                        "name": exc.__class__.__name__,
                        "passed": False,
                        "evidence": str(exc),
                    }
                ],
            },
        }
        save(args.output, report)
        raise
    save(args.output, report)
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    return 1 if report["summary"]["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
