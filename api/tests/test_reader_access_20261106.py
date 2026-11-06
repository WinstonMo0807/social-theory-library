from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.http import HttpResponse
from django.test import SimpleTestCase
from django.urls import resolve
from rest_framework.test import APIClient, APIRequestFactory

from common.middleware import ApiContractMiddleware
from common.permissions import CanReadLibrary
from distribution.services import signed_read_url
from distribution.views import _asset_file_headers


class ReaderAccessBoundaryTests(SimpleTestCase):
    def test_guest_endpoints_stop_before_documents_or_jobs(self):
        identifier = "00000000-0000-4000-8000-000000000001"
        paths = [
            "catalog/search/", "catalog/semantic-search/", "catalog/viewpoint-search/",
            "catalog/discovery-search/", f"catalog/discovery-search/{identifier}/",
            f"catalog/discovery-search/{identifier}/context/",
            f"catalog/passages/{identifier}/focus/", "catalog/parallel/versions/",
            "catalog/parallel/segments/", f"catalog/assets/{identifier}/manifest/",
            f"catalog/assets/{identifier}/outline/", f"catalog/assets/{identifier}/pages/1/",
            f"catalog/assets/{identifier}/search/", f"distribution/assets/{identifier}/access/",
            f"distribution/assets/{identifier}/file/", f"distribution/assets/{identifier}/file/?download=1",
            f"distribution/assets/{identifier}/file/?download=original", f"distribution/assets/{identifier}/ocr-status/",
            "reading/parallel-calibrations/public/",
        ]
        client = APIClient()
        for path in paths:
            with self.subTest(path=path):
                response = client.get("/api/" + path, HTTP_RANGE="bytes=0-15")
                self.assertEqual(response.status_code, 401)
                self.assertIn("no-store", response["Cache-Control"])
                self.assertNotEqual(response.get("Content-Type"), "application/pdf")
        for path in ["catalog/discovery-search/", "catalog/clean-copy/", "catalog/parallel/candidates/", "catalog/semantic-search/feedback/"]:
            with self.subTest(post=path):
                self.assertEqual(client.post("/api/" + path, {}, format="json").status_code, 401)
        self.assertEqual(client.head(f"/api/distribution/assets/{identifier}/file/").status_code, 401)

    def test_reader_permission_and_public_pages_remain_separate(self):
        raw = APIRequestFactory().get("/api/catalog/search/")
        reader = SimpleNamespace(is_authenticated=True)
        self.assertTrue(CanReadLibrary().has_permission(SimpleNamespace(_request=raw, user=reader), None))
        response = ApiContractMiddleware(lambda request: HttpResponse())(raw)
        self.assertIn("no-store", response["Cache-Control"])
        self.assertIn("Cookie", response["Vary"])
        for path in ["works/", "scholars/", "topics/", "theory-schools/", "home/"]:
            view = resolve("/api/catalog/" + path).func.cls()
            for permission in view.get_permissions():
                self.assertTrue(permission.has_permission(SimpleNamespace(user=SimpleNamespace(is_authenticated=False), method="GET"), view))

    def test_file_cache_and_cloud_link_require_private_delivery(self):
        response = _asset_file_headers(HttpResponse(), sha256="sample", access_status="public")
        self.assertIn("private, no-store", response["Cache-Control"])
        cloud = SimpleNamespace(status="ready", cdn_enabled=True, object_key="test.pdf", provider=SimpleNamespace(bucket="test", public_base_url="https://public.invalid"))
        client = Mock()
        client.generate_presigned_url.return_value = "https://signed.invalid/short-lived"
        with patch("distribution.services.s3_client", return_value=client):
            self.assertEqual(signed_read_url(cloud), "https://signed.invalid/short-lived")
        self.assertEqual(client.generate_presigned_url.call_args.kwargs["Params"]["ResponseCacheControl"], "private, no-store")
