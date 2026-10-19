/**
 * Chat Window Component
 * Main chat area with message display and empty state
 */

import { useEffect, useRef, useState, useCallback } from 'react';
import { BookOpen, Lightbulb, UtensilsCrossed } from 'lucide-react';
import type { Message } from '../../types';
import { MessageBubble } from './MessageBubble';

export interface ChatWindowProps {
    messages: Message[];
    isLoading: boolean;
    onSuggestionClick?: (text: string) => void;
    error?: string | null;
}

export function ChatWindow({ messages, isLoading, onSuggestionClick, error }: ChatWindowProps) {
    const messagesEndRef = useRef<HTMLDivElement>(null);
    const scrollContainerRef = useRef<HTMLDivElement>(null);
    const [isNearBottom, setIsNearBottom] = useState(true);
    const [isUserScrolling, setIsUserScrolling] = useState(false);

    // Check if user is near the bottom of the scroll container
    const checkIsNearBottom = useCallback(() => {
        const container = scrollContainerRef.current;
        if (!container) return true;

        const { scrollTop, scrollHeight, clientHeight } = container;
        const distanceFromBottom = scrollHeight - scrollTop - clientHeight;
        return distanceFromBottom < 100;
    }, []);

    // Handle scroll events to track user interaction
    const handleScroll = useCallback(() => {
        if (!isUserScrolling) {
            setIsUserScrolling(true);
            // Reset user scrolling flag after a short delay
            setTimeout(() => setIsUserScrolling(false), 1000);
        }
        setIsNearBottom(checkIsNearBottom());
    }, [isUserScrolling, checkIsNearBottom]);

    // Auto-scroll to bottom when new messages arrive, but only if user is near bottom
    useEffect(() => {
        if (isNearBottom && !isUserScrolling && messagesEndRef.current) {
            messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
        }
    }, [messages, isNearBottom, isUserScrolling]);

    // Set up scroll event listener
    useEffect(() => {
        const container = scrollContainerRef.current;
        if (container) {
            container.addEventListener('scroll', handleScroll, { passive: true });
            return () => container.removeEventListener('scroll', handleScroll);
        }
    }, [handleScroll]);

    // Initialize near bottom state
    useEffect(() => {
        setIsNearBottom(checkIsNearBottom());
    }, [checkIsNearBottom]);

    const isEmpty = messages.length === 0;

    return (
        <div
            ref={scrollContainerRef}
            className={`
        flex-1 px-4 pt-6 pb-2 md:px-6
        overflow-y-auto
      `}
        >
            {isEmpty ? (
                <EmptyState onSuggestionClick={onSuggestionClick} />
            ) : (
                <div className="max-w-3xl mx-auto w-full">
                    {messages.map((message) => (
                        <MessageBubble key={message.id} message={message} hasError={!!error} />
                    ))}

                    {/* Loading indicator */}
                    {isLoading &&
                        messages.length > 0 &&
                        messages[messages.length - 1].role === 'user' && (
                            <LoadingIndicator />
                        )}
                </div>
            )}
            {!isEmpty && <div ref={messagesEndRef} className="h-4" />}
        </div>
    );
}

/**
 * Empty state with welcome message and suggestions
 */
function EmptyState({
    onSuggestionClick,
}: {
    onSuggestionClick?: (text: string) => void;
}) {
    return (
        <div className="flex flex-col items-center justify-center h-full w-full animate-fade-up overflow-x-hidden px-4 box-border">
            <section className="empty-state-hero relative flex flex-col items-center justify-center pt-4 pb-8">
                <div className="relative mb-7">
                    <div className="absolute inset-0 rounded-full bg-ember-400/25 blur-2xl scale-150" />
                    <div className="relative w-16 h-16 rounded-[1.4rem] bg-white dark:bg-white/5 border border-cream-300/70 dark:border-white/10 p-2.5 shadow-[0_18px_40px_-24px_rgba(45,32,20,0.5)]">
                        <img
                            src="/logo1.png"
                            alt="CookHero"
                            className="w-full h-full object-contain animate-float"
                        />
                    </div>
                </div>
                <div className="ch-eyebrow mb-3">Your kitchen, on demand</div>
                <h1 className="ch-display text-[2.1rem] sm:text-[2.7rem] text-ink-900 dark:text-cream-50 text-center">
                    今晚，想吃点什么？
                </h1>
                <p className="mt-3 text-sm text-ink-500 dark:text-ink-300 text-center max-w-md">
                    告诉我你手边的食材或此刻的口味，剩下的交给 CookHero。
                </p>
            </section>

            {/* Suggestion Cards */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 w-full max-w-2xl mb-6">
                {[
                    { text: '红烧肉怎么做？', emoji: '🥩', hint: '经典家常菜' },
                    { text: '鸡蛋和西红柿能做什么？', emoji: '🥚', hint: '按食材匹配' },
                    { text: '推荐一道健康晚餐', emoji: '🥗', hint: '营养与热量' },
                    { text: '如何让炒菜更香？', emoji: '✨', hint: '厨房技巧' },
                ].map((item) => (
                    <SuggestionChip
                        key={item.text}
                        text={item.text}
                        emoji={item.emoji}
                        hint={item.hint}
                        onClick={onSuggestionClick}
                    />
                ))}
            </div>

            {/* Feature Strip */}
            <div className="flex flex-wrap items-center justify-center gap-x-6 gap-y-2 text-[11px] text-ink-400">
                <span className="inline-flex items-center gap-1.5">
                    <BookOpen className="w-3.5 h-3.5" />
                    菜谱检索
                </span>
                <span className="w-1 h-1 rounded-full bg-ink-300/60" />
                <span className="inline-flex items-center gap-1.5">
                    <Lightbulb className="w-3.5 h-3.5" />
                    烹饪技巧
                </span>
                <span className="w-1 h-1 rounded-full bg-ink-300/60" />
                <span className="inline-flex items-center gap-1.5">
                    <UtensilsCrossed className="w-3.5 h-3.5" />
                    食材搭配
                </span>
            </div>
        </div>
    );
}

/**
 * Suggestion card in empty state
 */
function SuggestionChip({
    text,
    emoji,
    hint,
    onClick,
}: {
    text: string;
    emoji: string;
    hint?: string;
    onClick?: (text: string) => void;
}) {
    return (
        <button
            className="group flex items-center gap-3.5 px-4 py-3.5 ch-card ch-card-hover !rounded-2xl text-left"
            onClick={() => onClick?.(text)}
        >
            <span className="w-10 h-10 rounded-xl bg-cream-100 dark:bg-white/[0.06] border border-cream-200/80 dark:border-white/10 flex items-center justify-center text-lg shrink-0 transition-transform duration-300 group-hover:scale-110 group-hover:-rotate-3">
                {emoji}
            </span>
            <span className="flex-1 min-w-0">
                <span className="block text-sm font-medium text-ink-800 dark:text-cream-100 truncate">
                    {text}
                </span>
                {hint && (
                    <span className="block text-[11px] text-ink-400 mt-0.5">{hint}</span>
                )}
            </span>
            <span className="text-ink-300 group-hover:text-ember-500 group-hover:translate-x-0.5 transition-all">
                →
            </span>
        </button>
    );
}

/**
 * Loading indicator when waiting for response
 */
function LoadingIndicator() {
    return (
        <div className="flex gap-4 mb-6">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-orange-400 to-orange-500 flex items-center justify-center shrink-0 shadow-sm">
                <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin" />
            </div>
            <div className="space-y-2 pt-2">
                <div className="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400">
                    <span className="animate-pulse">CookHero is thinking...</span>
                </div>
            </div>
        </div>
    );
}
