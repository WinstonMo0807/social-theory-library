import pytest
from django.test import RequestFactory
from django.http import JsonResponse
from catalog.models import CatalogingSession, Edition, ProjectionState, Work, TheorySchool
from catalog.services.work_editor import save_workflow_section
from catalog.services.projection_refresh import _captured_states
from catalog.services.dependency_engine import projection_types_for
from catalog.contracts.fields import FIELDS, FIELD_CONTRACTS
from common.legacy_telemetry import LegacyReadTelemetryMiddleware, legacy_read_snapshot
from ingestion.models import UploadBatch, UploadItem

pytestmark = pytest.mark.django_db


def test_upload_and_maintenance_saves_reuse_a_real_cataloging_process(admin_user):
    work=Work.objects.create(title="旧上传",document_type="book",language="zh-CN")
    edition=Edition.objects.create(work=work)
    batch=UploadBatch.objects.create(created_by=admin_user)
    item=UploadItem.objects.create(batch=batch,edition=edition,source_filename="kept.pdf")
    save_workflow_section(edition,"work",{"subtitle":"首次保存"},actor=admin_user)
    first=CatalogingSession.objects.get(edition=edition)
    assert first.upload_item_id==item.pk and first.source_type=="upload"
    save_workflow_section(edition,"work",{"subtitle":"继续保存"},actor=admin_user)
    assert CatalogingSession.objects.get(edition=edition).pk==first.pk
    assert UploadItem.objects.count()==1


def test_explicit_graph_and_timeline_states_are_not_lost_by_default_mapping():
    work=Work.objects.create(title="完整投递",document_type="book")
    edition=Edition.objects.create(work=work)
    for kind in ProjectionState.ProjectionType.values:
        ProjectionState.objects.create(object_type="edition",object_id=edition.pk,projection_type=kind,source_revision=1)
    captured=_captured_states("edition",edition.pk)
    assert {row['projection_type'] for row in captured}==set(ProjectionState.ProjectionType.values)
    assert all(row['source_revision']==1 for row in captured)


def test_field_contracts_and_actual_projection_dispatch_share_the_same_rules():
    assert FIELD_CONTRACTS['cover'].projection_impact==projection_types_for('work',['cover'])==('public',)
    assert FIELD_CONTRACTS['title'].projection_impact==projection_types_for('edition',['title'])
    assert FIELD_CONTRACTS['publication_year'].projection_impact==projection_types_for('edition',['publication_year'])
    assert all(set(field.projection_impact)<=set(ProjectionState.ProjectionType.values) for field in FIELDS)


def test_legacy_read_measurement_counts_table_access_without_retirement_claim():
    def view(request):
        list(TheorySchool.objects.values_list('id',flat=True))
        return JsonResponse({'ok':True})
    response=LegacyReadTelemetryMiddleware(view)(RequestFactory().get('/api/catalog/theory-schools/'))
    assert response.status_code==200
    report=legacy_read_snapshot(1)
    assert report['days'][0]['counts']['TheorySchool']==1
    assert report['days'][0]['observed_from']
    assert report['retirement_proven'] is False
