"""
Unit test for Reciprocal Rank Fusion logic.
Tests the ranking algorithm in isolation, no DB needed.
"""



def reciprocal_rank_fusion(
    semantic: list[str],
    keyword: list[str],
    k: int = 60,
) -> list[tuple[str, float]]:
    """Standalone RRF for testing (mirrors search_tool.py logic)."""
    scores: dict[str, float] = {}
    for rank, pid in enumerate(semantic):
        scores[pid] = scores.get(pid, 0) + 1 / (k + rank + 1)
    for rank, pid in enumerate(keyword):
        scores[pid] = scores.get(pid, 0) + 1 / (k + rank + 1)
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)


def test_rrf_boosts_items_in_both_lists():
    """Item appearing in both lists should rank higher than items in only one."""
    semantic = ["A", "B", "C"]
    keyword  = ["B", "D", "E"]
    results = reciprocal_rank_fusion(semantic, keyword)
    ids = [r[0] for r in results]
    # B appears in both → should be top 2
    assert ids.index("B") < ids.index("A")
    assert ids.index("B") < ids.index("D")


def test_rrf_all_items_present():
    """No items should be lost."""
    semantic = ["A", "B"]
    keyword  = ["C", "D"]
    results = reciprocal_rank_fusion(semantic, keyword)
    assert {r[0] for r in results} == {"A", "B", "C", "D"}


def test_rrf_empty_keyword_list():
    """Should work with only semantic results."""
    semantic = ["A", "B", "C"]
    results = reciprocal_rank_fusion(semantic, [])
    assert [r[0] for r in results] == ["A", "B", "C"]
