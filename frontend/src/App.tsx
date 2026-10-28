// src/App.tsx
import { useEffect, useState, useCallback, useRef, useMemo } from 'react';
import type { ReactElement } from 'react';
import { BookOpen, Loader2, Menu, LogOut, Settings, Utensils } from 'lucide-react';
import { Link, Navigate, Route, Routes, useLocation, useNavigate, useParams } from 'react-router-dom';
import { ChatWindow, ChatInput, Sidebar, KnowledgePanel } from './components';
import { AgentChatWindow, AgentChatInput } from './components/agent';
import { useTheme, useAuth, useConversationContext, useAgentContext } from './contexts';
import LandingPage from './pages/Landing';
import LoginPage from './pages/Login';
import RegisterPage from './pages/Register';
import DietManagementPage from './pages/diet/DietManagement';
import DietProfilePage from './pages/diet/DietProfile';
import PantryPage from './pages/diet/Pantry';
import RecipeSearchPage from './pages/recipes/RecipeSearch';
import RecipeLibraryPage from './pages/recipes/RecipeLibrary';
import RecipeDetailPage from './pages/recipes/RecipeDetail';
import CookingModePage from './pages/recipes/CookingMode';
import { getAdminWhoami } from './services/api/admin';

/**
 * Agent 会话 ID 是 UUID。不是这个形状的路径段（例如手写 /agent/admin）
 * 不必发一次注定 404 的请求，可直接复位到新会话。
 */
const AGENT_SESSION_ID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

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
        if (!AGENT_SESSION_ID_PATTERN.test(urlConversationId)) {
          navigate('/agent', { replace: true });
          initialSyncDone.current = true;
          return;
        }
        // 会话不存在 / 已被删除 / 不属于当前账号时，复位到干净的新会话，
        // 而不是把 "Session not found" 这种后端原文留在页面上。
        let cancelled = false;
        void agentSelectSession(urlConversationId).then((result) => {
          if (!cancelled && result === 'missing') {
            navigate('/agent', { replace: true });
          }
        });
        initialSyncDone.current = true;
        return () => {
          cancelled = true;
        };
      }
      chatSelectConversation(urlConversationId);
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
 * 后台已拆成独立入口（admin.html），主应用只保留一次跳转：
 * 这样旧书签、/evaluation 等历史重定向与 ?tab= 参数继续可用，
 * 同时后台的代码不会被打进主应用首屏。
 */
function AdminRedirect() {
  const location = useLocation();

  useEffect(() => {
    window.location.replace(`/admin.html${location.search}`);
  }, [location.search]);

  return (
    <div className="flex min-h-[60vh] items-center justify-center gap-2 text-sm text-ink-500 dark:text-ink-300">
      <Loader2 className="h-4 w-4 animate-spin" />
      正在进入管理控制台…
    </div>
  );
}

/**
 * Main layout component with sidebar
 */
function MainLayout({ children }: { children: React.ReactNode }) {
  const { username, logout, token } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const isAgentMode = location.pathname.startsWith('/agent');

  // 仅有后台权限的账号才显示"管理后台"入口；真正的权限校验在服务端。
  const [isAdmin, setIsAdmin] = useState(false);
  useEffect(() => {
    if (!token) {
      setIsAdmin(false);
      return;
    }
    let cancelled = false;
    getAdminWhoami(token)
      .then((res) => {
        if (!cancelled) setIsAdmin(res.is_admin);
      })
      .catch(() => {
        if (!cancelled) setIsAdmin(false);
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

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

  // Determine current view from pathname
  const isKnowledgeView = location.pathname.includes('/knowledge');
  const isAdminView = location.pathname.startsWith('/admin');
  const isDietView = location.pathname.includes('/diet');
  const isDietSubView = /\/diet\/(profile|pantry)/.test(location.pathname);
  const isRecipeView = location.pathname.startsWith('/recipes');
  const isRecipeLibraryView = location.pathname.includes('/recipes/library');
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
    } else {
      result.push({ label: sectionLabel });
    }
    return result;
  }, [location.pathname, isDietView, isRecipeView, isRecipeLibraryView, isKnowledgeView, isAdminView, isAgentMode, sectionLabel]);

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
              <img src="/logo.svg" alt="" className="w-8 h-8 drop-shadow-[0_4px_10px_rgba(226,96,44,0.3)]" />
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
              <img src="/logo.svg" alt="" className="w-7 h-7 drop-shadow-[0_4px_10px_rgba(226,96,44,0.3)]" />
              <span className="text-sm font-medium text-ink-900 dark:text-cream-100 truncate">
                {crumbs[crumbs.length - 1]?.label ?? sectionLabel}
              </span>
            </div>
          </div>
          <div className="flex items-center gap-1 sm:gap-1.5 text-xs text-ink-600 dark:text-ink-200 overflow-visible">
            {!isKnowledgeView && !isDietView && conversationId && (
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
            {isAdmin && (
              <button
                onClick={() => window.location.assign('/admin.html')}
                className={`ch-nav-pill ${isAdminView ? 'ch-nav-pill-active' : ''}`}
                title="管理后台"
              >
                <Settings className="w-4 h-4" />
                <span className="hidden sm:inline">管理后台</span>
              </button>
            )}
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
  const { isAuthenticated, isReady, logout } = useAuth();
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

  // 会话探测完成前不要重定向，否则刷新页面会闪一下登录页
  if (!isReady) {
    return (
      <div className="flex h-screen items-center justify-center bg-cream-50 dark:bg-[#12100c]">
        <Loader2 className="w-6 h-6 animate-spin text-ember-500" />
      </div>
    );
  }

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
      {/* 旧的运营页入口：已并入管理后台，保留链接兼容 */}
      <Route path="/evaluation" element={<Navigate to="/admin?tab=quality" replace />} />
      <Route path="/agent/evaluation" element={<Navigate to="/admin?tab=quality" replace />} />
      <Route path="/llm-stats" element={<Navigate to="/admin?tab=calls" replace />} />
      <Route path="/agent/llm-stats" element={<Navigate to="/admin?tab=calls" replace />} />
      {/* 命名空间碰撞：手写 /agent/admin 时进入真正的后台，而不是被当成会话 ID */}
      <Route path="/agent/admin" element={<Navigate to="/admin" replace />} />
      <Route path="/admin" element={<AdminRedirect />} />
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
      {/* 公开门面页：未登录也能访问，CTA 自行分流到 /agent 或 /login */}
      <Route path="/" element={<LandingPage />} />
      <Route path="*" element={<Navigate to="/agent" replace />} />
    </Routes>
  );
}

export default App;
