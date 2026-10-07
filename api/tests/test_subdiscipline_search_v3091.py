import pytest

from catalog.models import Discipline, Subdiscipline

pytestmark = pytest.mark.django_db


def test_tree_search_filters_the_full_queryset_before_pagination(api_client, admin_user):
    sociology = Discipline.objects.create(name="社会学", code="soc-search", slug="soc-search")
    anthropology = Discipline.objects.create(name="人类学", code="anth-search", slug="anth-search")
    history = Subdiscipline.objects.create(name="历史社会学", slug="history-search", discipline=sociology)
    politics = Subdiscipline.objects.create(name="政治人类学", foreign_name="Political Anthropology", slug="politics-search", discipline=anthropology)
    api_client.force_authenticate(admin_user)
    path = "/api/catalog/admin/subdisciplines/"
    for query, expected in [("社会学", history), ("政治", politics), ("Political", politics)]:
        response = api_client.get(path, {"search": query, "page_size": 1})
        assert response.status_code == 200
        assert response.data["count"] == 1
        assert [row["id"] for row in response.data["results"]] == [str(expected.pk)]
    scoped = api_client.get(path, {"search": "Political", "discipline": str(sociology.pk)})
    assert scoped.data["count"] == 0


def test_tree_search_does_not_expose_private_taxonomy_to_readers(api_client, reader_user):
    api_client.force_authenticate(reader_user)
    assert api_client.get("/api/catalog/admin/subdisciplines/", {"search": "社会学"}).status_code == 403
