import { policies, corpusVersion, type Policy } from "./data";

export type Filters = { region: string; kind: string; from: string; to: string };
export const emptyFilters: Filters = { region: "全部地区", kind: "全部类型", from: "", to: "" };
export type Hit = { policy: Policy; passage: Policy["passages"][number]; score: number };
export type SearchResult = { query: string; context: string; filters: Filters; hits: Hit[]; engine: "semantic" | "lexical"; notice: string; model?: string; corpusVersion: string };

const synonymGroups = [
  ["骑手", "外卖", "配送", "新就业", "新业态", "平台劳动", "劳动者", "平台用工"],
  ["算法", "调度", "订单", "奖惩", "控制", "自动化决策"],
  ["报酬", "工资", "收入", "计件", "分配"],
  ["休息", "工时", "工作时间", "工作量"],
  ["自主", "自主权", "选择", "关闭", "知情", "协商", "参与"],
  ["个人信息", "隐私", "数据", "公开信息"],
  ["社会保障", "权益", "责任", "劳动关系", "社会保护"],
];
export function effectiveQuery(query: string, previous: string) {
  // ponytail: explicit follow-up markers only; a full conversation planner belongs after this demo.
  const followup = /^(?:那|那么|这些|它们|其中|只看|仅看|继续|再看|比较|对比|帮我引用|能否|这能|能证明|有没有)/.test(query);
  return followup && previous ? `${previous.slice(0, 400)}；本次追问：${query}` : query;
}
export function candidateHits(query: string, filters: Filters): Hit[] {
  const groups = synonymGroups.filter(group => group.some(term => query.includes(term)));
  const tokens = [...new Set([...groups.flat(), ...(query.match(/[\p{Script=Han}]{2,}|[a-zA-Z]{3,}/gu) || [])])];
  const filtered = policies.filter(policy =>
    (filters.region === "全部地区" || policy.region === filters.region || policy.province === filters.region)
    && (filters.kind === "全部类型" || policy.kind === filters.kind)
    && (!filters.from || policy.date >= filters.from)
    && (!filters.to || policy.date <= filters.to));
  return filtered.flatMap(policy => policy.passages.map(passage => {
    const haystack = `${policy.title} ${policy.number} ${policy.topic} ${passage.text} ${passage.lens}`;
    const exactDocument = query.includes(policy.number) || query.includes(policy.title);
    const score = (exactDocument ? 100 : 0) + tokens.reduce((sum, term) => sum + (haystack.includes(term) ? Math.min(term.length, 4) : 0), 0);
    return { policy, passage, score };
  })).sort((a, b) => b.score - a.score);
}
export function suggestedFilters(query: string, current: Filters): Filters {
  const next = { ...current };
  if (/全国|不限地区|所有地区|全部地区|中央和地方/.test(query)) next.region = "全部地区";
  else {
    const regions = ["上海", "绍兴", "浙江"].filter(region => query.includes(region));
    if (regions.length === 1) next.region = regions[0];
    else if (regions.length > 1) next.region = "全部地区";
  }
  if (/只看法律|仅看法律/.test(query)) next.kind = "法律";
  if (/只看规章|仅看规章/.test(query)) next.kind = "部门规章";
  if (/全部类型|不限类型/.test(query)) next.kind = "全部类型";
  return next;
}
export function lexicalSearch(query: string, previous: string, filters: Filters): SearchResult {
  const context = effectiveQuery(query, previous);
  const activeFilters = suggestedFilters(query, filters);
  return { query, context, filters: activeFilters, hits: candidateHits(context, activeFilters).filter(hit => hit.score > 0).slice(0, 8), engine: "lexical", notice: "当前使用样本关键词与同义词检索。", corpusVersion };
}
