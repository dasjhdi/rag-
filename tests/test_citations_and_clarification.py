"""引用编号与澄清判定的单元测试。"""

from types import SimpleNamespace

from app.rag.pipeline.context_formatter import (
    build_index_map,
    format_numbered_context,
    source_title,
)


def _doc(title: str, content: str, **metadata):
    return SimpleNamespace(
        page_content=content,
        metadata={"dish_name": title, **metadata},
    )


class TestContextFormatter:
    def test_uses_source_index_for_numbering(self):
        sources = [
            {"type": "rag", "info": "红烧肉", "index": 1},
            {"type": "rag", "info": "番茄炒蛋", "index": 2},
        ]
        docs = [_doc("红烧肉", "五花肉切块"), _doc("番茄炒蛋", "番茄切块")]

        context = format_numbered_context(docs, sources)

        assert context.startswith("[1] 《红烧肉》")
        assert "[2] 《番茄炒蛋》" in context
        assert "五花肉切块" in context

    def test_same_dish_shares_one_number(self):
        """同一道菜被切成多个 chunk 时，应共用同一个引用编号。"""
        sources = [{"type": "rag", "info": "红烧肉", "index": 1}]
        docs = [
            _doc("红烧肉", "第一段"),
            _doc("红烧肉", "第二段"),
            _doc("番茄炒蛋", "第三段"),
        ]

        context = format_numbered_context(docs, sources)

        assert context.count("[1] 《红烧肉》") == 2
        # 未出现在 sources 里的文档顺延编号，避免与已有编号冲突
        assert "[2] 《番茄炒蛋》" in context

    def test_header_includes_metadata(self):
        docs = [_doc("红烧肉", "正文", category="荤菜", difficulty="简单")]
        context = format_numbered_context(docs, [])
        assert "[1] 《红烧肉》（荤菜 · 简单）" in context

    def test_empty_documents(self):
        assert format_numbered_context([], []) == ""

    def test_falls_back_to_category(self):
        doc = SimpleNamespace(page_content="x", metadata={"category": "烹饪技巧"})
        assert source_title(doc) == "烹饪技巧"

    def test_index_map_skips_web_sources(self):
        mapping = build_index_map(
            [
                {"type": "web", "info": "某网页", "index": 1},
                {"type": "rag", "info": "红烧肉", "index": 2},
            ]
        )
        assert mapping == {"红烧肉": 2}


class TestClarificationDecision:
    """`_build_clarification` 不依赖实例状态，可直接以空 self 调用。"""

    @staticmethod
    def _decide(intent, constraint=None):
        from app.services.conversation_service import ConversationService

        ctx = SimpleNamespace(constraint_decision=constraint)
        return ConversationService._build_clarification(object(), intent, ctx)

    def test_constraint_conflict_wins(self):
        decision = SimpleNamespace(
            needs_clarification=True,
            clarification_question="你标注了纯素，但提到了鸡蛋，要按蛋奶素处理吗？",
        )
        intent = SimpleNamespace(needs_clarification=False, need_rag=True, slots=None)
        assert "鸡蛋" in self._decide(intent, decision)

    def test_low_confidence_without_slots_asks(self):
        intent = SimpleNamespace(
            needs_clarification=True,
            need_rag=True,
            slots=SimpleNamespace(dish_names=[], ingredients=[]),
        )
        assert "确认" in self._decide(intent)

    def test_low_confidence_with_dish_answers_directly(self):
        intent = SimpleNamespace(
            needs_clarification=True,
            need_rag=True,
            slots=SimpleNamespace(dish_names=["红烧肉"], ingredients=[]),
        )
        assert self._decide(intent) is None

    def test_chitchat_is_not_interrupted(self):
        intent = SimpleNamespace(
            needs_clarification=True,
            need_rag=False,
            slots=SimpleNamespace(dish_names=[], ingredients=[]),
        )
        assert self._decide(intent) is None

    def test_confident_intent_passes_through(self):
        intent = SimpleNamespace(
            needs_clarification=False,
            need_rag=True,
            slots=SimpleNamespace(dish_names=[], ingredients=[]),
        )
        assert self._decide(intent) is None


class TestClarificationHandler:
    """澄清分支必须发出 sources/text/done，并把问题落库。"""

    @staticmethod
    def _make_service(saved: dict):
        from app.services.conversation_service import ConversationService

        service = ConversationService.__new__(ConversationService)

        async def fake_save(ctx, text, intent_result):
            saved["text"] = text

        service._save_response = fake_save  # type: ignore[method-assign]
        return service

    def test_emits_sse_and_persists(self):
        import asyncio
        from types import SimpleNamespace

        saved: dict = {}
        service = self._make_service(saved)
        ctx = SimpleNamespace(
            conv_id="conv-1",
            thinking_steps=[],
            thinking_start_time=None,
            thinking_end_time=None,
            answer_start_time=None,
            answer_end_time=None,
        )
        intent = SimpleNamespace(intent=SimpleNamespace(value="recommendation"))

        async def collect():
            return [event async for event in service._handle_clarification(ctx, "请确认需求？", intent)]

        events = asyncio.run(collect())
        joined = "".join(events)
        assert '"type": "sources"' in joined
        assert '"type": "text"' in joined
        assert '"type": "done"' in joined
        assert saved["text"] == "请确认需求？"
