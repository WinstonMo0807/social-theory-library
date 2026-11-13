"""Question recall ranks source text; metadata scopes stay explicit."""
import pytest
from catalog.services import discovery_projection as projection
from tests.test_discovery_sessions_v308 import fixture_source

pytestmark=pytest.mark.django_db


def setup_recall(monkeypatch):
    _,_,_,docs=fixture_source(2)
    calls=[]
    monkeypatch.setattr(projection,'normalize_texts',lambda texts:{'texts':texts})
    monkeypatch.setattr(projection,'embed_texts',lambda *args,**kwargs:{'vectors':[[1.0]+[0.0]*383]})
    def search(method,path,payload,**kwargs):
        calls.append(payload)
        chosen=docs[1] if 'vector' in payload or payload['attributesToSearchOn']!=['normalized_text'] else docs[0]
        return {'hits':[{'id':str(chosen.pk),'source_revision':chosen.source_revision}]}
    monkeypatch.setattr(projection,'meili',search)
    return docs,calls


def test_question_recalls_original_text_without_changing_the_semantic_question(monkeypatch):
    docs,calls=setup_recall(monkeypatch)
    question='共同体边界是如何形成的？'
    semantic_queries=[]
    def embed(texts,**kwargs):
        semantic_queries.extend(texts)
        return {'vectors':[[1.0]+[0.0]*383]}
    monkeypatch.setattr(projection,'embed_texts',embed)
    result=projection.discovery_candidates(question,'passages',{},['public'])
    assert calls[0]['q']==question and calls[0]['attributesToSearchOn']==['normalized_text']
    assert [row['id'] for row in result['sparse']]==[str(docs[0].pk)]
    assert [row['id'] for row in result['dense']]==[str(docs[1].pk)]
    assert len(calls)==3 and calls[-1]['hybrid']['semanticRatio']==1.0
    assert semantic_queries==[question]
    assert calls[1]['q']==question.rstrip('？')
    assert all('scope_token IN' in ' '.join(call['filter']) for call in calls)


@pytest.mark.parametrize('scope,field',[('title','title'),('authors','authors'),('terms','normalized_text')])
def test_explicit_field_scopes_keep_their_original_meaning(monkeypatch,scope,field):
    _,calls=setup_recall(monkeypatch)
    result=projection.discovery_candidates('明确字段条件','passages',{'search_scope':scope},['public'])
    assert len(calls)==1 and calls[0]['attributesToSearchOn']==[field]
    assert result['dense']==[]


@pytest.mark.parametrize('branch',['keyword','dense'])
def test_cutoff_placeholders_never_enter_candidate_fusion(monkeypatch,branch):
    docs,calls=setup_recall(monkeypatch)
    def search(method,path,payload,**kwargs):
        assert payload['showRankingScoreDetails'] is True
        current='dense' if 'vector' in payload else 'keyword'
        return {'hits':[{'id':str(docs[0].pk),'source_revision':docs[0].source_revision,
                         '_rankingScoreDetails':{'words':{'order':0,'score':0.5}}},
                        {'id':str(docs[1].pk),'source_revision':docs[1].source_revision,
                         '_rankingScoreDetails':{'skipped':{'order':0}} if current==branch else {'words':{'order':0,'score':0.2}}}]}
    monkeypatch.setattr(projection,'meili',search)
    result=projection.discovery_candidates('没有预设的问题','passages',{},['public'])
    key='dense' if branch=='dense' else 'sparse'
    assert [row['id'] for row in result[key]]==[str(docs[0].pk)]
    assert any(row['code']==branch+'_sort_incomplete' for row in result['warnings'])
