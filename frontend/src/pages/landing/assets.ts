/**
 * 落地页素材：全部来自真实菜谱库（data/recipe_images），
 * 通过后端 /media/recipe-images 提供，支持 ?w= 缩略。
 */

export interface Dish {
  name: string;
  en: string;
  file: string;
}

export const DISHES: Dish[] = [
  { name: '水煮鱼', en: 'Sichuan Poached Fish', file: '263711600393.jpg' },
  { name: '肉蟹煲', en: 'Crab Hot Pot', file: '257988e71549.jpg' },
  { name: '咖喱炒蟹', en: 'Curry Crab', file: '72d9966dfd20.jpg' },
  { name: '红烧鱼', en: 'Braised Fish', file: '25191468cd37.jpg' },
  { name: '可乐鸡翅', en: 'Cola Chicken Wings', file: 'dc0557174a72.jpg' },
  { name: '咕噜肉', en: 'Sweet & Sour Pork', file: 'c49722c10ac8.jpg' },
  { name: '乡村啤酒鸭', en: 'Beer Braised Duck', file: '154e1d4435fb.jpg' },
  { name: '冷吃兔', en: 'Cold Tossed Rabbit', file: '035e6ad81355.jpg' },
  { name: '冬瓜桑拿鸡', en: 'Steamed Chicken', file: '1e2787bace50.jpg' },
  { name: '手抓饼', en: 'Scallion Flatbread', file: 'b3f4822872f9.jpg' },
  { name: '煎饺', en: 'Pan-fried Dumplings', file: '67e883931e54.jpg' },
  { name: '杨枝甘露', en: 'Mango Pomelo Sago', file: 'e4db35c81551.jpg' },
  { name: '草莓冰淇淋', en: 'Strawberry Ice Cream', file: '1d8d85ff0bc8.jpg' },
  { name: '奥利奥冰淇淋', en: 'Oreo Ice Cream', file: '5c66874e314d.jpg' },
  { name: '奶茶', en: 'Milk Tea', file: '4eff573faaa1.jpg' },
  { name: '太阳蛋', en: 'Sunny-side Egg', file: '590337c5058b.jpg' },
];

export function dishSrc(file: string, width = 900): string {
  return `/media/recipe-images/${file}?w=${width}`;
}

/** Hero 轮播用的四张主图，按上菜顺序切换。 */
export const HERO_SLIDES = [DISHES[0], DISHES[1], DISHES[4], DISHES[5]];

/**
 * 场景配图：按「快手上菜 / 一桌硬菜 / 清淡减脂 / 可批量备菜」挑选，
 * 与每场景的文案对应，而不是复用同一批图。
 */
export const SCENE_SHOTS: string[][] = [
  ['67e883931e54.jpg', 'b3f4822872f9.jpg'], // 工作日晚餐：煎饺、手抓饼
  ['257988e71549.jpg', '263711600393.jpg'], // 家庭聚餐：肉蟹煲、水煮鱼
  ['529e6346f56f.jpg', '373e77b9d0b8.jpg'], // 减脂餐：蒜蓉西兰花、清蒸生蚝
  ['035e6ad81355.jpg', 'c49722c10ac8.jpg'], // 周末备菜：冷吃兔、咕噜肉
];
