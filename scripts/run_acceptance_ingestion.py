"""Upload, review, and publish the four-document acceptance corpus via HTTP."""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx


TERMINAL_STATES = {"needs_review", "ready", "published", "failed", "withdrawn"}


class ApiError(RuntimeError):
    pass


def request_json(
    client: httpx.Client,
    method: str,
    path: str,
    *,
    token: str | None = None,
    **kwargs: Any,
) -> Any:
    headers = dict(kwargs.pop("headers", {}))
    if token:
        headers["Authorization"] = f"Bearer {token}"
    response = client.request(method, path, headers=headers, **kwargs)
    try:
        payload = response.json()
    except ValueError:
        payload = {"body": response.text[:2000]}
    if response.is_error:
        raise ApiError(f"{method} {path} 返回 {response.status_code}: {payload}")
    return payload


def save_report(path: Path, report: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def wait_for_terminal(
    client: httpx.Client,
    token: str,
    item_id: str,
    timeout_seconds: int = 900,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        item = request_json(
            client,
            "GET",
            f"/api/ingestion/items/{item_id}/",
            token=token,
        )
        if item["status"] in TERMINAL_STATES:
            return item
        time.sleep(1)
    raise TimeoutError(f"上传记录 {item_id} 在 {timeout_seconds} 秒内没有完成处理。")


def review_payload(
    expected: dict[str, Any],
    automatic_item: dict[str, Any],
) -> dict[str, Any]:
    current = automatic_item.get("review_data") or {}
    fields = {
        "title": expected["title"],
        "subtitle": "",
        "document_type": expected["document_type"],
        "language": expected["language"],
        "version_label": "书库验收样本",
        "publication_year": expected["publication_year"],
        "publisher": expected.get("publisher", ""),
        "publication_place": expected.get("publication_place", ""),
        "journal_title": expected.get("journal_title", ""),
        "volume": expected.get("volume", ""),
        "issue": expected.get("issue", ""),
        "page_range": expected.get("page_range", ""),
        "degree_institution": "",
        "degree_type": "",
        "report_institution": "",
        "isbn": expected.get("isbn", ""),
        "doi": expected.get("doi", ""),
        "abstract": current.get("abstract", ""),
        "authors": expected["authors"],
        "theory_schools": expected["theory_schools"],
        "topics": expected["topics"],
        "lock_fields": [
            "title",
            "document_type",
            "language",
            "publication_year",
            "publisher",
            "publication_place",
            "journal_title",
            "volume",
            "issue",
            "page_range",
            "doi",
            "authors",
            "theory_schools",
            "topics",
        ],
        "retry_publication": False,
    }
    return fields


def run(
    api_base: str,
    corpus: Path,
    admin_email: str,
    password: str,
    report_path: Path,
) -> dict[str, Any]:
    manifest = json.loads((corpus / "manifest.json").read_text(encoding="utf-8"))
    report: dict[str, Any] = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "api_base": api_base,
        "corpus": str(corpus),
        "batch_id": None,
        "baseline_dashboard": None,
        "final_dashboard": None,
        "records": [],
        "errors": [],
    }

    with httpx.Client(base_url=api_base, timeout=httpx.Timeout(900)) as client:
        login = request_json(
            client,
            "POST",
            "/api/auth/login/",
            json={"email": admin_email, "password": password},
        )
        token = login["access"]
        report["admin"] = {
            "email": login["user"]["email"],
            "display_name": login["user"]["display_name"],
            "role": login["user"]["role"],
        }
        report["baseline_dashboard"] = request_json(
            client,
            "GET",
            "/api/ingestion/dashboard/",
            token=token,
        )
        batch = request_json(
            client,
            "POST",
            "/api/ingestion/batches/create/",
            token=token,
            json={
                "expected_count": len(manifest["records"]),
                "notes": "2026-07-28 四份真实开放文献随机文件名联动验收",
            },
        )
        report["batch_id"] = batch["id"]
        save_report(report_path, report)

        for index, source_record in enumerate(manifest["records"], start=1):
            record: dict[str, Any] = {
                "record_id": source_record["record_id"],
                "opaque_filename": source_record["opaque_filename"],
                "expected": source_record["expected"],
                "upload_response": None,
                "automatic_snapshot": None,
                "review_response": None,
                "publish_response": None,
                "final_item": None,
            }
            report["records"].append(record)
            save_report(report_path, report)
            pdf_path = corpus / source_record["opaque_filename"]
            with pdf_path.open("rb") as stream:
                upload = request_json(
                    client,
                    "POST",
                    f"/api/ingestion/batches/{batch['id']}/items/",
                    token=token,
                    data={
                        "client_token": f"acceptance-{index}-{source_record['record_id']}",
                    },
                    files={
                        "file": (
                            source_record["opaque_filename"],
                            stream,
                            "application/pdf",
                        )
                    },
                )
            record["upload_response"] = upload
            item_id = upload["item"]["id"]
            automatic = wait_for_terminal(client, token, item_id)
            record["automatic_snapshot"] = automatic
            save_report(report_path, report)
            if automatic["status"] == "failed":
                raise ApiError(
                    f"{source_record['record_id']} 入库失败: "
                    f"{automatic.get('error_code')} {automatic.get('error_message')}"
                )

            reviewed = request_json(
                client,
                "PUT",
                f"/api/ingestion/items/{item_id}/review/",
                token=token,
                json=review_payload(source_record["expected"], automatic),
            )
            record["review_response"] = reviewed
            published = request_json(
                client,
                "POST",
                f"/api/ingestion/items/{item_id}/publish/",
                token=token,
                json={},
            )
            record["publish_response"] = published
            record["final_item"] = request_json(
                client,
                "GET",
                f"/api/ingestion/items/{item_id}/",
                token=token,
            )
            save_report(report_path, report)

        report["final_dashboard"] = request_json(
            client,
            "GET",
            "/api/ingestion/dashboard/",
            token=token,
        )
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        save_report(report_path, report)
        return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-base", default="http://127.0.0.1:8001")
    parser.add_argument(
        "--corpus",
        type=Path,
        default=Path(
            "data/literature_runs/library_acceptance_20260728/acceptance_corpus"
        ),
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=Path(
            "data/literature_runs/library_acceptance_20260728/ingestion_run.json"
        ),
    )
    parser.add_argument(
        "--admin-email",
        default="acceptance-admin@local.test",
    )
    args = parser.parse_args()
    password = os.getenv("ACCEPTANCE_ADMIN_PASSWORD", "")
    if not password:
        raise SystemExit("请通过 ACCEPTANCE_ADMIN_PASSWORD 提供本地验收管理员密码。")
    args.report.parent.mkdir(parents=True, exist_ok=True)
    if args.report.exists():
        raise SystemExit(f"{args.report} 已存在。为保留证据，本脚本不会覆盖它。")
    try:
        report = run(
            args.api_base,
            args.corpus.resolve(),
            args.admin_email,
            password,
            args.report.resolve(),
        )
    except Exception as exc:
        if args.report.exists():
            report = json.loads(args.report.read_text(encoding="utf-8"))
            report.setdefault("errors", []).append(
                {
                    "at": datetime.now(timezone.utc).isoformat(),
                    "type": exc.__class__.__name__,
                    "detail": str(exc),
                }
            )
            save_report(args.report, report)
        raise
    print(
        json.dumps(
            {
                "report": str(args.report.resolve()),
                "batch_id": report["batch_id"],
                "published": sum(
                    row["final_item"]["status"] == "published"
                    for row in report["records"]
                ),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
