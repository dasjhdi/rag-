"""Recipe image extraction and resolution tests (offline)."""

from pathlib import Path

from PIL import Image

from app.diet.recipes.images import (
    collect_recipe_images,
    resolve_image_url,
    strip_markdown_images,
)
from app.diet.recipes.parser import parse_recipe_document


def _write_image(path: Path, color: tuple[int, int, int] = (220, 90, 40)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (24, 16), color).save(path, "JPEG")


def _write_recipe(root: Path, content: str) -> Path:
    recipe_dir = root / "dishes" / "demo"
    recipe_dir.mkdir(parents=True, exist_ok=True)
    path = recipe_dir / "demo.md"
    path.write_text(content, encoding="utf-8")
    return path


SAMPLE = """# 测试菜

一句简介。

## 必备原料和工具

- 鸡蛋 2 个

## 操作

1. 打蛋。
2. ![成品](./成品.jpg)
3. 炒 2 分钟。
"""


def test_local_image_is_resolved_and_url_encoded(tmp_path):
    root = tmp_path / "corpus"
    recipe_path = _write_recipe(root, SAMPLE)
    _write_image(recipe_path.parent / "成品.jpg")

    recipe = parse_recipe_document(
        "r1",
        "测试菜",
        SAMPLE,
        source=str(recipe_path),
        image_root=str(root),
    )
    data = recipe.to_dict()

    assert data["image_url"] is not None
    assert data["image_url"].startswith("/media/recipes/dishes/demo/")
    assert "%E6%88%90%E5%93%81.jpg" in data["image_url"]
    assert len(data["images"]) == 1
    assert data["images"][0]["alt"] == "成品"


def test_image_only_line_is_not_a_step_and_attaches_to_previous_step(tmp_path):
    root = tmp_path / "corpus"
    recipe_path = _write_recipe(root, SAMPLE)
    _write_image(recipe_path.parent / "成品.jpg")

    recipe = parse_recipe_document(
        "r2", "测试菜", SAMPLE, source=str(recipe_path), image_root=str(root)
    )

    assert len(recipe.steps) == 2
    assert recipe.steps[0].text == "打蛋。"
    assert recipe.steps[1].text == "炒 2 分钟。"
    assert recipe.steps[0].image_url is not None
    assert "![" not in " ".join(step.text for step in recipe.steps)


def test_cover_prefers_finished_dish_over_step_photo(tmp_path):
    root = tmp_path / "corpus"
    content = """# 菜

## 必备原料和工具
- 盐 适量

## 操作
1. 处理食材。
2. ![步骤图](./step.jpg)
3. ![成品图](./cover.jpg)
"""
    recipe_path = _write_recipe(root, content)
    _write_image(recipe_path.parent / "step.jpg", (10, 10, 10))
    _write_image(recipe_path.parent / "cover.jpg", (250, 120, 40))

    images, cover = collect_recipe_images(content, str(recipe_path), image_root=str(root))

    assert len(images) == 2
    assert cover is not None
    assert cover.endswith("cover.jpg")


def test_path_traversal_is_rejected(tmp_path):
    root = tmp_path / "corpus"
    recipe_path = _write_recipe(root, "# 菜\n\n## 操作\n1. ![x](../../secret.jpg)\n")
    secret = tmp_path / "secret.jpg"
    _write_image(secret)

    resolve = resolve_image_url("../../secret.jpg", str(recipe_path), image_root=str(root))

    assert resolve is None


def test_remote_image_url_is_preserved():
    url = resolve_image_url("https://example.com/a.jpg", "personal::user")
    assert url == "https://example.com/a.jpg"


def test_strip_markdown_images_keeps_text():
    assert strip_markdown_images("先切菜 ![图](./a.jpg) 再下锅") == "先切菜  再下锅"
