import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import './index.css';
import AdminApp from './pages/admin/AdminApp';
import { AuthProvider } from './contexts';

// 后台固定深色：不接 ThemeProvider，避免用户在主应用选的浅色主题把这里刷白。
// adm-root 用于把 admin.css 的全局规则限定在这一份文档里。
document.documentElement.classList.add('dark', 'adm-root');

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <AuthProvider>
      <AdminApp />
    </AuthProvider>
  </StrictMode>,
);
