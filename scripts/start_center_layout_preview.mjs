/** Loopback-only preview tooling. Never imported by the product or build. */
import fs from 'node:fs/promises';
import path from 'node:path';
import {createRequire} from 'node:module';
import {fileURLToPath,pathToFileURL} from 'node:url';
import assert from 'node:assert/strict';

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const web=path.join(root,'web');
const fixture=JSON.parse(await fs.readFile(path.join(root,'output/public-visual-20261110/audit/FIXTURE_RUNTIME.json'),'utf8'));
assert.equal(fixture.api_url,'http://127.0.0.1:18111/api');
assert(path.basename(fixture.fixture_directory).startsWith('stl-v305-e2e-'));
assert.equal(path.dirname(path.resolve(fixture.fixture_directory)),path.resolve(process.env.TEMP));
await fs.access(path.join(fixture.fixture_directory,'local_fixture.sqlite3'));
const health=await fetch(`${fixture.api_url}/health/`,{signal:AbortSignal.timeout(5000),redirect:'error'});
assert(health.ok,'Start the isolated fixture API first');

Object.assign(process.env,{
  INTERNAL_API_URL:fixture.api_url,
  NEXT_PUBLIC_API_URL:fixture.api_url,
  INTERNAL_API_TOKEN:'local-e2e-server-token-305-not-for-production',
  ALLOW_DEMO_FALLBACK:'false',
  WRANGLER_SEND_METRICS:'false',
});
process.chdir(web);
const require=createRequire(path.join(web,'package.json'));
const {createServer}=await import(pathToFileURL(require.resolve('vite')).href);
const server=await createServer({
  root:web,
  configFile:path.join(web,'vite.config.ts'),
  server:{host:'127.0.0.1',port:18110,strictPort:true,proxy:{'/api':{target:'http://127.0.0.1:18111',changeOrigin:false}}},
  plugins:[{
    name:'stl-isolated-fixture-workers-redirect',
    apply:'serve',
    enforce:'pre',
    transform(code,id){
      if(!id.replaceAll('\\','/').split('?')[0].endsWith('/lib/api/server-request.ts'))return;
      // Local Workers rejects redirect:error before sending the request.
      // The inherited !response.ok guard rejects manual redirects, without
      // following them or forwarding the synthetic token to another origin.
      assert(code.includes('redirect: "error"'),'Expected unmodified public transport source');
      return {code:code.replace('redirect: "error"','redirect: "manual"'),map:null};
    },
  }],
});
await server.listen();
server.printUrls();
console.log('Local synthetic preview only; product transport/config files are unchanged.');
