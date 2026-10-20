/**
 * Application constants
 */

// API Configuration
export const API_BASE = '/api/v1';

// Media assets (recipe photos). In development Vite proxies /media to the API;
// set VITE_MEDIA_BASE when the frontend and API are served from different origins.
export const MEDIA_BASE = (
  (import.meta.env.VITE_MEDIA_BASE as string | undefined) || ''
).replace(/\/$/, '');

// Pagination
export const CONVERSATIONS_PAGE_SIZE = 30;

// Storage Keys
export const STORAGE_KEYS = {
  TOKEN: 'cookhero_token',
  USERNAME: 'cookhero_username',
  THEME: 'theme',
  STREAMING_CACHE: 'cookhero_streaming_cache',
} as const;

// Intent Labels
export const INTENT_LABELS: Record<string, string> = {
  recipe_search: '菜谱搜索',
  cooking_tips: '烹饪技巧',
  ingredient_info: '食材信息',
  recommendation: '菜品推荐',
  general_chat: '闲聊',
};

// Date Category Labels
export const DATE_CATEGORY_LABELS = {
  today: 'Today',
  yesterday: 'Yesterday',
  lastWeek: 'Last 7 Days',
  lastMonth: 'Last 30 Days',
  older: 'Older',
} as const;

// Tool Labels: 工具标识 → 中文名
// 界面只展示中文名，英文标识仅作为 title 提示与调试用途保留。
export const TOOL_LABELS: Record<string, string> = {
  // 内置工具（app/agent/tools 与 app/diet/tools）
  calculator: '数学计算',
  datetime: '日期时间',
  web_search: '联网搜索',
  image_generator: 'AI 生图',
  knowledge_base_search: '菜谱知识库',
  deep_research: '深度研究',
  diet_plan: '饮食计划',
  diet_log: '饮食记录',
  diet_analysis: '营养分析',
  recipe_search: '菜谱搜索',
  nutrition_calculator: '营养计算',
  unit_converter: '单位换算',
  pantry_manager: '食材库存',
  shopping_list: '购物清单',
  kitchen_timer: '厨房计时',
  // 高德地图 MCP（内置 amap 服务）
  maps_geo: '地址转坐标',
  maps_regeocode: '坐标转地址',
  maps_ip_location: 'IP 定位',
  maps_weather: '天气查询',
  maps_text_search: '关键词搜索',
  maps_around_search: '周边搜索',
  maps_search_detail: '地点详情',
  maps_distance: '距离测量',
  maps_direction_driving: '驾车路线',
  maps_direction_walking: '步行路线',
  maps_direction_bicycling: '骑行路线',
  maps_direction_transit_integrated: '公共交通路线',
  maps_schema_navi: '一键导航',
  maps_schema_personal_map: '行程地图',
  maps_schema_take_taxi: '一键打车',
  // 内置子代理
  diet_planner: '饮食规划专家',
  generic: '通用助手',
};

// MCP / 内置服务名 → 中文名
export const SERVER_LABELS: Record<string, string> = {
  builtin: '内置工具',
  amap: '高德地图',
};

// 按长度倒序，保证后缀匹配时优先命中更长的键（如 maps_direction_driving 先于 maps_geo）
const TOOL_LABEL_KEYS = Object.keys(TOOL_LABELS).sort((a, b) => b.length - a.length);

/**
 * 还原 MCP 工具的真实名称。
 *
 * MCP 工具名格式为 `mcp_{server}_{tool}`，而 tool 自身可能含多个下划线
 * （如 mcp_amap_maps_direction_bicycling），因此不能按“第一个/最后一个下划线”截断，
 * 必须先按字典做后缀匹配，匹配不到才退化为剥掉 `mcp_{server}_` 一段。
 */
export function resolveToolName(name: string): string {
  if (TOOL_LABELS[name]) return name;
  if (!name.startsWith('mcp_')) return name;

  const matched = TOOL_LABEL_KEYS.find(
    (key) => name.endsWith(`_${key}`) || name === key
  );
  if (matched) return matched;

  const stripped = name.match(/^mcp_[^_]+_(.+)$/);
  return stripped ? stripped[1] : name;
}

/**
 * 取工具的中文显示名。
 * 未收录的工具会把下划线转为空格并首字母大写，保证仍可读，不会直接暴露裸标识。
 */
export function getToolLabel(name: string): string {
  const key = resolveToolName(name);
  if (TOOL_LABELS[key]) return TOOL_LABELS[key];
  return key
    .replace(/_/g, ' ')
    .replace(/\b[a-z]/g, (c) => c.toUpperCase());
}

/** 取 MCP / 内置服务的中文显示名 */
export function getServerLabel(name: string): string {
  return SERVER_LABELS[name] ?? name;
}

// App Info
export const APP_NAME = 'CookHero';
export const APP_EMOJI = '🍳';
