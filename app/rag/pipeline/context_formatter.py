"""把检索结果格式化成「可引用」的上下文。

为什么单独抽出来：
- 检索（rag_service）与约束过滤后的重建（constraints.service）都会生成上下文，
  两处必须用同一套编号规则，否则回答里的 [2] 可能指向另一道菜。
- 编号按「来源」而非「文本块」分配：同一道菜被切成多个 chunk 时共用同一个编号，
  与前端展示的来源卡片一一对应。
"""

from __future__ import annotations

from typing import Any, Iterable, Optional

DEFAULT_SOURCE_TITLE = "CookHero 知识库"


def source_title(document: Any) -> str:
    """从文档元数据里取一个可展示、可用于引用的标题。"""
    metadata = getattr(document, "metadata", None) or {}
    title = (
        metadata.get("dish_name")
        or metadata.get("title")
        or metadata.get("source_title")
        or metadata.get("category")
    )
    text = str(title).strip() if title else ""
    return text or DEFAULT_SOURCE_TITLE


def _source_meta(document: Any) -> str:
    """拼一个简短的副标题（分类 · 难度），没有就留空。"""
    metadata = getattr(document, "metadata", None) or {}
    bits = []
    for key in ("category", "difficulty"):
        value = metadata.get(key)
        if value:
            bits.append(str(value).strip())
    return " · ".join(bits)


def build_index_map(sources: Optional[Iterable[dict]]) -> dict[str, int]:
    """来源标题 -> 引用编号。"""
    mapping: dict[str, int] = {}
    for position, source in enumerate(sources or [], start=1):
        if not isinstance(source, dict):
            continue
        if source.get("type", "rag") != "rag":
            continue
        info = str(source.get("info") or "").strip()
        if not info:
            continue
        index = source.get("index")
        mapping[info] = int(index) if isinstance(index, int) and index > 0 else position
    return mapping


def format_numbered_context(
    documents: Iterable[Any],
    sources: Optional[Iterable[dict]] = None,
) -> str:
    """生成带 ``[n] 《标题》`` 头的上下文，供模型按编号引用。"""
    docs = list(documents or [])
    if not docs:
        return ""

    index_map = build_index_map(sources)
    next_index = max(index_map.values(), default=0) + 1

    blocks: list[str] = []
    for document in docs:
        title = source_title(document)
        index = index_map.get(title)
        if index is None:
            index = next_index
            index_map[title] = index
            next_index += 1

        meta = _source_meta(document)
        header = f"[{index}] 《{title}》" + (f"（{meta}）" if meta else "")
        content = str(getattr(document, "page_content", "") or "").strip()
        blocks.append(f"{header}\n{content}" if content else header)

    return "\n\n".join(blocks)
