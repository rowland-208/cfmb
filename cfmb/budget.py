PER_ROW_OVERHEAD = 8


def estimate_tokens(text: str) -> int:
    """Spec-mandated `len(text) // 4` token heuristic."""
    return len(text) // 4


def cap_rows(rows: list[dict], budget_tokens: int, content_key: str = "content") -> list[dict]:
    """Walks rows in input order, keeps as many as fit under the budget.

    When callers pass rows newest-first, this keeps the newest and drops the oldest
    once the budget is exhausted. Returns the kept rows in the same input order.
    """
    kept: list[dict] = []
    used = 0
    for row in rows:
        cost = estimate_tokens(row[content_key]) + PER_ROW_OVERHEAD
        if used + cost > budget_tokens:
            break
        kept.append(row)
        used += cost
    return kept
