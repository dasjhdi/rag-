// src/App.tsx
import { useEffect, useState, useCallback, useRef, useMemo } from 'react';
import type { ReactElement } from 'react';
import { BarChart3, BookOpen, Menu, LogOut, Utensils, ChevronDown } from 'lucide-react';
import { Link, Navigate, Route, Routes, useLocation, useNavigate, useParams } from 'react-router-dom';
import { ChatWindow, ChatInput, Sidebar, KnowledgePanel } from './components';
import { AgentChatWindow, AgentChatInput } from './components/agent';
import { useTheme, useAuth, useConversationContext, useAgentContext } from './contexts';
import LoginPage from './pages/Login';
import RegisterPage from './pages/Register';
import EvaluationPage from './pages/Evaluation';
import LLMStatsPage from './pages/LLMStats';
import DietManagementPage from './pages/diet/DietManagement';
import DietProfilePage from './pages/diet/DietProfile';
import PantryPage from './pages/diet/Pantry';
import RecipeSearchPage from './pages/recipes/RecipeSearch';
import RecipeLibraryPage from './pages/recipes/RecipeLibrary';
import RecipeDetailPage from './pages/recipes/RecipeDetail';
import CookingModePage from './pages/recipes/CookingMode';
import AdminConsolePage from './pages/admin/AdminConsole';

/**
 * Chat view component - handles both new chat and existing conversation
 */
function ChatView() {
  const { id: urlConversationId } = useParams<{ id?: string }>();
  const navigate = useNavigate();
  const location = useLocation();
  const { token } = useAuth();
  const isAgentMode = location.pathname.startsWith('/agent');

  // Standard Chat Context
  const {
    messages: chatMessages,
    conversationId: chatConversationId,
    isLoading: chatIsLoading,
    isStreaming: chatIsStreaming,
    error: chatError,
    sendMessage: chatSendMessage,
    selectConversation: chatSelectConversation,
    stopGeneration: chatStopGeneration,
  } = useConversationContext();

  // Agent Chat Context
  const {
      messages: agentMessages,
      sessionId: agentSessionId,
      isLoading: agentIsLoading,
      isStreaming: agentIsStreaming,
      error: agentError,
      sendMessage: agentSendMessage,
      selectSession: agentSelectSession,
      stopGeneration: agentStopGeneration,
  } = useAgentContext();

  // Unified State based on Mode
  const messages = isAgentMode ? agentMessages : chatMessages;
  const currentId = isAgentMode ? agentSessionId : chatConversationId;
  const isLoading = isAgentMode ? agentIsLoading : chatIsLoading;
  const isStreaming = isAgentMode ? agentIsStreaming : chatIsStreaming;
  const error = isAgentMode ? agentError : chatError;
  const stopGeneration = isAgentMode ? agentStopGeneration : chatStopGeneration;

  const [suggestionText, setSuggestionText] = useState<string>('');
  const [isToolSelectorOpen, setIsToolSelectorOpen] = useState(false);
  
  // Track if we've done initial sync to avoid re-triggering on subsequent renders
  const initialSyncDone = useRef(false);

  // Sync URL conversation ID with hook state on mount or when URL changes
  useEffect(() => {
    // Only sync from URL to state, not the other way around
    if (urlConversationId && urlConversationId !== currentId) {
        if (isAgentMode) {
            agentSelectSession(urlConversationId);
        } else {
            chatSelectConversation(urlConversationId);
        }
    }
    initialSyncDone.current = true;
  }, [urlConversationId, isAgentMode]); // Only depend on URL changes

  // Update URL when a NEW conversation is created (temp -> real ID)
  useEffect(() => {
    if (
      initialSyncDone.current &&
      currentId &&
      !currentId.startsWith('temp-') &&
      !urlConversationId // Only update URL if we're on /chat (no ID in URL yet)
    ) {
        const basePath = isAgentMode ? '/agent' : '/chat';
        navigate(`${basePath}/${currentId}`, { replace: true });
    }
  }, [currentId, urlConversationId, navigate, isAgentMode]);

  const handleSuggestionClick = (text: string) => {
    setSuggestionText(text);
  };

  const handleSuggestionConsumed = () => {
    setSuggestionText('');
  };

  useEffect(() => {
    if (!isAgentMode) {
      setIsToolSelectorOpen(false);
    }
  }, [isAgentMode]);

  return (
    <>
      {error && (
        <div className="absolute top-4 left-4 right-4 z-10 p-3 bg-red-50/90 dark:bg-red-900/25 border border-red-200/80 dark:border-red-800/60 rounded-xl text-red-700 dark:text-red-300 text-sm backdrop-blur-sm">
          {error}
        </div>
      )}
      
      {isAgentMode ? (
        <>
           <AgentChatWindow 
             messages={messages} 
             isLoading={isLoading} 
             onSuggestionClick={handleSuggestionClick} 
             error={error}
             isToolSelectorOpen={isToolSelectorOpen}
           />
          <div className="px-4 pb-4 pt-1 max-w-3xl w-full mx-auto">
            <AgentChatInput
              onSend={agentSendMessage}
              onCancel={stopGeneration}
              disabled={isLoading}
              isStreaming={isStreaming}
              placeholder="让 Agent 帮你规划…"
              externalValue={suggestionText}
              onExternalValueConsumed={handleSuggestionConsumed}
              token={token || undefined}
              onToolsOpenChange={setIsToolSelectorOpen}
            />
            <div className="text-center text-[11px] text-ink-400 mt-2.5">
              CookHero 可能会出错，重要信息请自行核实。
            </div>
          </div>
        </>
      ) : (
        <>
           <ChatWindow 
             messages={messages} 
             isLoading={isLoading} 
             onSuggestionClick={handleSuggestionClick}
             error={error}
           />
          <div className="px-4 pb-4 pt-1 max-w-3xl w-full mx-auto">
            <ChatInput
              onSend={chatSendMessage}
              onCancel={stopGeneration}
              disabled={isLoading}
              isStreaming={isStreaming}
              placeholder="问问 CookHero…"
              externalValue={suggestionText}
              onExternalValueConsumed={handleSuggestionConsumed}
            />
            <div className="text-center text-[11px] text-ink-400 mt-2.5">
              CookHero 可能会出错，重要信息请自行核实。
            </div>
          </div>
        </>
      )}
    </>
  );
}

/**
 * Main layout component with sidebar
 */
function MainLayout({ children }: { children: React.ReactNode }) {
  const { username, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const isAgentMode = location.pathname.startsWith('/agent');

  // Standard Chat Context
  const {
    conversationId: chatConversationId,
    conversations: chatConversations,
    totalConversations: chatTotalConversations,
    hasMoreConversations: chatHasMoreConversations,
    selectConversation: chatSelectConversation,
    clearMessages: chatClearMessages,
    removeConversation: chatRemoveConversation,
    renameConversation: chatRenameConversation,
    loadMoreConversations: chatLoadMoreConversations,
  } = useConversationContext();

  // Agent Chat Context
  const {
      sessionId: agentSessionId,
      sessions: agentSessions,
      totalSessions: agentTotalSessions,
      hasMoreSessions: agentHasMoreSessions,
      selectSession: agentSelectSession,
      clearMessages: agentClearMessages,
      removeSession: agentRemoveSession,
      loadMoreSessions: agentLoadMoreSessions,
      renameSession: agentRenameSession,
  } = useAgentContext();

  // Unified State based on Mode
  const conversationId = isAgentMode ? agentSessionId : chatConversationId;
  // Map Agent sessions to ConversationSummary format for Sidebar
  const conversations = isAgentMode
    ? agentSessions.map(s => ({
        id: s.id,
        title: s.title ?? undefined,
        created_at: s.created_at,
        updated_at: s.updated_at,
        message_count: s.message_count,
        last_message_preview: s.last_message_preview
    }))
    : chatConversations;

  const totalConversations = isAgentMode ? agentTotalSessions : chatTotalConversations;
  const hasMoreConversations = isAgentMode ? agentHasMoreSessions : chatHasMoreConversations;
  const loadMoreConversations = isAgentMode ? agentLoadMoreSessions : chatLoadMoreConversations;
  
  const selectConversation = isAgentMode ? agentSelectSession : chatSelectConversation;
  const clearMessages = isAgentMode ? agentClearMessages : chatClearMessages;
  const removeConversation = isAgentMode ? agentRemoveSession : chatRemoveConversation;
  // Now Agent sessions support renaming
  const renameConversation = isAgentMode ? agentRenameSession : chatRenameConversation; 

  const { isDark, toggleTheme } = useTheme();
  const [isSidebarOpen, setIsSidebarOpen] = useState(
    () => typeof window === 'undefined' || window.innerWidth >= 768
  );
  const [isAnalyticsMenuOpen, setIsAnalyticsMenuOpen] = useState(false);
  const analyticsMenuRef = useRef<HTMLDivElement>(null);

  // Determine current view from pathname
  const isKnowledgeView = location.pathname.includes('/knowledge');
  const isEvaluationView = location.pathname.includes('/evaluation');
  const isLLMStatsView = location.pathname.includes('/llm-stats');
  const isAdminView = location.pathname.startsWith('/admin');
  const isDietView = location.pathname.includes('/diet');
  const isDietSubView = /\/diet\/(profile|pantry)/.test(location.pathname);
  const isRecipeView = location.pathname.startsWith('/recipes');
  const isRecipeLibraryView = location.pathname.includes('/recipes/library');
  const isAnalyticsView = isEvaluationView || isLLMStatsView;
  const analyticsLabel = isEvaluationView ? '评估监控' : isLLMStatsView ? '模型统计' : '数据分析';
  const sectionLabel = isRecipeLibraryView
    ? '菜谱图鉴'
    : isRecipeView
      ? '菜谱'
      : isDietSubView
        ? '饮食管理'
        : isDietView
          ? '饮食管理'
          : isKnowledgeView
            ? '知识库'
            : isEvaluationView
              ? '评估监控'
              : isLLMStatsView
                ? '模型统计'
                : isAgentMode
                  ? 'Agent 工作台'
                  : '对话';

  // Breadcrumb trail derived from the current path. The last crumb is the
  // current page (not clickable); earlier crumbs link to their parent.
  const crumbs = useMemo(() => {
    const dietBase = isAgentMode ? '/agent/diet' : '/diet';
    const result: { label: string; to?: string }[] = [];
    if (isAdminView) {
      result.push({ label: '管理后台' });
    } else if (isDietView) {
      result.push({ label: '饮食管理', to: dietBase });
      if (/\/diet\/profile/.test(location.pathname)) result.push({ label: '饮食档案' });
      else if (/\/diet\/pantry/.test(location.pathname)) result.push({ label: '储物柜' });
    } else if (isRecipeView) {
      result.push({ label: '饮食管理', to: dietBase });
      if (isRecipeLibraryView) result.push({ label: '菜谱图鉴' });
      else if (/^\/(agent\/)?recipes\/[^/]+/.test(location.pathname)) result.push({ label: '菜谱详情' });
      else result.push({ label: '菜谱搜索' });
    } else if (isKnowledgeView) {
      result.push({ label: '知识库' });
    } else if (isEvaluationView) {
      result.push({ label: '数据分析' });
      result.push({ label: '评估监控' });
    } else if (isLLMStatsView) {
      result.push({ label: '数据分析' });
      result.push({ label: '模型统计' });
    } else {
      result.push({ label: sectionLabel });
    }
    return result;
  }, [location.pathname, isDietView, isRecipeView, isRecipeLibraryView, isKnowledgeView, isEvaluationView, isLLMStatsView, isAdminView, isAgentMode, sectionLabel]);

  useEffect(() => {
    setIsAnalyticsMenuOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (analyticsMenuRef.current && !analyticsMenuRef.current.contains(event.target as Node)) {
        setIsAnalyticsMenuOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const goBackToChat = useCallback(() => {
    const basePath = isAgentMode ? '/agent' : '/chat';
    if (conversationId && !conversationId.startsWith('temp-')) {
      navigate(`${basePath}/${conversationId}`);
    } else {
      navigate(basePath);
    }
  }, [conversationId, isAgentMode, navigate]);

  const handleToggleAgentMode = useCallback(() => {
      if (isAgentMode) {
          navigate('/chat');
      } else {
          navigate('/agent');
      }
  }, [isAgentMode, navigate]);

  const handleNewChat = useCallback(() => {
    clearMessages();
    navigate(isAgentMode ? '/agent' : '/chat');
    if (window.innerWidth < 768) {
      setIsSidebarOpen(false);
    }
  }, [clearMessages, navigate, isAgentMode]);

  const handleSelectConversation = useCallback((id: string) => {
    selectConversation(id);
    const basePath = isAgentMode ? '/agent' : '/chat';
    navigate(`${basePath}/${id}`);
    if (window.innerWidth < 768) {
      setIsSidebarOpen(false);
    }
  }, [selectConversation, navigate, isAgentMode]);

  const handleLogout = useCallback(() => {
    logout();
    navigate('/login');
  }, [logout, navigate]);

  return (
    <div className="flex h-screen ch-app-bg text-ink-900 dark:text-cream-100 transition-colors duration-200">
      <Sidebar
        isOpen={isSidebarOpen}
        toggleSidebar={() => setIsSidebarOpen(!isSidebarOpen)}
        conversations={conversations}
        totalConversations={totalConversations}
        hasMoreConversations={hasMoreConversations}
        onLoadMoreConversations={loadMoreConversations}
        currentConversationId={conversationId || null}
        onSelectConversation={handleSelectConversation}
        onNewChat={handleNewChat}
        onDeleteConversation={removeConversation}
        onRenameConversation={renameConversation}
        isDark={isDark}
        toggleTheme={toggleTheme}
        isAgentMode={isAgentMode}
        onToggleAgentMode={handleToggleAgentMode}
      />

      <div className="flex-1 flex flex-col h-full relative min-w-0">
        <header className="h-16 ch-glass border-b flex items-center px-3 md:px-5 justify-between z-50 shrink-0">
          <div className="flex items-center gap-3">
            <button
              onClick={() => setIsSidebarOpen(!isSidebarOpen)}
              className="ch-icon-btn"
              title={isSidebarOpen ? 'Hide sidebar' : 'Show sidebar'}
            >
              <Menu className="w-5 h-5" />
            </button>
            <div className="hidden sm:flex items-center gap-2.5 min-w-0">
              <img src="/logo1.png" alt="" className="w-7 h-7 object-contain" />
              <span className="ch-wordmark text-[13px] text-ink-400 dark:text-ink-400">
                CookHero
              </span>
              {crumbs.map((crumb, index) => (
                <span key={`${crumb.label}-${index}`} className="flex items-center gap-2.5 min-w-0">
                  <span className="text-ink-300 dark:text-ink-600 text-sm">/</span>
                  {index < crumbs.length - 1 && crumb.to ? (
                    <Link
                      to={crumb.to}
                      className="text-sm text-ink-500 dark:text-ink-300 hover:text-ember-600 dark:hover:text-ember-300 transition-colors truncate"
                    >
                      {crumb.label}
                    </Link>
                  ) : (
                    <span className="text-sm font-medium text-ink-900 dark:text-cream-100 truncate">
                      {crumb.label}
                    </span>
                  )}
                </span>
              ))}
            </div>
            <div className="flex sm:hidden items-center gap-2 min-w-0">
              <img src="/logo1.png" alt="" className="w-6 h-6 object-contain" />
              <span className="text-sm font-medium text-ink-900 dark:text-cream-100 truncate">
                {crumbs[crumbs.length - 1]?.label ?? sectionLabel}
              </span>
            </div>
          </div>
          <div className="flex items-center gap-1 sm:gap-1.5 text-xs text-ink-600 dark:text-ink-200 overflow-visible">
            {!isKnowledgeView && !isEvaluationView && !isLLMStatsView && !isDietView && conversationId && (
              <span className="hidden lg:inline font-mono text-[10px] text-ink-400 bg-white/50 dark:bg-white/5 border border-cream-300/50 dark:border-white/10 px-2 py-1 rounded-full truncate max-w-[140px]" title={conversationId}>
                {conversationId.slice(0, 8)}
              </span>
            )}
            <button
              onClick={() => {
                if (isDietView) {
                  if (isDietSubView) {
                    // From a diet sub-page, go up to the diet management hub.
                    navigate(isAgentMode ? '/agent/diet' : '/diet');
                  } else {
                    // Already on the diet hub → return to the conversation.
                    const basePath = isAgentMode ? '/agent' : '/chat';
                    if (conversationId && !conversationId.startsWith('temp-')) {
                      navigate(`${basePath}/${conversationId}`);
                    } else {
                      navigate(basePath);
                    }
                  }
                } else {
                  navigate(isAgentMode ? '/agent/diet' : '/diet');
                }
              }}
              className={`ch-nav-pill ${isDietView ? 'ch-nav-pill-active' : ''}`}
            >
              <Utensils className="w-4 h-4" />
              <span className="hidden sm:inline">{isDietView ? (isDietSubView ? '返回饮食管理' : '返回对话') : '饮食管理'}</span>
            </button>
            <button
              onClick={() => {
                if (isKnowledgeView) {
                  const basePath = isAgentMode ? '/agent' : '/chat';
                  if (conversationId && !conversationId.startsWith('temp-')) {
                    navigate(`${basePath}/${conversationId}`);
                  } else {
                    navigate(basePath);
                  }
                } else {
                  navigate(isAgentMode ? '/agent/knowledge' : '/knowledge');
                }
              }}
              className={`ch-nav-pill ${isKnowledgeView ? 'ch-nav-pill-active' : ''}`}
            >
              <BookOpen className="w-4 h-4" />
              <span className="hidden sm:inline">{isKnowledgeView ? '返回对话' : '知识库'}</span>
            </button>
            <div ref={analyticsMenuRef} className="relative">
              <button
                onClick={() => setIsAnalyticsMenuOpen(prev => !prev)}
                className={`ch-nav-pill ${isAnalyticsView ? 'ch-nav-pill-active' : ''}`}
              >
                <BarChart3 className="w-4 h-4" />
                <span className="hidden sm:inline">{analyticsLabel}</span>
                <ChevronDown className="w-3.5 h-3.5 opacity-60 hidden sm:block" />
              </button>
              {isAnalyticsMenuOpen && (
                <div className="absolute right-0 mt-2 w-44 ch-card !rounded-2xl overflow-hidden z-50 py-1.5">
                  {isAnalyticsView && (
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        setIsAnalyticsMenuOpen(false);
                        goBackToChat();
                      }}
                      className="w-full text-left px-4 py-2.5 text-sm text-ink-600 dark:text-ink-200 hover:bg-cream-100 dark:hover:bg-white/5 border-b border-cream-200/70 dark:border-white/5 transition-colors flex items-center gap-2"
                    >
                      返回对话
                    </button>
                  )}
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      setIsAnalyticsMenuOpen(false);
                      navigate(isAgentMode ? '/agent/evaluation' : '/evaluation');
                    }}
                    className={`w-full text-left px-4 py-2.5 text-sm transition-colors flex items-center gap-2.5 ${
                      isEvaluationView
                        ? 'text-ember-600 dark:text-ember-300 font-medium bg-ember-50/70 dark:bg-ember-500/10'
                        : 'text-ink-700 dark:text-ink-200 hover:bg-cream-100 dark:hover:bg-white/5'
                    }`}
                  >
                    评估监控
                  </button>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      setIsAnalyticsMenuOpen(false);
                      navigate(isAgentMode ? '/agent/llm-stats' : '/llm-stats');
                    }}
                    className={`w-full text-left px-4 py-2.5 text-sm transition-colors flex items-center gap-2.5 ${
                      isLLMStatsView
                        ? 'text-ember-600 dark:text-ember-300 font-medium bg-ember-50/70 dark:bg-ember-500/10'
                        : 'text-ink-700 dark:text-ink-200 hover:bg-cream-100 dark:hover:bg-white/5'
                    }`}
                  >
                    模型统计
                  </button>
                </div>
              )}
            </div>
            {username && (
              <div className="flex items-center gap-1.5 ml-1 pl-2 border-l border-cream-300/60 dark:border-white/10 shrink-0">
                <div className="w-7 h-7 rounded-full ch-avatar flex items-center justify-center text-[11px] font-bold">
                  {username.charAt(0).toUpperCase()}
                </div>
                <span className="font-medium text-[13px] hidden md:inline text-ink-700 dark:text-ink-100 max-w-[100px] truncate">
                  {username}
                </span>
                <span className="hidden sm:inline-flex">
                  <button
                    onClick={handleLogout}
                    className="ch-icon-btn !w-8 !h-8"
                    title="退出登录"
                  >
                    <LogOut className="w-4 h-4" />
                  </button>
                </span>
              </div>
            )}
          </div>
        </header>

        <main className="flex-1 flex flex-col overflow-hidden relative min-w-0">
          {children}
        </main>
      </div>
    </div>
  );
}

function RequireAuth({ children }: { children: ReactElement }) {
  const { isAuthenticated, logout } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();

  // Listen for auth-unauthorized event (triggered when 401 response received)
  useEffect(() => {
    const handleUnauthorized = () => {
      logout();
      navigate('/login', { replace: true });
    };

    window.addEventListener('auth-unauthorized', handleUnauthorized);
    return () => window.removeEventListener('auth-unauthorized', handleUnauthorized);
  }, [logout, navigate]);

  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  return children;
}

function App() {
  return (
    <Routes>
      {/* Protected routes with main layout */}
      <Route
        path="/chat"
        element={
          <RequireAuth>
            <MainLayout>
              <ChatView />
            </MainLayout>
          </RequireAuth>
        }
      />
      <Route
        path="/chat/:id"
        element={
          <RequireAuth>
            <MainLayout>
              <ChatView />
            </MainLayout>
          </RequireAuth>
        }
      />
      <Route
        path="/knowledge"
        element={
          <RequireAuth>
            <MainLayout>
              <KnowledgePanel />
            </MainLayout>
          </RequireAuth>
        }
      />
      <Route
        path="/agent/knowledge"
        element={
          <RequireAuth>
            <MainLayout>
              <KnowledgePanel />
            </MainLayout>
          </RequireAuth>
        }
      />
      <Route
        path="/evaluation"
        element={
          <RequireAuth>
            <MainLayout>
              <EvaluationPage />
            </MainLayout>
          </RequireAuth>
        }
      />
      <Route
        path="/agent/evaluation"
        element={
          <RequireAuth>
            <MainLayout>
              <EvaluationPage />
            </MainLayout>
          </RequireAuth>
        }
      />
      <Route
        path="/llm-stats"
        element={
          <RequireAuth>
            <MainLayout>
              <LLMStatsPage />
            </MainLayout>
          </RequireAuth>
        }
      />
      <Route
        path="/agent/llm-stats"
        element={
          <RequireAuth>
            <MainLayout>
              <LLMStatsPage />
            </MainLayout>
          </RequireAuth>
        }
      />
      <Route
        path="/admin"
        element={
          <RequireAuth>
            <MainLayout>
              <AdminConsolePage />
            </MainLayout>
          </RequireAuth>
        }
      />
      <Route
        path="/diet"
        element={
          <RequireAuth>
            <MainLayout>
              <DietManagementPage />
            </MainLayout>
          </RequireAuth>
        }
      />
      <Route
        path="/diet/profile"
        element={
          <RequireAuth>
            <MainLayout>
              <DietProfilePage />
            </MainLayout>
          </RequireAuth>
        }
      />
      <Route
        path="/diet/pantry"
        element={
          <RequireAuth>
            <MainLayout>
              <PantryPage />
            </MainLayout>
          </RequireAuth>
        }
      />
      <Route
        path="/recipes"
        element={
          <RequireAuth>
            <MainLayout>
              <RecipeSearchPage />
            </MainLayout>
          </RequireAuth>
        }
      />
      <Route
        path="/recipes/library"
        element={
          <RequireAuth>
            <MainLayout>
              <RecipeLibraryPage />
            </MainLayout>
          </RequireAuth>
        }
      />
      <Route
        path="/recipes/:id"
        element={
          <RequireAuth>
            <MainLayout>
              <RecipeDetailPage />
            </MainLayout>
          </RequireAuth>
        }
      />
      <Route
        path="/recipes/:id/cook"
        element={
          <RequireAuth>
            <MainLayout>
              <CookingModePage />
            </MainLayout>
          </RequireAuth>
        }
      />
      <Route
        path="/agent/diet"
        element={
          <RequireAuth>
            <MainLayout>
              <DietManagementPage />
            </MainLayout>
          </RequireAuth>
        }
      />
      <Route
        path="/agent/diet/profile"
        element={
          <RequireAuth>
            <MainLayout>
              <DietProfilePage />
            </MainLayout>
          </RequireAuth>
        }
      />
      <Route
        path="/agent/diet/pantry"
        element={
          <RequireAuth>
            <MainLayout>
              <PantryPage />
            </MainLayout>
          </RequireAuth>
        }
      />
      <Route
        path="/agent/recipes"
        element={
          <RequireAuth>
            <MainLayout>
              <RecipeSearchPage />
            </MainLayout>
          </RequireAuth>
        }
      />
      <Route
        path="/agent/recipes/library"
        element={
          <RequireAuth>
            <MainLayout>
              <RecipeLibraryPage />
            </MainLayout>
          </RequireAuth>
        }
      />
      <Route
        path="/agent"
        element={
          <RequireAuth>
            <MainLayout>
              <ChatView />
            </MainLayout>
          </RequireAuth>
        }
      />
      <Route
        path="/agent/:id"
        element={
          <RequireAuth>
            <MainLayout>
              <ChatView />
            </MainLayout>
          </RequireAuth>
        }
      />
      {/* Auth routes */}
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      {/* Default redirect to agent */}
      <Route path="/" element={<Navigate to="/agent" replace />} />
      <Route path="*" element={<Navigate to="/agent" replace />} />
    </Routes>
  );
}

export default App;
