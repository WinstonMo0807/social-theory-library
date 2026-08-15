"""Prepare a lawful four-document acceptance corpus with opaque PDF filenames.

The two books are complete public-domain Project Gutenberg texts converted to
searchable PDFs. The two journal articles are publisher-hosted CC BY PDFs.
PDF metadata is deliberately cleared for the generated books so the ingestion
pipeline must rely on document content instead of filename or embedded fields.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import secrets
import textwrap
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pymupdf


USER_AGENT = "SocialTheoryLibraryAcceptance/1.0 (+local validation)"
PAGE_RECT = pymupdf.paper_rect("a4")
PAGE_MARGIN = 54
BODY_FONT_SIZE = 10.25
BODY_LINE_HEIGHT = 13.8


@dataclass(frozen=True)
class CorpusItem:
    record_id: str
    source_kind: str
    source_url: str
    landing_page_url: str
    license_label: str
    expected: dict[str, Any]


ITEMS = (
    CorpusItem(
        record_id="book_veblen_1899",
        source_kind="gutenberg_text",
        source_url="https://www.gutenberg.org/cache/epub/833/pg833.txt",
        landing_page_url="https://www.gutenberg.org/ebooks/833",
        license_label="Project Gutenberg public domain in the USA",
        expected={
            "title": "The Theory of the Leisure Class",
            "document_type": "book",
            "language": "en",
            "authors": ["Thorstein Veblen"],
            "publication_year": 1899,
            "publisher": "The Macmillan Company",
            "publication_place": "New York",
            "theory_schools": ["制度主义社会学"],
            "topics": ["炫耀性消费"],
            "search_probe": "The institution of a leisure class is found in its best development",
        },
    ),
    CorpusItem(
        record_id="book_cooley_1902",
        source_kind="gutenberg_text",
        source_url="https://www.gutenberg.org/cache/epub/75145/pg75145.txt",
        landing_page_url="https://www.gutenberg.org/ebooks/75145",
        license_label="Project Gutenberg public domain in the USA",
        expected={
            "title": "Human Nature and the Social Order",
            "document_type": "book",
            "language": "en",
            "authors": ["Charles Horton Cooley"],
            "publication_year": 1902,
            "publisher": "Charles Scribner's Sons",
            "publication_place": "New York",
            "theory_schools": ["符号互动论"],
            "topics": ["自我与社会"],
            "search_probe": "A separate individual is an abstraction unknown to experience",
        },
    ),
    CorpusItem(
        record_id="article_patel_2023",
        source_kind="publisher_pdf",
        source_url=(
            "https://www.frontiersin.org/journals/sociology/articles/"
            "10.3389/fsoc.2023.1143776/pdf"
        ),
        landing_page_url=(
            "https://www.frontiersin.org/journals/sociology/articles/"
            "10.3389/fsoc.2023.1143776/full"
        ),
        license_label="Creative Commons Attribution 4.0 International",
        expected={
            "title": "Anti-colonial thought and global social theory",
            "document_type": "journal_article",
            "language": "en",
            "authors": ["Sujata Patel"],
            "publication_year": 2023,
            "publisher": "Frontiers Media SA",
            "journal_title": "Frontiers in Sociology",
            "volume": "8",
            "issue": "",
            "page_range": "1143776",
            "doi": "10.3389/fsoc.2023.1143776",
            "theory_schools": ["后殖民理论"],
            "topics": ["反殖民思想"],
            "search_probe": "collectively termed anti-colonial social theory",
        },
    ),
    CorpusItem(
        record_id="article_vrooman_2024",
        source_kind="publisher_pdf",
        source_url=(
            "https://journals.plos.org/plosone/article/file?"
            "id=10.1371%2Fjournal.pone.0296443&type=printable"
        ),
        landing_page_url=(
            "https://journals.plos.org/plosone/article?"
            "id=10.1371%2Fjournal.pone.0296443"
        ),
        license_label="Creative Commons Attribution 4.0 International",
        expected={
            "title": "A contemporary class structure: Capital disparities in The Netherlands",
            "document_type": "journal_article",
            "language": "en",
            "authors": ["J. Cok Vrooman", "Jeroen Boelhouwer", "Mérove Gijsberts"],
            "publication_year": 2024,
            "publisher": "Public Library of Science",
            "journal_title": "PLOS ONE",
            "volume": "19",
            "issue": "1",
            "page_range": "e0296443",
            "doi": "10.1371/journal.pone.0296443",
            "theory_schools": ["布迪厄启发的社会学"],
            "topics": ["社会阶级与不平等"],
            "search_probe": "Each social class has a distinctive mix of the four types of capital",
        },
    ),
)


def download_bytes(url: str) -> tuple[bytes, str]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = response.read()
        content_type = response.headers.get_content_type()
    return payload, content_type


def opaque_filename(existing: set[str]) -> str:
    while True:
        candidate = (
            f"{secrets.token_hex(2)}_{secrets.token_hex(3)}-"
            f"{secrets.randbelow(9000) + 1000}_{secrets.token_hex(2)}.pdf"
        )
        if candidate not in existing:
            existing.add(candidate)
            return candidate


def select_font() -> Path | None:
    candidates = (
        Path("C:/Windows/Fonts/georgia.ttf"),
        Path("C:/Windows/Fonts/times.ttf"),
        Path("C:/Windows/Fonts/arial.ttf"),
    )
    return next((path for path in candidates if path.exists()), None)


def visual_lines(text: str) -> list[str]:
    lines: list[str] = []
    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        clean = raw.expandtabs(4).rstrip()
        if not clean:
            if not lines or lines[-1]:
                lines.append("")
            continue
        wrapped = textwrap.wrap(
            clean,
            width=88,
            replace_whitespace=False,
            drop_whitespace=True,
            break_long_words=True,
            break_on_hyphens=False,
        )
        lines.extend(wrapped or [""])
    return lines


def text_to_pdf(text: str, target: Path) -> int:
    font_path = select_font()
    font_name = "AcceptanceBody" if font_path else "Times-Roman"
    max_lines = int((PAGE_RECT.height - 2 * PAGE_MARGIN - 20) // BODY_LINE_HEIGHT)
    lines = visual_lines(text)
    doc = pymupdf.open()

    for offset in range(0, len(lines), max_lines):
        page = doc.new_page(width=PAGE_RECT.width, height=PAGE_RECT.height)
        if font_path:
            page.insert_font(fontname=font_name, fontfile=str(font_path))
        y = PAGE_MARGIN + BODY_FONT_SIZE
        for line in lines[offset : offset + max_lines]:
            if line:
                page.insert_text(
                    (PAGE_MARGIN, y),
                    line,
                    fontname=font_name,
                    fontsize=BODY_FONT_SIZE,
                    color=(0, 0, 0),
                )
            y += BODY_LINE_HEIGHT
        page.insert_text(
            (PAGE_RECT.width / 2 - 16, PAGE_RECT.height - 24),
            str(page.number + 1),
            fontname="Helvetica",
            fontsize=8,
            color=(0.35, 0.35, 0.35),
        )

    doc.set_metadata(
        {
            "title": "",
            "author": "",
            "subject": "",
            "keywords": "",
            "creator": "",
            "producer": "",
        }
    )
    doc.save(target, garbage=4, deflate=True)
    page_count = doc.page_count
    doc.close()
    return page_count


def inspect_pdf(path: Path) -> dict[str, Any]:
    with pymupdf.open(path) as doc:
        first_page_text = doc[0].get_text("text")
        total_chars = sum(len(page.get_text("text")) for page in doc)
        metadata = dict(doc.metadata or {})
        return {
            "page_count": doc.page_count,
            "text_character_count": total_chars,
            "first_page_excerpt": first_page_text[:1000],
            "pdf_metadata": metadata,
        }


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_manifest(output: Path, records: list[dict[str, Any]]) -> None:
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "purpose": "真实开放文献批量入库与全局联动验收",
        "filename_rule": "输出文件名不包含题名、作者、DOI、ISBN或文献类型",
        "records": records,
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    with (output / "manifest.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=(
                "record_id",
                "opaque_filename",
                "sha256",
                "byte_size",
                "page_count",
                "text_character_count",
                "source_url",
                "landing_page_url",
                "license",
                "expected_title",
                "expected_type",
                "expected_authors",
                "expected_year",
            ),
        )
        writer.writeheader()
        for record in records:
            expected = record["expected"]
            writer.writerow(
                {
                    "record_id": record["record_id"],
                    "opaque_filename": record["opaque_filename"],
                    "sha256": record["sha256"],
                    "byte_size": record["byte_size"],
                    "page_count": record["inspection"]["page_count"],
                    "text_character_count": record["inspection"]["text_character_count"],
                    "source_url": record["source_url"],
                    "landing_page_url": record["landing_page_url"],
                    "license": record["license"],
                    "expected_title": expected["title"],
                    "expected_type": expected["document_type"],
                    "expected_authors": " | ".join(expected["authors"]),
                    "expected_year": expected["publication_year"],
                }
            )


def prepare(output: Path) -> list[dict[str, Any]]:
    output.mkdir(parents=True, exist_ok=True)
    manifest_path = output / "manifest.json"
    if manifest_path.exists():
        raise FileExistsError(
            f"{manifest_path} 已存在。请使用新的输出目录，避免覆盖上一轮验收证据。"
        )

    names: set[str] = set()
    records: list[dict[str, Any]] = []
    for item in ITEMS:
        payload, content_type = download_bytes(item.source_url)
        filename = opaque_filename(names)
        target = output / filename

        if item.source_kind == "publisher_pdf":
            if content_type != "application/pdf" or not payload.startswith(b"%PDF-"):
                raise ValueError(f"{item.record_id} 的来源没有返回真实 PDF。")
            target.write_bytes(payload)
        else:
            if not content_type.startswith("text/"):
                raise ValueError(f"{item.record_id} 的来源没有返回文本全文。")
            text_to_pdf(payload.decode("utf-8-sig"), target)

        inspection = inspect_pdf(target)
        if inspection["page_count"] < 2 or inspection["text_character_count"] < 1000:
            raise ValueError(f"{item.record_id} 生成的 PDF 不足以进行全文验收。")
        records.append(
            {
                "record_id": item.record_id,
                "opaque_filename": filename,
                "source_kind": item.source_kind,
                "source_url": item.source_url,
                "landing_page_url": item.landing_page_url,
                "license": item.license_label,
                "source_content_type": content_type,
                "sha256": sha256(target),
                "byte_size": target.stat().st_size,
                "inspection": inspection,
                "expected": item.expected,
            }
        )

    write_manifest(output, records)
    return records


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/acceptance_corpus_20260728"),
    )
    args = parser.parse_args()
    records = prepare(args.output.resolve())
    print(
        json.dumps(
            {
                "output": str(args.output.resolve()),
                "documents": len(records),
                "files": [record["opaque_filename"] for record in records],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
