"""Domain knowledge used by semantic understanding and constraint reasoning."""

from app.knowledge.ontology import (
    allergens_for,
    canonicalize_ingredients,
    diet_tags_for,
    explain_allergens,
    normalize_ingredient,
)

__all__ = [
    "normalize_ingredient",
    "canonicalize_ingredients",
    "allergens_for",
    "diet_tags_for",
    "explain_allergens",
]
