import { fileURLToPath, URL } from 'node:url'
import { defineConfig, type Plugin } from 'vite'
import vue from '@vitejs/plugin-vue'

// A genuinely offline artifact: no ES module fetch/CORS problem when double-clicking file://.
function singleFile(): Plugin {
  return {
    name: 'adm-offline-single-file',
    enforce: 'post',
    generateBundle(_, bundle) {
      const html = bundle['index.html']
      if (!html || html.type !== 'asset') throw new Error('Missing prototype HTML')
      let content = String(html.source)
      let scripts = ''
      for (const [name, asset] of Object.entries(bundle)) {
        if (asset.type === 'chunk') {
          content = content.replace(/<script\b[^>]*src="[^"]+"[^>]*><\/script>/, '')
          scripts += `<script>${asset.code.replace(/<\/script/gi, '<\\/script')}</script>`
          delete bundle[name]
        } else if (name.endsWith('.css')) {
          content = content.replace(
            /<link\b[^>]*rel="stylesheet"[^>]*>/,
            () => `<style>${String(asset.source)}</style>`,
          )
          delete bundle[name]
        }
      }
      if (/<script[^>]+src=|<link[^>]+rel="stylesheet"/.test(content))
        throw new Error('Prototype must be fully offline')
      html.source = content.replace('</body>', () => `${scripts}</body>`)
    },
  }
}
export default defineConfig({
  root: fileURLToPath(new URL('./prototypes/adm-review', import.meta.url)),
  base: './',
  plugins: [vue(), singleFile()],
  resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
  define: { __VUE_OPTIONS_API__: true, __VUE_PROD_DEVTOOLS__: false, __VUE_PROD_HYDRATION_MISMATCH_DETAILS__: false },
  server: { host: '127.0.0.1', port: 15267, strictPort: true },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    cssCodeSplit: false,
    rollupOptions: { output: { format: 'iife', inlineDynamicImports: true } },
  },
})
