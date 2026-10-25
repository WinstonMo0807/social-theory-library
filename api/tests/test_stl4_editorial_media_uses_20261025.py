"""Deferred display-use projection for editorial bibliography, without rewriting old revisions."""
from copy import deepcopy
from uuid import uuid4
import pytest
from django.utils import timezone
from catalog.models import Edition, RecommendationIssue, RecommendationIssueItem
from catalog.services import editorial_issues as ledger
from catalog.services.media import build_rendition, ingest_image
from catalog.services.public_editorial import directory_related
from tests.test_media_v305 import picture
from tests.test_publication_invariants_v305 import published_edition

pytestmark = pytest.mark.django_db


def material(actor, settings, tmp_path, uses):
    settings.MEDIA_ROOT = tmp_path
    media, _ = ingest_image(picture(), actor=actor)
    cover = build_rendition(media.pk, display_uses=uses)
    edition, revision = published_edition('合成策划引用书目')
    revision.snapshot = {'work':{'id':str(edition.work_id),'title':'合成策划引用书目',
        'cover_media':{'primary_rendition_id':str(cover.pk),'display_uses':uses}},'edition':{'public_slug':edition.public_slug}}
    revision.save()
    return edition, cover


def published_issue(actor, edition, *, uses=None, rendition=None, planned=False, cached_url=''):
    parent = RecommendationIssue.objects.create(title='合成媒体用途文章', slug=f'media-use-{uuid4()}')
    item = RecommendationIssueItem.objects.create(issue=parent, **({'linked_edition':edition} if planned else {}))
    row = {'id':str(item.pk),'kind':'planned' if planned else 'catalog','title':'合成书目','note':'','authors':'',
        'work_id':str(edition.work_id),'edition_id':str(edition.pk),'position':0,'cover_url':cached_url}
    if cached_url:
        row.update(available_work_id=str(edition.work_id),available_edition_id=str(edition.pk))
    if rendition: row['cover_rendition_id'] = str(rendition.pk)
    if uses is not None: row['cover_display_uses'] = uses
    revision = ledger._save_revision('recommendation_issue',parent.pk,{'title':parent.title,'items':[row],'body_blocks':[]},actor)
    ledger._publish_revision(revision,actor)
    parent.active_revision, parent.display_from, parent.published_at = revision, timezone.now(), timezone.now()
    parent.save()
    return parent, revision


def test_new_save_captures_published_selection_not_client_override(admin_user,settings,tmp_path):
    edition, _ = material(admin_user,settings,tmp_path,['mobile'])
    parent = ledger.create_issue({'title':'合成新稿','items':[{'kind':'catalog','work_id':str(edition.work_id),
        'edition_id':str(edition.pk),'cover_display_uses':['share']}]},admin_user)
    assert ledger.issue_draft_payload(parent)['items'][0]['cover_display_uses'] == ['mobile']


@pytest.mark.parametrize('uses',[[],['mobile'],['detail','list']])
def test_original_article_uses_do_not_follow_a_later_book_cover(admin_user,settings,tmp_path,uses):
    edition, cover = material(admin_user,settings,tmp_path,['list','mobile'])
    parent, revision = published_issue(admin_user,edition,uses=uses,rendition=cover)
    original = deepcopy(revision.materialized_preview)
    result = ledger.issue_payload(parent,public=True,include_body=False)
    assert result['items'][0]['cover_display_uses'] == uses
    revision.refresh_from_db()
    assert revision.materialized_preview == original
    assert 'cover_path' not in result['items'][0]


def test_legacy_article_reads_original_rendition_uses_without_backfill(admin_user,settings,tmp_path):
    edition, cover = material(admin_user,settings,tmp_path,['mobile'])
    parent, revision = published_issue(admin_user,edition,rendition=cover)
    assert ledger.issue_payload(parent,public=True,include_body=False)['items'][0]['cover_display_uses'] == ['mobile']
    revision.refresh_from_db()
    assert 'cover_display_uses' not in revision.materialized_preview['items'][0]


def test_withdrawn_edition_clears_old_cached_image_address(admin_user,settings,tmp_path):
    edition, cover = material(admin_user,settings,tmp_path,['list','mobile'])
    parent, _ = published_issue(admin_user,edition,uses=['list'],rendition=cover,cached_url='/synthetic/old-image.jpg')
    Edition.objects.filter(pk=edition.pk).update(state='withdrawn')
    row = ledger.issue_payload(parent,public=True,include_body=False)['items'][0]
    assert row['cover_url'] == '' and row['cover_display_uses'] == [] and row['status'] == 'unavailable'
    assert 'available_edition_id' not in row and 'available_work_id' not in row


def test_linked_plan_and_related_directory_keep_effective_version_uses(admin_user,settings,tmp_path):
    edition, _ = material(admin_user,settings,tmp_path,['mobile'])
    parent, _ = published_issue(admin_user,edition,planned=True)
    assert ledger.issue_payload(parent,public=True,include_body=False)['items'][0]['cover_display_uses'] == ['mobile']
    related = directory_related([{'id':str(parent.pk),'href':'/recommendations/synthetic',
        'article_metadata':{'scholar_ids':[],'reading_path_ids':[]}}])
    assert related['materials'][0]['cover_display_uses'] == ['mobile']
