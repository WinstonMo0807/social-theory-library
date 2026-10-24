"""Bounded PDF booklists using only the active public edition's stored cover."""
from functools import lru_cache
from hashlib import sha256
from io import BytesIO
from pathlib import PurePosixPath
import time
import warnings

from PIL import Image, ImageOps, UnidentifiedImageError
from rest_framework.exceptions import ValidationError

from catalog.models import MediaRendition, Work
from catalog.services.media import DEFAULT_MEDIA_DISPLAY_USES

MAX_COVER_BYTES = 6 * 1024 * 1024
MAX_TOTAL_COVER_BYTES = 32 * 1024 * 1024
MAX_COVER_PIXELS = 8_000_000
MAX_PDF_BYTES = 32 * 1024 * 1024


def cover_bytes(edition, budget):
    if not edition:
        return None, "来源不可用，未附封面"
    work = edition.active_catalog_revision.snapshot.get("work") or {}
    media = work.get("cover_media")
    checksum = ""
    if media:
        if "list" not in media.get("display_uses", DEFAULT_MEDIA_DISPLAY_USES):
            return None, "当前公开版未启用列表封面"
        # Use only a rendition recorded in this edition's immutable public snapshot.
        allowed = {str(row["id"]): row for row in media.get("renditions", []) if row.get("id")}
        identifier = str(media.get("primary_rendition_id") or "")
        if identifier not in allowed:
            return None, "当前公开版未记录有效封面"
        rendition = MediaRendition.objects.filter(pk=identifier, media_id=media.get("media_id")).first()
        if not rendition:
            return None, "公开封面记录已不可用"
        storage, name = rendition.file.storage, rendition.file.name
        checksum = rendition.checksum
    else:
        name = str(work.get("cover") or "")
        path = PurePosixPath(name)
        if not name:
            return None, "暂无公开封面"
        if not name.startswith("public/covers/") or path.is_absolute() or ".." in path.parts or "\\" in name or ":" in name:
            return None, "旧封面位置无法安全读取"
        storage = Work._meta.get_field("cover").storage
    try:
        with storage.open(name, "rb") as source:
            content = source.read(MAX_COVER_BYTES + 1)
        budget["bytes"] += len(content)
        if budget["bytes"] > MAX_TOTAL_COVER_BYTES:
            raise ValidationError("本次封面总量超过32 MiB，请减少作品或取消封面后导出。")
        if len(content) > MAX_COVER_BYTES:
            return None, "封面超过6 MiB，本次未嵌入"
        if checksum and sha256(content).hexdigest() != checksum:
            return None, "封面文件与记录不一致，本次未嵌入"
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(content)) as source:
                if source.format not in {"JPEG", "PNG", "WEBP"} or source.width * source.height > MAX_COVER_PIXELS:
                    return None, "封面格式或像素超过本次导出范围"
                picture = ImageOps.exif_transpose(source)
                picture.thumbnail((360, 480))
                background = Image.new("RGB", picture.size, "white")
                if picture.mode in {"RGBA", "LA"} or picture.mode == "P" and "transparency" in picture.info:
                    picture = picture.convert("RGBA")
                    background.paste(picture, mask=picture.getchannel("A"))
                else:
                    background.paste(picture.convert("RGB"))
                output = BytesIO()
                background.save(output, format="JPEG", quality=85)
        return output.getvalue(), ""
    except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        return None, "封面暂不可读取，书目信息仍保留"


def render(title, description, records, editions, *, include_covers, deadline):
    import fitz
    font = fitz.Font("china-s")
    budget = {"bytes": 0}
    ink = (.16, .15, .14)

    @lru_cache(maxsize=4096)
    def character_width(character, size):
        return font.text_length(character, fontsize=size)

    def wrapped(text, width, size):
        for paragraph in str(text or "").splitlines() or [""]:
            line, used = "", 0
            for character in paragraph:
                value = character_width(character, size)
                if used + value > width and line:
                    yield line
                    line, used = "", 0
                line += character
                used += value
            yield line

    def check_deadline():
        if time.monotonic() > deadline:
            raise ValidationError("本次导出内容准备超时，请减少作品或取消封面后重试。")

    with fitz.open() as document:
        page, y = None, 0

        def new_page():
            nonlocal page, y
            check_deadline()
            page = document.new_page(width=595, height=842)
            page.insert_text((44, 32), "私人书单 · 仅本次显式下载", fontname="china-s", fontsize=8, color=(.45, .42, .38))
            page.insert_text((285, 813), str(len(document)), fontsize=9, color=ink)
            y = 58

        def text(value, *, x=44, width=507, size=10.5):
            nonlocal y
            for line in wrapped(value, width, size):
                check_deadline()
                if page is None or y + size > 780:
                    new_page()
                if line:
                    page.insert_text((x, y), line, fontname="china-s", fontsize=size, color=ink)
                y += size + 6

        new_page()
        text(title, size=19)
        if description:
            text(description)
        text(f"{len(records)} 部作品 · 书目信息来自导出时的公开版本", size=9)
        for index, record in enumerate(records):
            check_deadline()
            if y + 136 > 780:
                new_page()
            page.draw_line((44, y), (551, y), color=(.83, .80, .74), width=.5)
            y += 19
            top = y
            first_page = page.number
            image, notice = cover_bytes(editions.get(record["id"]), budget) if include_covers else (None, "")
            x, width = (150, 401) if include_covers else (44, 507)
            if include_covers:
                frame = fitz.Rect(44, top - 10, 128, top + 106)
                if image:
                    page.insert_image(frame, stream=image, keep_proportion=True)
                else:
                    page.draw_rect(frame, color=(.83, .80, .74), fill=(.97, .96, .93))
                    page.insert_text((57, top + 44), "无可用封面", fontname="china-s", fontsize=9, color=(.45, .42, .38))
            text(f"{index + 1}. {record['title']}", x=x, width=width, size=13)
            text(record["citation"], x=x, width=width)
            if record.get("version"):
                text("版本：" + record["version"], x=x, width=width, size=9)
            if record.get("isbn"):
                text("ISBN：" + record["isbn"], x=x, width=width, size=9)
            if notice:
                text(notice, x=x, width=width, size=9)
            if include_covers and page.number == first_page:
                y = max(y, top + 120)
            if record["progress"]:
                text("本人阅读状态：" + record["progress"])
            if record["notes"]:
                text("本人笔记（仅本次勾选导出）", size=10)
                text(record["notes"])
            y += 14
        check_deadline()
        content = document.tobytes(garbage=4, deflate=True)
    if len(content) > MAX_PDF_BYTES:
        raise ValidationError("导出PDF超过32 MiB，请减少作品或取消封面后重试。")
    return content
