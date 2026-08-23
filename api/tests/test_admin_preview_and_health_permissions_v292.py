from __future__ import annotations

from hashlib import sha256
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from accounts.models import User
from catalog.models import (
    Asset,
    DocumentType,
    Edition,
    HealthIncident,
    PublicationState,
    PublisherAuthority,
    Work,
)
from catalog.services.admin_workspace import build_admin_workspace
from catalog.services.work_editor import save_workflow_section
from catalog.workflow_serializers import BibliographySectionSerializer


pytestmark = pytest.mark.django_db


def _edition_with_pdf(*, state: str) -> tuple[Edition, Asset, bytes]:
    work = Work.objects.create(
        document_type=DocumentType.BOOK,
        title=f"管理员 PDF 预览 {state}",
        language="zh-CN",
    )
    edition = Edition.objects.create(
        work=work,
        state=state,
        public_slug=f"admin-pdf-preview-{state}",
        is_primary=True,
    )
    payload = b"%PDF-1.4\nadmin preview\n%%EOF"
    digest = sha256(payload).hexdigest()
    asset = Asset.objects.create(
        edition=edition,
        kind=Asset.Kind.NORMALIZED,
        file=SimpleUploadedFile(
            f"admin-preview-{state}.pdf",
            payload,
            content_type="application/pdf",
        ),
        original_filename=f"admin-preview-{state}.pdf",
        mime_type="application/pdf",
        sha256=digest,
        byte_size=len(payload),
        page_count=1,
        status=Asset.Status.READY,
        validation_status=Asset.ValidationStatus.VALID,
        is_current=True,
    )
    return edition, asset, payload


@pytest.mark.parametrize("state", [PublicationState.DRAFT, PublicationState.READY])
def test_draft_and_ready_admin_pdf_preview_is_private_and_range_capable(
    api_client,
    admin_user,
    settings,
    tmp_path,
    state,
):
    settings.MEDIA_ROOT = tmp_path
    settings.NAS_PUBLIC_ROOT = tmp_path / "public"
    settings.ALLOW_LOCAL_PUBLIC_ASSET_ACCESS = True
    settings.REQUIRE_CLOUD_FOR_PUBLICATION = False
    settings.PUBLIC_DEPLOYMENT_MODE = False
    settings.X_ACCEL_REDIRECT_ENABLED = False
    edition, asset, payload = _edition_with_pdf(state=state)

    workspace = build_admin_workspace(
        edition,
        user=admin_user,
        mode="maintenance",
    )
    preview_path = f"/api/distribution/admin/assets/{asset.id}/preview/"
    assert workspace["context"]["pdf_preview_url"] == preview_path

    anonymous = api_client.get(preview_path, HTTP_RANGE="bytes=0-4")
    assert anonymous.status_code in {401, 403}

    api_client.force_authenticate(admin_user)
    preview = api_client.get(preview_path, HTTP_RANGE="bytes=0-4")
    assert preview.status_code == 206
    assert preview["Content-Range"] == f"bytes 0-4/{len(payload)}"
    assert preview["Content-Type"] == "application/pdf"
    assert preview["Cache-Control"] == "private, no-store, no-transform"
    assert b"".join(preview.streaming_content) == b"%PDF-"

    api_client.force_authenticate(user=None)
    public = api_client.get(
        f"/api/distribution/assets/{asset.id}/file/",
        HTTP_RANGE="bytes=0-4",
    )
    assert public.status_code == 404


def test_published_public_pdf_range_behavior_is_unchanged(
    api_client,
    settings,
    tmp_path,
):
    settings.MEDIA_ROOT = tmp_path
    settings.NAS_PUBLIC_ROOT = tmp_path / "public"
    settings.ALLOW_LOCAL_PUBLIC_ASSET_ACCESS = True
    settings.REQUIRE_CLOUD_FOR_PUBLICATION = False
    settings.PUBLIC_DEPLOYMENT_MODE = False
    settings.X_ACCEL_REDIRECT_ENABLED = False
    _edition, asset, payload = _edition_with_pdf(state=PublicationState.PUBLISHED)

    response = api_client.get(
        f"/api/distribution/assets/{asset.id}/file/",
        HTTP_RANGE="bytes=0-4",
    )

    assert response.status_code == 206
    assert response["Content-Range"] == f"bytes 0-4/{len(payload)}"
    assert response["Cache-Control"].startswith("public")
    assert b"".join(response.streaming_content) == b"%PDF-"


def _editor() -> User:
    identity = uuid4()
    return User.objects.create_user(
        username=f"health-editor-{identity}@example.org",
        email=f"health-editor-{identity}@example.org",
        role=User.Role.EDITOR,
        password="Health-Editor-Test-Password",
    )


def test_functional_health_mutations_require_status_and_retry_capabilities(
    api_client,
    admin_user,
):
    editor = _editor()
    endpoint = "/api/catalog/admin/functional-health/"

    api_client.force_authenticate(editor)
    get_response = api_client.get(endpoint)
    post_response = api_client.post(
        endpoint,
        {"action": "run_probe", "probe_key": "database"},
        format="json",
    )

    assert get_response.status_code == 403
    assert post_response.status_code == 403

    run = SimpleNamespace(id=uuid4(), probe_key="database", status="healthy")
    api_client.force_authenticate(admin_user)
    with (
        patch("catalog.services.system_health.run_health_probe", return_value=run) as probe,
        patch(
            "catalog.services.system_health.functional_health_snapshot",
            return_value={"capabilities": []},
        ),
    ):
        allowed = api_client.post(
            endpoint,
            {"action": "run_probe", "probe_key": "database"},
            format="json",
        )

    assert allowed.status_code == 200
    probe.assert_called_once()


def test_semantic_and_query_lexicon_recovery_require_elevated_capability(
    api_client,
    admin_user,
):
    endpoint = "/api/catalog/admin/functional-health/"
    incident = HealthIncident.objects.create(
        incident_key=f"health-capability-{uuid4()}",
        capability="search",
        probe_key="semantic",
        status=HealthIncident.Status.OPEN,
        safe_recovery_actions=["recover_semantic_queue"],
    )
    api_client.force_authenticate(admin_user)

    with patch("catalog.services.system_health.request_recovery") as request_recovery:
        response = api_client.post(
            endpoint,
            {
                "action": "recover",
                "incident_id": str(incident.id),
                "recovery_action": "recover_semantic_queue",
                "idempotency_key": "permission-test",
            },
            format="json",
        )

    assert response.status_code == 403
    request_recovery.assert_not_called()


def test_bibliography_picker_can_persist_publisher_authority_and_display_text(admin_user):
    edition, _asset, _payload = _edition_with_pdf(state=PublicationState.DRAFT)
    authority = PublisherAuthority.objects.create(
        canonical_name="统一出版社 Authority",
    )
    serializer = BibliographySectionSerializer(
        data={
            "publisher": "统一出版社 Authority",
            "publisher_authority_id": str(authority.id),
        },
        partial=True,
    )
    serializer.is_valid(raise_exception=True)

    save_workflow_section(
        edition,
        "bibliography",
        serializer.validated_data,
        actor=admin_user,
    )

    edition.refresh_from_db()
    assert edition.publisher == "统一出版社 Authority"
    assert edition.publisher_authority_id == authority.id
    workspace = build_admin_workspace(
        edition,
        user=admin_user,
        mode="maintenance",
    )
    assert workspace["data"]["bibliography"]["publisher_authority_id"] == authority.id
    assert workspace["data"]["bibliography"]["publisher_authority_name"] == authority.canonical_name
