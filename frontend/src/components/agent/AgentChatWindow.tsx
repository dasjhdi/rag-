/**
 * Agent Chat Window Component
 * Main chat area with message display and empty state for Agent mode
 */

import { useEffect, useRef, useState, useCallback } from 'react';
import { Bot, Calculator, Code } from 'lucide-react';
import type { Message } from '../../types';
import { AgentMessageBubble } from './AgentMessageBubble';

export interface AgentChatWindowProps {
    messages: Message[];
    isLoading: boolean;
    onSuggestionClick?: (text: string) => void;
    error?: string | null;
    isToolSelectorOpen?: boolean;
}

export function AgentChatWindow({ messages, isLoading, onSuggestionClick, error, isToolSelectorOpen }: AgentChatWindowProps) {
    messages = messages.filter(
        (message) =>
        (message.role === 'user' || message.role === 'assistant') && 
        ((message.content !== null && message.content !== undefined && message.content !== '') || message.trace !== undefined)
    )
    const messagesEndRef = useRef<HTMLDivElement>(null);
    const scrollContainerRef = useRef<HTMLDivElement>(null);
    const [isNearBottom, setIsNearBottom] = useState(true);
    const [isUserScrolling, setIsUserScrolling] = useState(false);
    const prevMessagesLengthRef = useRef(messages.length);

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

    // Force scroll to bottom when user sends a new message
    useEffect(() => {
        const prevLength = prevMessagesLengthRef.current;
        const currentLength = messages.length;

        // Check if a new user message was added
        if (currentLength > prevLength && messages.length > 0) {
            const lastMessage = messages[messages.length - 1];
            // If the new message is from user, force scroll to bottom
            if (lastMessage.role === 'user') {
                messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
            }
        }

        prevMessagesLengthRef.current = currentLength;
    }, [messages]);

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
                <EmptyState onSuggestionClick={onSuggestionClick} isToolSelectorOpen={isToolSelectorOpen} />
            ) : (
                <div className="max-w-3xl mx-auto w-full">
                    {messages
                    .map((message) => (
                        <AgentMessageBubble key={message.id} message={message} hasError={!!error} />
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
 * Empty state with welcome message and suggestions for Agent mode
 */
function EmptyState({
    onSuggestionClick,
    isToolSelectorOpen
}: {
    onSuggestionClick?: (text: string) => void;
    isToolSelectorOpen?: boolean;
}) {
    return (
        <div className="flex flex-col items-center justify-center h-full w-full animate-fade-up overflow-x-hidden px-4 box-border">
            {!isToolSelectorOpen && (
                <section className="empty-state-hero relative flex flex-col items-center justify-center pt-4 pb-8">
                    <div className="relative mb-7">
                        <div className="absolute inset-0 rounded-full bg-ember-400/25 blur-2xl scale-150" />
                        <div className="relative w-16 h-16 rounded-[1.4rem] bg-white dark:bg-white/5 border border-cream-300/70 dark:border-white/10 p-2.5 shadow-[0_18px_40px_-24px_rgba(45,32,20,0.5)]">
                            <img
                                src="/logo1.png"
                                alt="CookHero Agent"
                                className="w-full h-full object-contain animate-float"
                            />
                        </div>
                    </div>
                    <div className="ch-eyebrow mb-3">Agent Workspace</div>
                    <h1 className="ch-display text-[2.1rem] sm:text-[2.7rem] text-ink-900 dark:text-cream-50 text-center">
                        把做饭这件事，
                        <br />
                        交给会算账的<span className="text-ember-500">搭档</span>
                    </h1>
                    <p className="mt-3 text-sm text-ink-500 dark:text-ink-300 text-center max-w-md">
                        调取菜谱、换算单位、规划一周备餐——用一句话，让 Agent 动手。
                    </p>
                </section>
            )}

            {/* Agent Feature Cards */}
            <div className="hidden sm:grid grid-cols-1 sm:grid-cols-3 gap-3 w-full max-w-3xl mb-5">
                <FeatureCard
                    icon={<Calculator className="w-5 h-5" />}
                    title="精确换算"
                    description="单位、份量与营养计算"
                    tone="ember"
                />
                <FeatureCard
                    icon={<Code className="w-5 h-5" />}
                    title="数据分析"
                    description="营养结构与摄入对比"
                    tone="herb"
                />
                <FeatureCard
                    icon={<Bot className="w-5 h-5" />}
                    title="复杂规划"
                    description="备餐与采购清单"
                    tone="honey"
                />
            </div>

            {/* Suggestion Chips */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 w-full max-w-2xl">
                <SuggestionChip
                    text="计算 20 克鸡肉的卡路里"
                    emoji="🐔"
                    hint="营养计算"
                    onClick={onSuggestionClick}
                />
                <SuggestionChip
                    text="帮我记录一下今天的午餐"
                    emoji="⚖️"
                    hint="饮食记录"
                    onClick={onSuggestionClick}
                />
                <SuggestionChip
                    text="为 2 人制定一周备餐计划"
                    emoji="📅"
                    hint="计划生成"
                    onClick={onSuggestionClick}
                />
                <SuggestionChip
                    text="分析豆腐和牛肉的蛋白质含量"
                    emoji="📊"
                    hint="数据对比"
                    onClick={onSuggestionClick}
                />
            </div>
        </div>
    );
}

/**
 * Feature card in empty state
 */
function FeatureCard({
    icon,
    title,
    description,
    tone = 'ember',
}: {
    icon: React.ReactNode;
    title: string;
    description: string;
    tone?: 'ember' | 'herb' | 'honey';
}) {
    const toneClass = {
        ember: 'bg-ember-50 text-ember-600 dark:bg-ember-500/10 dark:text-ember-300',
        herb: 'bg-herb-50 text-herb-600 dark:bg-herb-500/10 dark:text-herb-300',
        honey: 'bg-honey-100/60 text-honey-500 dark:bg-honey-500/10 dark:text-honey-300',
    }[tone];

    return (
        <div className="ch-card ch-card-hover p-4 text-center">
            <div className={`w-10 h-10 rounded-xl flex items-center justify-center mx-auto mb-2.5 ${toneClass}`}>
                {icon}
            </div>
            <h3 className="font-semibold text-[13px] text-ink-800 dark:text-cream-100">
                {title}
            </h3>
            <p className="text-[11px] text-ink-400 mt-0.5">{description}</p>
        </div>
    );
}

/**
 * Suggestion chip button
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
                {hint && <span className="block text-[11px] text-ink-400 mt-0.5">{hint}</span>}
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
        <div className="flex gap-3 mb-6">
            <div className="w-9 h-9 rounded-xl ch-avatar flex items-center justify-center shrink-0 shadow-sm">
                <div className="w-4 h-4 border-2 border-white/90 border-t-transparent rounded-full animate-spin" />
            </div>
            <div className="space-y-2 pt-2">
                <div className="flex items-center gap-2 text-sm text-ink-500 dark:text-ink-300">
                    <span className="animate-pulse">Agent 正在思考…</span>
                </div>
            </div>
        </div>
    );
}
