import { offlinePrototype } from './prototypes/shared/offline-build'
import { fileURLToPath } from 'node:url'
import { liveAnnotation } from './prototypes/adm-review/live/contract-tools.mjs'
const config=offlinePrototype('adm-review',15267)
config.plugins=[liveAnnotation(),...(config.plugins || [])]
config.resolve={alias:[
  {find:'@/components/ComprehensiveExportDrawer.vue',replacement:fileURLToPath(new URL('./prototypes/adm-review/live/LiveExportDrawer.vue',import.meta.url))},
  {find:'@/api/http',replacement:fileURLToPath(new URL('./prototypes/adm-review/live/http.ts',import.meta.url))},
  {find:'@/stores/auth',replacement:fileURLToPath(new URL('./prototypes/adm-review/live/auth.ts',import.meta.url))},
  {find:'@/stores/comprehensiveExports',replacement:fileURLToPath(new URL('./prototypes/adm-review/live/exports.ts',import.meta.url))},
  {find:'@',replacement:fileURLToPath(new URL('./src',import.meta.url))},
]}
export default config
