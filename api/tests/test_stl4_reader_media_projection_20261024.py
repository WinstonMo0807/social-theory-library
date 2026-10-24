"""Deferred acceptance: version-bound media projection without database access."""
from copy import deepcopy
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

from django.test import SimpleTestCase

from catalog.services.media import snapshot_cover


class ReaderMediaProjectionTests(SimpleTestCase):
    def test_chosen_version_and_display_uses_survive_without_snapshot_mutation(self):
        primary, small, work_id, edition_id = [uuid4() for _ in range(4)]
        snapshot = {"work": {"cover_media": {"primary_rendition_id": str(primary),
            "display_uses": ["mobile"], "renditions": [{"id": str(small), "url": "/old/"}]}}}
        original = deepcopy(snapshot)
        edition = SimpleNamespace(pk=edition_id, work_id=work_id,
            active_catalog_revision=SimpleNamespace(snapshot=snapshot))
        result = snapshot_cover(edition)
        self.assertEqual(parse_qs(urlsplit(result["cover_url"]).query),
            {"edition_id": [str(edition_id)], "rendition": [str(primary)]})
        self.assertEqual(parse_qs(urlsplit(result["cover_media"]["renditions"][0]["url"]).query),
            {"edition_id": [str(edition_id)], "rendition": [str(small)]})
        self.assertEqual(result["cover_media"]["display_uses"], ["mobile"])
        self.assertEqual(snapshot, original)

    def test_unavailable_or_missing_public_cover_does_not_fall_back_to_draft(self):
        missing = {"cover_url": None, "cover_media": None}
        self.assertEqual(snapshot_cover(None), missing)
        self.assertEqual(snapshot_cover(SimpleNamespace(active_catalog_revision=None, cover="private-draft.jpg")), missing)
        self.assertEqual(snapshot_cover(SimpleNamespace(active_catalog_revision=SimpleNamespace(snapshot={}))), missing)
