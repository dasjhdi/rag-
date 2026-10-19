"""SU-17 约束推理集成测试（离线）。"""

from dataclasses import dataclass, field
from types import SimpleNamespace

from langchain_core.documents import Document

from app.conversation.types import ChatContext, ExtraOptions
from app.reasoning.constraints import constraint_reasoner
from app.reasoning.constraints.models import ConstraintDecision
from app.reasoning.constraints.service import rebuild_retrieval_result


@dataclass
class _FakeRetrieval:
    original_query: str
    rewritten_query: str
    context: str
    documents: list = field(default_factory=list)
    sources: list = field(default_factory=list)


def _ctx():
    return ChatContext(
        conv_id="c1",
        message="我对花生过敏",
        user_id=None,
        options=ExtraOptions(),
        history=[],
        history_dicts=[],
        history_text="",
        compressed_summary=None,
        compressed_count=0,
    )


def _doc(doc_id, title, content):
    return Document(
        page_content=content,
        metadata={"id": doc_id, "dish_name": title},
    )


def test_chat_context_has_constraint_fields():
    ctx = _ctx()
    assert ctx.constraint_context == ""
    assert ctx.constraint_decision is None


def test_analyze_writes_prompt_block():
    decision = constraint_reasoner.analyze(
        text="我对花生过敏",
        slots=SimpleNamespace(
            diet_constraints=["花生过敏"], ingredients=[], tastes=[]
        ),
    )
    assert decision.has_constraints
    assert decision.hard_count >= 1
    assert "过敏原" in decision.prompt_block


def test_no_constraint_keeps_empty_context():
    decision = constraint_reasoner.analyze(text="今天天气不错")
    assert not decision.has_constraints
    assert decision.prompt_block == ""


def test_filtering_updates_documents_context_and_sources():
    decision = constraint_reasoner.analyze(text="我对花生过敏")
    docs = [
        _doc("d1", "宫保鸡丁", "## 必备原料和工具\n- 花生米\n- 鸡胸肉"),
        _doc("d2", "清蒸鸡", "## 必备原料和工具\n- 鸡肉\n- 姜"),
    ]
    retrieval = _FakeRetrieval(
        original_query="花生过敏",
        rewritten_query="花生过敏",
        context="\n\n".join(doc.page_content for doc in docs),
        documents=docs,
        sources=[{"info": "旧来源"}],
    )

    decision = constraint_reasoner.evaluate_documents(docs, decision)
    filtered = rebuild_retrieval_result(
        retrieval,
        decision,
        lambda items: [{"info": item.metadata["dish_name"]} for item in items],
    )

    assert [doc.metadata["id"] for doc in filtered.documents] == ["d2"]
    assert "花生米" not in filtered.context
    assert filtered.sources == [{"info": "清蒸鸡"}]
    assert decision.removed_ids == ["d1"]


def test_prompt_mentions_unknown_candidates():
    decision = constraint_reasoner.analyze(text="我对花生过敏")
    docs = [
        _doc("d1", "神秘料理", ""),
        _doc("d2", "清蒸鸡", "## 必备原料和工具\n- 鸡肉"),
    ]
    decision = constraint_reasoner.evaluate_documents(docs, decision)
    assert "无法确认" in decision.prompt_block


def test_prompt_mentions_fallback():
    decision = constraint_reasoner.analyze(text="我对花生过敏")
    docs = [_doc("d1", "宫保鸡丁", "## 必备原料和工具\n- 花生米")]
    decision = constraint_reasoner.evaluate_documents(docs, decision)
    assert decision.fallback_used
    assert "回退" in decision.prompt_block


def test_analysis_failure_degrades_to_empty_decision(monkeypatch):
    def boom(**kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(
        "app.reasoning.constraints.service.parse_constraints", boom
    )
    decision = constraint_reasoner.analyze(text="花生过敏")
    assert isinstance(decision, ConstraintDecision)
    assert not decision.has_constraints
