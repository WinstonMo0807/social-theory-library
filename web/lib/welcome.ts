export type WelcomeBook = { id: string; title: string; author: string; coverImage?: string; available?: boolean };
export const welcomeChapters = [
  { title: "把问题带进文献", text: "用研究问题检索相关论述，从原文节选判断哪些材料值得细读。", href: "/explore/opinions", action: "检索观点" },
  { title: "在上下文中理解观点", text: "打开对应 PDF，把节选放回前后文，读清作者的论证。", href: "/explore/original", action: "查找原文" },
  { title: "引用之前，核对出处", text: "对照原文、版本与页码，为论文和课堂核对引用。", href: "/account/citation-audits", action: "核对引文" },
  { title: "让阅读成为积累", text: "把原文、笔记与书单留在读者中心，下次从已有材料继续研究。", href: "/account", action: "进入读者中心" },
];
export const welcomeCopies = [
  {
    id: "source", label: "原文优先", title: ["让每一个观点，", "都有原文可循。"],
    lead: "以原文为起点，用观点检索找到相关论述，把判断留给阅读。",
    question: "制度如何改变人的行动？", results: "先读相关原文", reader: "回到上下文", saved: "原文与思考，一起保存",
  },
  {
    id: "question", label: "问题出发", title: ["带着问题，", "找到相关的原文。"],
    lead: "从你关心的问题进入文献，在具体段落里寻找作者的回答。",
    question: "国家如何认识社会？", results: "从节选进入原文", reader: "把原文读完整", saved: "留下材料，接着追问",
  },
  {
    id: "debate", label: "思想交锋", title: ["同一个问题，", "读见不同的解释。"],
    lead: "用观点检索找到不同论述，回到上下文，理解分歧从何而来。",
    question: "技术进步一定带来社会进步吗？", results: "比较不同论述", reader: "理解论证的差异", saved: "保存分歧，写下判断",
  },
];

export const welcomeTextDefaults = {
  "history_title": "沿着学科史，读懂社会思想",
  "history_subjects": "社会学、政治学、人类学",
  "history_scholars": "学者",
  "history_theories": "理论流派",
  "history_works": "回到代表作品",
  "philosophy_title": "回到原文，理解思想的来处。",
  "philosophy_body": "让观点有出处，让不同的解释相遇。\n在阅读与追问中，形成自己的判断。",
  "features_title": "从研究问题出发，\n把阅读做深。",
  "features_body": "找相关论述，回到原文，把材料与笔记留给下一次研究。",
  "discovery_theory_title": "沿着思想的脉络",
  "discovery_theory_body": "从学者、流派与主题，发现彼此相连的作品。",
  "discovery_issue_title": "换一个角度读世界",
  "discovery_issue_body": "跟随特别策划，把分散的阅读连成一个问题。",
  "principles_title": "理解，从有据可查开始。",
  "principle_source_title": "保留出处",
  "principle_source_body": "辨认作者、版本与页码，回到观点出现的地方。",
  "principle_context_title": "读见上下文",
  "principle_context_body": "节选是阅读的起点，前后的论述同样重要。",
  "principle_debate_title": "容纳不同解释",
  "principle_debate_body": "沿着不同学者与流派，比较他们如何提出问题。",
  "principle_judgment_title": "留下自己的判断",
  "principle_judgment_body": "让笔记与材料一起保存，思考可以继续生长。",
  "invitation_title": "给思想一点时间。",
  "invitation_body": "一本书、一段原文、一个尚未解答的问题。\n从感兴趣的地方开始，慢慢读下去。",
  "faq_title": "你可能想知道",
  "faq_read_title": "需要登录才能阅读吗？",
  "faq_read_body": "公开馆藏可以直接检索与阅读。登录后，可以在读者中心保存自己的阅读资料。",
  "faq_cite_title": "怎样核对一段引文？",
  "faq_cite_body": "从原文节选打开对应文件，查看版本、页码与前后文；也可以在读者中心使用引文核对。",
  "faq_private_title": "我的笔记和阅读资料保存在哪里？",
  "faq_private_body": "登录后在读者中心管理笔记、书单与阅读计划。私人资料按账户权限访问。",
  "closing_title": "下一本书，\n下一次理解。",
  "enter_label": "进入书库"
};
export const welcomeTextLabels: Record<keyof typeof welcomeTextDefaults, string> = {
  "history_title": "学科史演示标题",
  "history_subjects": "演示学科（以顿号分隔）",
  "history_scholars": "演示关系左侧",
  "history_theories": "演示关系右侧",
  "history_works": "演示书籍标题",
  "philosophy_title": "原文理念标题",
  "philosophy_body": "原文理念正文",
  "features_title": "功能区标题",
  "features_body": "功能区引言",
  "discovery_theory_title": "理论入口标题",
  "discovery_theory_body": "理论入口介绍",
  "discovery_issue_title": "策划入口标题",
  "discovery_issue_body": "策划入口介绍",
  "principles_title": "阅读原则标题",
  "principle_source_title": "出处原则标题",
  "principle_source_body": "出处原则正文",
  "principle_context_title": "上下文原则标题",
  "principle_context_body": "上下文原则正文",
  "principle_debate_title": "多元解释标题",
  "principle_debate_body": "多元解释正文",
  "principle_judgment_title": "个人判断标题",
  "principle_judgment_body": "个人判断正文",
  "invitation_title": "阅读邀请标题",
  "invitation_body": "阅读邀请正文",
  "faq_title": "常见问题标题",
  "faq_read_title": "阅读问题",
  "faq_read_body": "阅读回答",
  "faq_cite_title": "引文问题",
  "faq_cite_body": "引文回答",
  "faq_private_title": "私人资料问题",
  "faq_private_body": "私人资料回答",
  "closing_title": "结束标题",
  "enter_label": "进入按钮文字"
};
export type WelcomeCopy = typeof welcomeCopies[number];
export type WelcomeConfig = {
  copies?: WelcomeCopy[];
  chapters?: Array<Pick<typeof welcomeChapters[number], "title" | "text" | "action">>;
  texts?: Partial<typeof welcomeTextDefaults>;
  edition_ids?: string[] | null;
};
export function welcomeContent(config?: WelcomeConfig) {
  return { copies: config?.copies ?? welcomeCopies,
    chapters: welcomeChapters.map((chapter, index) => ({ ...chapter, ...config?.chapters?.[index] })),
    texts: { ...welcomeTextDefaults, ...config?.texts } };
}
