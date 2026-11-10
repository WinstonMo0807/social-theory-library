from uuid import uuid4

import pytest
from tests.test_knowledge_core import source
from catalog import models as m
from catalog.services.knowledge_core import entity_for_legacy, match_entities
from catalog.services.intelligence_changes import submit_draft
from catalog.services.intelligence_queries import changeset_data

pytestmark = pytest.mark.django_db


def test_match_context_distinguishes_responsibility_and_source_claims(source,admin_user):
    person=m.Person.objects.create(preferred_name="同名人物")
    entity=entity_for_legacy(person)
    other=entity_for_legacy(m.Person.objects.create(preferred_name="同名人物"))
    m.Contribution.objects.create(person=person,edition=source.asset.edition,role="translator",approved=True)
    m.Contribution.objects.create(person=person,edition=source.asset.edition,role="author",approved=False)
    statements=[]
    for predicate in ["uses","criticizes"]:
        statement=m.Assertion.objects.create(text=f"来源中的{predicate}关系",predicate=predicate,status="published")
        m.AssertionParticipant.objects.create(assertion=statement,entity=entity,role="subject")
        m.AssertionSource.objects.create(assertion=statement,work=source.asset.edition.work,edition=source.asset.edition)
        statements.append(statement)
    draft=m.Assertion.objects.create(text="尚未发布的解释",predicate="inherits",status="draft")
    m.AssertionParticipant.objects.create(assertion=draft,entity=entity,role="subject")
    m.AssertionSource.objects.create(assertion=draft,work=source.asset.edition.work)
    candidates=match_entities("同名人物","person")
    assert {c["id"] for c in candidates}=={str(entity.pk),str(other.pk)}
    record=next(c for c in candidates if c["id"]==str(entity.pk))
    assert {(v["source_type"],v["role"]) for v in record["related_works"]}=={
        ("contribution","translator"),("assertion_source","uses"),("assertion_source","criticizes")}
    assert all(not c["automatic_same_identity"] for c in candidates)
    # Proposed candidate labels/context cannot spoof the actual library view.
    changeset=submit_draft(source,[{"id":str(uuid4()),"kind":"entity","dependencies":[],"payload":{
        "kind":"person","label":"同名人物","candidates":[{"id":str(entity.pk),"label":"伪造身份","related_works":[{"title":"伪造作品"}]}]}}],admin_user,request_id=uuid4())
    payload=changeset_data(changeset,admin_user)["items"][0]["payload"]
    assert payload["candidates"][0]["label"]=="同名人物"
    assert all(v["title"]==source.asset.edition.work.title for v in payload["candidates"][0]["related_works"])
    assert changeset.items.get().payload["candidates"][0]["label"]=="伪造身份"  # Original proposal remains auditable.
