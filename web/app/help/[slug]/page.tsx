import Link from "next/link";
import { ArrowLeft, ArrowRight } from "lucide-react";
import { notFound } from "next/navigation";
import { SiteFooter } from "@/components/site-footer";
const articles: Record<string, { title: string; intro: string; sections: Array<[string, string]> }> = {
  search: { title: "搜索资料", intro: "从一个问题或一段记得的原文开始，逐步缩小到可核对的来源。", sections: [["先看结果类型", "馆藏检索返回作品与版本；观点检索从问题出发组织相关段落；原文证据页用于跨作品比较。"], ["再回到原文", "检索结果只是一条入口。打开 Reader 后，核对页码、版本和完整段落，再决定是否保存或引用。"]] },
  reading: { title: "阅读文献", intro: "Reader 保留目录、连续阅读、书内搜索与页码定位，帮助你回到论述所在的上下文。", sections: [["目录和页码", "目录节点来自当前阅读文件的结构化结果，页码以 PDF 页序为准；纸面页码可能不同。"], ["私人记录", "登录后才会保存阅读进度、书签、划线和笔记，这些内容默认只对本人可见。"]] },
  citation: { title: "引用与导出", intro: "引用信息必须回到当前可访问的原文版本核对，系统不会把检索摘要当作作者原话。", sections: [["定位信息", "复制引用时保留作品、版本、PDF 页码和可用的证据定位；来源撤回或版本变化后，系统会提示重新核对。"], ["引文核验", "需要检查个人文稿时，从读者中心进入引文核验，上传和解析状态会单独显示。"]] },
  account: { title: "账户与隐私", intro: "阅读记录、笔记和研究会话属于你的私人资料。", sections: [["私人边界", "只有当前账户可以读取自己的研究项目、轮次、计划和记忆；工作人员身份不会自动扩大访问范围。"], ["删除与撤销", "删除或撤销授权后，派生的私人记录不会继续出现在研究工作区。"]] },
  source: { title: "来源与版本", intro: "书库的每个可引用结果都对应正式作品、出版版本和阅读文件。", sections: [["OCR 结果", "OCR 文字用于检索和定位，扫描页仍是最终核对依据。识别失败或部分完成会明确显示状态。"], ["版本变化", "新版本发布后，旧版本的证据身份不会自动改写；需要重新选择可访问的来源。"]] },
};
export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }) { const { slug } = await params; return { title: articles[slug]?.title || "帮助文章" }; }
export default async function HelpArticlePage({ params }: { params: Promise<{ slug: string }> }) { const { slug } = await params; const article = articles[slug]; if (!article) notFound(); return <><div className="stl4-support-page stl4-support-article"><nav className="stl4-support-breadcrumb"><Link href="/">首页</Link><span>/</span><Link href="/help">使用帮助与反馈</Link><span>/</span><strong>{article.title}</strong></nav><header><p className="stl4-support-kicker">使用帮助</p><h1>{article.title}</h1><p>{article.intro}</p></header><div className="stl4-support-article-grid">{article.sections.map(([title, body]) => <section key={title}><h2>{title}</h2><p>{body}</p></section>)}</div><Link className="stl4-support-back" href="/help"><ArrowLeft size={15} />返回帮助首页 <ArrowRight size={15} /></Link></div><SiteFooter /></>; }
