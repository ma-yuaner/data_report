import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

const apiProxy = { target: 'http://127.0.0.1:5160', changeOrigin: true }

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: { '/api': apiProxy },
  },
  preview: {
    host: '0.0.0.0',
    port: 4173,
    proxy: { '/api': apiProxy },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          'vue-vendor': ['vue', 'vue-router', 'pinia', 'axios'],
          'ant-design': ['ant-design-vue', '@ant-design/icons-vue'],
          'echarts-core': ['echarts/core', 'echarts/charts', 'echarts/components', 'echarts/renderers'],
        },
      },
    },
  },
})
