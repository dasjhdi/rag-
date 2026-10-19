"""SU-12 索引清单与一致性检查测试（离线）。"""

import json
import uuid
from pathlib import Path

from app.rag.vector_stores.index_manifest import (
    build_manifest,
    check_manifest,
    fingerprint_texts,
    load_manifest,
    save_manifest,
)
from scripts.check_index_manifest import main


def _temp_manifest_path() -> Path:
    return Path("data/index") / f"_test_manifest_{uuid.uuid4().hex}.json"


def _consistent_manifest():
    return build_manifest(
        collection="cook_hero_recipes",
        embedding_model="BAAI/bge-small-zh-v1.5",
        corpus_version="howtocook-v1",
        dimension=512,
    )


def test_fingerprint_is_stable_for_same_ordered_texts():
    first = fingerprint_texts(["番茄炒蛋", "红烧肉"])
    second = fingerprint_texts(["番茄炒蛋", "红烧肉"])

    assert first == second
    assert len(first) == 64


def test_fingerprint_changes_when_content_changes():
    assert fingerprint_texts(["番茄炒蛋"]) != fingerprint_texts(["番茄炒蛋 "])
    assert fingerprint_texts(["a", "b"]) != fingerprint_texts(["ab"])


def test_build_save_load_roundtrip():
    path = _temp_manifest_path()
    manifest = build_manifest(
        collection="cook_hero_recipes",
        embedding_model="BAAI/bge-small-zh-v1.5",
        corpus_version="howtocook-v1",
        dimension=512,
        document_count=10,
        chunk_count=42,
        texts=["番茄炒蛋", "红烧肉"],
    )
    try:
        save_manifest(path, manifest)
        loaded = load_manifest(path)

        assert loaded == manifest
        assert loaded["document_count"] == 10
        assert loaded["chunk_count"] == 42
        assert loaded["source_digest"] == fingerprint_texts(["番茄炒蛋", "红烧肉"])
    finally:
        path.unlink(missing_ok=True)


def test_load_missing_manifest_returns_none():
    assert load_manifest("data/index/does-not-exist.json") is None


def test_check_manifest_consistent():
    assert (
        check_manifest(
            _consistent_manifest(),
            collection="cook_hero_recipes",
            embedding_model="BAAI/bge-small-zh-v1.5",
            corpus_version="howtocook-v1",
            dimension=512,
        )
        == []
    )


def test_check_manifest_detects_collection_mismatch():
    issues = check_manifest(
        _consistent_manifest(),
        collection="other",
        embedding_model="BAAI/bge-small-zh-v1.5",
        corpus_version="howtocook-v1",
        dimension=512,
    )
    assert any(issue.startswith("collection mismatch") for issue in issues)


def test_check_manifest_detects_embedding_model_mismatch():
    issues = check_manifest(
        _consistent_manifest(),
        collection="cook_hero_recipes",
        embedding_model="BAAI/bge-large-zh-v1.5",
        corpus_version="howtocook-v1",
        dimension=512,
    )
    assert any(issue.startswith("embedding_model mismatch") for issue in issues)


def test_check_manifest_detects_corpus_version_mismatch():
    issues = check_manifest(
        _consistent_manifest(),
        collection="cook_hero_recipes",
        embedding_model="BAAI/bge-small-zh-v1.5",
        corpus_version="howtocook-v2",
        dimension=512,
    )
    assert any(issue.startswith("corpus_version mismatch") for issue in issues)


def test_check_manifest_detects_dimension_mismatch():
    issues = check_manifest(
        _consistent_manifest(),
        collection="cook_hero_recipes",
        embedding_model="BAAI/bge-small-zh-v1.5",
        corpus_version="howtocook-v1",
        dimension=1024,
    )
    assert any(issue.startswith("dimension mismatch") for issue in issues)


def test_check_manifest_missing():
    assert (
        check_manifest(
            None,
            collection="cook_hero_recipes",
            embedding_model="BAAI/bge-small-zh-v1.5",
            corpus_version="howtocook-v1",
            dimension=512,
        )
        == ["manifest_missing"]
    )


def test_script_passes_for_repository_manifest(capsys):
    exit_code = main(
        [
            "--manifest",
            "data/index/recipes_manifest.json",
            "--collection",
            "cook_hero_recipes",
            "--embedding-model",
            "BAAI/bge-small-zh-v1.5",
            "--corpus-version",
            "howtocook-v1",
            "--dimension",
            "512",
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["ok"] is True
    assert output["issues"] == []


def test_script_fails_for_inconsistent_manifest(capsys):
    exit_code = main(
        [
            "--manifest",
            "data/index/recipes_manifest.json",
            "--collection",
            "other",
            "--embedding-model",
            "BAAI/bge-small-zh-v1.5",
            "--corpus-version",
            "howtocook-v1",
            "--dimension",
            "512",
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert output["ok"] is False
    assert output["issues"]


def test_script_fails_when_manifest_missing(capsys):
    exit_code = main(
        [
            "--manifest",
            "data/index/does-not-exist.json",
            "--collection",
            "cook_hero_recipes",
            "--embedding-model",
            "BAAI/bge-small-zh-v1.5",
            "--corpus-version",
            "howtocook-v1",
            "--dimension",
            "512",
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert output["issues"] == ["manifest_missing"]
