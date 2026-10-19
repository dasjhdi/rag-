/**
 * Sidebar Component
 * Navigation sidebar with conversation list and user profile
 */

import {
    MessageSquare,
    Plus,
    PanelLeftClose,
    MoreHorizontal,
    Trash2,
    Pencil,
    Check,
    X,
    ChevronDown,
    Bot, // New Icon
} from 'lucide-react';
import { useState, useRef, useEffect, useMemo } from 'react';
import { ThemeToggle } from '../common/ThemeToggle';
import { UserProfileModal } from './UserProfileModal';
import { useAuth } from '../../contexts';
import { getDateCategory, DATE_CATEGORY_LABELS } from '../../utils';
import type { ConversationSummary } from '../../types';

// Date category types
type DateCategory = 'today' | 'yesterday' | 'lastWeek' | 'lastMonth' | 'older';

interface GroupedConversations {
    category: DateCategory;
    label: string;
    conversations: ConversationSummary[];
}

const categoryOrder: DateCategory[] = [
    'today',
    'yesterday',
    'lastWeek',
    'lastMonth',
    'older',
];

export interface SidebarProps {
    isOpen: boolean;
    toggleSidebar: () => void;
    conversations: ConversationSummary[];
    totalConversations?: number;
    hasMoreConversations?: boolean;
    onLoadMoreConversations?: () => void;
    currentConversationId: string | null;
    onSelectConversation: (id: string) => void;
    onNewChat: () => void;
    onDeleteConversation?: (id: string) => Promise<boolean>;
    onRenameConversation?: (id: string, newTitle: string) => Promise<boolean>;
    isDark: boolean;
    toggleTheme: () => void;
    
    // Agent specific
    isAgentMode?: boolean;
    onToggleAgentMode?: () => void;
}

export function Sidebar({
    isOpen,
    toggleSidebar,
    conversations,
    totalConversations = 0,
    hasMoreConversations = false,
    onLoadMoreConversations,
    currentConversationId,
    onSelectConversation,
    onNewChat,
    onDeleteConversation,
    onRenameConversation,
    isDark,
    toggleTheme,
    isAgentMode,
    onToggleAgentMode
}: SidebarProps) {
    const { username } = useAuth();
    const [profileOpen, setProfileOpen] = useState(false);
    const [menuOpenId, setMenuOpenId] = useState<string | null>(null);
    const [editingId, setEditingId] = useState<string | null>(null);
    const [editingTitle, setEditingTitle] = useState('');
    const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);
    const menuRef = useRef<HTMLDivElement>(null);
    const editInputRef = useRef<HTMLInputElement>(null);

    // Group conversations by date
    const groupedConversations = useMemo((): GroupedConversations[] => {
        const groups: Record<DateCategory, ConversationSummary[]> = {
            today: [],
            yesterday: [],
            lastWeek: [],
            lastMonth: [],
            older: [],
        };

        conversations.forEach((conv) => {
            const category = getDateCategory(conv.updated_at) as DateCategory;
            groups[category].push(conv);
        });

        return categoryOrder
            .filter((cat) => groups[cat].length > 0)
            .map((cat) => ({
                category: cat,
                label: DATE_CATEGORY_LABELS[cat],
                conversations: groups[cat],
            }));
    }, [conversations]);

    // Close menu when clicking outside
    useEffect(() => {
        const handleClickOutside = (event: MouseEvent) => {
            if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
                setMenuOpenId(null);
            }
        };
        document.addEventListener('mousedown', handleClickOutside);
        return () => document.removeEventListener('mousedown', handleClickOutside);
    }, []);

    // Focus input when editing starts
    useEffect(() => {
        if (editingId && editInputRef.current) {
            editInputRef.current.focus();
            editInputRef.current.select();
        }
    }, [editingId]);

    const handleMenuClick = (e: React.MouseEvent, convId: string) => {
        e.stopPropagation();
        setMenuOpenId(menuOpenId === convId ? null : convId);
        setDeleteConfirmId(null);
    };

    const handleRenameClick = (e: React.MouseEvent, conv: ConversationSummary) => {
        e.stopPropagation();
        setEditingId(conv.id);
        setEditingTitle(conv.title || conv.last_message_preview || 'New Conversation');
        setMenuOpenId(null);
    };

    const handleRenameSave = async (id: string) => {
        if (onRenameConversation && editingTitle.trim()) {
            await onRenameConversation(id, editingTitle.trim());
        }
        setEditingId(null);
        setEditingTitle('');
    };

    const handleRenameCancel = () => {
        setEditingId(null);
        setEditingTitle('');
    };

    const handleDeleteClick = (e: React.MouseEvent, convId: string) => {
        e.stopPropagation();
        setDeleteConfirmId(convId);
    };

    const handleDeleteConfirm = async (e: React.MouseEvent, id: string) => {
        e.stopPropagation();
        if (onDeleteConversation) {
            await onDeleteConversation(id);
        }
        setMenuOpenId(null);
        setDeleteConfirmId(null);
    };

    const handleDeleteCancel = (e: React.MouseEvent) => {
        e.stopPropagation();
        setDeleteConfirmId(null);
    };

    return (
        <>
            {/* Mobile Overlay */}
            {isOpen && (
                <div
                    className="fixed inset-0 bg-black/50 backdrop-blur-sm z-20 md:hidden"
                    onClick={toggleSidebar}
                    aria-hidden="true"
                />
            )}

            {/* Sidebar Container */}
            <div
                className={`
          fixed md:static inset-y-0 left-0 z-30
          flex flex-col flex-none
          bg-cream-100/70 dark:bg-[#151110]
          border-r border-cream-300/60 dark:border-white/5
          transform transition-all duration-300 ease-in-out shadow-xl md:shadow-none
          ${isOpen
                        ? 'translate-x-0 w-72 md:w-72'
                        : '-translate-x-full md:-translate-x-full md:w-0 md:opacity-0 md:pointer-events-none'
                    }
        `}
                role="navigation"
                aria-label="Sidebar"
            >
                {/* Header */}
                <SidebarHeader 
                    toggleSidebar={toggleSidebar} 
                    onNewChat={onNewChat}
                    isAgentMode={isAgentMode}
                    onToggleAgentMode={onToggleAgentMode} 
                />

                {/* Conversation List */}
                <div className="flex-1 overflow-y-auto px-3 py-3 space-y-1">
                    <div className="flex items-center justify-between px-2 mb-2">
                        <p className="text-[10px] text-ink-400 dark:text-ink-400 font-semibold uppercase tracking-[0.18em]">
                            {isAgentMode ? 'Recent Sessions' : 'Recent Chats'}
                        </p>
                        {totalConversations > 0 && (
                            <span className="text-[10px] text-ink-500 dark:text-ink-300 bg-cream-200/80 dark:bg-white/[0.06] px-1.5 py-0.5 rounded-full tabular-nums">
                                {totalConversations}
                            </span>
                        )}
                    </div>

                    {groupedConversations.map((group) => (
                        <div key={group.category} className="mb-2">
                            <p className="text-[10px] text-ink-400 px-2 py-1 font-medium tracking-wide">
                                {group.label}
                            </p>

                            {group.conversations.map((conv) => (
                                <ConversationItem
                                    key={conv.id}
                                    conversation={conv}
                                    isActive={currentConversationId === conv.id}
                                    isAgentMode={isAgentMode}
                                    isEditing={editingId === conv.id}
                                    editingTitle={editingTitle}
                                    menuOpen={menuOpenId === conv.id}
                                    deleteConfirm={deleteConfirmId === conv.id}
                                    onSelect={() => onSelectConversation(conv.id)}
                                    onMenuClick={(e) => handleMenuClick(e, conv.id)}
                                    onRenameClick={(e) => handleRenameClick(e, conv)}
                                    onRenameSave={() => handleRenameSave(conv.id)}
                                    onRenameCancel={handleRenameCancel}
                                    onEditingTitleChange={setEditingTitle}
                                    onDeleteClick={(e) => handleDeleteClick(e, conv.id)}
                                    onDeleteConfirm={(e) => handleDeleteConfirm(e, conv.id)}
                                    onDeleteCancel={handleDeleteCancel}
                                    menuRef={menuRef}
                                    editInputRef={editInputRef}
                                />
                            ))}
                        </div>
                    ))}

                    {/* Load More Button */}
                    {hasMoreConversations && onLoadMoreConversations && (
                        <button
                            onClick={onLoadMoreConversations}
                            className="w-full flex items-center justify-center gap-2 px-3 py-2 text-xs text-ink-500 dark:text-ink-300 hover:bg-white/60 dark:hover:bg-white/5 rounded-xl transition-colors"
                        >
                            <ChevronDown className="w-4 h-4" />
                            加载更多
                        </button>
                    )}

                    {/* Empty State */}
                    {conversations.length === 0 && (
                        <div className="text-center text-ink-400 text-sm py-12">
                            <div className="w-12 h-12 mx-auto mb-3 rounded-2xl bg-white/60 dark:bg-white/5 border border-cream-300/50 dark:border-white/10 flex items-center justify-center">
                                <MessageSquare className="w-5 h-5 opacity-60" />
                            </div>
                            <p className="text-ink-500 dark:text-ink-300">还没有对话</p>
                            <p className="text-xs mt-1 text-ink-400">从上方「开启新对话」开始</p>
                        </div>
                    )}
                </div>

                {/* Footer */}
                <SidebarFooter
                    username={username}
                    isDark={isDark}
                    toggleTheme={toggleTheme}
                    onProfileClick={() => setProfileOpen(true)}
                />

                <UserProfileModal open={profileOpen} onClose={() => setProfileOpen(false)} />
            </div>
        </>
    );
}

/**
 * Sidebar header with logo and new chat button
 */
function SidebarHeader({
    toggleSidebar,
    onNewChat,
    isAgentMode,
    onToggleAgentMode,
}: {
    toggleSidebar: () => void;
    onNewChat: () => void;
    isAgentMode?: boolean;
    onToggleAgentMode?: () => void;
}) {
    return (
        <div className="px-4 pt-5 pb-4">
            <div className="flex items-center justify-between mb-5">
                <div className="flex items-center gap-2.5 min-w-0">
                    <div className="w-9 h-9 rounded-2xl bg-white dark:bg-white/5 border border-cream-300/70 dark:border-white/10 flex items-center justify-center p-1.5 shadow-sm shrink-0">
                        <img
                            src="/logo1.png"
                            alt="CookHero Logo"
                            className="w-full h-full object-contain"
                        />
                    </div>
                    <div className="min-w-0">
                        <div className="ch-wordmark text-[17px] leading-none text-ink-900 dark:text-cream-100">
                            CookHero
                        </div>
                        <div className="text-[10px] tracking-[0.16em] uppercase text-ink-400 dark:text-ink-400 mt-1">
                            Kitchen Studio
                        </div>
                    </div>
                </div>
                <div className="md:hidden">
                    <button
                        onClick={toggleSidebar}
                        className="ch-icon-btn"
                        aria-label="Close sidebar"
                    >
                        <PanelLeftClose className="w-5 h-5" />
                    </button>
                </div>
            </div>

            <button
                onClick={onNewChat}
                className="ch-btn ch-btn-primary w-full !rounded-2xl !py-2.5"
            >
                <Plus className="w-4 h-4" />
                {isAgentMode ? '新建 Agent 会话' : '开启新对话'}
            </button>

            {onToggleAgentMode && (
                <button
                    onClick={onToggleAgentMode}
                    className="mt-2 w-full flex items-center justify-between px-3 py-2 rounded-2xl border border-cream-300/70 dark:border-white/10 bg-white/50 dark:bg-white/[0.03] hover:border-ember-300/60 transition-colors group"
                    title={isAgentMode ? '切换到标准对话' : '切换到 Agent 模式'}
                >
                    <span className="flex items-center gap-2 text-xs font-medium text-ink-600 dark:text-ink-200">
                        <span className={`w-6 h-6 rounded-lg flex items-center justify-center ${isAgentMode ? 'bg-ember-500/12 text-ember-600 dark:text-ember-300' : 'bg-herb-500/12 text-herb-600 dark:text-herb-300'}`}>
                            {isAgentMode ? <Bot className="w-3.5 h-3.5" /> : <MessageSquare className="w-3.5 h-3.5" />}
                        </span>
                        {isAgentMode ? 'Agent 模式' : '对话模式'}
                    </span>
                    <span className="text-[10px] text-ink-400 group-hover:text-ember-600 dark:group-hover:text-ember-300 transition-colors">
                        切换 →
                    </span>
                </button>
            )}
        </div>
    );
}

/**
 * Sidebar footer with user profile and theme toggle
 */
function SidebarFooter({
    username,
    isDark,
    toggleTheme,
    onProfileClick,
}: {
    username: string | null;
    isDark: boolean;
    toggleTheme: () => void;
    onProfileClick: () => void;
}) {
    return (
        <div className="p-3 border-t border-cream-300/50 dark:border-white/5">
            <div className="flex items-center justify-between gap-2 rounded-2xl bg-white/60 dark:bg-white/[0.04] border border-cream-300/50 dark:border-white/10 px-2.5 py-2">
                <button
                    onClick={onProfileClick}
                    className="flex items-center gap-2.5 focus:outline-none min-w-0 group"
                >
                    <div className="w-8 h-8 rounded-full ch-avatar flex items-center justify-center font-bold text-xs shrink-0">
                        {username ? username.charAt(0).toUpperCase() : 'U'}
                    </div>
                    <div className="text-left min-w-0">
                        <div className="font-semibold text-ink-900 dark:text-cream-100 text-[13px] truncate">
                            {username || 'User'}
                        </div>
                        <div className="text-[10px] text-ink-400 group-hover:text-ember-600 dark:group-hover:text-ember-300 transition-colors">
                            个人资料与设置
                        </div>
                    </div>
                </button>
                <ThemeToggle isDark={isDark} toggleTheme={toggleTheme} />
            </div>
        </div>
    );
}

/**
 * Individual conversation item
 */
function ConversationItem({
    conversation,
    isActive,
    isEditing,
    editingTitle,
    menuOpen,
    deleteConfirm,
    onSelect,
    onMenuClick,
    onRenameClick,
    onRenameSave,
    onRenameCancel,
    onEditingTitleChange,
    onDeleteClick,
    onDeleteConfirm,
    onDeleteCancel,
    menuRef,
    editInputRef,
}: {
    conversation: ConversationSummary;
    isActive: boolean;
    isAgentMode?: boolean;
    isEditing: boolean;
    editingTitle: string;
    menuOpen: boolean;
    deleteConfirm: boolean;
    onSelect: () => void;
    onMenuClick: (e: React.MouseEvent) => void;
    onRenameClick: (e: React.MouseEvent) => void;
    onRenameSave: () => void;
    onRenameCancel: () => void;
    onEditingTitleChange: (title: string) => void;
    onDeleteClick: (e: React.MouseEvent) => void;
    onDeleteConfirm: (e: React.MouseEvent) => void;
    onDeleteCancel: (e: React.MouseEvent) => void;
    menuRef: React.RefObject<HTMLDivElement | null>;
    editInputRef: React.RefObject<HTMLInputElement | null>;
}) {
    const [isComposing, setIsComposing] = useState(false);
    const displayTitle =
        conversation.title || conversation.last_message_preview || 'New Conversation';

    if (isEditing) {
        return (
            <div className="flex items-center gap-2 px-3 py-2.5 rounded-2xl bg-white dark:bg-white/[0.06] border border-ember-400/60 shadow-sm">
                <MessageSquare className="w-4 h-4 shrink-0 text-ember-500" />
                <input
                    ref={editInputRef}
                    type="text"
                    value={editingTitle}
                    onChange={(e) => onEditingTitleChange(e.target.value)}
                    onCompositionStart={() => setIsComposing(true)}
                    onCompositionEnd={() => setIsComposing(false)}
                    onKeyDown={(e) => {
                        if (e.key === 'Enter' && !isComposing) onRenameSave();
                        if (e.key === 'Escape') onRenameCancel();
                    }}
                    className="flex-1 bg-transparent text-sm text-ink-900 dark:text-cream-100 outline-none"
                />
                <button
                    onClick={onRenameSave}
                    className="p-1 text-green-600 hover:text-green-700 dark:text-green-500 dark:hover:text-green-400"
                    aria-label="Save"
                >
                    <Check className="w-4 h-4" />
                </button>
                <button
                    onClick={onRenameCancel}
                    className="p-1 text-gray-500 hover:text-gray-700 dark:hover:text-gray-300"
                    aria-label="Cancel"
                >
                    <X className="w-4 h-4" />
                </button>
            </div>
        );
    }

    return (
        <div className="relative group">
            {isActive && (
                <span className="absolute left-0 top-1/2 -translate-y-1/2 w-[3px] h-6 rounded-r-full bg-ember-500" />
            )}
            <button
                onClick={onSelect}
                className={`
          w-full flex items-center gap-3 px-3 py-2.5 rounded-2xl text-left text-sm transition-all duration-200
          ${isActive
                        ? 'bg-white dark:bg-white/[0.07] text-ink-900 dark:text-cream-100 font-medium shadow-sm border border-cream-300/60 dark:border-white/10'
                        : 'text-ink-600 dark:text-ink-200/80 hover:bg-white/60 dark:hover:bg-white/[0.04] border border-transparent'
                    }
        `}
            >
                <MessageSquare
                    className={`w-4 h-4 shrink-0 transition-colors ${isActive ? 'text-ember-500' : 'text-ink-400 group-hover:text-ember-500/80'}`}
                />
                <span className="truncate flex-1">{displayTitle}</span>

                <div
                    onClick={onMenuClick}
                    className="p-1 rounded-lg opacity-0 group-hover:opacity-100 hover:bg-cream-200 dark:hover:bg-white/10 transition-opacity text-ink-400"
                >
                    <MoreHorizontal className="w-4 h-4" />
                </div>
            </button>

            {/* Dropdown Menu */}
            {menuOpen && (
                <div
                    ref={menuRef}
                    className="absolute right-0 top-full mt-1 z-50 w-40 ch-card !rounded-2xl overflow-hidden py-1"
                >
                    {deleteConfirm ? (
                        <div className="px-3 py-2">
                            <p className="text-xs text-ink-500 dark:text-ink-300 mb-2">
                                确定删除这段对话？
                            </p>
                            <div className="flex gap-2">
                                <button
                                    onClick={onDeleteConfirm}
                                    className="flex-1 px-2 py-1 text-xs bg-red-500 hover:bg-red-600 text-white rounded-lg transition-colors"
                                >
                                    删除
                                </button>
                                <button
                                    onClick={onDeleteCancel}
                                    className="flex-1 px-2 py-1 text-xs bg-cream-200 dark:bg-white/10 hover:bg-cream-300 dark:hover:bg-white/15 text-ink-700 dark:text-ink-200 rounded-lg transition-colors"
                                >
                                    取消
                                </button>
                            </div>
                        </div>
                    ) : (
                        <>
                            <button
                                onClick={onRenameClick}
                                className="w-full flex items-center gap-2 px-3 py-2 text-sm text-ink-700 dark:text-ink-200 hover:bg-cream-100 dark:hover:bg-white/5"
                            >
                                <Pencil className="w-4 h-4" />
                                重命名
                            </button>
                            <button
                                onClick={onDeleteClick}
                                className="w-full flex items-center gap-2 px-3 py-2 text-sm text-red-600 dark:text-red-400 hover:bg-cream-100 dark:hover:bg-white/5"
                            >
                                <Trash2 className="w-4 h-4" />
                                删除
                            </button>
                        </>
                    )}
                </div>
            )}
        </div>
    );
}
