/**
 * Utility functions
 */

import { MEDIA_BASE } from '../constants';

export * from './date';
export * from './storage';

/**
 * Resolve a backend media path (e.g. /media/recipes/...) for <img src>.
 * When `width` is provided, ask the backend for a cached thumbnail.
 */
export function resolveMediaUrl(url?: string | null, width?: number): string | undefined {
  if (!url) return undefined;
  if (/^(?:https?:)?\/\//i.test(url) || url.startsWith('data:') || url.startsWith('blob:')) {
    return url;
  }
  const base = `${MEDIA_BASE}${url.startsWith('/') ? '' : '/'}${url}`;
  if (!width || !base.includes('/media/')) return base;
  return `${base}${base.includes('?') ? '&' : '?'}w=${width}`;
}

/**
 * Generate a unique ID for messages
 */
export function generateId(): string {
  return Date.now().toString(36) + Math.random().toString(36).substr(2);
}

/**
 * Wait for the next tick (useful for async operations)
 */
export const waitForNextTick = (): Promise<void> =>
  new Promise<void>((resolve) => {
    setTimeout(resolve, 0);
  });

/**
 * Capitalize the first letter of a string
 */
export function capitalize(str: string): string {
  if (!str) return str;
  return str.charAt(0).toUpperCase() + str.slice(1);
}

/**
 * Truncate a string to a maximum length
 */
export function truncate(str: string, maxLength: number): string {
  if (str.length <= maxLength) return str;
  return str.slice(0, maxLength) + '...';
}

/**
 * Check if a conversation ID is temporary (not yet saved to server)
 */
export function isTempConversationId(id: string): boolean {
  return id.startsWith('temp-');
}
