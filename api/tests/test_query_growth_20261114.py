from datetime import timedelta
from uuid import uuid4
from unittest.mock import patch
import pytest
from django.utils import timezone
from catalog.models import Contribution, Edition, EditorialRevision, KnowledgeNode, Person, ScholarProfile, Work, WorkNodeRelation, RecommendationPolicy, RecommendationSnapshot
from catalog.services.public_scholars import _knowledge, scholar_editions
from catalog.services.recommendations import current_recommendations
from .v304_helpers import activate_catalog_revision

pytestmark=pytest.mark.django_db

def test_knowledge_matches_published_whole_author_and_rechecks_withdrawal():
    person=Person.objects.create(preferred_name='Query fixture',authority_status='verified')
    profile=ScholarProfile.objects.create(person=person,slug='query-fixture',editorial_status='published')
    node=KnowledgeNode.objects.create(canonical_name_zh='Query fixture node',slug='query-fixture-node',node_type='concept',status='published')
    work=Work.objects.create(title='Query fixture work')
    WorkNodeRelation.objects.create(work=work,node=node,status='published')
    edition=Edition.objects.create(work=work,state='published',is_primary=True,public_slug='query-fixture-work')
    contribution=Contribution.objects.create(edition=edition,person=person,role='author',approved=True)
    activate_catalog_revision(edition,fulltext_ready=False)
    assert list(_knowledge(profile,scholar_editions(person.pk)).values_list('pk',flat=True))==[node.pk]
    contribution.role='editor';contribution.save()
    assert list(_knowledge(profile,scholar_editions(person.pk)).values_list('pk',flat=True))==[node.pk]
    # A version activation in between the bounded read and the final lookup must
    # not reinterpret the new editor-only snapshot as whole-book authorship.
    from catalog.services.publication_eligibility import public_editions
    from catalog.models import CatalogPublicationRevision
    calls=0
    def changed_public_editions():
        nonlocal calls
        calls+=1
        if calls==2:
            CatalogPublicationRevision.objects.filter(edition=edition,status='active').update(status='superseded')
            activate_catalog_revision(edition,fulltext_ready=False)
        return public_editions()
    editions=scholar_editions(person.pk)
    with patch('catalog.services.public_scholars.public_editions',side_effect=changed_public_editions):
        assert not _knowledge(profile,editions).exists()
    assert calls==2
    assert not _knowledge(profile,scholar_editions(person.pk)).exists()

def test_recommendation_filter_does_not_read_or_create_other_placements():
    now=timezone.now()
    for placement in ('home_scholars','home_topics','home_random'):
        policy,_=RecommendationPolicy.objects.get_or_create(placement=placement,defaults={'title':placement})
        RecommendationSnapshot.objects.create(policy=policy,starts_at=now-timedelta(hours=1),expires_at=now+timedelta(hours=1))
    counts=RecommendationPolicy.objects.count(),RecommendationSnapshot.objects.count()
    all_rows=current_recommendations(read_only=True)
    rows=current_recommendations(read_only=True,placements=('home_topics',))
    assert set(rows)=={'home_topics'} and rows['home_topics'].pk==all_rows['home_topics'].pk
    assert current_recommendations(read_only=True,placements=())=={}
    assert (RecommendationPolicy.objects.count(),RecommendationSnapshot.objects.count())==counts
