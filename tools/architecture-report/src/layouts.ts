export type Position = {id:string;x:number;y:number;w?:number;h?:number};
export const layouts:Record<string,Position[]> = {
  overview:[{id:'stl',x:385,y:238,w:280,h:152},{id:'knowledge',x:40,y:66,w:270,h:134},{id:'discovery',x:710,y:66,w:270,h:134},{id:'reader',x:730,y:316,w:270,h:134},{id:'research',x:475,y:505,w:270,h:134},{id:'admin',x:40,y:452,w:270,h:134}],
  workflow:[{id:'opinion',x:35,y:78,w:286,h:162},{id:'evidence',x:375,y:78,w:286,h:162},{id:'reader',x:715,y:78,w:286,h:162},{id:'citation',x:715,y:430,w:286,h:155},{id:'projects',x:375,y:430,w:286,h:155},{id:'compare',x:35,y:430,w:286,h:155}],
  technology:[{id:'frontend',x:15,y:50,w:288,h:98},{id:'api',x:374,y:50,w:288,h:98},{id:'auth',x:730,y:50,w:288,h:98},{id:'tasks',x:374,y:240,w:288,h:98},{id:'retrieval',x:730,y:240,w:288,h:98},{id:'inference',x:730,y:430,w:288,h:98},{id:'processing',x:15,y:240,w:288,h:98},{id:'index',x:374,y:430,w:288,h:98},{id:'ocr',x:15,y:430,w:288,h:98},{id:'postgres',x:15,y:610,w:230,h:80},{id:'files',x:282,y:610,w:230,h:80},{id:'research',x:550,y:610,w:200,h:80},{id:'relay',x:785,y:610,w:230,h:80}],
  design:[{id:'brand',x:560,y:60,w:440,h:150},{id:'tokens',x:30,y:60,w:440,h:150},{id:'controls',x:30,y:280,w:440,h:150},{id:'shells',x:560,y:280,w:440,h:150},{id:'home',x:30,y:575,w:280,h:90},{id:'reader',x:375,y:575,w:280,h:90},{id:'admin',x:720,y:575,w:280,h:90}],
};
