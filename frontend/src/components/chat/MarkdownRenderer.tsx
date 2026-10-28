/**
 * Markdown Renderer Component
 * Renders markdown content with syntax highlighting, custom styling and
 * inline citations: `[1]` becomes a clickable marker that scrolls to the
 * matching source card under the message.
 */

import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeHighlight from 'rehype-highlight';
import { Fragment, cloneElement, isValidElement, useMemo } from 'react';
import type { ReactElement, ReactNode } from 'react';
import type { Components } from 'react-markdown';

// Import highlight.js styles (GitHub Dark theme)
import 'highlight.js/styles/github-dark.css';

export interface MarkdownRendererProps {
  content: string;
  className?: string;
  /** 消息 ID：提供后把 [n] 渲染成跳转到来源卡片的锚点 */
  messageId?: string;
}

const CITATION_PATTERN = /\[(\d{1,2})\]/g;

function focusSource(messageId: string, index: string): void {
  const target = document.getElementById(`msg-${messageId}-source-${index}`);
  if (!target) return;
  target.scrollIntoView({ behavior: 'smooth', block: 'center' });
  target.classList.add('ring-2', 'ring-orange-400/60');
  window.setTimeout(() => {
    target.classList.remove('ring-2', 'ring-orange-400/60');
  }, 1600);
}

/**
 * 递归替换文本节点里的 [n]。
 * 跳过 code/pre，避免把代码里的数组下标当成引用。
 */
function renderCitations(node: ReactNode, messageId?: string): ReactNode {
  if (!messageId) return node;

  if (typeof node === 'string') {
    const parts = node.split(CITATION_PATTERN);
    if (parts.length === 1) return node;

    return parts.map((part, index) =>
      index % 2 === 1 ? (
        <button
          key={`cite-${part}-${index}`}
          type="button"
          onClick={() => focusSource(messageId, part)}
          className="mx-0.5 inline-flex h-4 min-w-4 items-center justify-center rounded bg-orange-100 px-1 align-super text-[10px] font-medium leading-none text-orange-700 transition-colors hover:bg-orange-200 dark:bg-orange-500/20 dark:text-orange-300 dark:hover:bg-orange-500/30"
          title={`查看来源 ${part}`}
        >
          {part}
        </button>
      ) : (
        <Fragment key={`text-${index}`}>{part}</Fragment>
      )
    );
  }

  if (Array.isArray(node)) {
    return node.map((child, index) => (
      <Fragment key={`node-${index}`}>{renderCitations(child, messageId)}</Fragment>
    ));
  }

  if (isValidElement(node)) {
    const tag = typeof node.type === 'string' ? node.type : '';
    if (tag === 'code' || tag === 'pre') return node;

    const children = (node.props as { children?: ReactNode }).children;
    if (children === undefined) return node;

    return cloneElement(
      node as ReactElement<{ children?: ReactNode }>,
      undefined,
      renderCitations(children, messageId)
    );
  }

  return node;
}

function buildComponents(messageId?: string): Components {
  const cite = (children: ReactNode) => renderCitations(children, messageId);

  return {
    h1: ({ children }) => <h1 className="text-2xl font-bold mt-4 mb-2">{cite(children)}</h1>,
    h2: ({ children }) => <h2 className="text-xl font-semibold mt-4 mb-2">{cite(children)}</h2>,
    h3: ({ children }) => <h3 className="text-lg font-semibold mt-3 mb-2">{cite(children)}</h3>,
    h4: ({ children }) => <h4 className="text-base font-semibold mt-3 mb-1">{cite(children)}</h4>,
    p: ({ children }) => <p className="my-2 leading-relaxed">{cite(children)}</p>,
    ul: ({ children }) => <ul className="my-2 ml-4 list-disc space-y-1">{children}</ul>,
    ol: ({ children }) => <ol className="my-2 ml-4 list-decimal space-y-1">{children}</ol>,
    li: ({ children }) => <li className="leading-relaxed">{cite(children)}</li>,
    a: ({ href, children }) => (
      <a
        href={href}
        className="text-orange-600 dark:text-orange-400 hover:underline"
        target="_blank"
        rel="noopener noreferrer"
      >
        {children}
      </a>
    ),
    blockquote: ({ children }) => (
      <blockquote className="border-l-4 border-orange-400 pl-4 my-3 italic text-gray-600 dark:text-gray-400">
        {cite(children)}
      </blockquote>
    ),
    code: ({ className, children }) => {
      const isInline = !className;
      if (isInline) {
        return (
          <code className="bg-gray-200 dark:bg-gray-700 text-gray-800 dark:text-gray-200 px-1.5 py-0.5 rounded text-sm font-mono">
            {children}
          </code>
        );
      }
      return <code className={className}>{children}</code>;
    },
    pre: ({ children }) => (
      <pre className="bg-gray-800 dark:bg-gray-900 text-gray-100 p-4 rounded-lg overflow-x-auto my-3 text-sm">
        {children}
      </pre>
    ),
    table: ({ children }) => (
      <div className="overflow-x-auto my-3">
        <table className="min-w-full border-collapse border border-gray-300 dark:border-gray-600">
          {children}
        </table>
      </div>
    ),
    thead: ({ children }) => (
      <thead className="bg-gray-100 dark:bg-gray-700">{children}</thead>
    ),
    th: ({ children }) => (
      <th className="border border-gray-300 dark:border-gray-600 px-3 py-2 text-left font-semibold">
        {cite(children)}
      </th>
    ),
    td: ({ children }) => (
      <td className="border border-gray-300 dark:border-gray-600 px-3 py-2">{cite(children)}</td>
    ),
    hr: () => <hr className="my-4 border-gray-300 dark:border-gray-600" />,
    strong: ({ children }) => <strong className="font-semibold">{cite(children)}</strong>,
    em: ({ children }) => <em className="italic">{cite(children)}</em>,
  };
}

const normalizeMarkdown = (content: string) => {
  const normalized = content.replace(/\r\n?/g, '\n').trim();

  const replacements: Array<[RegExp, string]> = [
    [/(\*\*[^*\n]+?\*\*)\s*([*-]\s+|\d+\.\s+)/g, '$1\n$2'],
    [/([。！？!?:：])\s*([*-]\s+|\d+\.\s+)/g, '$1\n$2'],
    [/([^\n])(\#{1,}\s*)/g, '$1\n$2'],
    [/([^\n])((?:[*-]|\d+\.)\s+\*\*)/g, '$1\n$2'],
    [/(\*\*[^*]+\*\*)(?=\*\*)/g, '$1\n'],
  ];

  return replacements.reduce(
    (text, [pattern, replacement]) => text.replace(pattern, replacement),
    normalized
  );
};

export function MarkdownRenderer({
  content,
  className = '',
  messageId,
}: MarkdownRendererProps) {
  const components = useMemo(() => buildComponents(messageId), [messageId]);

  if (!content) return null;
  const normalized = normalizeMarkdown(content);

  return (
    <div className={`markdown-content ${className}`}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeHighlight]}
        components={components}
      >
        {normalized}
      </ReactMarkdown>
    </div>
  );
}
