"""Import recipes from public web pages or photos.

The importer deliberately runs in the same shape as the rest of the diet
module: it converts whatever it reads into Markdown, stores that Markdown as a
personal knowledge document, and lets the existing recipe parser produce the
structured payload.  That keeps search, planning and RAG consistent with
manually-entered recipes.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import ipaddress
import json
import logging
import re
import socket
import uuid
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Any, Iterable, Optional
from urllib.parse import quote, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from PIL import Image

from app.diet.recipes.parser import parse_recipe_document
from app.services.personal_document_service import personal_document_service

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_IMPORT_ROOT = _PROJECT_ROOT / "data" / "imports" / "recipes"

_MAX_HTML_BYTES = 3 * 1024 * 1024
_MAX_IMAGE_BYTES = 10 * 1024 * 1024
_MAX_REDIRECTS = 4
_TIMEOUT = httpx.Timeout(12.0, connect=8.0)

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36 CookHeroImporter/1.0"
)
_BROWSER_HEADERS = {
    "User-Agent": _USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/*;q=0.8,*/*;q=0.7",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7",
}

_IMAGE_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}

_ISO_DURATION = re.compile(
    r"P(?:(?P<days>\d+)D)?(?:T(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?)?",
    re.IGNORECASE,
)
_SERVINGS = re.compile(r"(?P<count>\d+(?:\.\d+)?)\s*(?:人份|人|servings?)", re.IGNORECASE)
_SERVES = re.compile(r"serves?\s*(?P<count>\d+(?:\.\d+)?)", re.IGNORECASE)
_MINUTES = re.compile(r"(?P<count>\d+)\s*(?:分钟|minutes?|mins?)", re.IGNORECASE)
_NUMBERED_LINE = re.compile(r"^\s*(?:\d+[.)、]|[-*•])\s*")


class RecipeImportError(Exception):
    """A user-facing import failure with an HTTP status hint."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass
class ImportedRecipe:
    """A normalized recipe extracted from a page or a photo."""

    title: str
    description: str = ""
    category: str = ""
    difficulty: str = ""
    servings: float = 2.0
    total_minutes: Optional[float] = None
    ingredients: list[str] = field(default_factory=list)
    steps: list[str] = field(default_factory=list)
    image_urls: list[str] = field(default_factory=list)
    source_url: str = ""
    author: str = ""

    def to_markdown(self, hero_image_url: Optional[str] = None) -> str:
        """Render the same headings the deterministic parser understands."""
        title = _clean_text(self.title) or "导入的菜谱"
        description = _clean_text(self.description)
        if not description:
            host = urlparse(self.source_url).hostname if self.source_url else ""
            description = f"从 {host} 导入的菜谱。" if host else "导入的菜谱。"

        parts: list[str] = [f"# {title}", "", description, ""]
        if self.source_url:
            host = urlparse(self.source_url).hostname or self.source_url
            parts.extend([f"> 来源：[{host}]({self.source_url})", ""])
        if hero_image_url:
            parts.extend([f"![{title}]({hero_image_url})", ""])

        parts.extend(["## 必备原料和工具", ""])
        for ingredient in self.ingredients:
            parts.append(f"- {ingredient}")
        parts.append("")

        parts.extend(["## 操作", ""])
        for index, step in enumerate(self.steps, start=1):
            parts.append(f"{index}. {step}")
        parts.append("")

        parts.extend(["## 附加内容", ""])
        if self.servings:
            parts.append(f"- 份量：{_format_number(self.servings)} 人份")
        if self.total_minutes:
            parts.append(f"- 总耗时：约 {_format_number(self.total_minutes)} 分钟")
        if self.author:
            parts.append(f"- 作者：{self.author}")
        if self.source_url:
            parts.append(f"- 原始链接：{self.source_url}")
        parts.append("")
        return "\n".join(parts)


def _clean_text(value: Any, *, limit: int = 2000) -> str:
    """Flatten HTML/JSON-LD text into a single readable line."""
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return " ".join(_clean_text(item, limit=limit) for item in value if item)
    if isinstance(value, dict):
        for key in ("text", "name", "value", "description"):
            if value.get(key):
                return _clean_text(value[key], limit=limit)
        return ""
    text = str(value)
    if "<" in text and ">" in text:
        text = BeautifulSoup(text, "html.parser").get_text(" ", strip=True)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _format_number(value: float | int | None) -> str:
    if value is None:
        return ""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if abs(number - round(number)) < 1e-6:
        return str(int(round(number)))
    return f"{number:.1f}".rstrip("0").rstrip(".")


def parse_iso_duration(value: Any) -> Optional[float]:
    """Return minutes for an ISO-8601 duration (PT30M / PT1H20M)."""
    text = _clean_text(value, limit=64)
    if not text:
        return None
    match = _ISO_DURATION.search(text)
    if not match:
        return None
    days = float(match.group("days") or 0)
    hours = float(match.group("hours") or 0)
    minutes = float(match.group("minutes") or 0)
    seconds = float(match.group("seconds") or 0)
    total = days * 1440 + hours * 60 + minutes + seconds / 60
    return round(total, 1) if total > 0 else None


def _iter_json_ld_nodes(node: Any) -> Iterable[dict[str, Any]]:
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _iter_json_ld_nodes(value)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_json_ld_nodes(item)


def _is_recipe_type(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower().endswith("recipe")
    if isinstance(value, list):
        return any(_is_recipe_type(item) for item in value)
    return False


def _image_urls(value: Any, base_url: str) -> list[str]:
    urls: list[str] = []

    def collect(item: Any) -> None:
        if not item:
            return
        if isinstance(item, str):
            resolved = urljoin(base_url, item.strip())
            if resolved.startswith(("http://", "https://")):
                urls.append(resolved)
            return
        if isinstance(item, list):
            for child in item:
                collect(child)
            return
        if isinstance(item, dict):
            for key in ("url", "contentUrl", "image", "thumbnailUrl"):
                if item.get(key):
                    collect(item[key])
                    return

    collect(value)
    # Preserve order, drop duplicates.
    return list(dict.fromkeys(urls))


def _flatten_instructions(value: Any) -> list[str]:
    steps: list[str] = []

    def collect(item: Any) -> None:
        if not item:
            return
        if isinstance(item, str):
            text = _clean_text(item)
            if text:
                # Some sites put all steps in one string with newlines.
                if "\n" in str(item):
                    for line in str(item).splitlines():
                        line = _NUMBERED_LINE.sub("", _clean_text(line)).strip()
                        if line:
                            steps.append(line)
                else:
                    steps.append(_NUMBERED_LINE.sub("", text).strip())
            return
        if isinstance(item, list):
            for child in item:
                collect(child)
            return
        if isinstance(item, dict):
            item_type = str(item.get("@type") or "").lower()
            text = _clean_text(item.get("text") or item.get("name"))
            if text and "howtosection" not in item_type:
                steps.append(_NUMBERED_LINE.sub("", text).strip())
            for key in ("itemListElement", "steps", "step"):
                if item.get(key):
                    collect(item[key])

    collect(value)
    cleaned = [step for step in (s.strip() for s in steps) if len(step) > 1]
    return list(dict.fromkeys(cleaned))


def _parse_recipe_node(node: dict[str, Any], base_url: str) -> Optional[ImportedRecipe]:
    title = _clean_text(node.get("name") or node.get("headline"), limit=200)
    ingredients = [
        _clean_text(item, limit=400)
        for item in _as_list(node.get("recipeIngredient") or node.get("ingredients"))
    ]
    ingredients = [item for item in dict.fromkeys(ingredients) if item]
    steps = _flatten_instructions(
        node.get("recipeInstructions")
        or node.get("instructions")
        or node.get("recipeInstruction")
    )
    if not title or not ingredients or not steps:
        return None

    servings_value = node.get("recipeYield") or node.get("yield")
    servings = 2.0
    for item in _as_list(servings_value):
        text = _clean_text(item)
        match = _SERVINGS.search(text) or _SERVES.search(text)
        if match:
            servings = max(1.0, float(match.group("count")))
            break
        try:
            servings = max(1.0, float(str(item).strip()))
            break
        except (TypeError, ValueError):
            continue

    total_minutes = (
        parse_iso_duration(node.get("totalTime"))
        or (
            (parse_iso_duration(node.get("prepTime")) or 0)
            + (parse_iso_duration(node.get("cookTime")) or 0)
        )
        or None
    )
    if total_minutes == 0:
        total_minutes = None

    category_value = node.get("recipeCategory") or node.get("category")
    category = _clean_text(category_value, limit=40)
    if not category:
        category = "导入"
    difficulty = _infer_difficulty(total_minutes)

    description = _clean_text(node.get("description"), limit=400)
    author = _clean_text(node.get("author"), limit=120)

    return ImportedRecipe(
        title=title,
        description=description,
        category=category,
        difficulty=difficulty,
        servings=servings,
        total_minutes=total_minutes,
        ingredients=ingredients[:80],
        steps=steps[:60],
        image_urls=_image_urls(node.get("image"), base_url),
        source_url=base_url,
        author=author,
    )


def _infer_difficulty(total_minutes: Optional[float]) -> str:
    if not total_minutes:
        return "未知"
    if total_minutes <= 20:
        return "简单"
    if total_minutes <= 45:
        return "中等"
    if total_minutes <= 90:
        return "困难"
    return "非常困难"


def extract_json_ld_recipe(html: str, base_url: str) -> Optional[ImportedRecipe]:
    """Extract the first complete schema.org Recipe from JSON-LD blocks."""
    soup = BeautifulSoup(html, "html.parser")
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = script.string or script.get_text()
        if not raw or not raw.strip():
            continue
        try:
            payload = json.loads(raw)
        except (TypeError, ValueError):
            # Some sites emit trailing commas / control characters.
            try:
                payload = json.loads(re.sub(r"[\x00-\x1f]", " ", raw))
            except (TypeError, ValueError):
                continue
        for node in _iter_json_ld_nodes(payload):
            if _is_recipe_type(node.get("@type")):
                recipe = _parse_recipe_node(node, base_url)
                if recipe:
                    return recipe
    return None


def extract_dom_recipe(html: str, base_url: str) -> Optional[ImportedRecipe]:
    """Best-effort fallback for pages without schema.org markup."""
    soup = BeautifulSoup(html, "html.parser")

    def meta(name: str) -> str:
        tag = soup.find("meta", attrs={"property": name}) or soup.find(
            "meta", attrs={"name": name}
        )
        return _clean_text(tag.get("content")) if tag else ""

    title = meta("og:title") or _clean_text(
        (soup.find("h1") or soup.find("title")).get_text(" ", strip=True)
        if (soup.find("h1") or soup.find("title"))
        else ""
    )
    description = meta("og:description") or meta("description")
    image = meta("og:image") or meta("twitter:image")

    ingredients: list[str] = []
    for selector in (
        '[itemprop="recipeIngredient"]',
        '[class*="ingredient" i] li',
        '[class*="ingredient" i] p',
        '[class*="material" i] li',
        '[class*="配料"] li',
        '[class*="原料"] li',
    ):
        for element in soup.select(selector):
            text = _clean_text(element.get_text(" ", strip=True), limit=400)
            if text and len(text) <= 400:
                ingredients.append(text)
        if len(ingredients) >= 3:
            break

    steps: list[str] = []
    for selector in (
        '[itemprop="recipeInstructions"] li',
        '[itemprop="recipeInstructions"] p',
        '[class*="instruction" i] li',
        '[class*="direction" i] li',
        '[class*="method" i] li',
        '[class*="step" i] li',
        '[class*="步骤"] li',
    ):
        for element in soup.select(selector):
            text = _clean_text(element.get_text(" ", strip=True), limit=800)
            if text and len(text) > 2:
                steps.append(_NUMBERED_LINE.sub("", text).strip())
        if len(steps) >= 2:
            break
    if not steps:
        for selector in ("article ol li", "main ol li", ".recipe ol li"):
            for element in soup.select(selector):
                text = _clean_text(element.get_text(" ", strip=True), limit=800)
                if text and len(text) > 2:
                    steps.append(_NUMBERED_LINE.sub("", text).strip())
            if len(steps) >= 2:
                break

    ingredients = [item for item in dict.fromkeys(ingredients) if item]
    steps = [item for item in dict.fromkeys(steps) if item]
    if not title or not ingredients or not steps:
        return None

    body_text = _clean_text(soup.get_text(" ", strip=True), limit=20000)
    servings_match = _SERVINGS.search(body_text)
    servings = float(servings_match.group("count")) if servings_match else 2.0
    minutes_match = _MINUTES.search(body_text)
    total_minutes = float(minutes_match.group("count")) if minutes_match else None

    return ImportedRecipe(
        title=title[:200],
        description=description[:400],
        category="导入",
        difficulty=_infer_difficulty(total_minutes),
        servings=max(1.0, servings),
        total_minutes=total_minutes,
        ingredients=ingredients[:80],
        steps=steps[:60],
        image_urls=[image] if image else [],
        source_url=base_url,
    )


def extract_recipe_from_html(html: str, base_url: str) -> ImportedRecipe:
    recipe = extract_json_ld_recipe(html, base_url) or extract_dom_recipe(html, base_url)
    if not recipe:
        raise RecipeImportError(
            "没能从该页面识别出菜谱。请换一个菜谱详情页，或改用图片识别导入。",
            status_code=422,
        )
    return recipe


async def _validate_public_url(url: str) -> str:
    """Reject non-http(s), credentialed and private-network targets (SSRF)."""
    candidate = (url or "").strip()
    if not candidate:
        raise RecipeImportError("请输入要导入的链接")
    parsed = urlparse(candidate)
    if parsed.scheme.lower() not in {"http", "https"}:
        raise RecipeImportError("只支持 http/https 链接")
    if parsed.username or parsed.password:
        raise RecipeImportError("链接不能包含账号密码")
    host = parsed.hostname
    if not host:
        raise RecipeImportError("链接格式不正确")

    try:
        port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)
    except ValueError as exc:
        raise RecipeImportError("链接端口不正确") from exc
    try:
        infos = await asyncio.to_thread(
            socket.getaddrinfo, host, port, type=socket.SOCK_STREAM
        )
    except OSError as exc:
        raise RecipeImportError("无法解析该域名，请检查链接") from exc

    for info in infos:
        address = str(info[4][0]).split("%", 1)[0]
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            continue
        if not ip.is_global:
            raise RecipeImportError("不允许导入内网或本机地址")
    return candidate


async def _read_limited(response: httpx.Response, limit: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    async for chunk in response.aiter_bytes():
        total += len(chunk)
        if total > limit:
            raise RecipeImportError("页面或图片体积过大，已停止导入", status_code=413)
        chunks.append(chunk)
    return b"".join(chunks)


def _decode_html(data: bytes, content_type: str) -> str:
    charset = "utf-8"
    match = re.search(r"charset=([\w-]+)", content_type or "", re.IGNORECASE)
    if match:
        charset = match.group(1)
    for encoding in (charset, "utf-8", "gb18030"):
        try:
            return data.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("utf-8", errors="replace")


async def fetch_html(url: str) -> tuple[str, str]:
    """Fetch a public HTML page with manual redirect validation."""
    current = await _validate_public_url(url)
    async with httpx.AsyncClient(
        timeout=_TIMEOUT, follow_redirects=False, headers=_BROWSER_HEADERS
    ) as client:
        for _ in range(_MAX_REDIRECTS):
            try:
                async with client.stream("GET", current) as response:
                    if response.status_code in {301, 302, 303, 307, 308}:
                        location = response.headers.get("location")
                        if not location:
                            raise RecipeImportError("页面跳转失败")
                        current = urljoin(current, location)
                        await _validate_public_url(current)
                        continue
                    response.raise_for_status()
                    content_type = response.headers.get("content-type", "")
                    if "html" not in content_type.lower():
                        raise RecipeImportError("该链接不是网页，无法解析菜谱")
                    data = await _read_limited(response, _MAX_HTML_BYTES)
                    return _decode_html(data, content_type), str(response.url)
            except RecipeImportError:
                raise
            except httpx.HTTPStatusError as exc:
                raise RecipeImportError(
                    f"目标页面返回 {exc.response.status_code}，无法读取"
                ) from exc
            except httpx.HTTPError as exc:
                raise RecipeImportError("无法访问该链接，请稍后重试") from exc
        raise RecipeImportError("页面跳转次数过多")


def _save_image_bytes(data: bytes, user_id: str, extension: str) -> str:
    safe_user = quote(str(user_id), safe="")
    directory = _IMPORT_ROOT / safe_user
    directory.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}{extension}"
    (directory / filename).write_bytes(data)
    return f"/media/imports/recipes/{safe_user}/{filename}"


async def _fetch_image(url: str, referer: str) -> tuple[str, bytes]:
    """Fetch an image with manual redirect validation (SSRF-safe)."""
    current = await _validate_public_url(url)
    headers = {**_BROWSER_HEADERS, "Referer": referer}
    async with httpx.AsyncClient(
        timeout=_TIMEOUT, follow_redirects=False, headers=headers
    ) as client:
        for _ in range(_MAX_REDIRECTS):
            async with client.stream("GET", current) as response:
                if response.status_code in {301, 302, 303, 307, 308}:
                    location = response.headers.get("location")
                    if not location:
                        raise RecipeImportError("图片跳转失败")
                    current = urljoin(current, location)
                    await _validate_public_url(current)
                    continue
                response.raise_for_status()
                content_type = response.headers.get("content-type", "").split(";")[0].lower()
                return content_type, await _read_limited(response, _MAX_IMAGE_BYTES)
    raise RecipeImportError("图片跳转次数过多")


async def download_recipe_image(
    image_urls: list[str], source_url: str, user_id: str
) -> Optional[str]:
    """Download the first usable cover image and store it locally."""
    if not image_urls:
        return None
    for image_url in image_urls[:3]:
        try:
            content_type, data = await _fetch_image(image_url, source_url)
            extension = _IMAGE_EXTENSIONS.get(content_type)
            if not extension:
                continue
            with Image.open(BytesIO(data)) as image:
                image.verify()
            return _save_image_bytes(data, user_id, extension)
        except (RecipeImportError, httpx.HTTPError, OSError, ValueError) as exc:
            logger.info("Cover image skipped (%s): %s", image_url, exc)
            continue
    return None


def _decode_base64_image(value: str) -> bytes:
    text = (value or "").strip()
    if "," in text and text.lower().startswith("data:"):
        text = text.split(",", 1)[1]
    try:
        data = base64.b64decode(text, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise RecipeImportError("图片数据格式不正确") from exc
    if not data:
        raise RecipeImportError("图片为空")
    if len(data) > _MAX_IMAGE_BYTES:
        raise RecipeImportError("图片过大，请控制在 10MB 以内", status_code=413)
    return data


_VISION_PROMPT = """请从这张菜谱图片中提取结构化信息，只返回一个 JSON 对象，不要 Markdown 代码块：
{
  "title": "菜名",
  "description": "一句话简介",
  "servings": 2,
  "total_minutes": 30,
  "category": "荤菜/素菜/汤品/主食/甜品/早餐/饮品/其他",
  "difficulty": "非常简单/简单/中等/困难/非常困难",
  "ingredients": ["原料名 用量", "..."],
  "steps": ["步骤一", "步骤二", "..."]
}
要求：
- 只提取图片中明确出现的信息，不要编造；看不清的字段用空字符串或空数组。
- ingredients 保留原始用量描述，按图片顺序排列。
- steps 按顺序排列，过短的步骤可以合并。
"""


def _parse_json_payload(text: str) -> dict[str, Any]:
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-zA-Z]*\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        raw = raw[start : end + 1]
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise RecipeImportError("图片识别结果不是有效 JSON，请换一张更清晰的图片") from exc
    if not isinstance(payload, dict):
        raise RecipeImportError("图片识别结果格式不正确")
    return payload


def _payload_to_recipe(payload: dict[str, Any], source_url: str = "") -> ImportedRecipe:
    ingredients = [
        _clean_text(item, limit=400)
        for item in _as_list(payload.get("ingredients"))
    ]
    steps = [
        _clean_text(item, limit=800)
        for item in _as_list(payload.get("steps"))
    ]
    ingredients = [item for item in dict.fromkeys(ingredients) if item]
    steps = [item for item in dict.fromkeys(steps) if item]
    title = _clean_text(payload.get("title"), limit=200)
    if not title or not ingredients or not steps:
        raise RecipeImportError("图片中没有识别出完整的菜名/原料/步骤，请换一张图片")

    try:
        servings = max(1.0, float(payload.get("servings") or 2))
    except (TypeError, ValueError):
        servings = 2.0
    try:
        total_minutes = float(payload["total_minutes"]) if payload.get("total_minutes") else None
    except (TypeError, ValueError):
        total_minutes = None

    return ImportedRecipe(
        title=title,
        description=_clean_text(payload.get("description"), limit=400),
        category=_clean_text(payload.get("category"), limit=40) or "导入",
        difficulty=_clean_text(payload.get("difficulty"), limit=20)
        or _infer_difficulty(total_minutes),
        servings=servings,
        total_minutes=total_minutes,
        ingredients=ingredients[:80],
        steps=steps[:60],
        source_url=source_url,
    )


class RecipeImportService:
    """Create personal recipe documents from URLs or photos."""

    async def import_from_url(self, user_id: str, url: str) -> dict[str, Any]:
        html, final_url = await fetch_html(url)
        imported = extract_recipe_from_html(html, final_url)
        hero = await download_recipe_image(imported.image_urls, final_url, user_id)
        return await self._persist(user_id, imported, hero, final_url, "url")

    async def import_from_image(
        self,
        user_id: str,
        image_base64: str,
        mime_type: str = "image/jpeg",
        filename: str = "",
    ) -> dict[str, Any]:
        from app.vision.provider import ImageInput, VisionProvider

        provider = VisionProvider()
        data = _decode_base64_image(image_base64)
        valid, error = provider.validate_image(mime_type, len(data))
        if not valid:
            raise RecipeImportError(error or "不支持的图片格式")
        try:
            with Image.open(BytesIO(data)) as image:
                image.verify()
        except Exception as exc:
            raise RecipeImportError("图片无法读取，请换一张图片") from exc

        extension = _IMAGE_EXTENSIONS.get(mime_type, ".jpg")

        if not provider.is_enabled:
            raise RecipeImportError(
                "视觉模型未配置，暂时无法使用图片识别导入", status_code=503
            )
        raw = await provider.analyze(
            _VISION_PROMPT,
            [ImageInput.from_bytes(data, mime_type)],
            system_prompt="你是严谨的菜谱结构化助手，只输出 JSON。",
            user_id=user_id,
        )
        imported = _payload_to_recipe(_parse_json_payload(raw))
        hero = _save_image_bytes(data, user_id, extension)
        return await self._persist(user_id, imported, hero, "", "image")

    async def _persist(
        self,
        user_id: str,
        imported: ImportedRecipe,
        hero_image_url: Optional[str],
        source_url: str,
        imported_from: str,
    ) -> dict[str, Any]:
        title = _clean_text(imported.title, limit=200)
        if len(title) < 2:
            title = f"{title}菜谱" if title else "导入的菜谱"
        category = _clean_text(imported.category, limit=40) or "导入"
        if len(category) < 2:
            category = "导入"
        difficulty = _clean_text(imported.difficulty, limit=20) or "未知"
        if len(difficulty) < 2:
            difficulty = "未知"

        markdown = imported.to_markdown(hero_image_url)
        doc = await personal_document_service.create_document(
            user_id=user_id,
            dish_name=title,
            category=category,
            difficulty=difficulty,
            data_source="recipes",
            content=markdown,
        )

        parsed = parse_recipe_document(
            str(doc.id),
            doc.dish_name,
            doc.content,
            category=doc.category,
            difficulty=doc.difficulty,
            source=doc.source,
        )
        recipe = parsed.to_dict()
        recipe.pop("raw_content", None)
        logger.info(
            "Imported recipe id=%s user=%s from=%s title=%s",
            doc.id,
            user_id,
            imported_from,
            title,
        )
        return {
            "document": {
                "id": str(doc.id),
                "dish_name": doc.dish_name,
                "category": doc.category,
                "difficulty": doc.difficulty,
                "image_url": hero_image_url,
            },
            "recipe": recipe,
            "source_url": source_url,
            "imported_from": imported_from,
        }


recipe_import_service = RecipeImportService()
