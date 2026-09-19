"""Actual generated PDF and publication fixtures for isolated Reader E2E only."""
from hashlib import sha256

from django.conf import settings
from django.core.files.base import ContentFile
from django.utils import timezone


def seed_reader_v306():
    if settings.DATABASES["default"]["ENGINE"] != "django.db.backends.sqlite3" or "stl-v305-e2e-" not in settings.DATABASES["default"]["NAME"]:
        raise RuntimeError("Reader fixtures require the disposable E2E database")
    import fitz
    from catalog.models import Asset, CatalogPublicationRevision, Contribution, Edition, Page, Person, Work
    from catalog.services.knowledge_publication import catalog_snapshot

    document = fitz.open()
    for index in range(1001):
        page = document.new_page(width=595, height=842)
        page.insert_text((52,80), f"V306 Reader layout page {index+1}", fontsize=18)
        page.insert_text((52,125), "Evidence stays on the same physical page. Reader data remains private.", fontsize=11)
    content = document.tobytes(garbage=4, deflate=True)
    document.close()
    digest = sha256(content).hexdigest()
    work = Work.objects.create(id="30600000-0000-4000-8000-000000000310", title="V306阅读器布局与私人记录："+"长中文标题及多位责任者"*8, document_type="report", language="en")
    edition = Edition.objects.create(id="30600000-0000-4000-8000-000000000311", work=work, state="published", public_slug="v306-reader-layout", publication_year=2026, version_label="真实1001页隔离PDF", ocr_status="not_required")
    for index in range(3):
        person=Person.objects.create(preferred_name=f"隔离测试第{index+1}位责任者", authority_status="verified")
        Contribution.objects.create(edition=edition, person=person, role="author", approved=True, source="isolated-reader-fixture", order=index)
    original = Asset.objects.create(id="30600000-0000-4000-8000-000000000312", edition=edition, kind="original", sha256=digest, byte_size=len(content), page_count=1001, status="ready", validation_status="valid", access_status="public", original_filename="reader-layout.pdf")
    original.file.save("reader-layout.pdf", ContentFile(content), save=True)
    normalized = Asset.objects.create(id="30600000-0000-4000-8000-000000000313", edition=edition, kind="normalized", source_asset=original, sha256=digest, byte_size=len(content), page_count=1001, status="ready", validation_status="valid", access_status="public", original_filename="reader-layout.pdf")
    normalized.file.save("reader-layout.pdf", ContentFile(content), save=True)
    from accounts.models import User
    from ingestion.models import UploadBatch, UploadItem
    batch=UploadBatch.objects.create(created_by=User.objects.get(email="owner-v305@example.test"),source="isolated-existing-pdf",label="V306已有PDF复核",expected_count=1)
    UploadItem.objects.create(id="30600000-0000-4000-8000-000000000314",batch=batch,edition=edition,asset=original,source_filename="V306真实隔离PDF复核.pdf",status="ready",workflow_state="ready",sha256=digest,byte_size=len(content))
    Page.objects.bulk_create([Page(asset=normalized, index=index+1, printed_label="序言中的较长印刷页码标识" if index==0 else str(index), is_label_manual=index==0, label_source="manual" if index==0 else "file_index", width=595, height=842, text_source="embedded", text=f"V306 Reader layout page {index+1}") for index in range(1001)])
    snapshot, related=catalog_snapshot(edition,content_asset_id=normalized.pk)
    revision=CatalogPublicationRevision.objects.create(edition=edition,revision=1,status="active",metadata_ready=True,reader_asset=normalized,snapshot=snapshot,related_entities=related,content_fingerprint=digest,activated_at=timezone.now())
    edition.active_catalog_revision=revision
    edition.save(update_fields=["active_catalog_revision","updated_at"])
    # Source selector must browse all editions without choosing one implicitly.
    # These private bibliographic variants do not change the public reader.
    Edition.objects.bulk_create([
        Edition(id=f"30600000-0000-4000-8000-{index:012d}", work=work, is_primary=False,
                publication_mode="bibliographic", version_label=f"出处分页纯书目版本 {index}")
        for index in range(400, 440)
    ])
    # Display/preflight negative fixtures, deliberately not publicly active.
    for index,state in enumerate(("pending","invalid"),start=320):
        state_content=content+f"\n% distinct {state} validation fixture\n".encode()
        state_digest=sha256(state_content).hexdigest()
        item_work=Work.objects.create(title=f"V306-PDF-{state}", document_type="report", language="en")
        item_edition=Edition.objects.create(id=f"30600000-0000-4000-8000-{index:012d}",work=item_work)
        for kind in ("original","normalized"):
            item_asset=Asset.objects.create(edition=item_edition,kind=kind,status="ready",validation_status=state,sha256=state_digest,page_count=1001,original_filename=f"{state}.pdf")
            item_asset.file.save(f"{state}.pdf",ContentFile(state_content),save=True)
