import { ArrowLeft } from 'lucide-react';
import { Link, useLocation, useNavigate } from 'react-router-dom';

interface BackButtonProps {
  /** Fallback destination when there is no in-app history to go back to. */
  fallbackTo?: string;
  /** Optional explicit label; defaults to "返回上级". */
  label?: string;
  /** When true, always navigate to fallbackTo instead of using history. */
  forceFallback?: boolean;
  className?: string;
}

/**
 * Smart back button: prefers in-app history (navigate(-1)) so the user returns
 * to wherever they came from (e.g. knowledge base → recipes → back to knowledge),
 * and falls back to a fixed route when there is no history (direct entry/refresh).
 */
export function BackButton({
  fallbackTo = '/diet',
  label = '返回上级',
  forceFallback = false,
  className = 'inline-flex items-center gap-1.5 text-xs font-medium text-ink-500 dark:text-ink-300 hover:text-ember-600 dark:hover:text-ember-300 transition-colors',
}: BackButtonProps) {
  const navigate = useNavigate();
  const location = useLocation();
  const hasHistory = location.key !== 'default';
  // Callers may pass `state: { from: '/path' }` when navigating, so the back
  // button can return to a precise parent even on direct entry (no history).
  const stateFrom =
    typeof location.state === 'object' && location.state !== null
      ? (location.state as { from?: string }).from
      : undefined;
  const fallbackTarget = stateFrom || fallbackTo;

  if (!forceFallback && hasHistory) {
    return (
      <button type="button" onClick={() => navigate(-1)} className={className}>
        <ArrowLeft className="w-3.5 h-3.5" />
        {label}
      </button>
    );
  }

  return (
    <Link to={fallbackTarget} className={className}>
      <ArrowLeft className="w-3.5 h-3.5" />
      {label}
    </Link>
  );
}
