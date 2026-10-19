"""Fetch missing recipe cover images from public image search.

Usage:
    python -m scripts.fetch_recipe_images --dry-run
    python -m scripts.fetch_recipe_images --only 水煮鱼 --limit 5
    python -m scripts.fetch_recipe_images --limit 20
    python -m scripts.fetch_recipe_images

Images are stored in ``data/recipe_images`` and recorded in ``manifest.json``
keyed by the recipe's path relative to ``data/HowToCook``.  The recipe parser
uses that manifest as a fallback, so the corpus Markdown is never modified.

The script prefers Baidu image search for Chinese dish names (better semantic
matching), with Bing's async image endpoint as a fallback.  Both are public
search endpoints; source URLs are recorded for attribution.  Review licensing
before redistributing fetched images.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import html
import json
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Iterable, Optional
from urllib.parse import quote

import httpx
from PIL import Image, ImageOps

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CORPUS_ROOT = PROJECT_ROOT / "data" / "HowToCook"
DISHES_ROOT = CORPUS_ROOT / "dishes"
IMAGE_ROOT = PROJECT_ROOT / "data" / "recipe_images"
MANIFEST_PATH = IMAGE_ROOT / "manifest.json"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.diet.recipes.parser import parse_recipe_document  # noqa: E402

CATEGORY_HINTS = {
    "aquatic": "海鲜 菜",
    "breakfast": "早餐",
    "condiment": "调料",
    "dessert": "甜点",
    "drink": "饮品",
    "meat_dish": "家常菜",
    "semi-finished": "食材",
    "soup": "汤",
    "staple": "主食",
    "vegetable_dish": "素菜",
}

# Disambiguate names that collide with non-food subjects.
SPECIAL_HINTS = {
    "B52轰炸机": "鸡尾酒",
    "长岛冰茶": "鸡尾酒",
    "莫吉托": "鸡尾酒",
    "玛格丽特": "鸡尾酒",
    "血腥玛丽": "鸡尾酒",
    "太阳蛋": "早餐",
    "葱油": "调料",
    "油酥": "调料",
    "炒糖色": "调料",
    "鸡蛋花": "汤饮",
}

# Search engines do better with the canonical dish name than with the
# corpus's variant spelling.
TITLE_ALIASES = {
    "响油鳝丝": "响油鳝糊",
    "咖喱炒蟹": "咖喱蟹",
    "微波葱姜黑鳕鱼": "葱姜黑鳕鱼",
    "微波炉荷包蛋": "微波炉荷包蛋",
    "空气炸锅面包片": "空气炸锅吐司",
    "B52轰炸机": "B52鸡尾酒",
    "利提巧卡": "Litti Chokha",
    "鸡蛋花": "鸡蛋花汤",
}

# Queries that are known to disambiguate a dish from a same-named non-food
# subject.  These run before the generic category queries.
EXTRA_QUERIES = {
    "B52轰炸机": ["B52 鸡尾酒", "B-52 cocktail"],
    "长岛冰茶": ["长岛冰茶 鸡尾酒"],
    "利提巧卡": ["Litti Chokha recipe", "Litti Chokha"],
    "鸡蛋花": ["开水冲鸡蛋", "鸡蛋花汤 做法"],
}

PREFERRED_DOMAINS = (
    "xiachufang",
    "chuimg",
    "meishij",
    "douguo",
    "jingyan.baidu",
    "baidu.com",
    "zhihu",
    "sohu",
    "163.com",
    "sina.com",
    "weibo",
    "byteimg",
    "douyinpic",
)

BLOCKED_DOMAINS = (
    "699pic",
    "redocn",
    "nximg",
    "lhs11",
    "qpic.cn",
    "vivistar",
    "shuomingshu",
    "cgzdl",
    "tuchong",
    "zcool",
    "hellorf",
    "gettyimages",
    "shutterstock",
    "dreamstime",
)

BAD_URL_TOKENS = (
    "logo",
    "icon",
    "banner",
    "sprite",
    "qrcode",
    "avatar",
    "emoji",
    "placeholder",
    "watermark",
)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)
HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/*;q=0.8,*/*;q=0.7",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7",
}
TIMEOUT = httpx.Timeout(25.0, connect=10.0)
MAX_IMAGE_BYTES = 8 * 1024 * 1024


@dataclass
class Candidate:
    title: str
    page_url: str
    image_url: str
    provider: str
    score: float = 0.0


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value or "")).strip()


def _bigrams(text: str) -> set[str]:
    compact = re.sub(r"[^\w\u4e00-\u9fff]", "", text or "")
    return {compact[index : index + 2] for index in range(len(compact) - 1)} - {""}


def _build_queries(title: str, category: str) -> list[str]:
    hint = SPECIAL_HINTS.get(title)
    if not hint:
        for key, value in SPECIAL_HINTS.items():
            if key in title:
                hint = value
                break
    if not hint:
        hint = CATEGORY_HINTS.get(category, "")

    names = [TITLE_ALIASES.get(title, title)]
    if names[0] != title:
        names.append(title)

    queries: list[str] = list(EXTRA_QUERIES.get(title, []))
    for name in names:
        if hint and hint not in name:
            queries.append(f"{name} {hint}")
    for name in names:
        queries.append(f"{name} 成品图")
    queries.append(f"{title} 做法")
    # Last resort: the bare dish name often works when a hint makes the
    # search engine over-constrain the query.
    queries.extend(names)
    return list(dict.fromkeys(queries))


def _score_candidate(candidate: Candidate, title: str) -> float:
    text = f"{candidate.title} {candidate.page_url}".casefold()
    target = title.casefold()
    score = 0.0
    if target and target in text:
        score += 12
    elif candidate.title and (candidate.title.casefold() in target or target in candidate.title.casefold()):
        score += 8
    else:
        matches = sum(1 for bigram in _bigrams(title) if bigram.casefold() in text)
        score += min(matches * 2.0, 6.0)

    if any(domain in candidate.page_url for domain in PREFERRED_DOMAINS):
        score += 3
    if any(domain in candidate.page_url for domain in BLOCKED_DOMAINS):
        score -= 50
    if any(domain in candidate.image_url for domain in BLOCKED_DOMAINS):
        score -= 50
    lowered = candidate.image_url.casefold()
    if any(token in lowered for token in BAD_URL_TOKENS):
        score -= 30
    if candidate.provider == "baidu":
        score += 1.5
    return score


def _loads_json_loose(text: str):
    """Parse JSON that may contain raw control chars or invalid escapes."""
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        # Baidu sometimes emits e.g. ``\escape`` or raw newlines in titles.
        fixed = re.sub(r'\\(?!["\\/bfnrtu])', r"\\\\", text)
        return json.loads(fixed, strict=False)


def search_baidu(client: httpx.Client, query: str) -> list[Candidate]:
    response = client.get(
        "https://image.baidu.com/search/acjson",
        params={
            "tn": "resultjson_com",
            "ipn": "rj",
            "word": query,
            "pn": 0,
            "rn": 30,
        },
    )
    response.raise_for_status()
    payload = _loads_json_loose(response.text)
    candidates: list[Candidate] = []
    for item in payload.get("data") or []:
        if not isinstance(item, dict):
            continue
        image_url = item.get("middleURL") or item.get("thumbURL") or item.get("hoverURL")
        if not image_url:
            continue
        candidates.append(
            Candidate(
                title=_clean_text(item.get("fromPageTitleEnc") or ""),
                page_url=_clean_text(item.get("fromURL") or ""),
                image_url=image_url,
                provider="baidu",
            )
        )
    return candidates


def search_bing(client: httpx.Client, query: str) -> list[Candidate]:
    response = client.get(
        "https://cn.bing.com/images/async",
        params={
            "q": query,
            "first": 1,
            "count": 35,
            "cw": 1177,
            "ch": 738,
            "relp": 35,
            "tsc": "ImageHoverTitle",
            "datsrc": "I",
            "layout": "RowBased",
            "mmasync": 1,
        },
    )
    response.raise_for_status()
    candidates: list[Candidate] = []
    for raw in re.findall(r'm="([^"]+)"', response.text):
        try:
            item = json.loads(html.unescape(raw))
        except (TypeError, ValueError):
            continue
        image_url = item.get("murl")
        if not image_url:
            continue
        candidates.append(
            Candidate(
                title=_clean_text(item.get("t") or ""),
                page_url=_clean_text(item.get("purl") or ""),
                image_url=image_url,
                provider="bing",
            )
        )
    return candidates


def _rank(candidates: Iterable[Candidate], title: str) -> list[Candidate]:
    seen: set[str] = set()
    ranked: list[Candidate] = []
    for candidate in candidates:
        if candidate.image_url in seen:
            continue
        seen.add(candidate.image_url)
        candidate.score = _score_candidate(candidate, title)
        ranked.append(candidate)
    ranked.sort(key=lambda item: item.score, reverse=True)
    return ranked


def _download_and_normalize(
    client: httpx.Client, candidate: Candidate
) -> Optional[tuple[bytes, int, int]]:
    headers = {**HEADERS, "Accept": "image/avif,image/webp,image/*,*/*;q=0.8"}
    if candidate.page_url:
        # Header values must be ASCII; Chinese page URLs need percent-encoding.
        headers["Referer"] = quote(candidate.page_url, safe=":/?&=#%")
    try:
        with client.stream("GET", candidate.image_url, headers=headers) as response:
            response.raise_for_status()
            content_type = response.headers.get("content-type", "")
            if content_type and not content_type.lower().startswith("image/"):
                return None
            chunks: list[bytes] = []
            total = 0
            for chunk in response.iter_bytes():
                total += len(chunk)
                if total > MAX_IMAGE_BYTES:
                    return None
                chunks.append(chunk)
            data = b"".join(chunks)
    except (httpx.HTTPError, OSError):
        return None

    try:
        with Image.open(BytesIO(data)) as image:
            image.seek(0)
            image = ImageOps.exif_transpose(image)
            if image.mode in ("RGBA", "LA", "P"):
                background = Image.new("RGB", image.size, "white")
                rgba = image.convert("RGBA")
                background.paste(rgba, mask=rgba.split()[-1])
                image = background
            elif image.mode != "RGB":
                image = image.convert("RGB")

            width, height = image.size
            if width < 400 or height < 300:
                return None

            # Normalize to 4:3 so cards and detail headers crop predictably.
            target_ratio = 4 / 3
            if width / height > target_ratio:
                new_width = max(1, int(round(height * target_ratio)))
                left = max(0, (width - new_width) // 2)
                image = image.crop((left, 0, left + new_width, height))
            else:
                new_height = max(1, int(round(width / target_ratio)))
                top = max(0, (height - new_height) // 2)
                image = image.crop((0, top, width, top + new_height))

            image.thumbnail((1200, 900), Image.LANCZOS)
            output = BytesIO()
            image.save(output, "JPEG", quality=85, optimize=True, progressive=True)
            return output.getvalue(), image.width, image.height
    except (OSError, ValueError):
        return None


def _load_manifest() -> dict:
    if not MANIFEST_PATH.is_file():
        return {"version": 1, "generated_at": None, "images": {}}
    try:
        payload = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"version": 1, "generated_at": None, "images": {}}
    if not isinstance(payload, dict):
        return {"version": 1, "generated_at": None, "images": {}}
    payload.setdefault("images", {})
    return payload


def _save_manifest(manifest: dict) -> None:
    IMAGE_ROOT.mkdir(parents=True, exist_ok=True)
    manifest["version"] = 1
    manifest["generated_at"] = datetime.now(timezone.utc).isoformat()
    temp = MANIFEST_PATH.with_suffix(".json.tmp")
    temp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(MANIFEST_PATH)


def _scan_missing(only: Optional[str] = None) -> list[tuple[str, str, str, str]]:
    """Return (title, relative_path, category, absolute_path) for missing covers."""
    missing: list[tuple[str, str, str, str]] = []
    for markdown in sorted(DISHES_ROOT.rglob("*.md")):
        content = markdown.read_text(encoding="utf-8", errors="ignore")
        recipe = parse_recipe_document(
            markdown.stem,
            markdown.stem,
            content,
            source=str(markdown),
            image_root=str(CORPUS_ROOT),
        )
        if recipe.image_url:
            continue
        relative = markdown.relative_to(CORPUS_ROOT).as_posix()
        category = markdown.relative_to(DISHES_ROOT).parts[0]
        if only and only not in markdown.stem and only not in relative:
            continue
        missing.append((markdown.stem, relative, category, str(markdown)))
    return missing


_vision_provider = None
_vision_loop: Optional[asyncio.AbstractEventLoop] = None


def _get_vision_provider():
    global _vision_provider, _vision_loop
    if _vision_loop is None or _vision_loop.is_closed():
        _vision_loop = asyncio.new_event_loop()
    if _vision_provider is None:
        from app.vision.provider import VisionProvider

        _vision_provider = VisionProvider()
    return _vision_provider, _vision_loop


def _parse_verification(raw: str) -> tuple[bool, str]:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        text = text[start : end + 1]
    try:
        payload = json.loads(text)
    except (TypeError, ValueError):
        lowered = text.casefold()
        return ("true" in lowered or "yes" in lowered), text[:80]
    match = payload.get("match")
    if isinstance(match, str):
        match = match.strip().casefold() in {"true", "yes", "1", "是"}
    return bool(match), str(payload.get("reason") or "")[:80]


def _verify_with_vision(title: str, image_bytes: bytes) -> tuple[Optional[bool], str]:
    """Return (is_match, reason); None means verification was unavailable."""
    try:
        from app.vision.provider import ImageInput

        provider, loop = _get_vision_provider()
        if not provider.is_enabled:
            return None, "vision disabled"
        prompt = (
            f"你是严格的菜品图片审核员。判断图片是否与菜名「{title}」相符。\n"
            '只返回 JSON：{"match": true, "reason": "不超过20字"}\n'
            "如果图片是地图、文字截图、菜谱步骤图、商品包装、瓶装/罐装产品、"
            "促销海报、人物、风景或与菜名无关的内容，match 必须为 false。"
            "只接受能看清菜品/饮品/调料本身的实物照片。"
        )
        raw = loop.run_until_complete(
            provider.analyze(
                prompt,
                [ImageInput.from_bytes(image_bytes, "image/jpeg")],
                system_prompt="你是严格的菜品图片审核员，只输出 JSON。",
            )
        )
        return _parse_verification(raw)
    except Exception as exc:  # pragma: no cover - network/model dependent
        return None, str(exc)[:120]


def _fetch_one(
    client: httpx.Client,
    title: str,
    category: str,
    *,
    provider: str,
    max_candidates: int,
    sleep: float,
    verify: bool,
) -> Optional[dict]:
    queries = _build_queries(title, category)
    alias = TITLE_ALIASES.get(title)
    verify_title = f"{title}（{alias}）" if alias and alias != title else title
    attempts = 0
    max_attempts = max(1, max_candidates) * 3
    for query in queries:
        candidate_pool: list[Candidate] = []
        if provider in ("auto", "baidu"):
            try:
                candidate_pool.extend(search_baidu(client, query))
            except (httpx.HTTPError, ValueError):
                pass
            if sleep:
                time.sleep(sleep)
        if not candidate_pool and provider in ("auto", "bing"):
            try:
                candidate_pool.extend(search_bing(client, query))
            except (httpx.HTTPError, ValueError):
                pass
            if sleep:
                time.sleep(sleep)
        if provider == "auto" and candidate_pool:
            # Also try Bing as a second opinion for low-confidence Baidu pools.
            ranked = _rank(candidate_pool, title)
            if not ranked or ranked[0].score < 6:
                try:
                    candidate_pool.extend(search_bing(client, query))
                except (httpx.HTTPError, ValueError):
                    pass
                if sleep:
                    time.sleep(sleep)

        ranked = _rank(candidate_pool, title)
        for candidate in ranked[: max(1, max_candidates)]:
            if attempts >= max_attempts:
                return None
            attempts += 1
            normalized = _download_and_normalize(client, candidate)
            if not normalized:
                continue
            data, width, height = normalized

            verified: Optional[bool] = None
            verify_reason = "skipped"
            if verify:
                verified, verify_reason = _verify_with_vision(verify_title, data)
                if verified is False:
                    print(f"    reject {candidate.provider}: {verify_reason}")
                    continue

            digest = hashlib.sha1(data).hexdigest()[:12]
            filename = f"{digest}.jpg"
            IMAGE_ROOT.mkdir(parents=True, exist_ok=True)
            (IMAGE_ROOT / filename).write_bytes(data)
            confidence = "high" if candidate.score >= 10 else "medium" if candidate.score >= 4 else "low"
            return {
                "file": filename,
                "title": title,
                "provider": candidate.provider,
                "query": query,
                "source_url": candidate.image_url,
                "page_url": candidate.page_url,
                "license": "unknown",
                "width": width,
                "height": height,
                "confidence": confidence,
                "verified": verified,
                "verify_reason": verify_reason,
                "score": round(candidate.score, 1),
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            }
    return None


def _write_readme() -> None:
    IMAGE_ROOT.mkdir(parents=True, exist_ok=True)
    (IMAGE_ROOT / "README.md").write_text(
        "# Fetched recipe images\n\n"
        "These images were fetched from public image search results to fill in\n"
        "recipes that do not ship a photo in the HowToCook corpus.  The source\n"
        "URL and search page are recorded in `manifest.json` for attribution.\n\n"
        "They are intended for local development/demo use.  Review licensing\n"
        "before redistributing them or deploying this project publicly.\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch missing recipe cover images")
    parser.add_argument("--dry-run", action="store_true", help="只打印将处理的菜谱，不下载")
    parser.add_argument("--limit", type=int, default=0, help="最多处理多少道菜")
    parser.add_argument("--only", type=str, default="", help="只处理标题/路径包含该字符串的菜谱")
    parser.add_argument(
        "--provider",
        choices=("auto", "baidu", "bing"),
        default="auto",
        help="图片来源：auto（百度优先，Bing 兜底）",
    )
    parser.add_argument("--max-candidates", type=int, default=6, help="每个查询最多尝试几个候选图")
    parser.add_argument("--sleep", type=float, default=0.35, help="请求之间的间隔秒数")
    parser.add_argument("--no-verify", action="store_true", help="跳过视觉模型校验（更快，但可能补错图）")
    parser.add_argument("--overwrite", action="store_true", help="重新抓取 manifest 中已有的菜谱")
    args = parser.parse_args()

    manifest = _load_manifest()
    images = manifest.setdefault("images", {})
    missing = _scan_missing(args.only or None)
    if args.overwrite:
        # Only re-fetch recipes that are part of this run; never wipe entries
        # for recipes excluded by --only/--limit.
        targets = {relative for _, relative, _, _ in missing}
        for key in list(images):
            if key in targets:
                images.pop(key, None)
    else:
        # Incremental by default: skip recipes that already have an entry.
        missing = [item for item in missing if item[1] not in images]
    if args.limit:
        missing = missing[: args.limit]

    print(f"missing recipes: {len(missing)}")
    if args.dry_run:
        for title, relative, category, _ in missing:
            print(f"  {title:<20} {relative}  queries={_build_queries(title, category)}")
        return 0

    _write_readme()
    filled = 0
    failed: list[str] = []
    low_confidence: list[str] = []
    unverified: list[str] = []

    with httpx.Client(timeout=TIMEOUT, follow_redirects=True, headers=HEADERS) as client:
        for index, (title, relative, category, _) in enumerate(missing, start=1):
            prefix = f"[{index}/{len(missing)}] {title}"
            entry = _fetch_one(
                client,
                title,
                category,
                provider=args.provider,
                max_candidates=args.max_candidates,
                sleep=args.sleep,
                verify=not args.no_verify,
            )
            if not entry:
                print(f"{prefix}  FAILED")
                failed.append(title)
                continue
            images[relative] = entry
            _save_manifest(manifest)
            filled += 1
            print(
                f"{prefix}  {entry['provider']:<5} {entry['confidence']:<6} "
                f"verified={entry.get('verified')}  {entry['width']}x{entry['height']}  {entry['file']}"
            )
            if entry["confidence"] == "low":
                low_confidence.append(f"{title} ({relative})")
            if entry.get("verified") is not True:
                unverified.append(f"{title} ({relative})")

    _save_manifest(manifest)
    print("\n=== summary ===")
    print(f"filled: {filled}")
    print(f"failed: {len(failed)}")
    if failed:
        print("failed recipes:")
        for title in failed:
            print(f"  - {title}")
    if low_confidence:
        print("low-confidence (review recommended):")
        for item in low_confidence:
            print(f"  - {item}")
    if unverified:
        print("not visually verified (review recommended):")
        for item in unverified:
            print(f"  - {item}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
