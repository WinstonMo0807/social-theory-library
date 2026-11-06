/** Versioned help describes existing product behavior, never a sample collection. */
export const supportSections = [
  ["guide", "使用指南"], ["content", "内容说明"], ["faq", "常见问题"],
  ["source", "来源纠错"], ["feedback", "使用反馈"], ["updates", "公告与更新"],
] as const;
export type SupportSection = typeof supportSections[number][0];
export function supportSection(value: string | undefined): SupportSection {
  return supportSections.find(([key]) => key === value)?.[0] ?? "guide";
}
export type HelpArticle = { title: string; intro: string; steps: { id: string; title: string; body: string }[] };
export const helpArticles: Record<string, HelpArticle> = {
  terms: { title: "使用条款", intro: "开放原则、资源来源与使用边界。", steps: [] },
  search: { title: "搜索资料", intro: "登录或注册后，从书名、作者、概念或问题开始搜索。", steps: [
    { id: "query", title: "输入检索内容", body: "在搜索框输入书名、作者、概念或你记得的原文。先用明确词语检索，再根据结果调整范围。热门搜索来自公开汇总，不代表馆藏一定覆盖该问题。" },
    { id: "scope", title: "选择结果范围", body: "探索页分别提供馆藏、观点、原文证据与提问入口。需要找一本书时先看馆藏；需要比较论述时查看观点或原文证据。" },
    { id: "verify", title: "回到完整原文", body: "摘要和匹配段落是阅读入口。打开原文，核对作者、版本、PDF 页码和上下文，再判断结果是否回答了你的问题。" },
    { id: "empty", title: "没有找到时", body: "尝试更短的关键词、常见译名或作者名。空结果也可能表示当前公开馆藏尚未覆盖，不能据此断言文献或观点不存在。" },
  ] },
  reading: { title: "阅读文献", intro: "登录或注册后，即可阅读和下载文献。", steps: [
    { id: "open", title: "打开原文", body: "在馆藏详情或检索结果点击阅读。可访问的阅读文件在 Reader 中打开；来源不可用时，先查看页面提示，不用其他版本替代当前来源。" },
    { id: "navigate", title: "使用目录与页码", body: "目录节点定位到当前文件的实际页面。PDF 页序包含封面等页面，可能与书页上印出的页码不同。双页扫描仍只有一个 PDF 物理页。" },
    { id: "search", title: "在书内查找", body: "书内搜索依赖当前可用的解析或 OCR 文字。扫描图像仍是核对依据；未识别内容不等于原书没有该文字。" },
    { id: "notes", title: "保存私人记录", body: "登录后可以保存阅读进度、书签、划线和笔记。" },
  ] },
  citation: { title: "查找原文与引用", intro: "从检索结果回到原文，再复制所需格式。", steps: [
    { id: "open", title: "打开原文", body: "在搜索结果或书目信息页，点击“阅读”进入图书的正文页面。" },
    { id: "pages", title: "核对页码", body: "在阅读页面底部或右上角，确认当前的 PDF 页码与纸本页码，确保引用位置准确。" },
    { id: "copy", title: "复制引用", body: "点击“引用”按钮，选择所需的引用格式，核对书目信息与页码，点击“复制”即可。" },
    { id: "mismatch", title: "如遇页码不符", body: "请核对版本或提交纠错。" },
  ] },
  account: { title: "账户与隐私", intro: "登录或注册后，即可阅读、下载和使用探索功能。", steps: [
    { id: "public", title: "浏览网页", body: "访客可以浏览书目、学者、理论流派、主题和特别策划。阅读 PDF、下载及探索功能请先登录或注册。" },
    { id: "private", title: "私人资料", body: "阅读记录、笔记、研究会话和个人上传资料按账户隔离。工作人员身份不会自动获得读取私人正文的权限。" },
    { id: "memory", title: "明确笔记用途", body: "研究过程中形成的候选笔记仍需本人确认。保存笔记与授权后续使用是不同操作，撤销授权不会把私人内容变成公开资料。" },
    { id: "manage", title: "管理个人资料", body: "在读者中心的隐私与资料页查看可导出、删除及撤销的范围。先查看具体影响，再确认不可恢复的操作。反馈中的邮箱是可选的，请勿附上密码、登录令牌或私人稿件正文。" },
  ] },
  source: { title: "来源与版本", intro: "区分原始页面、识别文字与编者说明，核对实际可访问的版本。", steps: [
    { id: "identity", title: "确认来源身份", body: "作品、出版版本和数字文件分别记录。相同书名不表示是同一版本，旧引用也不会自动改写为新文件。" },
    { id: "text", title: "核对识别文字", body: "OCR 和检索文字可能有遗漏、顺序错误或误字。正式引用请回看原始页面；机器建议不等于人工确认。" },
    { id: "unavailable", title: "遇到来源不可用", body: "以 Reader 或来源页面当次返回的状态为准。访问失败不代表文件已永久删除。可重新读取，或提交该公开页面的来源纠错。" },
    { id: "report", title: "提供可核对的位置", body: "说明作品或文件、PDF 页码、看到的内容和预期内容。仅关联公开页面；不要把私人笔记、签名下载地址或账户页面粘贴到反馈中。" },
  ] },
};
export const supportFaqs = [
  { id: "reliable", category: "search", question: "如何判断内容或来源是否可靠？", answer: "先查看作品、出版版本和来源信息，再打开原文核对上下文。检索摘要、OCR 文字与机器生成的候选关系不能替代原文，也不自动成为作者本人的结论。", article: "source" },
  { id: "page", category: "citation", question: "印刷页码和 PDF 页码为什么不同？", answer: "PDF 页序可能包括封面、目录等前置页，扫描件也可能一页包含两个印刷页。引用时保留 PDF 物理页，并核对书页上真实的印刷页码；没有可靠映射时不会推测。", article: "citation" },
  { id: "unchecked", category: "citation", question: "可以引用尚未核实的内容吗？", answer: "可以把检索结果作为继续阅读的线索。正式引用前应自行核对可访问的原文、版本与页码。无法核实的内容应明确其限制，不将摘要改写为作者原话。", article: "citation" },
  { id: "missing", category: "search", question: "遇到缺失页面或来源失效怎么办？", answer: "先重新读取当前来源并确认网络状态。如果仍然不可用，可以提交来源纠错并附上公开页面位置。不要用另一文件的页码替代当前引用。", article: "source" },
  { id: "declare", category: "citation", question: "如何提交来源纠错？", answer: "进入提交反馈，选择内容错误，说明作品、文件版本、PDF 页码和问题。关联页面与联系邮箱均可选择不提供。", article: "source" },
  { id: "login", category: "account", question: "阅读需要登录吗？", answer: "需要。登录或注册后，即可阅读 PDF、下载和使用探索功能。", article: "account" },
  { id: "empty", category: "search", question: "找不到想要的书怎么办？", answer: "尝试作者名、原文书名或不同译名，并检查检索范围。无结果可能表示当前公开馆藏没有收录；可以通过反馈提出内容建议。", article: "search" },
  { id: "contact", category: "account", question: "我还有其他问题，如何联系？", answer: "可以直接提交使用反馈。邮箱为可选字段，不填写也可以提交；请只提供处理该问题所需的信息。", article: "account" },
] as const;
