import assert from 'node:assert/strict';
import { clampOffset } from '../lib/reader-floating-layout.mjs';

// A moved control must stay reachable after dragging or shrinking the viewport.
const base = { left: 100, top: 80, width: 300, height: 60 };
assert.deepEqual(clampOffset({x: 147, y: 91}, base, {width:1280,height:720}), {x:147,y:91});
assert.deepEqual(clampOffset({x: -999, y: 999}, base, {width:800,height:600}), {x:-92,y:452});
assert.deepEqual(clampOffset({x: 999, y: 999}, base, {width:390,height:300}), {x:-18,y:152});
// An oversized panel still retains its top-left handle on screen.
assert.deepEqual(clampOffset({x:999,y:-999}, {...base,width:1000,height:900}, {width:800,height:600}), {x:-92,y:-72});
console.log('Reader control bounds: passed');
