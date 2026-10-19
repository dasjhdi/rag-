"""SU-3.1 多路召回合并测试（离线）。"""

from langchain_core.documents import Document

from app.rag.pipeline.retrieval import merge_documents


def _doc(content, *, parent_id=None, source="recipes", score=0.1):
    metadata = {"data_source": source, "retrieval_score": score}
    if parent_id is not None:
        metadata["parent_id"] = parent_id
    return Document(page_content=content, metadata=metadata)


def test_merge_keeps_highest_score_for_same_parent():
    low = _doc("低分片段", parent_id="p1", score=0.2)
    high = _doc("高分片段", parent_id="p1", score=0.9)

    merged = merge_documents([low, high])

    assert len(merged) == 1
    assert merged[0].page_content == "高分片段"
    assert merged[0].metadata["retrieval_score"] == 0.9


def test_merge_sorts_by_score_descending():
    docs = [
        _doc("a", parent_id="p1", score=0.1),
        _doc("b", parent_id="p2", score=0.8),
        _doc("c", parent_id="p3", score=0.4),
    ]

    merged = merge_documents(docs)

    assert [doc.page_content for doc in merged] == ["b", "c", "a"]


def test_merge_does_not_cross_sources():
    recipe = _doc("菜谱", parent_id="same", source="recipes", score=0.5)
    personal = _doc("个人文档", parent_id="same", source="personal", score=0.4)

    merged = merge_documents([recipe, personal])

    assert len(merged) == 2


def test_merge_deduplicates_missing_parent_by_content():
    first = _doc("相同内容", score=0.3)
    second = _doc("相同内容", score=0.7)
    other = _doc("不同内容", score=0.5)

    merged = merge_documents([first, second, other])

    assert len(merged) == 2
    assert merged[0].page_content == "相同内容"
    assert merged[0].metadata["retrieval_score"] == 0.7


def test_merge_empty_returns_empty():
    assert merge_documents([]) == []


def test_merge_tolerates_bad_scores():
    bad = _doc("坏分数", parent_id="p1", score="not-a-number")
    good = _doc("好分数", parent_id="p2", score=0.5)

    merged = merge_documents([bad, good])

    assert merged[0].page_content == "好分数"
    assert len(merged) == 2
