# app/conversation/types.py
"""Data classes for conversation processing."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.tools.web_search import WebSearchResult
from app.vision import VisionAnalysisResult


@dataclass
class ExtraOptions:
    """Optional features that can be enabled per request."""

    web_search: bool = False
    # Future extensibility: add more options here
    # deep_reasoning: bool = False
    # multimodal: bool = False

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "ExtraOptions":
        if not data:
            return cls()
        return cls(
            web_search=data.get("web_search", False),
        )


@dataclass
class UnifiedSource:
    """
    Unified source structure for frontend display.

    Attributes:
        type: Source type - "rag" for knowledge base, "web" for web search
        info: Display text describing the source
        url: Optional URL for web sources (clickable link)
        index: 知识库来源的引用编号，与回答里的 [n] 对应
    """

    type: str  # "rag" | "web"
    info: str
    url: Optional[str] = None
    index: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        result = {"type": self.type, "info": self.info}
        if self.url:
            result["url"] = self.url
        if self.index is not None:
            result["index"] = self.index
        return result

    @classmethod
    def from_rag_source(cls, source_dict: Dict[str, Any]) -> "UnifiedSource":
        """Convert RAG service source to unified format."""
        info = source_dict.get("info") or source_dict.get("title") or "CookHero 知识库"
        raw_index = source_dict.get("index")
        return cls(
            type="rag",
            info=info,
            url=source_dict.get("url"),
            index=int(raw_index) if isinstance(raw_index, int) else None,
        )

    @classmethod
    def from_web_result(cls, result: WebSearchResult) -> "UnifiedSource":
        """Convert web search result to unified format."""
        # Use title as info for cleaner display
        info = f"{result.title}" if result.title else result.source
        return cls(
            type="web",
            info=info,
            url=result.url,
        )


@dataclass
class ChatContext:
    """Holds all context needed during chat processing."""

    conv_id: str
    message: str
    user_id: Optional[str]
    options: ExtraOptions
    history: List[Dict]
    history_dicts: List[Dict[str, str]]
    history_text: str
    compressed_summary: Optional[str]
    compressed_count: int

    # User personalization context
    user_profile: Optional[str] = None
    user_instruction: Optional[str] = None

    # Mutable state during processing
    sources: List[UnifiedSource] = field(default_factory=list)
    thinking_steps: List[str] = field(default_factory=list)
    web_search_context: str = ""
    rag_context: str = ""
    rewritten_query: str = ""
    # 知识库检索执行了但没有任何命中：用于触发「诚实降级」提示
    retrieval_empty: bool = False

    # Constraint reasoning (SU-17)
    constraint_context: str = ""
    constraint_decision: Optional[Any] = None

    # Vision/Multimodal context
    images: Optional[List[Dict[str, str]]] = (
        None  # List of {"data": base64, "mime_type": ...}
    )
    vision_result: Optional[VisionAnalysisResult] = None
    vision_context: str = ""  # Context built from vision analysis

    # Timing metrics (milliseconds)
    thinking_start_time: Optional[float] = None
    thinking_end_time: Optional[float] = None
    answer_start_time: Optional[float] = None
    answer_end_time: Optional[float] = None
