export type IdentityProfile = Record<string, string | number | null>;
export type ProfileField = { key: string; label: string; number?: boolean; date?: boolean; multiline?: boolean; options?: Record<string, string>; max?: number };
export const profileFields: Record<string, ProfileField[]> = {
  organization: [
    { key: "organization_type", label: "组织类型", options: { university: "高校", research_institute: "研究机构", association: "学会或协会", government: "政府机构", archive: "档案或收藏机构", other: "其他机构" } },
    { key: "country", label: "国家或地区", max: 120 }, { key: "original_name", label: "原文名称", max: 300 },
  ],
  event: [
    { key: "event_type", label: "事件类型", options: { birth: "人物出生", death: "人物去世", appointment: "任职任教", scholar: "学者", publication: "重要发表", concept_proposed: "理论概念提出", school_formation: "学派形成", debate: "争论", institution: "机构", theoretical_turn: "理论转向", translation: "重要译介", china_reception: "进入中国学界", institutionalization: "学科制度化", formation: "形成", development: "发展" } },
    { key: "start_year", label: "起始年份", number: true }, { key: "end_year", label: "结束年份", number: true },
    { key: "start_date", label: "开始日期（有确切记录时）", date: true }, { key: "end_date", label: "结束日期（有确切记录时）", date: true },
    { key: "date_label", label: "日期说明", max: 120 },
    { key: "date_precision", label: "日期精度", options: { unknown: "精度未确认", year: "确切年份", approximate: "约年", range: "时间区间", month: "月份", day: "日期" } },
    { key: "source", label: "事件出处", max: 1000, multiline: true },
  ],
  research_object: [
    { key: "object_kind", label: "对象类型", options: { community: "社区或群体", population: "人群", institution: "制度", process: "社会过程", practice: "实践", place: "地区", other: "其他研究对象" } },
    { key: "geographic_scope", label: "地域范围" }, { key: "temporal_scope", label: "时期范围" },
    { key: "population", label: "人群范围" }, { key: "unit_of_analysis", label: "分析单位" },
  ],
};
