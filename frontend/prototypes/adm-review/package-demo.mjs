// Generated portable deliverables only; sources remain in the prototype checkout.
import { copyFile,readFile } from 'node:fs/promises'
const built=new URL('./dist/index.html',import.meta.url)
const html=await readFile(built,'utf8')
if(/<script[^>]+src=|<link[^>]+rel="stylesheet"/.test(html))throw new Error('Offline package still has external entry assets')
const output=new URL('../../../../ADM产品验收台_DEMO_0.4.html',import.meta.url)
const guide=new URL('../../../../ADM产品验收台_先看使用说明.html',import.meta.url)
await copyFile(built,output)
await copyFile(new URL('./使用说明_0.4.html',import.meta.url),guide)
await copyFile(new URL('./PRD_0.4.html',import.meta.url),new URL('../../../../ADM管理PRD_0.4.html',import.meta.url))
console.log('Portable ADM demo and HTML guide generated in the workspace root. No server required.')
