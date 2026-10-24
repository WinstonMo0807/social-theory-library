"""Deferred version-bound media projection acceptance; not run in development."""
from copy import deepcopy
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

from catalog.serializers import WorkCardSerializer


def test_media_urls_follow_the_selected_edition_without_mutating_the_snapshot():
    work, edition, media, rendition = uuid4(), uuid4(), uuid4(), uuid4()
    snapshot = {"work": {"cover": "retained-original", "cover_media": {"media_id": str(media),
        "primary_rendition_id": str(rendition), "display_uses": ["mobile"],
        "renditions": [{"id": str(rendition), "width": 640, "height": 900, "url": "/old-primary-image"}]}}}
    original = deepcopy(snapshot)

    class SelectedCard(WorkCardSerializer):
        def _public_catalog(self, obj):
            return SimpleNamespace(pk=edition), snapshot

    serializer = SelectedCard()
    obj = SimpleNamespace(pk=work, id=work)
    for image in [serializer.get_cover(obj), serializer.get_cover_media(obj)["renditions"][0]["url"],
                  serializer.get_recommendation_image(obj), serializer.get_recommendation_media(obj)["renditions"][0]["url"]]:
        query = parse_qs(urlsplit(image).query)
        assert query == {"edition_id": [str(edition)], "rendition": [str(rendition)]}
    assert serializer.get_cover_media(obj)["display_uses"] == ["mobile"]
    assert snapshot == original
