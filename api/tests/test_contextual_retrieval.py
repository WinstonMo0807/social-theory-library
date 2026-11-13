from catalog.services.retrieval.contextual import passage_context, embedding_input


def test_context_does_not_rewrite_evidence_or_infer_claimant():
    exact="甲😀乙\n原文  空白"
    context=passage_context({"title":"论集", "authors":["编者"]}, {"chapter_path":["第一章", "批评与回应"], "node_kind":"footnote"})
    assert "批评与回应" in context and "注释" in context and "编者" not in context
    assert embedding_input(context, exact).endswith(exact)


def test_context_branch_shares_rrf_and_source_validation(monkeypatch):
    from catalog.services import discovery_projection as projection, discovery_sessions as sessions
    from catalog.services.retrieval import locators
    from catalog.services.retrieval.search import retrieve_channel
    one={"id":"one", "excerpt":"原文一"}; two={"id":"two", "excerpt":"原文二"}
    monkeypatch.setattr(projection,"discovery_candidates",lambda *a,**k:{"sparse":[one],"dense":[],"contextual":[two],"warnings":[]})
    checked=[]
    def validate(channel, rows, *args, **kwargs):
        checked.append([r["id"] for r in rows]); return rows
    monkeypatch.setattr(projection,"validate_discovery_results",validate)
    monkeypatch.setattr(sessions,"_deduplicate",lambda rows:rows)
    monkeypatch.setattr(sessions,"_diverse_prefix",lambda rows,**kwargs:rows)
    monkeypatch.setattr(locators,"attach_locators",lambda rows:rows)
    result=retrieve_channel("研究问题", "passages", {"_keyword_only":True}, ["public"])
    assert [r["id"] for r in result["rows"]] == ["one","two"]
    assert len(checked) == 2 and result["retrieval"]["candidates"]["contextual"] == 1
