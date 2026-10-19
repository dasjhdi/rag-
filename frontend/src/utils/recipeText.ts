/**
 * 菜谱文本清洗：去掉 HowToCook 源数据里残留的 MediaWiki 标记
 * 例如 `[[自制成品|[[面包.jpg]]` → `面包`
 */
export function cleanRecipeText(text?: string | null): string {
  if (!text) return '';

  let value = text;
  for (let i = 0; i < 3; i += 1) {
    value = value.replace(/\[\[([^[\]]*)\|([^[\]]*)\]\]/g, '$2');
    value = value.replace(/\[\[([^[\]]*)\]\]/g, '$1');
  }

  return value
    .replace(/!\[[^\]]*\]\([^)]*\)/g, '')
    .replace(/[\[\]]/g, '')
    .replace(/\s+/g, ' ')
    .trim();
}
