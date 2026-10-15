"""Fit an experimental context window using the actual reranker tokenizer."""
CONTEXT_POLICY = "adjacent-evidence-v1"


def fit_context(tokenizer, query, hit, before, after, *, max_tokens=512):
    # Do not silently remove a comparison target or a negation in the question.
    if len(tokenizer.encode(query, add_special_tokens=False).ids) > 128:
        raise ValueError("context_query_budget")
    count = lambda text: len(tokenizer.encode(query, pair=text).ids)
    if count(hit) > max_tokens:
        raise ValueError("context_hit_budget")
    remaining = max(0, max_tokens - count(hit) - 4)
    left = tokenizer.encode(before, add_special_tokens=False)
    right = tokenizer.encode(after, add_special_tokens=False)
    left_budget = min(len(left.ids), remaining // 2)
    right_budget = min(len(right.ids), remaining - left_budget)
    left_budget = min(len(left.ids), remaining - right_budget)
    before_part = before[left.offsets[-left_budget][0]:] if left_budget else ""
    after_part = after[:right.offsets[right_budget - 1][1]] if right_budget else ""
    def joined():
        return "\n".join(part for part in (before_part, hit, after_part) if part)
    text = joined()
    # Retokenizing at boundaries can change token counts. Only trim neighbours.
    while count(text) > max_tokens and (before_part or after_part):
        if len(before_part) > len(after_part):
            before_part = before_part[1:]
        else:
            after_part = after_part[:-1]
        text = joined()
    return text, before_part != before or after_part != after
