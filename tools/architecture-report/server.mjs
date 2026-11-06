import http from 'node:http';
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {exportScene} from './export.mjs';
const here=path.dirname(fileURLToPath(import.meta.url)),dist=path.join(here,'dist');
const port=5274,origin=`http://127.0.0.1:${port}`;
const types={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.svg':'image/svg+xml','.png':'image/png','.woff2':'font/woff2','.json':'application/json; charset=utf-8','.csv':'text/csv; charset=utf-8','.webm':'video/webm'};
let busy=false;
const server=http.createServer(async(req,res)=>{
  res.setHeader('Cache-Control','no-store');res.setHeader('X-Content-Type-Options','nosniff');res.setHeader('X-Robots-Tag','noindex, nofollow, noarchive');
  res.setHeader('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'");
  if(req.headers.host!==`127.0.0.1:${port}`&&req.headers.host!==`localhost:${port}`){res.writeHead(403);res.end('Local host only');return;}
  try{
    const url=new URL(req.url,origin);
    if(url.pathname==='/api/export'){
      if(req.method!=='POST'||req.headers.origin!==origin){res.writeHead(403);res.end('Same-origin POST required');return;}
      if(busy){res.writeHead(409);res.end('已有导出正在进行，请稍后重试');return;}
      let body='';for await(const chunk of req){body+=chunk;if(body.length>1024){res.writeHead(413);res.end('Request too large');return;}}
      const params=JSON.parse(body);if(!['overview','sitemap','workflow','technology','design','status'].includes(params.scene)||!['png','video'].includes(params.kind)||!Number.isInteger(params.phase)||params.phase<0||params.phase>3){res.writeHead(400);res.end('Invalid export options');return;}
      busy=true;
      try{
        const file=await exportScene({...params,origin});const buffer=await fs.readFile(file);
        res.writeHead(200,{'Content-Type':types[path.extname(file)],'Content-Disposition':`attachment; filename="STL-${path.basename(file)}"`});res.end(buffer);
      }finally{busy=false;}
      return;
    }
    if(!['GET','HEAD'].includes(req.method)){res.writeHead(405);res.end();return;}
    let pathname=decodeURIComponent(url.pathname);if(pathname==='/')pathname='/index.html';
    const file=path.resolve(dist,'.'+pathname);
    if(!file.startsWith(dist+path.sep)){res.writeHead(403);res.end();return;}
    const content=await fs.readFile(file);res.writeHead(200,{'Content-Type':types[path.extname(file)]||'application/octet-stream'});res.end(req.method==='HEAD'?undefined:content);
  }catch(error){if(!res.headersSent)res.writeHead(error.code==='ENOENT'?404:500,{'Content-Type':'text/plain; charset=utf-8'});res.end(error.code==='ENOENT'?'Not found':'导出或读取失败，请检查本地终端日志');console.error(error.message);}
});
server.listen(port,'127.0.0.1',()=>console.log(`STL 架构展映 ${origin}\n仅监听本机；无业务 API 代理、数据库访问或公开部署。`));
server.on('error',error=>{console.error(error.message);process.exitCode=1;});
