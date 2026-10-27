// Local prototype preview only. Never serves repository files or proxies APIs.
import { createServer } from 'node:http'
import { readFile } from 'node:fs/promises'
const file=new URL('./dist/index.html',import.meta.url)
const server=createServer(async(req,res)=>{
  if(req.url!=='/'&&req.url!=='/index.html'){res.writeHead(404);res.end('Prototype only');return}
  try{const body=await readFile(file);res.writeHead(200,{'Content-Type':'text/html;charset=utf-8','Cache-Control':'no-store','X-Content-Type-Options':'nosniff'});res.end(body)}catch{res.writeHead(503);res.end('Build the ADM prototype first')}
})
server.on('error',()=>{console.error('ADM DEMO local port 15267 unavailable; use the offline HTML instead.');process.exitCode=1})
server.listen(15267,'127.0.0.1',()=>console.log('ADM synthetic prototype: http://127.0.0.1:15267 (no production connections)'))
