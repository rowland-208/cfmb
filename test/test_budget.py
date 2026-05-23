from cfmb.budget import PER_ROW_OVERHEAD, cap_rows, estimate_tokens


def test_estimate_tokens_uses_div_4():
    assert estimate_tokens("") == 0
    assert estimate_tokens("abc") == 0          # 3 // 4 == 0
    assert estimate_tokens("abcd") == 1
    assert estimate_tokens("a" * 40) == 10


def test_cap_rows_empty_input_returns_empty():
    assert cap_rows([], 100) == []


def test_cap_rows_all_fit_returns_all():
    rows = [{"content": "a" * 12}, {"content": "b" * 12}]   # each: 3 + 8 = 11 tokens
    out = cap_rows(rows, budget_tokens=100)
    assert out == rows


def test_cap_rows_drops_after_budget_in_input_order():
    rows = [
        {"content": "a" * 40},   # 10 + 8 = 18
        {"content": "b" * 40},   # 18  (total 36)
        {"content": "c" * 40},   # 18  (would exceed 50)
    ]
    out = cap_rows(rows, budget_tokens=50)
    assert [r["content"] for r in out] == ["a" * 40, "b" * 40]


def test_cap_rows_first_row_exceeds_budget_returns_empty():
    rows = [{"content": "x" * 1000}]
    assert cap_rows(rows, budget_tokens=10) == []


def test_cap_rows_respects_per_row_overhead():
    # Three rows of 4-char content: each costs 1 + 8 = 9 tokens.
    rows = [{"content": "abcd"} for _ in range(5)]
    # Budget 20 fits 2 (cost 18), not 3 (cost 27).
    out = cap_rows(rows, budget_tokens=20)
    assert len(out) == 2


def test_cap_rows_custom_content_key():
    rows = [{"body": "a" * 12}, {"body": "b" * 12}]
    out = cap_rows(rows, budget_tokens=100, content_key="body")
    assert out == rows


def test_per_row_overhead_constant_is_documented():
    # Guards against silent changes.
    assert PER_ROW_OVERHEAD == 8
