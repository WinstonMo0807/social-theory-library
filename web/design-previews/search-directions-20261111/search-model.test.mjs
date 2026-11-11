import test from 'node:test';
import assert from 'node:assert/strict';
import {matches,optionsFor,sortWorks,fold} from './search-model.ts';

test('searchable facets combine OR within a facet, AND across facets, and count alternatives',()=>{
  const base={topic:'',summary:'',href:'',reader:'reader',cover:''};
  const works=[
    {...base,id:'1',title:'甲书',author:'作者甲',year:'2016',topics:['乡村']},
    {...base,id:'2',title:'乙书',author:'作者乙',year:'2020',topics:['乡村']},
    {...base,id:'3',title:'丙书',author:'作者乙',year:'2016',topics:['城市']},
  ];
  const filters={author:['作者甲','作者乙'],year:['2016']};
  assert.deepEqual(works.filter(w=>matches(w,filters,'')).map(w=>w.id),['1','3']);
  assert.deepEqual(works.filter(w=>matches(w,{...filters,topics:['乡村']},'')).map(w=>w.id),['1']);
  assert.equal(optionsFor(works,'author',{author:['作者甲'],year:['2016']},'').find(o=>o.value==='作者乙').count,1);
  assert.equal(optionsFor(works,'documentType',{},'').find(o=>o.value==='journal_article').count,0);
  assert.deepEqual(optionsFor(works,'language',{},''),[]);
  assert.deepEqual(sortWorks(works,'year','').map(w=>w.id),['2','1','3']);
  assert.equal(fold('Ｍ． 韦伯'),fold('m·韦伯'));
});
