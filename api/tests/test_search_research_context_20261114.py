"""Per-turn materials remain private, bounded, idempotent and independent of scope."""
from types import SimpleNamespace
from uuid import uuid4
import pytest
from rest_framework.exceptions import ValidationError, NotFound
from reading import research
from reading.research_serializers import TurnCreateInput
from tests.test_discovery_sessions_v308 import fixture_source

pytestmark = pytest.mark.django_db

def test_selected_passages_keep_distinct_offsets(reader_user):
    _, _, spans, _ = fixture_source(count=1)
    raw = {'evidence_span_id': str(spans[0].id)}
    source = research.resolve_reference(raw, reader_user, strict=True)['quote']
    first, second = source[:8], source[-8:]
    refs = research.references([{**raw, 'selected_text':first}, {**raw, 'selected_text':second}], reader_user)
    assert len(refs) == 2
    assert research.resolve_reference(refs[0], reader_user, strict=True)['quote'] == first
    assert research.resolve_reference(refs[1], reader_user, strict=True)['quote'] == second
    assert refs[0]['selection_start'] != refs[1]['selection_start']
    with pytest.raises(ValidationError):
        research.references([{**raw, 'selected_text':'不存在的原文禁止伪造'}], reader_user)

def test_context_snapshot_is_independent_and_retry_immutable(reader_user, admin_user, monkeypatch):
    monkeypatch.setattr('reading.tasks.enqueue_research_turn', lambda *args, **kwargs: None)
    _, _, spans, _ = fixture_source(count=2)
    refs = [{'evidence_span_id': str(row.id)} for row in spans]
    project = research.create_project(reader_user, {'request_id':str(uuid4()),'title':'限定研究'})
    project = research.change_selection(reader_user, project.id, {'expected_revision':project.revision,'action':'add','references':refs})
    data={'request_id':str(uuid4()),'expected_revision':project.revision,'question':'共同利益有哪些边界？',
          'scope':{'kind':'passages','references':[refs[0]]},'context_refs':[refs[1]]}
    turn=research.start_turn(SimpleNamespace(user=reader_user),project.id,data)
    saved=research.unpack(turn)
    assert saved['context_explicit'] is True
    assert saved['selected_refs'][0]['evidence_span_id']==str(spans[1].id)
    assert saved['scope']['references'][0]['evidence_span_id']==str(spans[0].id)
    assert research.start_turn(SimpleNamespace(user=reader_user),project.id,data).id==turn.id
    with pytest.raises(research.ResearchConflict):
        research.start_turn(SimpleNamespace(user=reader_user),project.id,{**data,'context_refs':[]})
    with pytest.raises(NotFound):
        research.start_turn(SimpleNamespace(user=admin_user),project.id,data)
    project.refresh_from_db()
    following=research.start_turn(SimpleNamespace(user=reader_user),project.id,{
        'request_id':str(uuid4()),'expected_revision':project.revision,'question':'还有哪些条件？','parent_id':str(turn.id),'context_refs':[]})
    assert research.unpack(following)['scope']==saved['scope']
    assert research.unpack(following)['selected_refs']==[]
    turn.refresh_from_db()
    assert research.unpack(turn)==saved
    project.refresh_from_db()
    assert len(research.unpack(project)['selections'])==2

def test_context_count_and_stale_source_rejected(reader_user, monkeypatch):
    monkeypatch.setattr('reading.tasks.enqueue_research_turn', lambda *args, **kwargs: None)
    edition, _, spans, _=fixture_source(count=1)
    ref={'evidence_span_id':str(spans[0].id)}
    project=research.create_project(reader_user,{'request_id':str(uuid4()),'title':'边界'})
    body={'request_id':str(uuid4()),'expected_revision':project.revision,'question':'原文条件？','context_refs':[ref]*21}
    serializer=TurnCreateInput(data=body)
    assert not serializer.is_valid() and 'context_refs' in serializer.errors
    with pytest.raises(ValidationError):research.start_turn(SimpleNamespace(user=reader_user),project.id,body)
    spans[0].is_stale=True
    spans[0].save(update_fields=['is_stale'])
    with pytest.raises(ValidationError):research.start_turn(SimpleNamespace(user=reader_user),project.id,{**body,'context_refs':[ref]})
    assert project.turns.count()==0
