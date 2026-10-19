# 菜谱补图说明

HowToCook 语料中有部分菜谱没有自带成品图。前端会用“首字 + 暂无成品图”的暖色卡片兜底，
同时项目提供了一套**可逆的补图覆盖机制**：

- 图片保存在 `data/recipe_images/`
- 覆盖关系记录在 `data/recipe_images/manifest.json`
- 解析器优先使用菜谱 Markdown 里的图片；只有当 Markdown 没有可用图片时，才读取 manifest
- 因此补图不会修改 `data/HowToCook` 里的原始 Markdown，语料同步后也不会丢失

## 使用

```bash
# 查看还有多少道菜缺图（只打印，不下载）
python -m scripts.fetch_recipe_images --dry-run

# 先试跑几道
python -m scripts.fetch_recipe_images --only 水煮鱼

# 批量补齐（百度优先，Bing 兜底；视觉模型校验）
python -m scripts.fetch_recipe_images --sleep 0.15 --max-candidates 5

# 跳过视觉校验（更快，但可能补错图）
python -m scripts.fetch_recipe_images --no-verify
```

常用参数：

| 参数 | 说明 |
| --- | --- |
| `--limit N` | 最多处理 N 道 |
| `--only 关键词` | 只处理标题/路径包含关键词的菜谱 |
| `--provider auto\|baidu\|bing` | 图片来源策略，默认 `auto` |
| `--max-candidates N` | 每个查询最多尝试 N 张候选图 |
| `--no-verify` | 跳过视觉模型校验 |
| `--overwrite` | 重抓本次选中的菜谱（只影响 `--only`/`--limit` 命中的条目，不会清空整个 manifest） |

默认是增量模式：manifest 里已有条目的菜谱会被跳过，中断后可直接重跑续补。

> 2026-10-19 修复：早期版本的 `--overwrite` 会清空整个 manifest，配合 `--only` 使用会丢失其它条目。
> 该问题已修复；现有 manifest 是从审核检查表与文件时间序列重建并逐张人工复核的，
> 但原始抓取的 `source_url` / `query` 未能恢复（字段为 `null`）。

## 匹配策略

1. 按菜谱分类构造查询：水产 → “海鲜 菜”，早餐 → “早餐”，调料 → “调料”，饮品 → “饮品”等
2. 对易混淆菜名做别名与消歧：如“响油鳝丝”使用“响油鳝糊”、“咖喱炒蟹”使用“咖喱蟹”、
   “B52轰炸机”追加“鸡尾酒”
3. 中文菜名优先使用百度图片搜索；结果不足时用 Bing 图片异步接口兜底
4. 只接受 400×300 以上、宽高比合理的图片，统一裁剪为 4:3 并压缩为 JPEG
5. 视觉模型复核：“图片是否与菜名相符”，地图、文字截图、产品包装、人物、风景等会被拒绝
6. manifest 记录 `provider`、`query`、`source_url`、`page_url`、`confidence`、`verified`

## 当前覆盖

- HowToCook 语料 373 道菜，补图 195 道，**覆盖率 100%**（373/373 有图）
- 补图全部经过视觉校验或人工复核（`verified: true`）
- 缩略图接口对原图宽度不超过请求宽度的图片直接返回原文件，避免无谓重编码

## 版权说明

补图来自公开图片搜索结果，`manifest.json` 保留了每张图的来源页面与图片地址，仅用于本地开发/演示。
在公开发布或商用前，请替换为有明确授权的图片，或删除 `data/recipe_images/` 与 manifest 中对应条目。

## 回滚

```bash
rm -rf data/recipe_images
```

删除后解析器会自动回到“首字 + 暂无成品图”的兜底状态，无需改代码。
