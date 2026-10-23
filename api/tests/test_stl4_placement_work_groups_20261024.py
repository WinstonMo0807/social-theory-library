"""Deferred acceptance for M32: paginate distinct identities and pick exact editions."""
import pytest

from catalog.content_placement_views import grouped_placement_source_rows, placement_source_rows
from catalog.models import Edition, RecycleEntry, Work


@pytest.mark.django_db
def test_grouping_precedes_pagination_without_merging_equal_titles():
    work = Work.objects.create(title="同题名作品")
    for year in range(1980, 2010):
        Edition.objects.create(work=work, publication_year=year)
    different_work = Work.objects.create(title="同题名作品")
    other = Edition.objects.create(work=different_work, publication_year=2005)
    rows = list(grouped_placement_source_rows({"sort": "newest"}))
    assert len(rows) == 2 and {row.work_id for row in rows} == {work.pk, different_work.pk}
    first = next(row for row in rows if row.work_id == work.pk)
    assert first.publication_year == 2009 and first.version_count == 30
    assert placement_source_rows({"work_id": work.pk}).count() == 30
    RecycleEntry.objects.create(model_label="catalog.edition", kind="edition", object_id=other.pk, name="旧版本")
    assert grouped_placement_source_rows({"sort": "newest"}).count() == 1


@pytest.mark.django_db
def test_group_representative_matches_filter_and_unknown_year_stays_last():
    work = Work.objects.create(title="年份与版本")
    known = Edition.objects.create(work=work, publication_year=2000, isbn="9780000000001")
    Edition.objects.create(work=work)
    assert grouped_placement_source_rows({"sort": "newest"}).get().pk == known.pk
    matched = grouped_placement_source_rows({"q": "9780000000001"}).get()
    assert matched.pk == known.pk and matched.version_count == 2
