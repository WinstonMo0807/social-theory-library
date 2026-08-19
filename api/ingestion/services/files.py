from pathlib import Path
from pathlib import PurePosixPath
import hashlib
import os
import re
import shutil
import tempfile
from typing import Callable
import unicodedata

import fitz
from django.core.files import File
from django.core.files.storage import FileSystemStorage


INVALID_FILENAME_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
SPACE_RE = re.compile(r"\s+")


class SourceFileMissing(RuntimeError):
    """The database names an intake source that is not available in storage."""

    def __init__(self, message: str, *, error_code: str = "source_file_missing"):
        self.error_code = error_code
        super().__init__(message)


def sha256_file(path: str | Path, chunk_size: int = 1024 * 1024) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with Path(path).open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def is_pdf(path: str | Path) -> bool:
    with Path(path).open("rb") as handle:
        return handle.read(5) == b"%PDF-"


def materialize_field_file(field_file) -> tuple[Path, Callable[[], None] | None]:
    """Return a local path for either filesystem or private object storage uploads."""
    name = str(getattr(field_file, "name", "") or "").strip()
    if not name:
        raise SourceFileMissing("入库记录没有关联正式 PDF。")
    try:
        local_path = Path(field_file.path)
    except (AttributeError, NotImplementedError):
        local_path = None
    if local_path is not None:
        try:
            if not local_path.is_file():
                raise SourceFileMissing("正式书库存储中的 PDF 不存在。")
        except FileNotFoundError as exc:
            raise SourceFileMissing("正式书库存储中的 PDF 不存在。") from exc
        return local_path, None
    try:
        suffix = Path(name).suffix or ".pdf"
        temporary = tempfile.NamedTemporaryFile(
            prefix="library-intake-",
            suffix=suffix,
            delete=False,
        )
        temporary_path = Path(temporary.name)
        try:
            with temporary, field_file.open("rb") as source:
                shutil.copyfileobj(source, temporary, length=1024 * 1024)
        except Exception:
            temporary_path.unlink(missing_ok=True)
            raise
        return temporary_path, lambda: temporary_path.unlink(missing_ok=True)
    except FileNotFoundError as exc:
        raise SourceFileMissing("正式书库存储中的 PDF 不存在。") from exc


def store_path_in_file_field(instance, field_name: str, source_path: str | Path, original_name: str) -> str:
    """Persist a local path through an existing Django FileField without loading it into memory."""

    source_path = Path(source_path)
    field_file = getattr(instance, field_name)
    storage = field_file.storage
    field = instance._meta.get_field(field_name)
    if isinstance(storage, FileSystemStorage):
        generated_name = field.generate_filename(instance, original_name)
        available_name = storage.get_available_name(
            generated_name,
            max_length=field.max_length,
        )
        try:
            destination = Path(storage.path(available_name))
            destination.parent.mkdir(parents=True, exist_ok=True)
            os.link(source_path, destination)
            field_file.name = available_name
            return "filesystem_hardlink"
        except (AttributeError, NotImplementedError, OSError):
            pass

    with source_path.open("rb") as source:
        field_file.save(original_name, File(source), save=False)
    return "storage_copy"


def validate_pdf_structure(path: str | Path, max_pages: int) -> int:
    try:
        document = fitz.open(str(path))
    except Exception as exc:
        raise ValueError("PDF 结构损坏，无法打开。") from exc
    try:
        if document.needs_pass:
            raise ValueError("PDF 受密码保护，必须先移除密码才能入库。")
        if document.page_count < 1:
            raise ValueError("PDF 不包含可阅读页面。")
        if document.page_count > max_pages:
            raise ValueError(f"PDF 页数超过当前上限 {max_pages} 页。")
        return document.page_count
    finally:
        document.close()


def safe_component(value: str, fallback: str = "未命名") -> str:
    value = unicodedata.normalize("NFKC", value or "")
    value = INVALID_FILENAME_RE.sub("_", value)
    value = SPACE_RE.sub(" ", value).strip(" .")
    return value[:180] or fallback


def canonical_pdf_filename(title: str, authors: list[str], year: int | None) -> str:
    author = safe_component("、".join(authors[:3]), "佚名")
    year_text = str(year) if year else "出版年不详"
    title_text = safe_component(title)
    return f"{author}_{year_text}_{title_text}.pdf"


def rename_normalized_asset(asset, filename: str) -> str:
    """Rename the public NAS copy without changing the immutable original."""
    current = PurePosixPath(asset.file.name)
    filename = safe_component(Path(filename).stem) + ".pdf"
    desired = str(current.with_name(filename))
    if desired == asset.file.name:
        return desired
    storage = asset.file.storage
    available = storage.get_available_name(desired, max_length=1000)
    with asset.file.open("rb") as source:
        saved_name = storage.save(available, source)
    try:
        storage.delete(asset.file.name)
    except PermissionError:
        # Windows does not allow deleting a PDF while an active preview response
        # still holds the old file. The database can safely move to the new
        # canonical copy; the unreferenced file is left for storage cleanup.
        pass
    asset.file.name = saved_name
    asset.save(update_fields=["file", "updated_at"])
    return saved_name
