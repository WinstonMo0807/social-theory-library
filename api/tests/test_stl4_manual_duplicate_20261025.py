"""Deferred acceptance for exact same-title review before manual catalogue save."""
from uuid import uuid4

import pytest

from catalog import manual_catalog_views as manual
from catalog.models import CatalogingSession, Edition, Work
from ingestion.models import AuditEvent

pytestmark = pytest.mark.django_db
URL = '/api/catalog/admin/manual-catalog/'


def get(client, actor, **query):
    client.force_authenticate(actor)
    client.credentials(HTTP_X_EDITOR_OWNER=str(actor.pk))
    return client.get(URL, query)


def work(title):
    result = Work.objects.create(title=title)
    Edition.objects.create(work=result)
    return result


def test_same_title_uses_save_guard_normalization_and_all_pages(api_client, admin_user):
    matches = [work('STRASSE') for _ in range(14)]
    work('STRASSE 另一部资料')
    before = (Work.objects.count(), CatalogingSession.objects.count(), AuditEvent.objects.count())
    first = get(api_client, admin_user, match_title=' Straße ', q='无关检索条件')
    assert first.status_code == 200 and first.data['count'] == 14
    assert first.data['pages'] == 2 and len(first.data['results']) == 12
    second = get(api_client, admin_user, match_title=' Straße ', page=2)
    assert {row['id'] for row in first.data['results'] + second.data['results']} == {str(row.pk) for row in matches}
    assert before == (Work.objects.count(), CatalogingSession.objects.count(), AuditEvent.objects.count())
    assert 'no-store' in first['Cache-Control']


def test_full_title_is_not_truncated_to_search_limit(api_client, admin_user):
    target = work('合成资料' * 50)
    response = get(api_client, admin_user, match_title=target.title)
    assert response.status_code == 200 and response.data['results'][0]['id'] == str(target.pk)
    assert get(api_client, admin_user, match_title=' ').status_code == 400
    assert get(api_client, admin_user, match_title='字' * 601).status_code == 400


def test_empty_preflight_does_not_bypass_final_duplicate_guard(api_client, admin_user):
    title = '并发创建的合成同名作品'
    assert get(api_client, admin_user, match_title=title).data['count'] == 0
    work(title)
    response = api_client.post(URL, {
        'request_id': str(uuid4()), 'session_id': None, 'expected_version': '', 'mode': 'new_work',
        'edition_id': None, 'candidate_version': '', 'acknowledge_similar': False, 'continue_files': False,
        'prefills': [], 'form': {'work': {'title': title, 'document_type': 'book', 'language': 'zh-CN',
                                       'subtitle': '', 'abstract': ''}, 'bibliography': {}, 'contributors': []},
    }, format='json')
    assert response.status_code == 409
    assert Work.objects.filter(title=title).count() == 1


def test_preflight_remains_private_and_rechecks_current_session(api_client, admin_user, reader_user, monkeypatch):
    target = work('合成权限范围资料')
    assert get(api_client, reader_user, match_title=target.title).status_code == 403
    api_client.force_authenticate(admin_user)
    api_client.credentials(HTTP_X_EDITOR_OWNER=str(reader_user.pk))
    assert api_client.get(URL, {'match_title': target.title}).status_code == 403
    original = manual.form_for

    def revoke(*args, **kwargs):
        result = original(*args, **kwargs)
        type(admin_user).objects.filter(pk=admin_user.pk).update(token_version=admin_user.token_version + 1)
        return result

    monkeypatch.setattr(manual, 'form_for', revoke)
    assert get(api_client, admin_user, match_title=target.title).status_code == 403
