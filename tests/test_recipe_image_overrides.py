"""Fetched-image override tests (offline)."""

import json
from pathlib import Path

from PIL import Image

from app.diet.recipes.images import override_image_for
from app.diet.recipes.parser import parse_recipe_document


def _write_image(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (24, 16), (220, 90, 40)).save(path, "JPEG")


def _setup(tmp_path: Path) -> tuple[Path, Path, str]:
    corpus = tmp_path / "HowToCook"
    recipe = corpus / "dishes" / "meat_dish" / "demo.md"
    recipe.parent.mkdir(parents=True, exist_ok=True)
    recipe.write_text("# 测试菜\n\n## 操作\n1. 炒熟。\n", encoding="utf-8")

    image_dir = tmp_path / "recipe_images"
    _write_image(image_dir / "abc123.jpg")
    (image_dir / "manifest.json").write_text(
        json.dumps(
            {
                "version": 1,
                "images": {
                    "dishes/meat_dish/demo.md": {
                        "file": "abc123.jpg",
                        "title": "测试菜",
                    }
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return corpus, recipe, "dishes/meat_dish/demo.md"


def test_override_is_used_when_recipe_has_no_image(tmp_path):
    corpus, recipe, _ = _setup(tmp_path)
    parsed = parse_recipe_document(
        "r1",
        "测试菜",
        recipe.read_text(encoding="utf-8"),
        source=str(recipe),
        image_root=str(corpus),
    )

    assert parsed.image_url == "/media/recipe-images/abc123.jpg"
    assert parsed.images[0].alt == "测试菜"


def test_content_image_wins_over_override(tmp_path):
    corpus, recipe, _ = _setup(tmp_path)
    _write_image(recipe.parent / "local.jpg")
    content = "# 测试菜\n\n## 操作\n1. 炒熟。\n\n![本地图](./local.jpg)\n"

    parsed = parse_recipe_document(
        "r2", "测试菜", content, source=str(recipe), image_root=str(corpus)
    )

    assert parsed.image_url is not None
    assert "/media/recipes/" in parsed.image_url
    assert "recipe-images" not in parsed.image_url


def test_override_ignores_path_traversal_filename(tmp_path):
    corpus, recipe, relative = _setup(tmp_path)
    manifest_path = tmp_path / "recipe_images" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["images"][relative]["file"] = "../../secret.jpg"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    assert override_image_for(str(recipe), image_root=str(corpus)) is None


def test_override_returns_none_without_manifest(tmp_path):
    corpus = tmp_path / "HowToCook"
    recipe = corpus / "dishes" / "meat_dish" / "demo.md"
    recipe.parent.mkdir(parents=True, exist_ok=True)
    recipe.write_text("# 菜\n", encoding="utf-8")

    assert override_image_for(str(recipe), image_root=str(corpus)) is None
