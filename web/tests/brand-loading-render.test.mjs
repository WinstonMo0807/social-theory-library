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
  const {brandLoadingVariants,pickBrandLoadingVariant} = await server.ssrLoadModule('/lib/brand-loading.ts');
  assert.deepEqual([...brandLoadingVariants],['l5','l6','j','k']);
  // Pending HTML must already select a CSS animation, without waiting for
  // hydration/useEffect. Logo and decorations share the SVG scaling system.
  for (const variant of brandLoadingVariants) {
    const html = renderToStaticMarkup(createElement(BrandLoadingMark,{initialVariant:variant,size:'hero'}));
    assert.match(html,new RegExp(`data-variant="${variant}"`));
    assert.match(html,/stl-symbol-20261027.svg#mark/);
    if (variant === 'l5' || variant === 'l6') {
      assert.match(html,/viewBox="0 0 256 224"/);
      assert.match(html,/stroke-width="3"/);
    } else {
      assert.match(html,/viewBox="12 17 230 154"/);
    }
  }
  assert.match(renderToStaticMarkup(createElement(BrandLoadingMark)),/data-variant="l5"/);
  const random = Math.random;
  try {
    for (const [input,expected] of [[0,'l5'],[.2499,'l5'],[.25,'l6'],[.4999,'l6'],[.5,'j'],[.7499,'j'],[.75,'k'],[.999,'k']]) {
      Math.random = () => input;
      assert.equal(pickBrandLoadingVariant(input),expected);
      assert.match(renderToStaticMarkup(createElement(Loading)),new RegExp(`data-variant="${expected}"`));
    }
  } finally { Math.random = random; }
  console.log('Brand loading: four variants, random boundaries, original logo and server-rendered selection passed');
} finally { await server.close(); }
