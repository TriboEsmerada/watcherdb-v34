import { defineConfig } from 'vite';
import { resolve } from 'path';

export default defineConfig({
  root: '.',
  build: {
    outDir: 'static/js/dist',
    emptyOutDir: true,
    lib: {
      entry: {
        'security-utils': resolve(__dirname, 'src/security-utils.ts'),
        'innovative-features': resolve(__dirname, 'src/innovative-features.ts'),
      },
      formats: ['iife'],
      name: 'WatcherDB',
    },
    rollupOptions: {
      output: {
        entryFileNames: '[name].js',
        chunkFileNames: '[name].js',
      },
    },
    minify: 'terser',
    sourcemap: true,
  },
});
