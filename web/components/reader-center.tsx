"use client";

import Link from "next/link";
import { ReaderBooklists } from "./research/reader-booklists";
import { CollectionLink } from "@/components/collection-link";
import {
  ArrowRight,
  Bookmark,
  BookOpen,
  Clock3,
  Download,
  FileText,
  Heart,
  Highlighter,
  List,
  LogOut,
  LockKeyhole,
  Mail,
  RefreshCw,
  Settings,
  StickyNote,
} from "lucide-react";
import { FormEvent, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  apiRequest,
  subscribeToSessionChanges,
  classifyClientError,
  clearStoredSession,
  getServerSessionCredential,
  isUnauthenticatedError,
  logoutCurrentSession,
  type ClientErrorCategory,
} from "@/lib/api";
import { adaptApiWork as adaptWork } from "@/lib/public-data-adapters";
import type { ApiWork } from "@/lib/api/public-catalog";
import { readAllPages } from "@/lib/api/read-all-pages";
import { withPrivateOwner } from "@/lib/api/private-owner";
import { useSessionBootstrap } from "@/lib/use-session-bootstrap";
import { useActionGuard } from "@/lib/use-action-guard";
import { ActionButton, AsyncStatus, type ActionState } from "./action-feedback";
import { BookCard, BookCover, SectionHeading } from "./ui";
import { DisplayPreferences } from "./display-preferences";
import { ReaderOverview } from "./research/reader-overview";
import { ResearchCenterNav } from "./research/research-center-nav";
import { SaveTopicButton, useTopicSaveCommands } from "./save-topic-button";

const tabs = [
  [BookOpen, "概览"],
  [Heart, "收藏"],
  [Bookmark, "书签"],
  [Highlighter, "高亮与划线"],
  [StickyNote, "笔记"],
  [List, "书单"],
  [Clock3, "阅读历史"],
  [Mail, "荐书投稿"],
  [Settings, "账户设置"],
] as const;

type ProgressSnapshot = {
  id: string;
  asset: string;
  current_page: number;
  progress_ratio: number;
  updated_at: string;
};
type ProgressRow = ProgressSnapshot & { work: ApiWork };
type SavedRow = {
  id: string;
  work_data: ApiWork | null;
  reading_progress: ProgressSnapshot | null;
  created_at: string;
};
type SavedTopicRow = {
  id: string;
  topic: string;
  name: string;
  slug: string;
  description: string;
  created_at: string;
};
type AnnotationRow = {
  id: string;
  asset: string;
  work: ApiWork;
  kind: string;
  quote: string;
  body_text: string;
  selector: { page_index?: number };
  created_at: string;
};
type BookmarkRow = {
  id: string;
  asset: string;
  work: ApiWork;
  label: string;
  page: string;
  page_index: number;
  created_at: string;
};
type ReadingListRow = {
  id: string;
  title: string;
  description: string;
  items: { id: string; work: string; title: string }[];
};
type HistoryRow = {
  id: string;
  asset: string;
  work: ApiWork;
  page_index: number;
  session_seconds: number;
  created_at: string;
};
type NoteGroupRow = {
  asset: string;
  work: ApiWork;
  note_count: number;
  latest_at: string;
  previews: AnnotationRow[];
};
type PlanItem = {
  id?: string;
  title?: string;
  status?: string;
  note?: string;
  reader_url?: string | null;
  available?: boolean;
};
type PlanRow = {
  id: string;
  status?: string;
  data?: { goal?: string; items?: PlanItem[]; generation_status?: string };
  updated_at: string;
};

type ReaderData = {
  progress: ProgressRow[];
  saved: SavedRow[];
  savedTopics: SavedTopicRow[];
  annotations: AnnotationRow[];
  bookmarks: BookmarkRow[];
  lists: ReadingListRow[];
  history: HistoryRow[];
  plans: PlanRow[];
};

type ReaderResourceKey = keyof ReaderData | "noteGroups";
type ReaderResourceError = {
  label: string;
  message: string;
  category: ClientErrorCategory;
};

const emptyData: ReaderData = {
  progress: [],
  saved: [],
  savedTopics: [],
  annotations: [],
  bookmarks: [],
  lists: [],
  history: [],
  plans: [],
};

export function ReaderCenter() {
  const bootstrap = useSessionBootstrap();
  const params = useSearchParams();
  const key = bootstrap.state.status === "authenticated" ? String(bootstrap.state.user?.id) : bootstrap.state.status;
  return params.get("section") === "lists" ? <ReaderBooklists /> : <ReaderCenterWorkspace key={key} bootstrap={bootstrap} />;
}

function ReaderCenterWorkspace({ bootstrap }: { bootstrap: ReturnType<typeof useSessionBootstrap> }) {
  const searchParams = useSearchParams();
  const router = useRouter();
  const { state: session, retry: retrySession } = bootstrap;
  const requests = useRef<AbortController | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    requests.current = controller;
    const unsubscribe = subscribeToSessionChanges(() => controller.abort());
    return () => { controller.abort(); unsubscribe(); };
  }, []);
  async function privateRequest<T>(path: string, options: RequestInit = {}, credential?: string | null): Promise<T> {
    const owner = session.user?.id;
    const controller = requests.current;
    if (session.status !== "authenticated" || owner === undefined || !controller || controller.signal.aborted) throw new Error("登录账户需要重新确认。");
    const signal = AbortSignal.any([controller.signal, AbortSignal.timeout(30000), ...(options.signal ? [options.signal] : [])]);
    const headers = new Headers(options.headers);
    headers.set("X-Reader-Owner", String(owner));
    return withPrivateOwner(String(owner), () => apiRequest<T>(path, { ...options, headers, signal, cache: "no-store" }, credential), signal);
  }
  const topicCommands = useTopicSaveCommands(session.status === "authenticated" && session.user ? String(session.user.id) : null);
  const section = searchParams.get("section");
  const [selectedTab, selectTab] = useState<{ section: string | null; label: string } | null>(null);
  const active = selectedTab?.section === section ? selectedTab.label : section === "lists" ? "书单" : section === "settings" ? "账户设置" : section === "history" ? "阅读历史" : section === "saved" ? "收藏" : "概览";
  const setActive = (label: string) => { if (label === "书单") router.push("/account/collections"); else selectTab({ section, label }); };
  const [profile, setProfile] = useState<{ display_name: string; email: string } | null>(null);
  const [readerData, setReaderData] = useState<ReaderData>(emptyData);
  const [noteGroups, setNoteGroups] = useState<NoteGroupRow[]>([]);
  const [resourcesLoading, setResourcesLoading] = useState(true);
  const [dataOwnerId, setDataOwnerId] = useState<number | null>(null);
  const [resourceErrors, setResourceErrors] = useState<Partial<Record<ReaderResourceKey, ReaderResourceError>>>({});
  const [resourceAttempt, setResourceAttempt] = useState(0);
  const [submissionTitle, setSubmissionTitle] = useState("");
  const [submissionNote, setSubmissionNote] = useState("");
  const [message, setMessage] = useState("");
  const [messageState, setMessageState] = useState<ActionState>("idle");
  const [profileName, setProfileName] = useState("");
  const { pendingAction, startAction, finishAction } = useActionGuard();

  function beginReaderAction(key: string, pendingMessage: string) {
    if (!startAction(key)) return false;
    setMessage(pendingMessage);
    setMessageState("pending");
    return true;
  }

  function finishReaderAction(key: string, state: Exclude<ActionState, "idle" | "pending">, nextMessage: string) {
    setMessage(nextMessage);
    setMessageState(state);
    finishAction(key);
  }

  useEffect(() => {
    if (session.status === "unauthenticated") {
      window.location.replace("/login?next=/account");
    }
  }, [session.status]);

  useEffect(() => {
    let mounted = true;
    Promise.resolve().then(() => {
      if (!mounted) return;
      if (session.status !== "authenticated" || !session.user) {
        setProfile(null);
        return;
      }
      setProfile({
        display_name: session.user.display_name,
        email: session.user.email,
      });
      setProfileName(session.user.display_name);
    });
    return () => {
      mounted = false;
    };
  }, [session.status, session.user]);

  useEffect(() => {
    if (active === "概览" || session.status !== "authenticated" || !session.user) return;
    const credential = getServerSessionCredential();
    if (!credential) return;
    const owner = String(session.user.id);
    const controller = new AbortController();
    let mounted = true;
    Promise.resolve().then(() => {
      if (!mounted) return;
      setResourcesLoading(true);
      setResourceErrors({});
    });

    const requests: Promise<{ key: ReaderResourceKey; label: string; results: unknown[] }>[] = [
      readAllPages<ProgressRow>("/reading/progress/", credential, controller.signal, owner)
        .then((results) => ({ key: "progress", label: "阅读进度", results })),
      readAllPages<SavedRow>("/reading/saved/", credential, controller.signal, owner)
        .then((results) => ({ key: "saved", label: "文献收藏", results })),
      readAllPages<SavedTopicRow>("/reading/saved-topics/", credential, controller.signal, owner)
        .then((results) => ({ key: "savedTopics", label: "主题收藏", results })),
      readAllPages<AnnotationRow>("/reading/annotations/", credential, controller.signal, owner)
        .then((results) => ({ key: "annotations", label: "高亮与笔记", results })),
      readAllPages<NoteGroupRow>("/reading/annotations/note-groups/", credential, controller.signal, owner)
        .then((results) => ({ key: "noteGroups", label: "作品笔记", results })),
      readAllPages<BookmarkRow>("/reading/bookmarks/", credential, controller.signal, owner)
        .then((results) => ({ key: "bookmarks", label: "书签", results })),
      readAllPages<ReadingListRow>("/reading/lists/", credential, controller.signal, owner)
        .then((results) => ({ key: "lists", label: "书单", results })),
      readAllPages<HistoryRow>("/reading/history/", credential, controller.signal, owner)
        .then((results) => ({ key: "history", label: "阅读历史", results })),
      readAllPages<PlanRow>("/reading/reading-plans/", credential, controller.signal, owner)
        .then((results) => ({ key: "plans", label: "阅读计划", results })),
    ];

    Promise.allSettled(requests).then((results) => {
      if (!mounted) return;
      const nextData: ReaderData = {
        progress: [],
        saved: [],
        savedTopics: [],
        annotations: [],
        bookmarks: [],
        lists: [],
        history: [],
        plans: [],
      };
      let nextNoteGroups: NoteGroupRow[] = [];
      const nextErrors: Partial<Record<ReaderResourceKey, ReaderResourceError>> = {};
      let sessionExpired = false;

      results.forEach((result, index) => {
        if (result.status === "fulfilled") {
          const { key, results: rows } = result.value;
          switch (key) {
            case "progress": nextData.progress = rows as ProgressRow[]; break;
            case "saved": nextData.saved = rows as SavedRow[]; break;
            case "savedTopics": nextData.savedTopics = rows as SavedTopicRow[]; break;
            case "annotations": nextData.annotations = rows as AnnotationRow[]; break;
            case "noteGroups": nextNoteGroups = rows as NoteGroupRow[]; break;
            case "bookmarks": nextData.bookmarks = rows as BookmarkRow[]; break;
            case "lists": nextData.lists = rows as ReadingListRow[]; break;
            case "history": nextData.history = rows as HistoryRow[]; break;
            case "plans": nextData.plans = rows as PlanRow[]; break;
          }
          return;
        }
        if (isUnauthenticatedError(result.reason)) {
          sessionExpired = true;
          return;
        }
        const key = ["progress", "saved", "savedTopics", "annotations", "noteGroups", "bookmarks", "lists", "history", "plans"][index] as ReaderResourceKey;
        const labels = ["阅读进度", "文献收藏", "主题收藏", "高亮与笔记", "作品笔记", "书签", "书单", "阅读历史", "阅读计划"];
        nextErrors[key] = {
          label: labels[index],
          message: result.reason instanceof Error ? result.reason.message : "内容暂时无法读取。",
          category: classifyClientError(result.reason, "resource"),
        };
      });

      if (sessionExpired) {
        clearStoredSession();
        window.location.replace("/login?next=/account");
        return;
      }
      setReaderData(nextData);
      setDataOwnerId(session.user?.id ?? null);
      setNoteGroups(nextNoteGroups);
      setResourceErrors(nextErrors);
    }).finally(() => {
      if (mounted) setResourcesLoading(false);
    });

    return () => {
      mounted = false;
      controller.abort();
    };
  }, [active, resourceAttempt, session.status, session.user]);


  async function logout() {
    const actionKey = "logout";
    if (!beginReaderAction(actionKey, "正在退出登录……")) return;
    try {
      await logoutCurrentSession(session.user ? String(session.user.id) : undefined);
      finishReaderAction(actionKey, "success", "已退出登录，正在返回书库首页……");
      router.push("/");
    } catch (error) {
      finishReaderAction(actionKey, "error", error instanceof Error ? error.message : "退出登录失败。");
    }
  }

  async function submitRecommendation(event: FormEvent) {
    event.preventDefault();
    const token = getServerSessionCredential();
    if (!token) return;
    const actionKey = "submit-recommendation";
    if (!beginReaderAction(actionKey, "正在准备投稿邮件……")) return;
    try {
      const result = await privateRequest<{ detail: string; mailto: string; email: string }>(
        "/reading/submit/",
        {
          method: "POST",
          body: JSON.stringify({ title: submissionTitle, note: submissionNote }),
        },
        token,
      );
      finishReaderAction(actionKey, "success", result.detail);
      if (!result.mailto.startsWith("mailto:")) throw new Error("投稿邮件链接无效，请稍后重试。");
      window.location.assign(result.mailto);
    } catch (error) {
      finishReaderAction(actionKey, "error", error instanceof Error ? error.message : "投稿邮件发送失败。");
    }
  }

  async function exportReaderData() {
    const token = getServerSessionCredential();
    if (!token || session.status !== "authenticated" || !session.user) return;
    const actionKey = "export-reader-data";
    if (!beginReaderAction(actionKey, "正在导出个人数据……")) return;
    try {
      const payload = await privateRequest<Record<string, unknown>>("/reading/export/", { cache: "no-store" }, token);
      const blob = new Blob([JSON.stringify(payload, null, 2)], {
        type: "application/json;charset=utf-8",
      });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `社会理论书库-个人数据-${new Date().toISOString().slice(0, 10)}.json`;
      link.click();
      URL.revokeObjectURL(url);
      finishReaderAction(actionKey, "success", "个人数据文件已准备，已开始下载。");
    } catch (error) {
      finishReaderAction(actionKey, "error", error instanceof Error ? error.message : "个人数据导出失败。");
    }
  }

  async function deleteRecord(kind: "saved" | "annotations" | "bookmarks", id: string) {
    const token = getServerSessionCredential();
    const owner = session.user?.id;
    if (!token || owner === undefined) return;
    if (!window.confirm("确定删除这条个人阅读记录吗？")) return;
    const actionKey = `delete-record:${kind}:${id}`;
    if (!beginReaderAction(actionKey, "正在删除个人阅读记录……")) return;
    try {
      await privateRequest(`/reading/${kind}/${id}/`, { method: "DELETE" }, token);
      setReaderData((current) => ({
        ...current,
        saved: kind === "saved" ? current.saved.filter((item) => item.id !== id) : current.saved,
        annotations: kind === "annotations" ? current.annotations.filter((item) => item.id !== id) : current.annotations,
        bookmarks: kind === "bookmarks" ? current.bookmarks.filter((item) => item.id !== id) : current.bookmarks,
      }));
      if (kind === "annotations") {
        const groups = await readAllPages<NoteGroupRow>(
          "/reading/annotations/note-groups/",
          token,
          requests.current?.signal,
          String(owner),
        );
        setNoteGroups(groups);
      }
      finishReaderAction(actionKey, "success", "个人阅读记录已删除。");
    } catch (error) {
      finishReaderAction(actionKey, "error", error instanceof Error ? error.message : "删除失败。");
    }
  }

  async function updateProfile(event: FormEvent) {
    event.preventDefault();
    const token = getServerSessionCredential();
    if (!token) return;
    const actionKey = "update-profile";
    if (!beginReaderAction(actionKey, "正在保存显示名称……")) return;
    try {
      const updated = await privateRequest<{ display_name: string; email: string }>(
        "/auth/me/",
        { method: "PATCH", body: JSON.stringify({ display_name: profileName }) },
        token,
      );
      setProfile(updated);
      finishReaderAction(actionKey, "success", "显示名称已更新。");
    } catch (error) {
      finishReaderAction(actionKey, "error", error instanceof Error ? error.message : "账户更新失败。");
    }
  }

  if (["unknown", "loading", "unauthenticated"].includes(session.status)) {
    return (
      <div className="account-loading">
        {session.status === "unauthenticated" ? "登录已过期，正在转到登录页面……" : "正在验证登录状态……"}
      </div>
    );
  }

  if (session.status === "forbidden") {
    return (
      <div className="account-loading" data-error-category={session.errorCategory}>
        <strong>当前账户不能访问读者中心</strong>
        <p>{session.message}</p>
        <Link href="/">返回书库首页</Link>
      </div>
    );
  }

  if (session.status === "temporary_error") {
    return (
      <div className="account-loading" data-error-category={session.errorCategory}>
        <strong>认证服务暂时不可用</strong>
        <p>{session.message}</p>
        <button type="button" onClick={retrySession}><RefreshCw size={15} />保留会话并重试</button>
      </div>
    );
  }

  if (!profile || (active !== "概览" && dataOwnerId !== session.user?.id)) {
    return <div className="account-loading">正在读取账户资料……</div>;
  }

  const user = profile;

  return (
    <div className="reader-center">
      <div className="account-content">
        <header className="reader-center-heading">
          <div><p className="eyebrow">读者中心</p><h1>读者中心 <small className="reader-center-private"><LockKeyhole size={13} />仅本人可见</small></h1><p>继续阅读，整理笔记与研究。</p></div>
          <div className="reader-center-heading-actions">
            <div className="reader-center-create-links" aria-label="创建资料">
              <Link href="/explore/opinions">＋ 新建研究</Link>
              <Link href="/explore/original">新建笔记</Link>
              <Link href="/account/plans">创建计划</Link>
            </div>
            <div className="reader-center-user"><span>{user.display_name}</span><small>{user.email}</small><ActionButton type="button" state={pendingAction === "logout" ? "pending" : "idle"} pendingLabel="正在退出" disabled={Boolean(pendingAction) && pendingAction !== "logout"} onClick={() => void logout()}><LogOut size={14} /> 退出</ActionButton></div>
          </div>
        </header>
        {active !== "概览" ? <ResearchCenterNav active={active === "书单" ? "lists" : undefined} counts={{ notes: resourceErrors.noteGroups ? undefined : noteGroups.length, plans: resourceErrors.plans ? undefined : readerData.plans.length, lists: resourceErrors.lists ? undefined : readerData.lists.length }} /> : null}
        <details className="reader-legacy-nav"><summary>更多资料与账户操作</summary><nav aria-label="更多读者资料">{tabs.map(([Icon, label]) => <button className={active === label ? "active" : ""} type="button" key={label} onClick={() => setActive(label)}><Icon size={15} />{label}</button>)}</nav></details>
        {Array.from(topicCommands.memory.current.entries()).filter(([id, operation]) => operation.owner === String(session.user?.id) && (active !== "收藏" || !readerData.savedTopics.some(row => row.topic === id))).map(([id]) => <section key={id} className="form-message"><p>有一项主题收藏操作尚待核对，原请求与期望版本仍保留。</p><SaveTopicButton topicId={id} commands={topicCommands} onChange={() => setResourceAttempt(value => value + 1)} /></section>)}

        {active !== "概览" && resourcesLoading ? <p className="form-message" role="status">正在读取个人阅读资料……</p> : null}
        {active !== "概览" && Object.keys(resourceErrors).length ? (
          <section className="form-message error" role="status" data-error-category="resource_error">
            <strong>部分内容暂时无法加载</strong>
            <ul>
              {Object.entries(resourceErrors).map(([key, error]) => (
                <li key={key} data-error-category={error?.category}>{error?.label}：{error?.message}</li>
              ))}
            </ul>
            <button type="button" onClick={() => setResourceAttempt((value) => value + 1)}>
              <RefreshCw size={15} />重试未完成的内容
            </button>
          </section>
        ) : null}

        {active === "概览" ? <ReaderOverview ownerId={String(session.user!.id)} /> : null}

        {active === "收藏" ? (
          <DataPanel title="收藏">
            {readerData.saved.map((saved) => {
              const work = saved.work_data ? adaptWork(saved.work_data) : null;
              const progress = work ? saved.reading_progress : null;
              return (
                <div className="reader-saved-row" key={saved.id}>
                  {work ? <BookCard work={work} dense /> : <p>来源暂不可用。收藏记录保留，可由你移除。</p>}
                  <span className="reader-saved-actions">
                    {progress ? (
                      <CollectionLink href={`/reader/${progress.asset}?page=${progress.current_page}`}>
                        第 {progress.current_page} 页继续 <ArrowRight size={14} />
                      </CollectionLink>
                    ) : null}
                    <ActionButton type="button" state={pendingAction === `delete-record:saved:${saved.id}` ? "pending" : "idle"} pendingLabel="移除中" disabled={Boolean(pendingAction) && pendingAction !== `delete-record:saved:${saved.id}`} onClick={() => void deleteRecord("saved", saved.id)}>移除收藏</ActionButton>
                  </span>
                </div>
              );
            })}
            {readerData.savedTopics.map((topic) => (
              <article className="reader-data-row" key={topic.id}>
                <Bookmark size={17} />
                <div><strong>{topic.name}</strong><p>{topic.description || "馆藏主题"}</p></div>
                <span className="reader-data-actions">
                  {topic.slug ? <Link href={`/topics/${topic.slug}`}>打开 <ArrowRight size={14} /></Link> : <span>来源当前不可用</span>}
                  <SaveTopicButton topicId={topic.topic} commands={topicCommands} onChange={saved => { if (!saved) setReaderData(current => ({ ...current, savedTopics: current.savedTopics.filter(item => item.id !== topic.id) })); }} />
                </span>
              </article>
            ))}
            {!readerData.saved.length && !readerData.savedTopics.length ? <p className="empty-state">你还没有收藏文献或主题。</p> : null}
          </DataPanel>
        ) : null}

        {active === "书签" ? (
          <DataPanel title="书签">
            {readerData.bookmarks.map((item) => (
              <article className="reader-data-row" key={item.id}>
                <Bookmark size={17} />
                <div><strong>{adaptWork(item.work).title}</strong><p>{item.label || "页面书签"}</p></div>
                <span className="reader-data-actions"><CollectionLink href={`/reader/${item.asset}?page=${item.page_index}`}>打开 <ArrowRight size={14} /></CollectionLink><ActionButton type="button" state={pendingAction === `delete-record:bookmarks:${item.id}` ? "pending" : "idle"} pendingLabel="删除中" disabled={Boolean(pendingAction) && pendingAction !== `delete-record:bookmarks:${item.id}`} onClick={() => void deleteRecord("bookmarks", item.id)}>删除</ActionButton></span>
              </article>
            ))}
            {!readerData.bookmarks.length ? <p className="empty-state">你还没有保存书签。</p> : null}
          </DataPanel>
        ) : null}

        {active === "高亮与划线" ? (
          <DataPanel title="高亮与划线">
            {readerData.annotations
              .filter((item) => item.kind !== "note")
              .map((item) => (
                <article className="reader-data-row" key={item.id}>
                  <Highlighter size={17} />
                  <div><strong>{adaptWork(item.work).title}</strong><blockquote>{item.quote || "未保存引文"}</blockquote>{item.body_text ? <p>{item.body_text}</p> : null}</div>
                  <span className="reader-data-actions"><CollectionLink href={`/reader/${item.asset}?page=${item.selector.page_index ?? 1}&focus=${item.id}`}>打开 <ArrowRight size={14} /></CollectionLink><ActionButton type="button" state={pendingAction === `delete-record:annotations:${item.id}` ? "pending" : "idle"} pendingLabel="删除中" disabled={Boolean(pendingAction) && pendingAction !== `delete-record:annotations:${item.id}`} onClick={() => void deleteRecord("annotations", item.id)}>删除</ActionButton></span>
                </article>
              ))}
          </DataPanel>
        ) : null}

        {active === "笔记" ? (
          <DataPanel title="笔记">
            {noteGroups.map((group) => {
              const work = adaptWork(group.work);
              return (
                <article className="reader-note-book" key={group.asset}>
                  <header>
                    <BookCover work={work} size="small" />
                    <div>
                      <strong>{work.title}</strong>
                      <p>{work.author} · {group.note_count} 条笔记</p>
                      <small>最近记录于 {new Date(group.latest_at).toLocaleString("zh-CN", { timeZone: "Asia/Hong_Kong" })}</small>
                    </div>
                    <Link href={`/account/notes/${group.asset}`}>查看全部 <ArrowRight size={14} /></Link>
                  </header>
                  <div className="reader-note-previews">
                    {group.previews.map((item) => (
                      <article key={item.id}>
                        <small>第 {item.selector.page_index ?? 1} 页 · {new Date(item.created_at).toLocaleString("zh-CN", { timeZone: "Asia/Hong_Kong" })}</small>
                        <blockquote>{item.quote || "未保存所选原文"}</blockquote>
                        <p>{item.body_text || "这条笔记没有补充文字。"}</p>
                        <span className="reader-data-actions">
                          <CollectionLink href={`/reader/${item.asset}?page=${item.selector.page_index ?? 1}&focus=${item.id}`}>打开原页 <ArrowRight size={13} /></CollectionLink>
                          <ActionButton type="button" state={pendingAction === `delete-record:annotations:${item.id}` ? "pending" : "idle"} pendingLabel="删除中" disabled={Boolean(pendingAction) && pendingAction !== `delete-record:annotations:${item.id}`} onClick={() => void deleteRecord("annotations", item.id)}>删除</ActionButton>
                        </span>
                      </article>
                    ))}
                  </div>
                </article>
              );
            })}
            {!noteGroups.length ? <p className="empty-state">你还没有保存笔记。</p> : null}
          </DataPanel>
        ) : null}

        {active === "阅读历史" ? (
          <DataPanel title="阅读历史">
            {readerData.history.map((item) => (
              <article className="reader-data-row" key={item.id}>
                <Clock3 size={17} />
                <div><strong>{adaptWork(item.work).title}</strong><p>读到第 {item.page_index} 页</p><small>{new Date(item.created_at).toLocaleString("zh-CN", { timeZone: "Asia/Hong_Kong" })}</small></div>
                <CollectionLink href={`/reader/${item.asset}?page=${item.page_index}`}>继续 <ArrowRight size={14} /></CollectionLink>
              </article>
            ))}
            {!readerData.history.length ? <p className="empty-state">暂无阅读历史。</p> : null}
          </DataPanel>
        ) : null}

        {active === "荐书投稿" ? (
          <form className="submission-panel panel" onSubmit={submitRecommendation}>
            <SectionHeading title="通过邮箱荐书" />
            <p>这里不直接上传 PDF。填写信息后会打开你的邮件应用，由你确认后发送给管理员。</p>
            <label><span>文献题名</span><input value={submissionTitle} onChange={(event) => setSubmissionTitle(event.target.value)} required /></label>
            <label><span>推荐说明与合法来源</span><textarea rows={7} value={submissionNote} onChange={(event) => setSubmissionNote(event.target.value)} /></label>
            <ActionButton className="button" type="submit" state={pendingAction === "submit-recommendation" ? "pending" : "idle"} pendingLabel="正在准备邮件" disabled={Boolean(pendingAction) && pendingAction !== "submit-recommendation"}><Mail size={16} /> 发送投稿邮件</ActionButton>
          </form>
        ) : null}

        {active === "账户设置" ? (
          <DataPanel title="账户与数据">
            <article className="reader-data-row"><Settings size={17} /><div><strong>{user.display_name}</strong><p>{user.email}</p></div></article>
            <form className="profile-name-form" onSubmit={updateProfile}><label><span>显示名称</span><input value={profileName} onChange={(event) => setProfileName(event.target.value)} required /></label><ActionButton className="button secondary" type="submit" state={pendingAction === "update-profile" ? "pending" : "idle"} pendingLabel="正在保存" disabled={Boolean(pendingAction) && pendingAction !== "update-profile"}>保存名称</ActionButton></form>
            <DisplayPreferences />
            <Link className="button secondary" href="/reset-password">重置密码</Link>
            <Link className="button secondary" href="/account/settings/privacy"><Settings size={16} /> 隐私与资料</Link>
            <Link className="button secondary" href="/account/settings/privacy/export"><Download size={16} /> 按类别导出与删除资料</Link>
            <Link className="button secondary" href="/account/source-updates"><RefreshCw size={16} /> 来源更新</Link>
            <Link className="button secondary" href="/explore?mode=ask"><Settings size={16} /> 个人模型服务与书库问答</Link>
            <ActionButton className="button secondary" type="button" state={pendingAction === "export-reader-data" ? "pending" : "idle"} pendingLabel="正在导出" disabled={Boolean(pendingAction) && pendingAction !== "export-reader-data"} onClick={() => void exportReaderData()}><Download size={16} /> 导出个人数据</ActionButton>
          </DataPanel>
        ) : null}
        {message ? <AsyncStatus className="reader-center-message" state={messageState} message={message} /> : null}
      </div>
    </div>
  );
}

function DataPanel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="account-empty account-data-panel panel">
      <FileText size={22} />
      <h2>{title}</h2>
      <div>{children}</div>
    </section>
  );
}
