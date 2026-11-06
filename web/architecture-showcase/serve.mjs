import http from 'node:http';
import { readFile, stat } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
const isPublic=process.argv.includes('--public');
const root = path.join(path.dirname(fileURLToPath(import.meta.url)),isPublic?'dist-public':'dist');
const port = Number(process.argv[2] || 5196);
const bind=process.env.SHOWCASE_BIND||'127.0.0.1';
if(bind!=='127.0.0.1'&&!isPublic)throw new Error('Only the stripped public build may listen outside localhost.');
const hosts=['127.0.0.1:'+port,'localhost:'+port,...(isPublic?['preview.winstonmo.com','preview.winstonmo.com:'+port]:[])];
const types={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.json':'application/json; charset=utf-8','.svg':'image/svg+xml','.png':'image/png','.woff2':'font/woff2','.csv':'text/csv; charset=utf-8'};
http.createServer(async(req,res)=>{
  res.setHeader('Cache-Control','no-store'); res.setHeader('X-Content-Type-Options','nosniff');
  res.setHeader('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'");
  res.setHeader('X-Robots-Tag','noindex, nofollow');
  if(!hosts.includes(req.headers.host)||!['GET','HEAD'].includes(req.method)){res.writeHead(403).end();return;}
  try{
    const url=new URL(req.url,'http://localhost');
    const file=path.resolve(root,'.'+decodeURIComponent(url.pathname==='/'?'/index.html':url.pathname));
    if(!file.startsWith(root+path.sep)||!(await stat(file)).isFile()){res.writeHead(404).end();return;}
    const body=await readFile(file);res.writeHead(200,{'Content-Type':types[path.extname(file)]||'application/octet-stream'});res.end(req.method==='HEAD'?undefined:body);
  }catch{res.writeHead(404).end('Not found');}
}).listen(port,bind,()=>console.log(`STL ${isPublic?'public':'internal'} architecture: ${bind}:${port}`));
