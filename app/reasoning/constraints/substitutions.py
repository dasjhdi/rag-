"""静态食材替代建议（SU-15）。

替代建议只提供方向，必须由用户确认配料表；不构成医学或营养结论。
"""

from __future__ import annotations

from app.knowledge.ontology import normalize_ingredient


SUBSTITUTION_MAP: dict[str, tuple[str, ...]] = {
    "花生": ("南瓜籽", "葵花籽"),
    "花生酱": ("芝麻酱", "南瓜籽酱"),
    "坚果": ("南瓜籽", "葵花籽"),
    "牛奶": ("无乳糖牛奶", "豆奶"),
    "酸奶": ("无乳糖酸奶", "豆乳酸奶"),
    "奶油": ("椰浆", "植物奶油"),
    "黄油": ("植物油", "椰子油"),
    "奶酪": ("植物奶酪", "豆腐"),
    "鸡蛋": ("嫩豆腐", "亚麻籽粉"),
    "鸭蛋": ("嫩豆腐", "亚麻籽粉"),
    "面粉": ("无麸质面粉", "米粉"),
    "面条": ("米粉", "无麸质面条"),
    "面包": ("无麸质面包", "米饭"),
    "酱油": ("无麸质酱油", "椰子氨基酱油"),
    "猪肉": ("鸡胸肉", "豆腐"),
    "五花肉": ("鸡胸肉", "杏鲍菇"),
    "牛肉": ("鸡胸肉", "豆腐"),
    "鸡肉": ("豆腐", "杏鲍菇"),
    "羊肉": ("鸡胸肉", "豆腐"),
    "虾": ("豆腐", "杏鲍菇"),
    "鱼": ("豆腐", "杏鲍菇"),
    "蟹": ("豆腐", "杏鲍菇"),
    "蛤蜊": ("豆腐", "杏鲍菇"),
    "蚝油": ("素蚝油", "香菇酱"),
    "鱼露": ("酱油", "香菇调味汁"),
}


def suggest_substitutions(ingredient: str) -> list[str]:
    """返回某个食材的替代方向，统一附带“需确认”。"""
    canonical = normalize_ingredient(ingredient)
    if not canonical:
        return []
    targets = SUBSTITUTION_MAP.get(canonical, ())
    return [
        f"{canonical} → {target}（需确认，请核对配料表与过敏原）"
        for target in targets
    ]


__all__ = ["SUBSTITUTION_MAP", "suggest_substitutions"]
