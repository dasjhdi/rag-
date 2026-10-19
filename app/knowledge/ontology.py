"""
食材与过敏原本体（SU-5）。

数据与逻辑分离：别名、过敏原和饮食标签存放在 ``data/ingredients.json``，
本模块只负责加载、归一化和推导。数据文件缺失或损坏时降级为空索引，
调用方不会因为知识库问题而中断主链路。
"""

from __future__ import annotations

import json
import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Optional

logger = logging.getLogger(__name__)

_DATA_PATH = Path(__file__).resolve().parent / "data" / "ingredients.json"
_WHITESPACE = re.compile(r"\s+")

# 菜名或常见短语中包含食材字面量，但本身不是该食材。
_NON_INGREDIENT_PHRASES = (
    "鱼香肉丝",
    "鱼香茄子",
    "鱼香",
    "素鸡",
    "素肉",
    "素鸭",
    "素火腿",
    "鱼豆腐",
    "蛋白质",
)

# 单字别名容易误伤，只保留明确的食材单字。
_SAFE_SINGLE_CHAR_ALIASES = frozenset(
    {"鱼", "虾", "蟹", "盐", "糖", "醋", "姜", "蒜", "葱", "米"}
)


def _clean(value: object) -> str:
    """Normalize case and whitespace for matching."""
    if not isinstance(value, str):
        return ""
    return _WHITESPACE.sub(" ", value.strip()).casefold()


@lru_cache(maxsize=1)
def _load_index() -> tuple[dict[str, dict[str, frozenset[str]]], dict[str, str]]:
    """
    Load the ingredient index once.

    Returns:
        ``(records, aliases)`` where ``records`` maps canonical names to their
        allergen/diet sets and ``aliases`` maps every normalized alias to a
        canonical name.
    """
    try:
        raw = json.loads(_DATA_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        logger.warning("Ingredient ontology data not found: %s", _DATA_PATH)
        return {}, {}
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Failed to load ingredient ontology: %s", exc)
        return {}, {}

    records: dict[str, dict[str, frozenset[str]]] = {}
    aliases: dict[str, str] = {}

    for item in raw.get("ingredients", []):
        if not isinstance(item, dict):
            continue
        name = _clean(item.get("name"))
        if not name:
            continue

        records[name] = {
            "allergens": frozenset(
                tag
                for tag in (_clean(value) for value in item.get("allergens", []))
                if tag
            ),
            "diet_tags": frozenset(
                tag
                for tag in (_clean(value) for value in item.get("diet_tags", []))
                if tag
            ),
        }
        aliases[name] = name
        for alias in item.get("aliases", []):
            cleaned = _clean(alias)
            if cleaned:
                aliases[cleaned] = name

    return records, aliases


def normalize_ingredient(name: str) -> str:
    """Map an alias to its canonical ingredient name; unknown names pass through."""
    cleaned = _clean(name)
    if not cleaned:
        return ""
    _, aliases = _load_index()
    return aliases.get(cleaned, cleaned)


def is_known_ingredient(name: str) -> bool:
    """Return whether the canonical name exists in the ontology."""
    canonical = normalize_ingredient(name)
    records, _ = _load_index()
    return canonical in records


def canonicalize_ingredients(names: Optional[Iterable[str]]) -> list[str]:
    """Normalize, de-duplicate and preserve input order."""
    result: list[str] = []
    seen: set[str] = set()

    if isinstance(names, str):
        names = [names]

    for name in names or []:
        canonical = normalize_ingredient(name)
        if canonical and canonical not in seen:
            seen.add(canonical)
            result.append(canonical)

    return result


def allergens_for(names: Iterable[str]) -> set[str]:
    """Return the union of allergens implied by the supplied ingredients."""
    records, _ = _load_index()
    allergens: set[str] = set()

    for name in canonicalize_ingredients(names):
        allergens.update(records.get(name, {}).get("allergens", ()))

    return allergens


def diet_tags_for(names: Iterable[str]) -> set[str]:
    """
    Return diet tags shared by every known ingredient.

    A dish is vegetarian/vegan/gluten-free only when all of its known
    ingredients are. Unknown ingredients are ignored rather than assumed safe.
    """
    records, _ = _load_index()
    shared: Optional[set[str]] = None

    for name in canonicalize_ingredients(names):
        record = records.get(name)
        if record is None:
            continue
        tags = set(record.get("diet_tags", ()))
        shared = tags if shared is None else shared & tags

    return shared or set()


def explain_allergens(names: Iterable[str]) -> dict[str, list[str]]:
    """Explain which canonical ingredient contributed each allergen."""
    records, _ = _load_index()
    explanation: dict[str, list[str]] = {}

    for name in canonicalize_ingredients(names):
        for allergen in records.get(name, {}).get("allergens", ()):
            explanation.setdefault(allergen, []).append(name)

    return {
        allergen: sorted(set(ingredients))
        for allergen, ingredients in explanation.items()
    }


def _mask_non_ingredient_phrases(text: str) -> str:
    """用等长空格屏蔽菜名中的伪食材字面量。"""
    masked = text
    for phrase in _NON_INGREDIENT_PHRASES:
        masked = masked.replace(phrase, " " * len(phrase))
    return masked


def find_ingredients(text: str) -> list[str]:
    """从文本中识别已知食材，返回按出现顺序去重的规范名。

    使用最长优先匹配，避免 ``花生酱`` 被拆成 ``花生``、``皮蛋`` 被拆成
    ``蛋``。未知文本返回空列表，调用方应将其视为“无法确认”而不是安全。
    """
    if not isinstance(text, str) or not text.strip():
        return []

    masked = _mask_non_ingredient_phrases(text)
    haystack = masked.casefold()
    _, aliases = _load_index()
    if not aliases:
        return []

    candidates: list[tuple[str, str]] = []
    for alias, canonical in aliases.items():
        folded = alias.casefold()
        if len(folded) == 1 and folded not in _SAFE_SINGLE_CHAR_ALIASES:
            continue
        candidates.append((folded, canonical))

    # 最长优先，确保复合食材不会被拆成更短的别名。
    candidates.sort(key=lambda item: (-len(item[0]), item[0]))
    occupied = [False] * len(haystack)
    matches: list[tuple[int, str]] = []

    for folded, canonical in candidates:
        start = 0
        while True:
            index = haystack.find(folded, start)
            if index < 0:
                break
            end = index + len(folded)
            if not any(occupied[index:end]):
                matches.append((index, canonical))
                for position in range(index, end):
                    occupied[position] = True
            start = index + 1

    matches.sort(key=lambda item: item[0])
    result: list[str] = []
    seen: set[str] = set()
    for _, canonical in matches:
        if canonical not in seen:
            seen.add(canonical)
            result.append(canonical)
    return result


_INGREDIENT_HEADING = re.compile(
    r"(?m)^(?P<hashes>#{1,6})[ \t]*"
    r"(?P<name>必备原料和工具|必备原料|原料|食材|配料|主料|辅料)[ \t]*$"
)


def extract_ingredients_from_document(text: str, title: str = "") -> list[str]:
    """从菜谱文档中提取食材。

    优先读取“必备原料和工具/原料/食材/配料”章节；章节不存在时才回退到
    标题与全文，避免正文中的菜名、描述被误判为食材。
    """
    if not isinstance(text, str):
        text = ""

    segments: list[str] = []
    for match in _INGREDIENT_HEADING.finditer(text):
        level = len(match.group("hashes"))
        start = match.end()
        next_heading = re.search(
            rf"(?m)^#{{1,{level}}}[ \t]+", text[start:]
        )
        end = start + next_heading.start() if next_heading else len(text)
        segments.append(text[start:end])

    if segments:
        return find_ingredients("\n".join(segments))

    fallback = f"{title or ''}\n{text}"
    return find_ingredients(fallback)


__all__ = [
    "normalize_ingredient",
    "is_known_ingredient",
    "canonicalize_ingredients",
    "allergens_for",
    "diet_tags_for",
    "explain_allergens",
    "find_ingredients",
    "extract_ingredients_from_document",
]
