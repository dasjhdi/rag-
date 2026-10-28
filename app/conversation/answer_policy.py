"""回答策略：输出预算与上下文提示拼装。

这里只放**纯字符串/纯计算**逻辑，不依赖数据库、RAG 服务或模型客户端，
便于单元测试与复用（conversation_service 只做一层薄封装）。
"""

import re
from typing import Any, Dict, List, Optional

# 每种意图的输出上限（token）。菜谱要给足步骤，闲聊不该占同样预算：
# 触顶后模型会草率收尾，所以这里取「够用且不浪费」的值，而不是越小越好。
INTENT_MAX_TOKENS: Dict[str, int] = {
    "recipe_search": 1600,
    "recommendation": 1300,
    "cooking_tips": 1200,
    "ingredient_info": 900,
    "general_chat": 700,
}
DEFAULT_MAX_TOKENS = 1400

# 知识库未命中、也没有网搜结果时的降级指令
_MISS_INSTRUCTION = (
    "【知识库未命中（必须遵守）】\n"
    "本轮没有检索到相关菜谱或资料。请按以下方式回答：\n"
    "1. 开头明确说明「知识库里没有找到对应的菜谱」；\n"
    "2. 只给通用原则、思路和判断标准，不要给出精确时间、温度、克数；\n"
    "3. 可以建议用户用菜名或主要食材换个说法再问一次。\n"
)

# 未命中但网搜有结果：允许作答，但必须标明来源且不补数值
_MISS_WITH_WEB_INSTRUCTION = (
    "【知识库命中情况】\n"
    "本轮 CookHero 知识库没有检索到对应菜谱，下面的信息来自网络搜索。\n"
    "请说明这部分内容来自网络而非菜谱库；只使用搜索资料里写明的数值，没有写就不要补。\n"
)


def max_tokens_for(intent_result: Optional[Any]) -> int:
    """按意图给出输出上限；识别不到意图时回到默认值。"""
    if intent_result is None:
        return DEFAULT_MAX_TOKENS
    intent = getattr(intent_result, "intent", None)
    key = getattr(intent, "value", None) or str(intent or "")
    return INTENT_MAX_TOKENS.get(key, DEFAULT_MAX_TOKENS)


def build_context_prompt(
    rag_context: str,
    web_context: str,
    rewritten_query: str,
    vision_context: str = "",
    constraint_context: str = "",
    retrieval_empty: bool = False,
) -> str:
    """拼装本轮给模型的上下文提示块。

    顺序即优先级：图片 → 检索语句 → 饮食约束 → 知识库资料 → 未命中提示 → 网搜。
    ``retrieval_empty`` 为真且知识库确实没内容时，会插入「诚实降级」指令，
    避免模型凭空补出精确到分钟的火候。
    """
    parts = []

    # Add vision context first (if available)
    if vision_context.strip():
        parts.append(
            "【图片工具分析结果】\n"
            "用户上传了图片，以下是工具分析结果，请参考回答：\n"
            f"{vision_context.strip()}\n"
        )

    if rewritten_query.strip():
        parts.append(f"【重写后的检索语句】\n{rewritten_query}\n")

    # Add constraint reasoning before RAG so hard constraints are prominent.
    if constraint_context.strip():
        parts.append(
            "【饮食约束推理结果】\n"
            "以下约束由确定性规则得出，请严格遵守并在回答中解释排除原因：\n"
            f"{constraint_context.strip()}\n"
        )

    # Add RAG context (local knowledge) with citation rules
    if rag_context.strip():
        parts.append(
            "【本地知识库资料（可引用）】\n"
            "每条资料以 [编号] 开头，代表一条可引用的来源。引用规则：\n"
            "1. 引用某条资料的具体内容时，在句末标注对应编号，如 [1]；\n"
            "2. 只标注真正用到的编号，不要把所有来源罗列一遍；\n"
            "3. 编号必须来自资料开头，不要自行编造；\n"
            "4. 资料未覆盖的推断不要加编号，并说明属于通用经验。\n"
            f"{rag_context.strip()}\n"
        )

    # 知识库未命中：明确要求「诚实降级」，否则模型会补出精确到分钟的火候
    if retrieval_empty and not rag_context.strip():
        parts.append(
            _MISS_WITH_WEB_INSTRUCTION if web_context.strip() else _MISS_INSTRUCTION
        )

    # Add web search context
    if web_context.strip():
        parts.append(
            "【互联网搜索工具分析结果】\n"
            "下面是从互联网搜索获取的补充信息（请注意甄别信息可靠性）：\n"
            f"{web_context.strip()}\n"
        )

    # 本轮没有资料可引用：明确禁止出现编号，避免沿用历史角标造成「点开对不上」
    if not rag_context.strip() and not web_context.strip():
        parts.append("【引用约束】本轮没有可引用的资料，回答中不要出现 [编号] 形式的引用标记。\n")

    return "\n".join(parts)


# 上一轮的引用角标，例如 [1]、[12]
_CITATION_RE = re.compile(r"\[\d{1,2}\]")


def _strip_citations(text: str) -> str:
    """去掉历史回答里的引用编号。

    上一轮的 [1] 指向上一轮的来源；本轮来源可能完全不同甚至为空，
    模型很容易照抄这个编号，用户点开却对不上。历史只保留纯正文。
    """
    cleaned = _CITATION_RE.sub("", text)
    # 去掉编号后可能留下多余空格：压缩连续空格、清理标点前与行尾的空格
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"[ \t]+(?=[，。；：！？、])", "", cleaned)
    cleaned = re.sub(r"[ \t]+$", "", cleaned, flags=re.MULTILINE)
    return cleaned


def history_for_llm(history: List[dict]) -> List[dict]:
    """把库里的历史消息裁成给模型的最小结构：只留 role + 正文。

    两件事：
    1. 不拼来源附录——来源已按消息单独存储，拼进正文会让每轮上下文重复
       携带最多 5 条来源（每条最多 8KB），多轮后纯属浪费 token；
    2. 去掉历史回答里的 [n] 角标——它们属于上一轮的来源列表，跨轮复用
       会指向不存在的资料。
    不改动落库内容。
    """
    result = []
    for item in history:
        role = item.get("role", "user")
        content = item.get("content") or ""
        if role == "assistant":
            content = _strip_citations(content)
        result.append({"role": role, "content": content})
    return result
