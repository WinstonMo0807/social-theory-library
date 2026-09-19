from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.utils import timezone
from django.test.utils import CaptureQueriesContext
from django.db import connection

from catalog.models import Asset, Edition, HealthCheckRun, SiteSetting, Work
from catalog.services.catalog_availability import batch_catalog_availability, catalog_availability, _projection_result
from catalog.services.knowledge_studio import _work_status
from .test_publication_invariants_v305 import published_edition

pytestmark=pytest.mark.django_db


def rows(edition):
    return {row["key"]:row for row in catalog_availability(edition)["capabilities"]}


def test_bibliographic_has_six_explicit_inapplicable_capabilities_without_runtime_probes():
    edition=Edition.objects.create(work=Work.objects.create(title="纯书目"),publication_mode="bibliographic")
    with patch("reading.runtime_profiles.active_library_runtime_summary", side_effect=AssertionError("must not inspect runtime for no-document bibliography")):
        result=catalog_availability(edition)
    assert result["live_probes_performed"] is False
    assert result["private_reader_data"] == "not_read"
    assert {row["key"] for row in result["capabilities"]} == {"pdf","text","fulltext","semantic","viewpoint","qa"}
    assert all(row["status"] == "not_applicable" and row["applicable"] is False for row in result["capabilities"])


@pytest.mark.parametrize("validation,expected",[("pending","pending"),("invalid","failed"),("valid","ready")])
def test_pdf_states_do_not_expose_an_unpublished_asset_or_infer_live_storage(validation,expected):
    edition=Edition.objects.create(work=Work.objects.create(title="校验状态"))
    Asset.objects.create(edition=edition,kind="normalized",sha256=uuid4().hex,status="ready",validation_status=validation)
    with patch("django.db.models.fields.files.FieldFile.open",side_effect=AssertionError("no storage probe")):
        value=rows(edition)
    assert value["pdf"]["status"] == expected
    assert value["pdf"]["public_ready"] is False
    assert value["pdf"]["runtime_verified"] is False
    assert value["pdf"]["source"]["asset_id"]
    assert value["fulltext"]["status"] != "ready"


def test_paused_ocr_and_disabled_semantic_are_not_pdf_failure(settings):
    settings.SEMANTIC_SEARCH_ENABLED=False
    edition=Edition.objects.create(work=Work.objects.create(title="暂停不阻断PDF"))
    Asset.objects.create(edition=edition,kind="normalized",sha256=uuid4().hex,status="ready",validation_status="valid")
    SiteSetting.objects.create(key="ocr_processing_paused",value=True)
    result=rows(edition)
    assert result["pdf"]["status"] == "ready"
    assert result["text"]["status"] == "paused"
    assert result["semantic"]["status"] == "disabled"


def test_old_runtime_observation_is_not_current_success():
    edition=Edition.objects.create(work=Work.objects.create(title="过期观测"))
    Asset.objects.create(edition=edition,kind="normalized",sha256=uuid4().hex,status="ready",validation_status="valid")
    HealthCheckRun.objects.create(probe_key="storage_reader",status="healthy",reachable=True,functional=True,started_at=timezone.now()-timedelta(days=10))
    result=rows(edition)["pdf"]
    assert result["runtime_verified"] is False
    assert result["source"]["runtime_observation"]["status"] == "unknown"


def test_studio_work_status_does_not_use_bare_publication_flag():
    edition=Edition.objects.create(work=Work.objects.create(title="不存在活动快照"),state="published")
    assert _work_status(edition.work) != "published"
    valid,_=published_edition("真实公开")
    assert _work_status(valid.work) == "published"


def test_batch_availability_queries_do_not_scale_with_book_count():
    def measure(count):
        editions=[Edition.objects.create(work=Work.objects.create(title=f"批次{uuid4()}"),publication_mode="bibliographic") for _ in range(count)]
        with CaptureQueriesContext(connection) as queries:
            result=batch_catalog_availability(editions)
        assert len(result)==count
        return len(queries)
    first=measure(1)
    assert measure(25)<=first+2


def test_projection_cannot_borrow_another_edition_or_a_late_old_source():
    active=SimpleNamespace(pk=uuid4(),edition_id=uuid4(),provenance={})
    document=SimpleNamespace(pk=uuid4(),asset_id=uuid4())
    wrong=SimpleNamespace(pk=active.pk,edition_id=uuid4(),document_revision_id=document.pk,reader_asset_id=document.asset_id,status="active",metadata_ready=True)
    result=_projection_result("fulltext",active,document,{"revisions":{active.pk:wrong}})
    assert result[0]=="stale"
    same=SimpleNamespace(**{**vars(wrong),"edition_id":active.edition_id})
    result=_projection_result("fulltext",active,document,{"revisions":{active.pk:same},"events":{}})
    assert result[0]=="unknown"
