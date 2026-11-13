import assert from 'node:assert/strict';
import { clampOffset, createReaderFloatingLayout } from '../lib/reader-floating-layout.mjs';

// A moved control must stay reachable after dragging or shrinking the viewport.
const base = { left: 100, top: 80, width: 300, height: 60 };
assert.deepEqual(clampOffset({x: 147, y: 91}, base, {width:1280,height:720}), {x:147,y:91});
assert.deepEqual(clampOffset({x: -999, y: 999}, base, {width:800,height:600}), {x:-92,y:452});
assert.deepEqual(clampOffset({x: 999, y: 999}, base, {width:390,height:300}), {x:-18,y:152});
// An oversized panel still retains its top-left handle on screen.
assert.deepEqual(clampOffset({x:999,y:-999}, {...base,width:1000,height:900}, {width:800,height:600}), {x:-92,y:-72});
console.log('Reader control bounds: passed');

// Position preferences survive opening another book, remain owner-scoped,
// and reset without touching any reading records.
const saved = new Map(), listeners = new Map();
globalThis.localStorage = { getItem: key => saved.get(key), setItem: (key, value) => saved.set(key, value) };
globalThis.sessionStorage = { getItem: () => null };
globalThis.window = { innerWidth: 1280, innerHeight: 800, matchMedia: () => ({ matches: true }), addEventListener() {}, removeEventListener() {} };
globalThis.ResizeObserver = class { observe() {} disconnect() {} };
function book() {
  const element = { dataset: { readerFloat: 'outline' }, style: {}, getBoundingClientRect() { return {...base,left:base.left+(this._readerOffset?.x||0),top:base.top+(this._readerOffset?.y||0)}; } };
  const grip = { closest: () => element };
  const root = { querySelectorAll: () => [element], addEventListener: (name, fn) => listeners.set(name, fn), removeEventListener: name => listeners.delete(name) };
  return {element,root,grip};
}
let current = book(), controller = createReaderFloatingLayout(current.root, 'reader:owner-a');
listeners.get('keydown')({ target: { closest: () => current.grip }, key:'ArrowRight', preventDefault() {}, stopPropagation() {} });
assert.equal(current.element.style.translate, '10px 0px');
controller.destroy();
current = book();controller = createReaderFloatingLayout(current.root, 'reader:owner-a');
assert.equal(current.element.style.translate, '10px 0px');
controller.destroy();
controller = createReaderFloatingLayout(current.root, 'reader:owner-b');
assert.equal(current.element.style.translate, '');
controller.destroy();
controller = createReaderFloatingLayout(current.root, 'reader:owner-a');
controller.reset();assert.deepEqual(JSON.parse(saved.get('reader:owner-a')), {});
assert.equal(current.element.style.translate, '');controller.destroy();
console.log('Reader cross-book persistence, owner isolation and reset: passed');
