"""SU-4 语义缓存 scope 测试（离线）。"""

from app.rag.cache import build_cache_scope
from app.rag.cache.cache_manager import CacheManager


def test_rag_config_exposes_scope_and_multi_query_fields():
    from app.config import DefaultRAGConfig

    assert DefaultRAGConfig.retrieval.multi_query_enabled is False
    assert DefaultRAGConfig.retrieval.max_queries == 3
    assert DefaultRAGConfig.cache.corpus_version == "howtocook-v1"


def test_scope_is_idempotent():
    first = build_cache_scope(
        "user-1", corpus_version="v1", embedding_model="bge-small"
    )
    second = build_cache_scope(
        "user-1", corpus_version="v1", embedding_model="bge-small"
    )
    assert first == second


def test_scope_changes_with_corpus_version():
    old = build_cache_scope("user-1", corpus_version="v1")
    new = build_cache_scope("user-1", corpus_version="v2")
    assert old != new


def test_scope_changes_with_embedding_model():
    old = build_cache_scope(embedding_model="bge-small")
    new = build_cache_scope(embedding_model="bge-large")
    assert old != new


def test_scope_changes_with_user():
    assert build_cache_scope("alice") != build_cache_scope("bob")


def test_scope_falls_back_to_global_when_empty():
    assert build_cache_scope() == "global"
    assert build_cache_scope(None, corpus_version="", embedding_model="  ") == "global"


def test_scope_ignores_blank_dimensions():
    assert build_cache_scope(" user-1 ") == build_cache_scope("user-1")


def test_scope_parts_are_labeled_and_encoded():
    scope = build_cache_scope(
        "user|1", corpus_version="v1", embedding_model="BAAI/bge-small"
    )
    assert "u=user%7C1" in scope
    assert "c=v1" in scope
    assert "e=BAAI%2Fbge-small" in scope
    assert "|" in scope


def test_l1_key_contains_full_scope_and_differs():
    manager = CacheManager.__new__(CacheManager)
    scope_a = build_cache_scope("user-1", corpus_version="v1")
    scope_b = build_cache_scope("user-1", corpus_version="v2")

    key_a = manager._get_cache_key("personal", "番茄炒蛋", scope_a)
    key_b = manager._get_cache_key("personal", "番茄炒蛋", scope_b)

    assert scope_a in key_a
    assert scope_b in key_b
    assert key_a != key_b


def test_l1_key_keeps_global_compatibility():
    manager = CacheManager.__new__(CacheManager)
    key = manager._get_cache_key("recipes", "番茄炒蛋", None)
    assert "rag:retrieval:recipes:global:" in key
