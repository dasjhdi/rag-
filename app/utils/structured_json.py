import json
from typing import Any, Dict, Iterator, Optional
import re

# Markdown fenced block (json or plain)
FENCED_BLOCK_RE = re.compile(
    r"```(?:json)?\s*([\s\S]*?)```",
    re.IGNORECASE,
)
# Kept for backwards compatibility; the balanced scanner below is preferred.
JSON_BLOCK_RE = FENCED_BLOCK_RE
JSON_OBJECT_RE = re.compile(
    r"\{[\s\S]*?\}",
    re.MULTILINE,
)


def _iter_balanced_json_objects(content: str) -> Iterator[str]:
    """Yield balanced ``{...}`` candidates, ignoring braces inside strings."""
    length = len(content)
    index = 0
    while index < length:
        start = content.find("{", index)
        if start == -1:
            return

        depth = 0
        in_string = False
        escaped = False
        for pos in range(start, length):
            char = content[pos]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    yield content[start : pos + 1]
                    index = pos + 1
                    break
        else:
            # Unbalanced from this start; try the next opening brace.
            index = start + 1


def _try_loads(candidate: str) -> Optional[Any]:
    """Parse JSON, tolerating trailing commas emitted by some models."""
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        pass

    cleaned = re.sub(r",\s*([}\]])", r"\1", candidate)
    if cleaned != candidate:
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            return None
    return None


def extract_first_valid_json(content: str) -> Dict[str, Any]:
    """Extract the first valid JSON object from LLM output.

    Handles fenced code blocks, prose before/after the object, nested objects,
    and braces inside string values. Raises ``ValueError`` when no JSON object
    can be recovered.
    """
    if not content or not content.strip():
        raise ValueError("No valid JSON found in response")

    text = content.strip()

    # Fast path: the whole response is a JSON object.
    parsed = _try_loads(text)
    if isinstance(parsed, dict):
        return parsed

    candidates = list(FENCED_BLOCK_RE.findall(text))
    candidates.extend(_iter_balanced_json_objects(text))

    for candidate in candidates:
        parsed = _try_loads(candidate.strip())
        if isinstance(parsed, dict):
            return parsed

    raise ValueError("No valid JSON found in response")
