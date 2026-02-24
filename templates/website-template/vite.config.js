import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [
    react({
      // Treat .js files as JSX so existing .js components don't need renaming
      include: ['**/*.js', '**/*.jsx']
    })
  ],
  server: {
    port: 3000,
    open: true
  },
  build: {
    outDir: 'build'
  },
  esbuild: {
    loader: 'jsx',
    include: /src\/.*\.[jt]sx?$/,
    exclude: []
  },
  optimizeDeps: {
    esbuildOptions: {
      loader: {
        '.js': 'jsx'
      }
    }
  }
});
