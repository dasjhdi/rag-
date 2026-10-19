/**
 * Import a recipe from a public URL or a photo.
 * The backend stores it as a personal recipe and returns the parsed payload.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  ArrowRight,
  CheckCircle2,
  ImagePlus,
  Link2,
  Loader2,
  Sparkles,
  UploadCloud,
  X,
} from 'lucide-react';
import { Modal, RecipeImage } from '../common';
import { useAuth } from '../../contexts';
import { importRecipeFromImage, importRecipeFromUrl } from '../../services/api/diet';
import type { RecipeImportResult } from '../../types/diet';

type Tab = 'url' | 'image';

interface ImportRecipeModalProps {
  open: boolean;
  onClose: () => void;
  onOpenRecipe: (recipeId: string) => void;
  onImported?: (result: RecipeImportResult) => void;
}

const ACCEPTED_TYPES = ['image/jpeg', 'image/png', 'image/webp', 'image/gif'];
const MAX_IMAGE_MB = 10;

function formatHost(url?: string): string {
  if (!url) return '';
  try {
    return new URL(url).hostname;
  } catch {
    return url;
  }
}

function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const value = String(reader.result || '');
      resolve(value.includes(',') ? value.split(',', 2)[1] : value);
    };
    reader.onerror = () => reject(new Error('读取图片失败'));
    reader.readAsDataURL(file);
  });
}

export function ImportRecipeModal({
  open,
  onClose,
  onOpenRecipe,
  onImported,
}: ImportRecipeModalProps) {
  const { token } = useAuth();
  const [tab, setTab] = useState<Tab>('url');
  const [url, setUrl] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState('');
  const [dragging, setDragging] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState<RecipeImportResult | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) {
      setTab('url');
      setUrl('');
      setFile(null);
      setPreview('');
      setDragging(false);
      setLoading(false);
      setError('');
      setResult(null);
    }
  }, [open]);

  useEffect(() => {
    if (!file) {
      setPreview('');
      return;
    }
    const objectUrl = URL.createObjectURL(file);
    setPreview(objectUrl);
    return () => URL.revokeObjectURL(objectUrl);
  }, [file]);

  const pickFile = useCallback((next: File | null) => {
    setError('');
    if (!next) return;
    if (!ACCEPTED_TYPES.includes(next.type)) {
      setError('只支持 JPG、PNG、WebP、GIF 图片');
      return;
    }
    if (next.size > MAX_IMAGE_MB * 1024 * 1024) {
      setError(`图片不能超过 ${MAX_IMAGE_MB}MB`);
      return;
    }
    setFile(next);
  }, []);

  const resetForAnother = () => {
    setResult(null);
    setUrl('');
    setFile(null);
    setError('');
  };

  const submit = async () => {
    if (!token || loading) return;
    setError('');
    setLoading(true);
    try {
      let imported: RecipeImportResult;
      if (tab === 'url') {
        const trimmed = url.trim();
        if (!/^https?:\/\//i.test(trimmed)) {
          throw new Error('请输入以 http:// 或 https:// 开头的菜谱链接');
        }
        imported = await importRecipeFromUrl(token, trimmed);
      } else {
        if (!file) {
          throw new Error('请先选择一张菜谱图片');
        }
        const imageBase64 = await fileToBase64(file);
        imported = await importRecipeFromImage(token, {
          image_base64: imageBase64,
          mime_type: file.type,
          filename: file.name,
        });
      }
      setResult(imported);
      onImported?.(imported);
    } catch (err) {
      setError(err instanceof Error ? err.message : '导入失败，请稍后重试');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal open={open} onClose={onClose} title="导入菜谱" maxWidth="2xl">
      <div className="max-h-[78vh] overflow-y-auto p-5 md:p-6">
        {result ? (
          <div className="space-y-5">
            <div className="flex items-center gap-2 text-herb-600 dark:text-herb-300">
              <CheckCircle2 className="w-5 h-5" />
              <span className="text-sm font-medium">已加入「我的菜谱」，并完成向量化</span>
            </div>

            <div className="overflow-hidden rounded-2xl border border-cream-300/60 dark:border-white/10">
              <RecipeImage
                src={result.document.image_url || result.recipe.image_url}
                title={result.recipe.title}
                alt={result.recipe.title}
                className="aspect-[16/8]"
                loading="eager"
                width={800}
              />
              <div className="p-5">
                <h3 className="ch-display text-2xl text-ink-900 dark:text-cream-50">
                  {result.recipe.title}
                </h3>
                <p className="mt-1 text-sm text-ink-500 dark:text-ink-300">
                  {result.recipe.ingredients.length} 种食材 · {result.recipe.steps.length} 个步骤
                  {result.recipe.nutrition?.totals?.calories
                    ? ` · ${Math.round(result.recipe.nutrition.totals.calories)} kcal`
                    : ''}
                </p>
                {result.source_url ? (
                  <p className="mt-1 truncate text-xs text-ink-400">
                    来源：{formatHost(result.source_url)}
                  </p>
                ) : null}
              </div>
            </div>

            <div className="flex flex-wrap gap-3">
              <button
                type="button"
                onClick={() => onOpenRecipe(result.document.id)}
                className="ch-btn ch-btn-primary"
              >
                查看菜谱
                <ArrowRight className="w-4 h-4" />
              </button>
              <button type="button" onClick={resetForAnother} className="ch-btn ch-btn-secondary">
                再导入一个
              </button>
            </div>
          </div>
        ) : (
          <div className="space-y-5">
            <div className="flex gap-2 rounded-2xl bg-cream-100/80 p-1.5 dark:bg-white/5">
              <button
                type="button"
                onClick={() => {
                  setTab('url');
                  setError('');
                }}
                className={`flex flex-1 items-center justify-center gap-2 rounded-xl px-4 py-2.5 text-sm font-medium transition-colors ${
                  tab === 'url'
                    ? 'bg-white text-ink-900 shadow-sm dark:bg-ink-800 dark:text-cream-100'
                    : 'text-ink-500 hover:text-ink-700 dark:text-ink-300 dark:hover:text-cream-100'
                }`}
              >
                <Link2 className="w-4 h-4" />
                从链接导入
              </button>
              <button
                type="button"
                onClick={() => {
                  setTab('image');
                  setError('');
                }}
                className={`flex flex-1 items-center justify-center gap-2 rounded-xl px-4 py-2.5 text-sm font-medium transition-colors ${
                  tab === 'image'
                    ? 'bg-white text-ink-900 shadow-sm dark:bg-ink-800 dark:text-cream-100'
                    : 'text-ink-500 hover:text-ink-700 dark:text-ink-300 dark:hover:text-cream-100'
                }`}
              >
                <ImagePlus className="w-4 h-4" />
                图片识别
              </button>
            </div>

            {tab === 'url' ? (
              <div className="space-y-3">
                <label className="block">
                  <span className="ch-label">菜谱链接</span>
                  <div className="ch-input flex items-center gap-2 !py-2.5">
                    <Link2 className="w-4 h-4 shrink-0 text-ink-400" />
                    <input
                      value={url}
                      onChange={event => setUrl(event.target.value)}
                      onKeyDown={event => {
                        if (event.key === 'Enter') {
                          event.preventDefault();
                          void submit();
                        }
                      }}
                      placeholder="https://www.xiachufang.com/recipe/..."
                      className="w-full bg-transparent text-sm outline-none placeholder-ink-400"
                      autoFocus
                    />
                  </div>
                </label>
                <p className="text-xs leading-relaxed text-ink-400">
                  支持带结构化数据的菜谱网页（大部分菜谱站、美食博客）。会自动抓取菜名、原料、步骤和封面图。
                </p>
                <button
                  type="button"
                  onClick={() => void submit()}
                  disabled={loading || !url.trim()}
                  className="ch-btn ch-btn-primary w-full !py-3"
                >
                  {loading ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin" />
                      正在抓取并解析…
                    </>
                  ) : (
                    <>
                      <Sparkles className="w-4 h-4" />
                      导入这道菜
                    </>
                  )}
                </button>
              </div>
            ) : (
              <div className="space-y-3">
                <input
                  ref={inputRef}
                  type="file"
                  accept={ACCEPTED_TYPES.join(',')}
                  className="hidden"
                  onChange={event => {
                    pickFile(event.target.files?.[0] || null);
                    event.target.value = '';
                  }}
                />
                {preview ? (
                  <div className="relative overflow-hidden rounded-2xl border border-cream-300/60 dark:border-white/10">
                    <img src={preview} alt="待识别的菜谱" className="max-h-64 w-full object-cover" />
                    <button
                      type="button"
                      onClick={() => setFile(null)}
                      className="absolute right-2 top-2 rounded-full bg-ink-900/70 p-1.5 text-white hover:bg-ink-900"
                      aria-label="移除图片"
                    >
                      <X className="w-4 h-4" />
                    </button>
                  </div>
                ) : (
                  <button
                    type="button"
                    onClick={() => inputRef.current?.click()}
                    onDragOver={event => {
                      event.preventDefault();
                      setDragging(true);
                    }}
                    onDragLeave={() => setDragging(false)}
                    onDrop={event => {
                      event.preventDefault();
                      setDragging(false);
                      pickFile(event.dataTransfer.files?.[0] || null);
                    }}
                    className={`flex w-full flex-col items-center justify-center gap-3 rounded-2xl border-2 border-dashed px-6 py-12 transition-colors ${
                      dragging
                        ? 'border-ember-400 bg-ember-50/70 dark:bg-ember-500/10'
                        : 'border-cream-300 bg-cream-50/60 hover:border-ember-300 dark:border-white/10 dark:bg-white/[0.03]'
                    }`}
                  >
                    <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-ember-100 text-ember-600 dark:bg-ember-500/15 dark:text-ember-300">
                      <UploadCloud className="w-6 h-6" />
                    </span>
                    <span className="text-sm font-medium text-ink-700 dark:text-cream-100">
                      拖入菜谱照片，或点击选择
                    </span>
                    <span className="text-xs text-ink-400">
                      支持 JPG / PNG / WebP / GIF，最大 {MAX_IMAGE_MB}MB
                    </span>
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => void submit()}
                  disabled={loading || !file}
                  className="ch-btn ch-btn-primary w-full !py-3"
                >
                  {loading ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin" />
                      正在识别图片…
                    </>
                  ) : (
                    <>
                      <Sparkles className="w-4 h-4" />
                      识别并导入
                    </>
                  )}
                </button>
              </div>
            )}

            {error ? (
              <div className="rounded-xl border border-red-200/70 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-800/50 dark:bg-red-900/25 dark:text-red-300">
                {error}
              </div>
            ) : null}

            <p className="border-t border-cream-200/70 pt-4 text-xs leading-relaxed text-ink-400 dark:border-white/10">
              导入后会进入「我的菜谱」，可在知识库中编辑或删除；菜谱也会自动参与搜索、饮食计划和 RAG 检索。
            </p>
          </div>
        )}
      </div>
    </Modal>
  );
}
