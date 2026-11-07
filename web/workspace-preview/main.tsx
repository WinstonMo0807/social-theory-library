import { createRoot } from "react-dom/client";
import { useEffect, useRef, useState } from "react";
import { Activity, ArrowUpRight, BookOpen, Check, ChevronDown, FileText, History, Library, MessageSquare, MoreHorizontal, Plus, RefreshCw, Search, Settings2, Sparkles, UserRound, X } from "lucide-react";
import { BrandImage } from "../components/brand-image";
import { LoadingState } from "../components/ui/loading-state";
import { ActionMenuBehavior } from "../components/ui/action-menu-behavior";
import { Dialog } from "../components/ui/dialog";
import { SystemStatusView, type StatusPayload } from "../components/system-status-center";
import { CommentReviewEmpty } from "../components/admin/curation/article-comment-review";
import "../styles/tokens/type-fonts.css";
import "../styles/layout/brand-identity.css";
import "../styles/features/workspace-polish.css";
import "./preview.css";

// Deliberately illustrative. This LAN-only build has no API proxy or credentials.
const services: StatusPayload = {
  database: { status: "healthy", vendor: "PostgreSQL", version: "16.14", migration_heads: ["目录与文件", "账户与权限", "阅读与研究"] },
  redis: { status: "healthy", reachable: true },
  celery: { status: "healthy", default_worker: "可用", ingestion_worker: "可用", beat: "可用" },
  storage: { status: "healthy", reachable: true, reason: "文件存储可连接。" },
  query_lexicon: { status: "configured", reason: "已配置检索词典。" },
  semantic: { status: "unavailable", reason: "暂时无法连接索引服务。请在服务恢复后刷新状态。" },
  embedding: { status: "not_tested", reason: "已保存模型配置，尚未收到检查结果。", model: "当前配置的语义模型", credential_configured: true },
  ai: { status: "not_configured", reason: "尚未配置 AI 服务。可在“模型与服务”中设置。" },
  web_enrichment: { status: "disabled", reason: "联网资料来源未启用。" },
  backup: { status: "not_available", reason: "暂无备份检查记录。" },
};
const sections = [
  { id: "maintenance", title: "运行维护", icon: Activity },
  { id: "files", title: "馆藏与任务", icon: Library },
  { id: "editor", title: "内容编辑", icon: FileText },
  { id: "comments", title: "评论审核", icon: MessageSquare },
  { id: "reader", title: "读者中心", icon: UserRound },
] as const;
type Section = typeof sections[number]["id"];
const fileRows = ["示例扫描件.pdf", "示例论文集.pdf", "示例研究资料.pdf"];

function App() {
  const params = new URLSearchParams(location.search);
  const [variant, setVariant] = useState(params.get("variant") === "B" ? "B" : "A");
  const [section, setSection] = useState<Section>(sections.some(s => s.id === params.get("section")) ? params.get("section") as Section : "maintenance");
  const [loading, setLoading] = useState(false);
  const [empty, setEmpty] = useState(false);
  const [query, setQuery] = useState("");
  const [modal, setModal] = useState("");
  const [commentState, setCommentState] = useState("empty");
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const page = sections.find(s => s.id === section)!;
  useEffect(() => {
    const next = new URL(location.href); next.searchParams.set("variant", variant); next.searchParams.set("section", section);
    history.replaceState(null, "", next);
  }, [variant, section]);
  useEffect(() => () => { if (timer.current) clearTimeout(timer.current); }, []);
  function reload() { setLoading(true); if (timer.current) clearTimeout(timer.current); timer.current = setTimeout(() => setLoading(false), 1800); }
  function changeSection(next: Section) { setSection(next); setLoading(false); setQuery(""); if(timer.current) clearTimeout(timer.current); }
  function More({ name }: { name: string }) { return <details data-action-menu className="proposal-more"><summary aria-label={`${name}的更多操作`}><MoreHorizontal size={19} /></summary><div data-menu-panel><button onClick={() => setModal(`${name} · 处理记录`)}><History size={16} />处理记录</button><button onClick={() => setModal(`${name} · 详情`)}><FileText size={16} />查看详情</button></div></details>; }
  return <div className="workspace-proposal" data-workspace-variant={variant}>
    <ActionMenuBehavior />
    <div className="proposal-bar"><span>内网方案 · 示例数据</span><div className="proposal-switch" role="group" aria-label="排版方案"><button aria-pressed={variant === "A"} onClick={() => setVariant("A")}>A · 清晰列表</button><button aria-pressed={variant === "B"} onClick={() => setVariant("B")}>B · 分区工作台</button></div></div>
    <div className="proposal-shell">
      <aside className="proposal-sidebar"><div className="proposal-brand"><BrandImage /></div><nav aria-label="比较页面">{sections.map(s => <button key={s.id} aria-current={section === s.id ? "page" : undefined} onClick={() => changeSection(s.id)}><s.icon size={18} /><span>{s.title}</span></button>)}</nav><a className="proposal-real" href="http://192.168.5.6:18084/home" target="_blank" rel="noreferrer">打开正式书库<ArrowUpRight size={16} /></a></aside>
      <main className="proposal-main">
        <header className="proposal-title"><div><h1>{page.title}</h1>{section === "reader" ? <span className="proposal-private">仅本人可见</span> : null}</div><button className="proposal-button" onClick={reload} disabled={loading}><RefreshCw size={16} className={loading ? "spin" : ""} />{loading ? "刷新中" : "重新加载"}</button></header>
        {section === "maintenance" && (loading ? <LoadingState>正在读取服务状态…</LoadingState> : <SystemStatusView payload={services} />)}
        {section === "files" && <><form className="proposal-search" onSubmit={e => { e.preventDefault(); reload(); }}><Search size={18} /><input aria-label="查找馆藏" placeholder="搜索书名、作者或文件名" value={query} onChange={e => setQuery(e.target.value)} /><button type="submit">搜索</button></form><div className="proposal-list-tools"><span>文件与处理</span><button aria-pressed={empty} onClick={() => setEmpty(!empty)}>{empty ? "显示示例文件" : "查看空列表"}</button></div>{loading ? <LoadingState>正在读取馆藏…</LoadingState> : empty || !fileRows.some(s => s.includes(query)) ? <div className="workspace-empty"><BookOpen size={28} /><div><h3>{query ? "未找到匹配的文件" : "暂无文件"}</h3><p>{query ? "换个关键词再试。" : "上传后，文件会显示在这里。"}</p></div></div> : <div className="proposal-file-list">{fileRows.filter(s => s.includes(query)).map((name,i) => <article key={name}><span className="proposal-file-icon"><FileText size={25} strokeWidth={1.2} /></span><div><h2>{name}</h2><span className="proposal-meta">PDF · {i+1} 个处理记录</span></div><span className="proposal-status"><Check size={14} />已完成</span><div className="proposal-row-actions"><button onClick={() => setModal(`${name} · 详情`)}>查看详情</button><More name={name} /></div></article>)}</div>}</>}
        {section === "editor" && <><div className="proposal-editor-header"><h2>新的理论条目</h2><button className="proposal-button" onClick={() => setModal("保存草稿")}>保存草稿</button></div><nav className="proposal-tabs" aria-label="条目编辑"><span>基本信息</span><strong>相关关系</strong><span>关联材料</span></nav><div className="proposal-editor-body"><div className="workspace-empty"><Plus size={26} /><div><h3>保存后即可添加关系</h3><p>先填写名称并保存草稿。</p></div></div><aside className="knowledge-object-context-panel is-empty"><Sparkles size={22} /><div><strong>预览与发布</strong><p>保存草稿后，可预览读者页面并查看发布状态。</p></div></aside></div></>}
        {section === "comments" && <section className="comment-review-panel"><header><h2>文章评论</h2><button className="proposal-button" onClick={() => setCommentState(commentState === "empty" ? "pending" : "empty")}>{commentState === "empty" ? "查看待审示例" : "查看空状态"}</button></header><p className="workspace-help">仅审核读者同意公开的署名和评论。</p><details className="workspace-note"><summary>审核范围</summary><p>账户私人资料不在审核范围内。旧版评论保留在原文章，不迁入新版。</p></details>{loading ? <LoadingState>正在读取评论…</LoadingState> : commentState === "empty" ? <CommentReviewEmpty /> : <><label className="workspace-field">审核说明<input placeholder="填写本次处理原因（选填）" /></label><article className="proposal-comment"><div className="proposal-comment-person"><span><UserRound size={20} /></span><strong>示例读者</strong><small>{commentState === "published" ? "已公开" : "待审核"}</small></div><p>能否增加与这篇文章相关的延伸阅读？</p><div className="proposal-row-actions"><button className="primary" onClick={() => setCommentState("published")} disabled={commentState === "published"}>公开评论</button><button onClick={() => setCommentState("empty")}>不公开</button></div></article></>}</section>}
        {section === "reader" && <><div className="proposal-reader-intro"><div><h2>继续上一次研究</h2><p>阅读、笔记和研究，保存在一起。</p></div><button className="proposal-button primary" onClick={() => setModal("新建研究")}><Plus size={17} />新建研究</button></div><nav className="proposal-tabs" aria-label="个人资料"><strong>我的研究</strong><span>笔记</span><span>阅读计划</span><span>书单</span></nav>{loading ? <LoadingState>正在读取你的资料…</LoadingState> : <div className="proposal-research-list">{["技术进步与社会公平", "从地方知识理解社会"].map((name,i)=><article key={name}><div className="proposal-research-heading"><FileText size={21}/><More name={name}/></div><h2>{name}</h2><p>{i+2} 条笔记 · {i+1} 次检索</p><button onClick={()=>setModal(name)}>继续研究 <ArrowUpRight size={16}/></button></article>)}</div>}</>}
        <footer className="proposal-footnote">方案中的记录仅用于比较排版，不读写账户、馆藏或任务。</footer>
      </main>
    </div>
    <Dialog open={Boolean(modal)} onRequestClose={() => setModal("")} className="proposal-dialog" aria-labelledby="proposal-dialog-title"><div className="proposal-dialog-body"><header><h2 id="proposal-dialog-title">{modal}</h2><button onClick={() => setModal("")} aria-label="关闭"><X size={20}/></button></header>{modal.includes("处理记录") ? <ol className="proposal-history"><li><Check size={16}/><div><strong>文件已处理</strong><p>示例记录 · 本轮处理完成</p></div></li><li><FileText size={16}/><div><strong>文件已接收</strong><p>示例记录 · 等待处理</p></div></li></ol> : <div className="workspace-empty"><FileText size={26}/><div><h3>{modal === "新建研究" ? "为研究命名" : "内容预览"}</h3>{modal === "新建研究" ? <input aria-label="研究名称" placeholder="输入你关心的问题"/> : <p>这是内网交互示例，不会修改正式内容。</p>}</div></div>}<footer><button className="proposal-button primary" onClick={()=>setModal("")}>返回</button></footer></div></Dialog>
  </div>;
}

createRoot(document.getElementById("root")!).render(<App />);
