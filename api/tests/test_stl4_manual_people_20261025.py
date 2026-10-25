"""Deferred acceptance: all permitted contributor candidates remain reachable."""
import pytest

from catalog.models import Person
from tests.test_stl4_manual_duplicate_20261025 import get, work

pytestmark = pytest.mark.django_db


def test_people_pages_are_independent_of_book_pages(api_client, admin_user):
    people = [Person.objects.create(preferred_name='合成同名责任者', original_name=f'Candidate {index:02d}') for index in range(17)]
    work('合成同名作品')
    first = get(api_client, admin_user, people='合成同名责任者', q='合成同名作品', page=999)
    second = get(api_client, admin_user, people='合成同名责任者', people_page=2, q='合成同名作品')
    assert first.status_code == second.status_code == 200
    assert first.data['people_count'] == 17 and first.data['people_pages'] == 2
    assert len(first.data['people']) == 15 and len(second.data['people']) == 2
    assert first.data['count'] == second.data['count'] == 1
    assert {row['id'] for row in first.data['people'] + second.data['people']} == {str(row.pk) for row in people}


def test_person_exclusions_empty_results_and_out_of_range_pages(api_client, admin_user):
    target = Person.objects.create(preferred_name='合成保留责任者')
    for status in ['merged', 'archived', 'rejected']:
        Person.objects.create(preferred_name='合成保留责任者', authority_status=status)
    response = get(api_client, admin_user, people='合成保留责任者', people_page=999)
    assert response.data['people_count'] == 1 and response.data['people_page'] == 1
    assert response.data['people'][0]['id'] == str(target.pk)
    empty = get(api_client, admin_user, people='不存在的合成人物', people_page=2)
    assert empty.data['people_count'] == 0 and empty.data['people'] == []
    assert empty.data['people_page'] == 1 and empty.data['people_pages'] == 1


def test_complete_name_search_and_current_parameter_validation(api_client, admin_user):
    target = Person.objects.create(preferred_name='合成姓名' * 50)
    result = get(api_client, admin_user, people=target.preferred_name)
    assert result.status_code == 200 and result.data['people'][0]['id'] == str(target.pk)
    assert get(api_client, admin_user, people='字' * 241).status_code == 400
    assert get(api_client, admin_user, people=target.preferred_name, people_page=0).status_code == 400
    assert get(api_client, admin_user).data['people_count'] == 0
