import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react({
      babel: {
        plugins: [['babel-plugin-react-compiler']],
      },
    }),
  ],
  server: {
    host: '0.0.0.0',  // 允许公网访问
    port: 5173,       // 默认端口
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    // 打包输出到项目根目录的 static 文件夹
    outDir: path.resolve(__dirname, '../../static'),
    emptyOutDir: true,
    // 代码分割优化：将大型 chunk 拆分为更小的模块
    rollupOptions: {
      output: {
        manualChunks: {
          // React 核心库单独打包
          'vendor-react': ['react', 'react-dom', 'react-router-dom'],
          // 图表库单独打包
          'vendor-charts': ['recharts'],
          // Markdown 渲染单独打包
          'vendor-markdown': ['react-markdown', 'remark-gfm'],
          // 工具库单独打包
          'vendor-utils': ['axios', 'zustand', 'clsx', 'tailwind-merge'],
          // 图标库单独打包
          'vendor-icons': ['lucide-react', '@remixicon/react'],
        },
      },
    },
    // 提高警告阈值，避免大 chunk 警告
    chunkSizeWarningLimit: 600,
  },
})
