"""Conservative title/page observations for native bookmarks, not accuracy scores."""
from collections import Counter, defaultdict
import re
import unicodedata


def title_key(value):
    # Keep chapter/section numbers: stripping them can confuse two introductions.
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return "".join(char for char in text if char.isalnum())


class BookmarkObservations:
    def __init__(self, entries):
        self.wanted = {title_key(row[1]) for row in entries if len(row) >= 3}
        self.pages = defaultdict(set)
        self.targets = defaultdict(set)
        self.overflow = set()
        for row in entries:
            if len(row) >= 3 and type(row[2]) is int and row[2] > 0:
                self.targets[title_key(row[1])].add(row[2])

    def observe(self, page, text):
        text = str(text or "").strip()
        if not text or len(text) > 600:
            return
        key = title_key(text)
        if key and key in self.wanted:
            if len(self.pages[key]) < 21 or page in self.targets[key] or page in self.pages[key]:
                self.pages[key].add(page)
            else:
                self.overflow.add(key)

    def observe_blocks(self, page, blocks):
        for block in blocks:
            if block.get("type", 0) != 0:
                continue
            lines = []
            for line in block.get("lines", []):
                text = "".join(str(span.get("text", "")) for span in line.get("spans", []))
                self.observe(page, text)
                lines.append(text)
            self.observe(page, " ".join(lines))

    def review(self, nodes, contents_pages, is_contents_title):
        """Keep all original nodes/positions; ambiguous observations need a person."""
        duplicates = Counter((title_key(node["title"]), node.get("pdf_page"), tuple(node.get("pdf_position", []))) for node in nodes)
        problems = []
        for node in nodes:
            if node.get("calibration_status") != "native":
                continue  # Structural/coordinate failures already have their own diagnostic.
            title, page = node["title"], node["pdf_page"]
            key = title_key(title)
            observed = self.pages.get(key, set())
            matches = sorted(observed if is_contents_title(title) else observed - contents_pages)
            generic = not any(char.isalpha() for char in title) or re.search(
                r"(?:https?://|www\.|\ufffd)|^(?:(?:bookmark|page|untitled)\s*\d*|未命名(?:书签)?\d*)$", title, re.I)
            if generic:
                code, reason = "bookmark_title_unverified", "标题像网址、编号或未命名项，请核对真实章节名称。"
            elif duplicates[(key, page, tuple(node.get("pdf_position", [])))] > 1:
                code, reason = "duplicate_bookmark", "同名书签重复指向同一位置，原节点均保留，请核对层级与用途。"
            elif key in self.overflow:
                code, reason = "bookmark_title_repeated", "同名文字出现过多，可能是页眉；保留有界对比页与原落点，须人工核对。"
            elif page not in matches:
                code = "bookmark_target_mismatch" if matches else "bookmark_title_unverified"
                reason = "标题只在其他正文页观察到，原落点未自动改动。" if matches else "未在落点页观察到完整标题；可能缺少可读文字、OCR或标题跨块，请人工校准。"
            elif len(matches) > 1:
                code, reason = "bookmark_title_repeated", "同名文字出现在多页，可能是页眉或重复章节，请核对当前落点。"
            else:
                continue
            node["calibration_status"] = "needs_review"
            problems.append({"code": code, "node_id": node["id"], "message": f"{title}：{reason}",
                             "observed_pages": matches[:20], "observed_page_count": len(matches),
                             "observed_page_count_is_lower_bound": key in self.overflow})
        return problems
