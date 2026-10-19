"""
中文领域分词与本地 BM25（SU-3.2）

作用：

- 用 jieba + 领域词典保证菜名/食材不被切碎
- 提供与 Milvus 内建 BM25 相互独立的本地词法打分，用于对照与兜底

设计约束：

- 词典文件缺失时降级为纯 jieba 分词，不抛异常
- 纯函数、无网络、无数据库依赖
"""

from __future__ import annotations

import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import Sequence

import jieba
from rank_bm25 import BM25Okapi

logger = logging.getLogger(__name__)

DOMAIN_DICT_PATH = Path(__file__).resolve().parent / "reference" / "domain_dict.txt"

# 仅保留纯功能词，避免误删检索中有意义的词
STOPWORDS: frozenset[str] = frozenset(
    {
        "的",
        "地",
        "得",
        "了",
        "着",
        "过",
        "和",
        "与",
        "及",
        "或",
        "在",
        "是",
        "我",
        "你",
        "他",
        "她",
        "它",
        "我们",
        "你们",
        "他们",
        "这",
        "那",
        "这些",
        "那些",
        "个",
        "些",
        "有",
        "能",
        "可以",
        "怎么",
        "如何",
        "什么",
        "吗",
        "呢",
        "吧",
        "啊",
        "呀",
        "哦",
        "请",
        "帮",
        "帮我",
        "想要",
        "想",
        "一些",
        "一个",
        "告诉",
        "一下",
    }
)

_HAS_ALNUM = re.compile(r"[0-9A-Za-z\u4e00-\u9fff]")
_dict_loaded = False


@lru_cache(maxsize=1)
def load_domain_terms() -> tuple[str, ...]:
    """读取领域词典；文件缺失或读取失败时返回空元组。"""
    try:
        raw = DOMAIN_DICT_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        logger.warning("domain dict not found: %s", DOMAIN_DICT_PATH)
        return ()
    except Exception as exc:  # noqa: BLE001 - 降级为纯 jieba
        logger.warning("failed to read domain dict %s: %s", DOMAIN_DICT_PATH, exc)
        return ()

    terms: list[str] = []
    seen: set[str] = set()
    for line in raw.splitlines():
        term = line.strip()
        if not term or term.startswith("#"):
            continue
        if term in seen:
            continue
        seen.add(term)
        terms.append(term)
    return tuple(terms)


def _ensure_domain_dict() -> None:
    """把领域词注入 jieba（幂等）。"""
    global _dict_loaded
    if _dict_loaded:
        return
    _dict_loaded = True
    for term in load_domain_terms():
        try:
            jieba.add_word(term, freq=20000, tag="nz")
        except Exception as exc:  # pragma: no cover - jieba 内部异常
            logger.warning("failed to add domain term %r: %s", term, exc)


def tokenize(text: str, *, drop_stopwords: bool = True) -> list[str]:
    """
    中文分词。

    Args:
        text: 待分词文本。
        drop_stopwords: 是否移除功能词。

    Returns:
        分词结果（小写化、去空白、去纯标点）。
    """
    if not isinstance(text, str):
        return []
    if not text.strip():
        return []

    _ensure_domain_dict()

    tokens: list[str] = []
    for raw in jieba.lcut(text):
        token = raw.strip()
        if not token or not _HAS_ALNUM.search(token):
            continue
        token = token.lower()
        if drop_stopwords and token in STOPWORDS:
            continue
        tokens.append(token)
    return tokens


def bm25_scores(query: str, docs: Sequence[str]) -> list[float]:
    """
    计算每个文档相对查询的 BM25 分数。

    查询为空或语料无有效词时返回全 0。
    """
    if not docs:
        return []

    query_tokens = tokenize(query)
    corpus = [tokenize(doc) for doc in docs]

    if not query_tokens or not any(corpus):
        return [0.0] * len(docs)

    try:
        bm25 = BM25Okapi(corpus)
        scores = bm25.get_scores(query_tokens)
    except Exception as exc:  # noqa: BLE001 - 词法兜底不应中断主链路
        logger.warning("bm25 scoring failed: %s", exc)
        return [0.0] * len(docs)

    return [float(score) for score in scores]


def bm25_rank(
    query: str, docs: Sequence[str], top_k: int
) -> list[tuple[int, float]]:
    """
    按 BM25 分数降序返回 (文档下标, 分数)。

    Args:
        query: 查询文本。
        docs: 候选文档文本。
        top_k: 返回条数上限，小于 1 时返回空列表。
    """
    if top_k <= 0:
        return []

    scores = bm25_scores(query, docs)
    ranked = sorted(enumerate(scores), key=lambda item: (-item[1], item[0]))
    return ranked[:top_k]


__all__ = [
    "DOMAIN_DICT_PATH",
    "STOPWORDS",
    "load_domain_terms",
    "tokenize",
    "bm25_scores",
    "bm25_rank",
]
