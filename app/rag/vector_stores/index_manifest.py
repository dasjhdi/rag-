"""Milvus 索引清单与一致性检查（SU-12）。

清单只保存元数据与语料摘要，不保存文档正文或连接凭据。
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional


def fingerprint_texts(texts: Iterable[str]) -> str:
    """按输入顺序计算 SHA-256 指纹。

    每段文本先写入 8 字节长度前缀再写入 UTF-8 内容，避免
    ``["a", "b"]`` 与 ``["ab"]`` 这类边界变化产生相同指纹。
    """

    digest = hashlib.sha256()
    for text in texts:
        encoded = str(text).encode("utf-8")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
    return digest.hexdigest()


def build_manifest(
    *,
    collection: str,
    embedding_model: str,
    corpus_version: str,
    dimension: int,
    document_count: int = 0,
    chunk_count: int = 0,
    texts: Optional[Iterable[str]] = None,
) -> dict[str, Any]:
    """构造可持久化的索引清单。"""

    source_digest = fingerprint_texts(texts) if texts is not None else ""
    created_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    return {
        "collection": str(collection),
        "embedding_model": str(embedding_model),
        "corpus_version": str(corpus_version),
        "dimension": int(dimension),
        "document_count": int(document_count),
        "chunk_count": int(chunk_count),
        "source_digest": source_digest,
        "created_at": created_at,
    }


def save_manifest(path: str | Path, manifest: dict[str, Any]) -> None:
    """把清单写入 JSON 文件，必要时创建父目录。"""

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def load_manifest(path: str | Path) -> Optional[dict[str, Any]]:
    """读取清单；文件不存在时返回 ``None``。"""

    source = Path(path)
    if not source.exists():
        return None
    with source.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"索引清单必须是 JSON 对象：{source}")
    return data


def check_manifest(
    manifest: Optional[dict[str, Any]],
    *,
    collection: str,
    embedding_model: str,
    corpus_version: str,
    dimension: int,
) -> list[str]:
    """比较清单与期望值，返回人类可读的不一致列表。"""

    if manifest is None:
        return ["manifest_missing"]

    issues: list[str] = []
    expected = {
        "collection": str(collection),
        "embedding_model": str(embedding_model),
        "corpus_version": str(corpus_version),
        "dimension": int(dimension),
    }

    for field, expected_value in expected.items():
        actual_value = manifest.get(field)
        if field == "dimension" and actual_value is not None:
            try:
                actual_value = int(actual_value)
            except (TypeError, ValueError):
                pass
        if actual_value != expected_value:
            issues.append(
                f"{field} mismatch: manifest={actual_value} expected={expected_value}"
            )

    return issues


__all__ = [
    "fingerprint_texts",
    "build_manifest",
    "save_manifest",
    "load_manifest",
    "check_manifest",
]
