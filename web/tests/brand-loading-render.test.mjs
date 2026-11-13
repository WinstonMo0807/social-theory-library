import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';
import react from '@vitejs/plugin-react';

const root = fileURLToPath(new URL('../', import.meta.url));
const server = await createServer({configFile:false,root,plugins:[react()],resolve:{alias:{'@':root}},server:{middlewareMode:true},logLevel:'error'});
try {
  const {BrandLoadingMark} = await server.ssrLoadModule('/components/ui/brand-loading-mark.tsx');
  const {default:Loading} = await server.ssrLoadModule('/app/loading.tsx');
  // Pending HTML must already select a CSS animation, without waiting for
  // hydration/useEffect. Logo and decorations share the SVG scaling system.
  for (const variant of ['l5','l6','l7']) {
    const html = renderToStaticMarkup(createElement(BrandLoadingMark,{initialVariant:variant,size:'hero'}));
    assert.match(html,new RegExp(`data-variant="${variant}"`));
    assert.match(html,/viewBox="0 0 256 224"/);
    assert.match(html,/stroke-width="3"/);
  }
  assert.match(renderToStaticMarkup(createElement(BrandLoadingMark)),/data-variant="l5"/);
  const random = Math.random;
  try {
    for (const [input,expected] of [[0,'l5'],[.5,'l6'],[.999,'l7']]) {
      Math.random = () => input;
      assert.match(renderToStaticMarkup(createElement(Loading)),new RegExp(`data-variant="${expected}"`));
    }
  } finally { Math.random = random; }
  console.log('Brand loading: three server-rendered variants, pre-hydration animation and shared SVG scale passed');
} finally { await server.close(); }
