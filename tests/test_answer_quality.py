"""回答质量相关：输出预算、诚实降级、提示词骨架。

只依赖纯逻辑模块（answer_policy / prompts），不导入 RAG 服务与模型客户端，
因此测试不会触发 embedding 模型加载。
"""

from types import SimpleNamespace

from app.conversation.answer_policy import (
    DEFAULT_MAX_TOKENS,
    INTENT_MAX_TOKENS,
    build_context_prompt,
    history_for_llm,
    max_tokens_for,
)
from app.conversation.prompts import SYSTEM_PROMPT


class TestOutputBudget:
    def test_each_intent_has_budget(self):
        assert INTENT_MAX_TOKENS, "意图预算表不能为空"
        for intent, expected in INTENT_MAX_TOKENS.items():
            assert max_tokens_for(SimpleNamespace(intent=SimpleNamespace(value=intent))) == expected

    def test_unknown_intent_falls_back(self):
        assert (
            max_tokens_for(SimpleNamespace(intent=SimpleNamespace(value="something_new")))
            == DEFAULT_MAX_TOKENS
        )

    def test_missing_intent_falls_back(self):
        assert max_tokens_for(None) == DEFAULT_MAX_TOKENS

    def test_recipe_budget_is_largest(self):
        """菜谱要装下步骤，预算必须比闲聊宽。"""
        assert INTENT_MAX_TOKENS["recipe_search"] > INTENT_MAX_TOKENS["general_chat"]

    def test_budget_stays_within_reasonable_range(self):
        """太小会截断步骤，太大则失去收窄的意义。"""
        assert all(600 <= value <= 2000 for value in INTENT_MAX_TOKENS.values())


class TestHonestDegradation:
    def test_empty_retrieval_adds_warning(self):
        prompt = build_context_prompt(
            rag_context="",
            web_context="",
            rewritten_query="佛跳墙",
            retrieval_empty=True,
        )
        assert "知识库未命中" in prompt
        assert "没有找到对应的菜谱" in prompt
        # 必须明确禁止编造精确数值
        assert "不要给出精确时间、温度、克数" in prompt

    def test_hit_does_not_add_warning(self):
        prompt = build_context_prompt(
            rag_context="[1] 《红烧肉》\n正文",
            web_context="",
            rewritten_query="红烧肉",
            retrieval_empty=False,
        )
        assert "知识库未命中" not in prompt
        assert "红烧肉" in prompt

    def test_empty_retrieval_with_web_marks_source(self):
        prompt = build_context_prompt(
            rag_context="",
            web_context="某站的做法：小火 40 分钟",
            rewritten_query="佛跳墙",
            retrieval_empty=True,
        )
        assert "知识库命中情况" in prompt
        assert "来自网络搜索" in prompt
        # 有网搜结果时不应再要求「只给通用原则」
        assert "知识库未命中（必须遵守）" not in prompt

    def test_ordering_puts_constraints_before_knowledge(self):
        prompt = build_context_prompt(
            rag_context="[1] 《红烧肉》",
            web_context="",
            rewritten_query="红烧肉",
            constraint_context="用户不吃猪肉",
        )
        assert prompt.index("饮食约束") < prompt.index("本地知识库资料")


class TestPromptStructure:
    def test_answer_skeleton_present(self):
        assert "<answer_structure>" in SYSTEM_PROMPT
        for section in ("一句话结论", "关键参数", "失败补救"):
            assert section in SYSTEM_PROMPT

    def test_history_citation_rule_present(self):
        assert "历史消息里的 [编号] 不要沿用" in SYSTEM_PROMPT

    def test_emoji_limited_to_tone_sentences(self):
        assert "步骤、参数、警告里不要用" in SYSTEM_PROMPT


class TestHistoryTrim:
    """历史消息不再携带来源附录：每轮少传最多 5×8KB。"""

    def test_sources_appendix_not_injected(self):
        history = [
            {"role": "user", "content": "红烧肉怎么做"},
            {
                "role": "assistant",
                "content": "先焯水再炒糖色 [1]",
                "sources": [{"type": "rag", "info": "很长的资料" * 2000, "index": 1}],
            },
        ]
        trimmed = history_for_llm(history)
        assert "[参考来源" not in trimmed[1]["content"]
        assert "很长的资料" not in trimmed[1]["content"]
        # 上一轮的引用角标要去掉，避免跨轮指向不存在的来源
        assert trimmed[1]["content"] == "先焯水再炒糖色"
        assert [item["role"] for item in trimmed] == ["user", "assistant"]

    def test_user_citations_untouched(self):
        trimmed = history_for_llm([{"role": "user", "content": "第 [2] 步是什么"}])
        assert trimmed[0]["content"] == "第 [2] 步是什么"

    def test_only_role_and_content_kept(self):
        trimmed = history_for_llm(
            [{"role": "assistant", "content": "x", "sources": [{"info": "y"}]}]
        )
        assert set(trimmed[0]) == {"role", "content"}


class TestIntentFallback:
    """模型不可用时的关键词兜底：做菜问题仍要检索，闲聊才不检索。"""

    @staticmethod
    def _detector():
        from app.conversation.intent import IntentDetector

        # 不实例化，避免创建模型客户端；被测方法不依赖实例状态
        return object.__new__(IntentDetector)

    def test_recipe_question_still_retrieves(self):
        result = self._detector()._safe_default("红烧肉怎么做？")
        assert result.need_rag is True
        assert result.intent.value == "recipe_search"
        assert result.needs_clarification is False

    def test_cooking_question_uses_tips_intent(self):
        result = self._detector()._safe_default("炖肉的火候怎么掌握")
        assert result.need_rag is True
        assert result.intent.value == "cooking_tips"

    def test_chitchat_does_not_retrieve(self):
        result = self._detector()._safe_default("你好呀")
        assert result.need_rag is False
        assert result.intent.value == "general_chat"

    def test_empty_query_does_not_retrieve(self):
        assert self._detector()._safe_default("").need_rag is False


class TestNoSourceNoCitation:
    def test_empty_context_forbids_citation_markers(self):
        prompt = build_context_prompt(
            rag_context="",
            web_context="",
            rewritten_query="",
        )
        assert "不要出现 [编号]" in prompt

    def test_with_knowledge_no_forbidden_block(self):
        prompt = build_context_prompt(
            rag_context="[1] 《红烧肉》",
            web_context="",
            rewritten_query="红烧肉",
        )
        assert "不要出现 [编号]" not in prompt


class TestFollowUpFallback:
    def test_follow_up_question_still_retrieves(self):
        from app.conversation.intent import IntentDetector

        detector = object.__new__(IntentDetector)
        result = detector._safe_default("那如果番茄太酸怎么办？")
        assert result.need_rag is True
