import test from 'node:test';
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {readFileSync} from 'node:fs';

test('the known public proxy preserves HTTPS, LAN HTTP and rejects a foreign forwarded host',()=>{
 const nginx=readFileSync(new URL('../../deploy/nginx/default.conf.template',import.meta.url),'utf8');
 const [api,web]=nginx.split('    location / {');
 assert.match(web,/proxy_set_header X-Forwarded-Proto \$forwarded_proto;/);
 assert.match(api,/proxy_set_header X-Forwarded-Proto \$library_forwarded_proto;/);
 const source=`
  import assert from 'node:assert/strict';
  import {nodeToWebRequest} from './node_modules/vinext/dist/server/prod-server.js';
  const request=(host,proto,forwarded)=>nodeToWebRequest({method:'GET',url:'/login?next=%2Fexplore',headers:{host,'x-forwarded-proto':proto,...forwarded?{'x-forwarded-host':forwarded}:{}},socket:{}}).url;
  assert.equal(request('books.winstonmo.com','https'),'https://books.winstonmo.com/login?next=%2Fexplore');
  assert.equal(request('192.168.5.6:18084','http'),'http://192.168.5.6:18084/login?next=%2Fexplore');
  assert.equal(request('books.winstonmo.com','https','attacker.invalid'),'https://books.winstonmo.com/login?next=%2Fexplore');
 `;
 const result=spawnSync(process.execPath,['--input-type=module','-e',source],{cwd:new URL('..',import.meta.url),env:{...process.env,VINEXT_TRUSTED_HOSTS:'books.winstonmo.com'},encoding:'utf8'});
 assert.equal(result.status,0,result.stdout+result.stderr);
});
