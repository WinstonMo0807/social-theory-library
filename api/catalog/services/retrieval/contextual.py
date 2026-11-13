"""Source-grounded contextual retrieval; derived context is never a quotation.

Uses the contextual retrieval pattern (Anthropic, 2024), with deterministic
book/section metadata instead of an unconfigured generative model. The raw
slice and code-point offsets remain the only source for evidence locators.
"""

CONTEXT_VERSION = 1


def passage_context(header, metadata):
    path = [str(title) for title in metadata.get("chapter_path", []) if title]
    # Book responsibilities do not establish the claimant of this passage.
    labels = ["作品：" + header.get("title", "")]
    if path:
        labels.append("章节：" + " / ".join(path))
    kind = metadata.get("node_kind")
    if kind in {"footnote", "references", "table"}:
        labels.append("材料类型：" + {"footnote":"注释", "references":"参考文献", "table":"表格"}[kind])
    return "\n".join(labels)


def embedding_input(context, exact):
    return f"passage: {context}\n原文：{exact}"
