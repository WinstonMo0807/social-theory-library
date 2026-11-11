export type Work = {
  id: string; title: string; author: string; year: string; topic: string; summary: string;
  href: string; reader: string; cover: string; documentType?: string; language?: string;
  theories?: string[]; topics?: string[]; concepts?: string[];
};
export const facetNames = {
  documentType: '内容类型', theories: '理论流派', topics: '研究专题', concepts: '文献标签',
  author: '作者', year: '出版时间', language: '语言', access: '开放状态',
};
export type FacetKey = keyof typeof facetNames;
export type Filters = Partial<Record<FacetKey, string[]>>;
export type FacetOption = { value: string; label: string; count: number };
export const fold = (text: string) => text.normalize('NFKC').toLocaleLowerCase().replace(/[\s·・.]/g, '');
export function values(work: Work, key: FacetKey): string[] {
  if (key === 'documentType') return [work.documentType || 'book'];
  if (key === 'access') return [work.reader ? 'readable' : 'metadata'];
  if (key === 'theories' || key === 'topics' || key === 'concepts') return work[key] || [];
  return work[key] ? [work[key]!] : [];
}
export function matches(work: Work, filters: Filters, query: string, omit?: FacetKey) {
  return Object.entries(filters).every(([key, selected]) => key === omit || !selected?.length || selected.some(value => values(work, key as FacetKey).includes(value)))
    && (!query.trim() || fold([work.title, work.author, work.summary, work.topic].join(' ')).includes(fold(query)));
}
export function optionsFor(works: Work[], key: FacetKey, filters: Filters, query: string): FacetOption[] {
  const fixed = key === 'documentType' ? [['book','图书'],['journal_article','期刊论文'],['thesis','学位论文'],['report','研究报告']]
    : key === 'access' ? [['readable','可在线阅读'],['metadata','仅书目信息']] : null;
  const options = fixed || [...new Set(works.flatMap(work => values(work, key)))].map(value => [value, value]);
  const available = works.filter(work => matches(work, filters, query, key));
  return options.map(([value,label]) => ({value,label,count:available.filter(work => values(work,key).includes(value)).length}))
    .sort((a,b) => fixed ? 0 : key === 'year' ? Number(b.value)-Number(a.value) : b.count-a.count || a.label.localeCompare(b.label,'zh-CN'));
}
export function sortWorks(works: Work[], sort: string, query: string) {
  if (sort === 'year') return [...works].sort((a,b) => Number(b.year)-Number(a.year));
  if (sort === 'relevance' && query.trim()) {
    const q = fold(query);
    const score = (w: Work) => (fold(w.title).includes(q)?8:0)+(fold(w.author).includes(q)?4:0)+(fold(w.summary).includes(q)?1:0);
    return [...works].sort((a,b) => score(b)-score(a));
  }
  return works;
}
