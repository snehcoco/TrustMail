import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { resolve } from 'path';

/**
 * Vite Configuration for TrustMail Chrome Extension
 *
 * Multi-entry build producing:
 *   dist/popup/index.html       — Browser action popup
 *   dist/options/index.html     — Options page
 *   dist/background/service-worker.js  — MV3 service worker
 *   dist/content/*.js           — Content scripts (one per platform)
 *
 * All output goes into dist/ which is loaded as an unpacked extension.
 */
export default defineConfig({
  plugins: [react()],

  resolve: {
    alias: {
      '@': resolve(__dirname, './src'),
      '@components': resolve(__dirname, './src/components'),
      '@services': resolve(__dirname, './src/services'),
      '@utils': resolve(__dirname, './src/utils'),
      '@hooks': resolve(__dirname, './src/hooks'),
    },
  },

  build: {
    outDir: 'dist',
    emptyOutDir: true,
    sourcemap: false, // No source maps in extension for security
    minify: 'esbuild',

    rollupOptions: {
      input: {
        // React entry points
        popup: resolve(__dirname, 'popup/index.html'),
        options: resolve(__dirname, 'options/index.html'),
        // Background service worker (module)
        'background/service-worker': resolve(__dirname, 'background/service-worker.ts'),
        // Content scripts (per platform)
        'content/gmail': resolve(__dirname, 'content/gmail.ts'),
        'content/outlook': resolve(__dirname, 'content/outlook.ts'),
        'content/yahoo': resolve(__dirname, 'content/yahoo.ts'),
        'content/proton': resolve(__dirname, 'content/proton.ts'),
      },

      output: {
        // Preserve entry file names for manifest.json references
        entryFileNames: '[name].js',
        chunkFileNames: 'chunks/[name]-[hash].js',
        assetFileNames: 'assets/[name]-[hash][extname]',
        // Inline small chunks to reduce HTTP requests (N/A for extension but good practice)
        inlineDynamicImports: false,
      },
    },
  },

  // Dev server for popup development (chrome://extensions/ still needed for full integration)
  server: {
    port: 5173,
    strictPort: true,
  },
});
