import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

export default defineConfig({
  plugins: [vue()],
  server: {
    host: "0.0.0.0",
    port: 5173,
    // HTTPS支持（可选）
    // https: {
    //   cert: process.env.SSL_CERT_FILE,
    //   key: process.env.SSL_KEY_FILE,
    // },
  },
  build: {
    // 性能优化：代码分割
    rollupOptions: {
      output: {
        manualChunks: {
          'vue-vendor': ['vue'],
          'echarts-vendor': ['echarts'],
          'utils': ['./src/utils/api.ts', './src/utils/timeFormatters.ts', './src/utils/dataExport.ts'],
        },
      },
    },
    // 启用压缩
    minify: 'terser',
    terserOptions: {
      compress: {
        drop_console: true,
        drop_debugger: true,
      },
    },
    // 启用source map（生产环境可关闭）
    sourcemap: false,
    // Chunk大小警告阈值
    chunkSizeWarningLimit: 1000,
  },
  // 优化依赖预构建
  optimizeDeps: {
    include: ['vue', 'echarts'],
  },
});
