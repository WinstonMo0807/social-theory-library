from hashlib import sha256
from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from catalog.models import Asset, Edition, Page, Passage, PublicationState, Work
from catalog.services.semantic_chunks import build_semantic_chunks
from tests.v304_helpers import activate_catalog_revision


def _published_asset(*, access_status: str, seed: str):
    digest = sha256(seed.encode("utf-8")).hexdigest()
    work = Work.objects.create(
        title=f"访问控制测试 {seed}",
        language="zh-CN",
    )
    edition = Edition.objects.create(
        work=work,
        state=PublicationState.PUBLISHED,
        public_slug=f"access-{digest[:20]}",
        publication_year=2026,
    )
    asset = Asset.objects.create(
        edition=edition,
        kind=Asset.Kind.NORMALIZED,
        file=SimpleUploadedFile(
            f"access-{digest[:20]}.pdf",
            b"%PDF-1.4\n%%EOF",
            content_type="application/pdf",
        ),
        sha256=digest,
        status=Asset.Status.READY,
        access_status=access_status,
        page_count=1,
    )
    text = f"Embargoed full text for {access_status} access must follow reader permissions."
    page = Page.objects.create(
        asset=asset,
        index=1,
        text_source=Page.TextSource.EMBEDDED,
        width=595,
        height=842,
        text=text,
        normalized_text=text.casefold(),
    )
    passage = Passage.objects.create(
        page=page,
        order=0,
        text=text,
        normalized_text=text.casefold(),
        bbox_union=[70, 120, 510, 220],
    )
    chunk = build_semantic_chunks(asset)[0]
    activate_catalog_revision(edition, reader_asset=asset)
    return asset, passage, chunk, text


@pytest.mark.django_db
@pytest.mark.parametrize(
    "access_status",
    [
        Asset.AccessStatus.PUBLIC,
        Asset.AccessStatus.REGISTERED,
        Asset.AccessStatus.RESTRICTED,
        Asset.AccessStatus.PRIVATE,
    ],
)
@pytest.mark.parametrize("viewer", ["anonymous", "reader", "staff"])
def test_asset_content_endpoints_follow_distribution_access_permissions(
    api_client,
    reader_user,
    admin_user,
    tmp_path,
    settings,
    access_status,
    viewer,
):
    settings.MEDIA_ROOT = tmp_path / "media"
    settings.ALLOW_LOCAL_PUBLIC_ASSET_ACCESS = True
    settings.REQUIRE_CLOUD_FOR_PUBLICATION = False
    asset, passage, chunk, protected_text = _published_asset(
        access_status=access_status,
        seed=f"{viewer}-{access_status}",
    )
    if viewer == "reader":
        api_client.force_authenticate(reader_user)
    elif viewer == "staff":
        api_client.force_authenticate(admin_user)

    distribution = api_client.get(f"/api/distribution/assets/{asset.id}/access/")
    expected_distribution_status = 200
    if viewer == "anonymous" and access_status == Asset.AccessStatus.REGISTERED:
        expected_distribution_status = 401
    elif viewer != "staff" and access_status in {
        Asset.AccessStatus.RESTRICTED,
        Asset.AccessStatus.PRIVATE,
    }:
        expected_distribution_status = 403
    assert distribution.status_code == expected_distribution_status
    expected_allowed = distribution.status_code == 200
    with patch("catalog.views.external_passage_ids", return_value=None), patch(
        "catalog.views.search_highlights",
        return_value={},
    ):
        responses = {
            "passage_focus": api_client.get(
                f"/api/catalog/passages/{passage.id}/focus/"
            ),
            "chunk_focus": api_client.get(
                f"/api/catalog/passages/{chunk.id}/focus/"
            ),
            "manifest": api_client.get(
                f"/api/catalog/assets/{asset.id}/manifest/"
            ),
            "page": api_client.get(
                f"/api/catalog/assets/{asset.id}/pages/1/"
            ),
            "search": api_client.get(
                f"/api/catalog/assets/{asset.id}/search/",
                {"q": "embargoed"},
            ),
            "global_search": api_client.get(
                "/api/catalog/search/",
                {"q": "embargoed full text"},
            ),
        }

    if expected_allowed:
        assert {name: response.status_code for name, response in responses.items()} == {
            "passage_focus": 200,
            "chunk_focus": 200,
            "manifest": 200,
            "page": 200,
            "search": 200,
            "global_search": 200,
        }
        assert responses["passage_focus"].data["text"] == protected_text
        assert responses["chunk_focus"].data["text"] == protected_text
        assert responses["page"].data["text"] == protected_text
        assert protected_text in responses["search"].data["matches"][0]["snippet"]
        assert any(
            protected_text in row["snippet"]
            for row in responses["global_search"].data["passages"]
        )
        return

    assert {
        name: response.status_code
        for name, response in responses.items()
        if name != "global_search"
    } == {
        "passage_focus": 404,
        "chunk_focus": 404,
        "manifest": 404,
        "page": 404,
        "search": 404,
    }
    assert responses["global_search"].status_code == 200
    assert not responses["global_search"].data["passages"]
    assert all(
        protected_text.encode("utf-8") not in response.content
        for response in responses.values()
    )
