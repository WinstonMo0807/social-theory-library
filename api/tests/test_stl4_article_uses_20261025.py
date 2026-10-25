"""Deferred article-body reverse-use acceptance; no development execution."""
from uuid import uuid4
import pytest
from catalog.models import CurationProject, EditorialRevision, KnowledgeNode, RecommendationIssue, RecycleEntry
from catalog.services import editorial_issues as ledger
from tests.test_stl4_person_node_directory_20261024 import node, scholar
from tests.test_stl4_placement_uses_20261024 import url

pytestmark = pytest.mark.django_db


def issue():
    return RecommendationIssue.objects.create(title='合成引用文章', slug=f'article-uses-{uuid4()}')


def saved(parent, source, actor, *, kind='node', empty=False):
    return ledger._save_revision('recommendation_issue', parent.pk, {'title':parent.title, 'items':[], 'body_blocks':[] if empty else [
        {'id':str(uuid4()), 'type':'analysis', 'text':'不应出现在影响摘要中的正文', 'references':[{'type':kind, 'id':str(source.pk)}]}]}, actor)


def get(client, actor, source, *, kind='node', page=1):
    client.force_authenticate(actor)
    client.credentials(HTTP_X_EDITOR_OWNER=str(actor.pk))
    return client.get(url(source, kind), {'scope':'articles', 'page':page})


def test_original_public_and_scheduled_references_survive_draft_removal(api_client, admin_user):
    source, parent = node(), issue()
    active = saved(parent, source, admin_user)
    scheduled = saved(parent, source, admin_user)
    latest = saved(parent, source, admin_user, empty=True)
    parent.active_revision, parent.scheduled_revision = active, scheduled
    parent.save()
    response = get(api_client, admin_user, source)
    assert response.status_code == 200 and response.data['scope'] == 'articles'
    assert 'no-store' in response['Cache-Control']
    rows = response.data['results']
    assert response.data['count'] == 2 and {row['revision_id'] for row in rows} == {str(active.pk),str(scheduled.pk)}
    assert any('登记排期修订' in row['revision_note'] for row in rows)
    assert all(f"history={row['revision_id']}" in row['edit_url'] for row in rows)
    assert '不应出现在影响摘要中的正文' not in str(response.data)
    parent.active_revision, parent.scheduled_revision = latest, None
    parent.save()
    assert get(api_client, admin_user, source).data['count'] == 0


def test_project_visibility_precedes_counts_and_changes_take_effect(api_client, admin_user, reader_user):
    source, parent = node(), issue()
    project = CurationProject.objects.create(title='合成私人项目', owner=reader_user, visibility='team')
    parent.project = project
    parent.save()
    saved(parent, source, admin_user)
    response = get(api_client, admin_user, source)
    assert response.data['count'] == 0 and str(parent.pk) not in str(response.data)
    project.collaborators.add(admin_user)
    assert get(api_client, admin_user, source).data['count'] == 1
    project.collaborators.remove(admin_user)
    assert get(api_client, admin_user, source).data['count'] == 0
    assert get(api_client, reader_user, source).status_code == 403


def test_scholar_uses_person_identity_not_profile_or_equal_uuid_node(api_client, admin_user):
    source, parent = scholar(), issue()
    collision = KnowledgeNode.objects.create(id=source.person_id, canonical_name_zh='编号相同的另一模型', node_type='concept', slug=f'collision-{uuid4()}')
    revision = saved(parent, source.person, admin_user, kind='person')
    assert get(api_client, admin_user, source, kind='scholar').data['count'] == 1
    assert get(api_client, admin_user, collision).data['count'] == 0
    EditorialRevision.objects.filter(pk=revision.pk).update(materialized_preview={'body_blocks':[
        {'type':'comparison', 'rows':[{'person_id':source.person_id.hex, 'cells':[]}]}]})
    assert get(api_client, admin_user, source, kind='scholar').data['count'] == 1


def test_recycled_article_only_remains_in_original_recovery_scope(api_client, admin_user):
    from catalog.recycle_issue_references import issue_references
    source, parent = node(), issue()
    saved(parent, source, admin_user)
    RecycleEntry.objects.create(kind='recommendation-issue',model_label='catalog.recommendationissue',object_id=parent.pk,name=parent.title,deleted_by=admin_user)
    assert get(api_client, admin_user, source).data['count'] == 0
    assert issue_references(source, admin_user).count() == 1


def test_pagination_exact_structural_matches_and_invalid_scope(api_client, admin_user):
    source = node()
    for _ in range(13):
        saved(issue(), source, admin_user)
    first, second = get(api_client, admin_user, source), get(api_client, admin_user, source, page=2)
    assert first.data['count'] == second.data['count'] == 13
    assert len(first.data['results']) == 12 and len(second.data['results']) == 1
    assert not {r['revision_id'] for r in first.data['results']} & {r['revision_id'] for r in second.data['results']}
    assert get(api_client, admin_user, source, page=3).status_code == 404
    assert api_client.get(url(source), {'scope':'unknown'}).status_code == 400
    assert api_client.post(url(source), {}, format='json').status_code == 405
    api_client.credentials(HTTP_X_EDITOR_OWNER='different-owner')
    assert api_client.get(url(source), {'scope':'articles'}).status_code == 403


def test_free_text_and_malformed_old_blocks_are_not_invented_as_references(api_client, admin_user):
    source, parent = node(), issue()
    row = saved(parent, source, admin_user)
    for value in ({'body_blocks':[None, 'bad', {'type':'paragraph','text':str(source.pk),'target':{'type':'node','id':str(source.pk)}}]},
                  {'body_blocks':{'target':{'type':'node','id':str(source.pk)}}},
                  {'body_blocks':[{'type':'comparison','rows':[None,{'cells':'bad'}]}]}):
        EditorialRevision.objects.filter(pk=row.pk).update(materialized_preview=value)
        response = get(api_client, admin_user, source)
        assert response.status_code == 200 and response.data['count'] == 0


def test_other_article_cannot_be_opened_through_revision_identifier(api_client, admin_user):
    source, first, second = node(), issue(), issue()
    revision = saved(first, source, admin_user)
    api_client.force_authenticate(admin_user)
    api_client.credentials(HTTP_X_EDITOR_OWNER=str(admin_user.pk))
    response = api_client.get(f'/api/catalog/admin/recommendation-issues/{second.pk}/', {'revision':str(revision.pk)})
    assert response.status_code == 404
