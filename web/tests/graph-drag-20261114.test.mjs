import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import * as React from 'react';
import ts from 'typescript';

const require=createRequire(import.meta.url);
const nodes=tree=>Array.isArray(tree)?tree.flatMap(nodes):React.isValidElement(tree)?[tree,...nodes(tree.props.children)]:[];
function harness(){
  const effects=[],layout=[],frames=new Map(),commits=[],paints=[];let frame=0,reads=0,captured=false;
  const hooks={...React,useId:()=> 'graph-test',useRef:current=>({current}),useState:value=>[value,()=>{}],useMemo:fn=>fn(),useEffect:fn=>effects.push(fn),useLayoutEffect:fn=>layout.push(fn)};
  const modules={react:hooks,'@/components/media-placement':{mediaGraphicClass:()=>''},'./theory-graph.module.css':{default:{}},'lucide-react':new Proxy({},{get:()=>()=>null})};
  const source=readFileSync(new URL('../components/public/graph-canvas.tsx',import.meta.url),'utf8');
  const code=ts.transpileModule(source,{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText;
  const exports={};let resized;
  new Function('require','exports','requestAnimationFrame','cancelAnimationFrame','ResizeObserver',code)(name=>modules[name]??require(name),exports,fn=>{frames.set(++frame,fn);return frame;},id=>frames.delete(id),class {constructor(fn){resized=fn;}observe(){}disconnect(){}});
  const tree=exports.GraphCanvas({graph:{nodes:[],edges:[],candidate_edges:[],candidate_count:null},selectedNode:'',selectedEdge:'',zoom:1,offset:{x:0,y:0},onTransform:(zoom,point)=>commits.push({zoom,point})});
  const svg=nodes(tree).find(n=>n.type==='svg'&&n.props.role==='group');
  const layer=nodes(svg).find(n=>n.type==='g'&&n.props.ref);
  const target={setPointerCapture(){captured=true;},hasPointerCapture(){return captured;},releasePointerCapture(){captured=false;},getBoundingClientRect(){reads++;return {width:500};},addEventListener(){},removeEventListener(){}};
  svg.props.ref.current=target;layer.props.ref.current={setAttribute:(_,value)=>paints.push(value)};
  layout.forEach(fn=>fn());const cleanups=effects.map(fn=>fn()).filter(Boolean);paints.length=0;
  const event=(x,y,pointerId=1)=>({button:0,isPrimary:pointerId===1,pointerId,clientX:x,clientY:y,currentTarget:target,target:{closest:()=>null}});
  return {svg,commits,paints,frames,event,reads:()=>reads,resize:()=>resized(),flush(){const pending=[...frames.values()];frames.clear();pending.forEach(fn=>fn());},close(){cleanups.forEach(fn=>fn());}};
}

test('a burst of drag events paints once and commits its final position once, even if released before the frame',()=>{
  const h=harness();h.svg.props.onPointerDown(h.event(10,10));
  for(let n=1;n<=40;n++)h.svg.props.onPointerMove(h.event(10+n,10+n));
  assert.equal(h.reads(),1);assert.equal(h.frames.size,1);assert.equal(h.commits.length,0);
  h.flush();assert.equal(h.paints.length,1);assert.match(h.paints[0],/translate\(80 80\)/);
  h.svg.props.onPointerMove(h.event(60,70));h.svg.props.onPointerUp(h.event(60,70));h.svg.props.onLostPointerCapture(h.event(60,70));
  assert.deepEqual(h.commits,[{zoom:1,point:{x:100,y:120}}]);assert.equal(h.frames.size,0);h.close();
});

test('other pointers do not move the view; cancellation, resize and teardown leave no queued transform',()=>{
  const h=harness();h.svg.props.onPointerDown(h.event(0,0));h.svg.props.onPointerMove(h.event(100,100,2));assert.equal(h.frames.size,0);
  h.svg.props.onPointerMove(h.event(20,10));h.svg.props.onPointerCancel(h.event(20,10));assert.deepEqual(h.commits[0].point,{x:40,y:20});assert.equal(h.frames.size,0);
  h.svg.props.onPointerDown(h.event(0,0));h.svg.props.onPointerMove(h.event(5,5));h.resize();assert.equal(h.frames.size,0);
  h.svg.props.onPointerDown(h.event(0,0));h.svg.props.onPointerMove(h.event(5,5));h.close();assert.equal(h.frames.size,0);
});

test('a second touch cannot replace or end an active primary drag',()=>{
 const h=harness();h.svg.props.onPointerDown(h.event(0,0));h.svg.props.onPointerMove(h.event(20,10));h.flush();
 h.svg.props.onPointerDown(h.event(100,100,2));h.svg.props.onPointerUp(h.event(100,100,2));h.svg.props.onLostPointerCapture(h.event(100,100,2));
 assert.equal(h.commits.length,0);assert.match(h.paints.at(-1),/translate\(40 20\)/);
 h.svg.props.onPointerMove(h.event(30,20));h.svg.props.onPointerUp(h.event(30,20));assert.deepEqual(h.commits,[{zoom:1,point:{x:60,y:40}}]);h.close();
});
