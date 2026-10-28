import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // 允许通过内网穿透/临时隧道访问开发服务器（Vite 7 默认只放行 localhost）。
    // 前导点表示允许该域名的所有子域，例如 xxx.trycloudflare.com。
    // 仅影响 `npm run dev`，生产构建由 Nginx 托管，与此配置无关。
    allowedHosts: ['.trycloudflare.com', '.ngrok-free.app', '.ngrok.io'],
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/media': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    }
  },
  build: {
    rollupOptions: {
      // 双入口：主应用（index.html）与独立后台（admin.html）。
      // 后台单独打一份产物，打开 /admin.html 时不会加载主应用的聊天与落地页代码。
      input: {
        main: 'index.html',
        admin: 'admin.html',
      },
    },
  },
  // 生产构建的同源预览：`npm run preview` 后在前端端口上同时提供
  // 静态资源与 /api、/media 代理，行为和线上网关（Caddy/Nginx）一致，
  // 便于在没有反向代理的环境里验证 Cookie 会话链路。
  preview: {
    port: 4173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/media': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
