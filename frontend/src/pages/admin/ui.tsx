/**
 * 后台公用小组件：日期格式化、CSV 导出、轻量弹窗。
 * 不引入 UI 库，避免继续增大已经 1.3MB 的包体。
 */

import { useEffect } from 'react';
import { X } from 'lucide-react';

export const ROLE_LABELS: Record<string, string> = {
  super_admin: '超级管理员',
  ops: '运营',
  support: '客服',
  viewer: '只读',
  user: '普通用户',
};

export const ROLE_CLASSES: Record<string, string> = {
  super_admin: 'bg-purple-100 text-purple-700 dark:bg-purple-500/15 dark:text-purple-300',
  ops: 'bg-blue-100 text-blue-700 dark:bg-blue-500/15 dark:text-blue-300',
  support: 'bg-teal-100 text-teal-700 dark:bg-teal-500/15 dark:text-teal-300',
  viewer: 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300',
  user: 'bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400',
};

export function formatDate(value: string | null): string {
  if (!value) return '—';
  // 后端返回的是 naive UTC，补上 Z 再转本地时间
  const d = new Date(value.endsWith('Z') ? value : `${value}Z`);
  if (Number.isNaN(d.getTime())) return '—';
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export function formatMoney(value: number, currency = 'CNY'): string {
  const symbol = currency === 'USD' ? '$' : '¥';
  if (value >= 1000) return `${symbol}${value.toFixed(0)}`;
  if (value >= 1) return `${symbol}${value.toFixed(2)}`;
  return `${symbol}${value.toFixed(3)}`;
}

/** 导出 CSV（带 BOM，Excel 打开不乱码） */
export function exportCsv(filename: string, header: string[], rows: (string | number)[][]): void {
  const escape = (cell: string | number) => {
    const text = String(cell ?? '');
    return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
  };
  const body = [header, ...rows].map((row) => row.map(escape).join(',')).join('\r\n');
  const blob = new Blob([`\uFEFF${body}`], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

export function Modal({
  title,
  children,
  onClose,
  width = 'max-w-md',
}: {
  title: string;
  children: React.ReactNode;
  onClose: () => void;
  width?: string;
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <div
        className={`relative w-full ${width} bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-2xl shadow-xl`}
      >
        <div className="flex items-center justify-between px-5 py-3 border-b border-gray-100 dark:border-gray-800">
          <h3 className="text-sm font-semibold text-gray-800 dark:text-gray-100">{title}</h3>
          <button
            onClick={onClose}
            className="p-1 rounded text-gray-400 hover:text-gray-700 dark:hover:text-gray-200"
            aria-label="关闭"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
        <div className="px-5 py-4">{children}</div>
      </div>
    </div>
  );
}
