"""SU-6 多模态到检索桥接测试（离线）。"""

from app.vision.agent import VisionAgent, VisionAnalysisResult, VisionIntent


def _result(
    *,
    food=True,
    dish=None,
    ingredients=None,
    intent=None,
    confidence=0.9,
) -> VisionAnalysisResult:
    info = {}
    if dish is not None:
        info["dish_name"] = dish
    if ingredients is not None:
        info["ingredients"] = ingredients

    return VisionAnalysisResult(
        is_food_related=food,
        intent=intent or (
            VisionIntent.RECIPE_REQUEST if food else VisionIntent.GENERAL_IMAGE
        ),
        description="测试图片",
        extracted_info=info,
        direct_response=None,
        confidence=confidence,
        raw_response="{}",
    )


def test_non_food_image_returns_none():
    result = _result(food=False, dish="番茄炒蛋", ingredients=["番茄"])
    assert VisionAgent().build_retrieval_query(result) is None


def test_ingredients_are_normalized_and_deduplicated():
    result = _result(ingredients=["马铃薯", "土豆", "洋芋"])
    assert VisionAgent().build_retrieval_query(result) == "土豆"


def test_ingredient_string_is_split():
    result = _result(ingredients="番茄, 鸡蛋、番茄")
    assert VisionAgent().build_retrieval_query(result) == "番茄 鸡蛋"


def test_dish_only_returns_dish_name():
    result = _result(dish="宫保鸡丁")
    assert VisionAgent().build_retrieval_query(result) == "宫保鸡丁"


def test_dish_and_ingredients_are_combined():
    result = _result(dish="番茄炒蛋", ingredients=["番茄", "鸡蛋"])
    query = VisionAgent().build_retrieval_query(result)
    assert query == "番茄炒蛋 番茄 鸡蛋"


def test_no_dish_and_no_ingredients_returns_none():
    assert VisionAgent().build_retrieval_query(_result()) is None


def test_query_is_single_line():
    result = _result(dish="宫保\n鸡丁", ingredients=["鸡胸肉"])
    query = VisionAgent().build_retrieval_query(result)
    assert "\n" not in query
    assert query == "宫保 鸡丁 鸡肉"


def test_query_length_is_bounded():
    result = _result(ingredients=[f"食材{i}" for i in range(40)])
    query = VisionAgent().build_retrieval_query(result)
    assert len(query) <= VisionAgent.MAX_RETRIEVAL_QUERY_LENGTH


def test_unknown_ingredient_is_preserved():
    result = _result(ingredients=["  神秘食材  "])
    assert VisionAgent().build_retrieval_query(result) == "神秘食材"


def test_empty_ingredient_values_are_ignored():
    result = _result(ingredients=["", "  ", None, "番茄"])
    assert VisionAgent().build_retrieval_query(result) == "番茄"


def test_direct_answer_for_dish_identification():
    result = _result(
        dish="什锦炒虾仁",
        ingredients=["虾仁", "西兰花", "玉米"],
        intent=VisionIntent.DISH_IDENTIFICATION,
    )
    answer = VisionAgent().build_direct_answer(result)
    assert answer is not None
    assert "什锦炒虾仁" in answer
    assert "虾仁、西兰花、玉米" in answer
    assert "请问" not in answer


def test_direct_answer_for_ingredient_identification():
    result = _result(
        ingredients="虾仁, 西兰花、玉米",
        intent=VisionIntent.INGREDIENT_IDENTIFICATION,
    )
    answer = VisionAgent().build_direct_answer(result)
    assert answer is not None
    assert "虾仁、西兰花、玉米" in answer
    assert "暂未确定具体名称" in answer


def test_direct_answer_requires_dish_or_ingredients():
    result = _result(intent=VisionIntent.DISH_IDENTIFICATION)
    assert VisionAgent().build_direct_answer(result) is None


def test_direct_answer_not_used_for_recipe_request():
    result = _result(
        dish="什锦炒虾仁",
        ingredients=["虾仁"],
        intent=VisionIntent.RECIPE_REQUEST,
    )
    assert VisionAgent().build_direct_answer(result) is None


def test_direct_answer_not_used_for_non_food_image():
    result = _result(
        food=False,
        dish="什锦炒虾仁",
        ingredients=["虾仁"],
        intent=VisionIntent.GENERAL_IMAGE,
    )
    assert VisionAgent().build_direct_answer(result) is None


def test_direct_answer_marks_low_confidence():
    result = _result(
        dish="疑似虾仁时蔬",
        ingredients=["虾仁"],
        intent=VisionIntent.DISH_IDENTIFICATION,
        confidence=0.4,
    )
    answer = VisionAgent().build_direct_answer(result)
    assert answer is not None
    assert "置信度较低" in answer


def test_direct_answer_ignores_empty_ingredients():
    result = _result(
        dish="时蔬小炒",
        ingredients=["", "  ", None, "虾仁", "虾仁"],
        intent=VisionIntent.DISH_IDENTIFICATION,
    )
    answer = VisionAgent().build_direct_answer(result)
    assert answer is not None
    assert answer.count("虾仁") == 1

def test_direct_answer_accepts_list_dish_name():
    """模型有时把候选菜名返回成数组，不能因此丢掉菜名。"""
    result = _result(
        dish=["虾仁炒时蔬", "什锦炒虾仁"],
        ingredients=["虾仁", "西兰花"],
        intent=VisionIntent.DISH_IDENTIFICATION,
    )
    answer = VisionAgent().build_direct_answer(result)
    assert answer is not None
    assert "虾仁炒时蔬" in answer
    assert "什锦炒虾仁" in answer
    assert "['" not in answer


def test_retrieval_query_accepts_list_dish_name():
    result = _result(dish=["虾仁炒时蔬", "什锦炒虾仁"], ingredients=["西兰花"])
    query = VisionAgent().build_retrieval_query(result)
    assert query == "虾仁炒时蔬 / 什锦炒虾仁 西兰花"


def test_rag_context_renders_list_dish_name_and_ingredients():
    result = _result(
        dish=["虾仁炒时蔬", "什锦炒虾仁"], ingredients=["西兰花", "玉米粒"]
    )
    context = VisionAgent().build_context_for_rag(result, "这是什么菜")
    assert "虾仁炒时蔬 / 什锦炒虾仁" in context
    assert "西兰花, 玉米粒" in context
    assert "['" not in context
