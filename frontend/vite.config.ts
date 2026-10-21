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
  }
})
