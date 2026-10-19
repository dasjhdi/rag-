"""Family member merge and validation tests."""

import pytest
from pydantic import ValidationError

from app.api.v1.endpoints.family import FamilyMemberRequest
from app.diet.family.service import merge_family_members


def test_merge_family_members_deduplicates_constraints():
    merged = merge_family_members(
        [
            {
                "allergies": ["花生", "牛奶"],
                "dietary_restrictions": ["vegetarian"],
                "disliked_foods": ["香菜"],
                "calorie_goal": 1800,
                "servings_factor": 1.0,
            },
            {
                "allergies": ["花生", "虾"],
                "dietary_restrictions": ["gluten_free"],
                "disliked_foods": ["香菜", "芹菜"],
                "calorie_goal": 2200,
                "servings_factor": 0.5,
            },
        ]
    )
    assert merged["allergies"] == ["花生", "牛奶", "虾"]
    assert merged["dietary_restrictions"] == ["vegetarian", "gluten_free"]
    assert merged["avoided_foods"] == ["香菜", "芹菜"]
    assert merged["calorie_goal"] == 4000
    assert merged["household_size"] == 1.5
    assert merged["family_member_count"] == 2


def test_merge_empty_family_uses_defaults():
    merged = merge_family_members([])
    assert merged["allergies"] == []
    assert merged["calorie_goal"] is None
    assert merged["household_size"] == 1.0
    assert merged["family_member_count"] == 0


def test_family_member_request_validation():
    with pytest.raises(ValidationError):
        FamilyMemberRequest(calorie_goal=100)
    with pytest.raises(ValidationError):
        FamilyMemberRequest(servings_factor=0)
    member = FamilyMemberRequest(name="妈妈", allergies=["花生"], servings_factor=0.8)
    assert member.name == "妈妈"
    assert member.allergies == ["花生"]
