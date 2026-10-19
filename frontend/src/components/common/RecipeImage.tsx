/**
 * Recipe cover / step image with a warm fallback when no photo exists.
 * The fallback uses the dish's first character and a deterministic warm
 * palette so a grid without photos still feels intentional.
 *
 * Images are loaded lazily: an IntersectionObserver defers setting the real
 * `src` until the element is near the viewport, and a shimmer skeleton is
 * shown until the image decodes — so a 373-card grid never fires 373
 * network requests at once.
 */

import { useEffect, useRef, useState } from 'react';
import { resolveMediaUrl } from '../../utils';

interface RecipeImageProps {
  src?: string | null;
  alt?: string;
  title?: string;
  className?: string;
  imageClassName?: string;
  loading?: 'lazy' | 'eager';
  width?: number;
}

const FALLBACK_VARIANTS = [
  {
    wrap: 'from-ember-100 via-cream-100 to-ember-200 dark:from-ember-900/35 dark:via-ink-800 dark:to-ember-800/25',
    text: 'text-ember-600/35 dark:text-ember-300/25',
    label: 'text-ember-700/45 dark:text-ember-200/40',
  },
  {
    wrap: 'from-herb-100 via-cream-100 to-herb-200 dark:from-herb-900/35 dark:via-ink-800 dark:to-herb-800/25',
    text: 'text-herb-600/35 dark:text-herb-300/25',
    label: 'text-herb-700/45 dark:text-herb-200/40',
  },
  {
    wrap: 'from-honey-100 via-cream-100 to-honey-200 dark:from-amber-900/35 dark:via-ink-800 dark:to-amber-800/25',
    text: 'text-honey-500/40 dark:text-amber-300/25',
    label: 'text-honey-500/55 dark:text-amber-200/40',
  },
];

export function RecipeImage({
  src,
  alt,
  title,
  className = '',
  imageClassName = '',
  loading = 'lazy',
  width,
}: RecipeImageProps) {
  const [failedUrl, setFailedUrl] = useState<string | null>(null);
  const [inView, setInView] = useState(loading === 'eager');
  const [loaded, setLoaded] = useState(false);
  const containerRef = useRef<HTMLDivElement | null>(null);

  const resolved = resolveMediaUrl(src, width);
  const failed = Boolean(resolved) && failedUrl === resolved;

  useEffect(() => {
    if (inView || loading === 'eager') return;
    const node = containerRef.current;
    if (!node) return;
    const observer = new IntersectionObserver(
      entries => {
        if (entries[0]?.isIntersecting) {
          setInView(true);
          observer.disconnect();
        }
      },
      { rootMargin: '400px' }
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [inView, loading]);

  const label = (title || alt || '菜').trim();
  const initial = Array.from(label)[0] || '菜';
  const variant = FALLBACK_VARIANTS[(initial.codePointAt(0) || 0) % FALLBACK_VARIANTS.length];

  const showFallback = failed || !resolved;
  const showSkeleton = resolved && !failed && !loaded;

  return (
    <div
      ref={containerRef}
      className={`relative overflow-hidden bg-gradient-to-br ${showFallback ? variant.wrap : 'from-ember-100 via-cream-100 to-herb-100 dark:from-ember-900/30 dark:via-ink-800 dark:to-herb-900/30'} ${className}`}
    >
      {resolved && !failed && inView ? (
        <img
          src={resolved}
          alt={alt || title || ''}
          loading={loading}
          decoding="async"
          referrerPolicy="no-referrer"
          onError={() => setFailedUrl(resolved || null)}
          onLoad={() => setLoaded(true)}
          className={`h-full w-full object-cover transition-opacity duration-300 ${loaded ? 'opacity-100' : 'opacity-0'} ${imageClassName}`}
        />
      ) : null}

      {showSkeleton ? (
        <div className="absolute inset-0 animate-pulse bg-gradient-to-br from-cream-100 to-cream-200 dark:from-ink-800 dark:to-ink-700/60" />
      ) : null}

      {showFallback ? (
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className={`ch-display text-[3.6rem] leading-none ${variant.text}`}>
            {initial}
          </span>
          <span
            className={`mt-2 text-[9px] font-semibold uppercase tracking-[0.18em] ${variant.label}`}
          >
            暂无成品图
          </span>
        </div>
      ) : null}

      <div className="pointer-events-none absolute inset-0 bg-gradient-to-t from-ink-900/10 to-transparent" />
    </div>
  );
}
