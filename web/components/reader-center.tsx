"use client";

import Link from "next/link";
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
  Mail,
  Settings,
  StickyNote,
} from "lucide-react";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { apiRequest, clearStoredSession, getStoredAccessToken, logoutCurrentSession } from "@/lib/api";
import { adaptWork, type ApiWork } from "@/lib/server-api";
import { BookCard, BookCover, SectionHeading } from "./ui";
import { DisplayPreferences } from "./display-preferences";

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

type Paginated<T> = { count?: number; next?: string | null; results: T[] };
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
  work_data: ApiWork;
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

type ReaderData = {
  progress: ProgressRow[];
  saved: SavedRow[];
  savedTopics: SavedTopicRow[];
  annotations: AnnotationRow[];
  bookmarks: BookmarkRow[];
  lists: ReadingListRow[];
  history: HistoryRow[];
};

const emptyData: ReaderData = {
  progress: [],
  saved: [],
  savedTopics: [],
  annotations: [],
  bookmarks: [],
  lists: [],
  history: [],
};

export function ReaderCenter() {
  const [active, setActive] = useState("概览");
  const [user, setUser] = useState<{ display_name: string; email: string } | null>(null);
  const [readerData, setReaderData] = useState<ReaderData>(emptyData);
  const [noteGroups, setNoteGroups] = useState<NoteGroupRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [submissionTitle, setSubmissionTitle] = useState("");
  const [submissionNote, setSubmissionNote] = useState("");
  const [message, setMessage] = useState("");
  const [newListTitle, setNewListTitle] = useState("");
  const [profileName, setProfileName] = useState("");

  useEffect(() => {
    const token = getStoredAccessToken();
    if (!token) {
      window.location.replace("/login?next=/account");
      return;
    }
    Promise.all([
      apiRequest<{ display_name: string; email: string }>("/auth/me/", {}, token),
      apiRequest<Paginated<ProgressRow>>("/reading/progress/", {}, token),
      apiRequest<Paginated<SavedRow>>("/reading/saved/", {}, token),
      apiRequest<Paginated<SavedTopicRow>>("/reading/saved-topics/", {}, token),
      apiRequest<Paginated<AnnotationRow>>("/reading/annotations/", {}, token),
      apiRequest<Paginated<NoteGroupRow>>("/reading/annotations/note-groups/", {}, token),
      apiRequest<Paginated<BookmarkRow>>("/reading/bookmarks/", {}, token),
      apiRequest<Paginated<ReadingListRow>>("/reading/lists/", {}, token),
      apiRequest<Paginated<HistoryRow>>("/reading/history/", {}, token),
    ])
      .then(([profile, progress, saved, savedTopics, annotations, noteGroupRows, bookmarks, lists, history]) => {
        setUser(profile);
        setProfileName(profile.display_name);
        setReaderData({
          progress: progress.results,
          saved: saved.results,
          savedTopics: savedTopics.results,
          annotations: annotations.results,
          bookmarks: bookmarks.results,
          lists: lists.results,
          history: history.results,
        });
        setNoteGroups(noteGroupRows.results);
      })
      .catch(() => {
        clearStoredSession();
        window.location.replace("/login?next=/account");
      })
      .finally(() => setLoading(false));
  }, []);

  const recentProgress = useMemo(
    () => [...readerData.progress]
      .sort((left, right) => right.updated_at.localeCompare(left.updated_at))
      .slice(0, 5),
    [readerData.progress],
  );
  const savedWorks = readerData.saved.map((item, index) => adaptWork(item.work_data, index));

  async function logout() {
    await logoutCurrentSession();
    window.location.href = "/";
  }

  async function submitRecommendation(event: FormEvent) {
    event.preventDefault();
    const token = getStoredAccessToken();
    if (!token) return;
    setMessage("");
    try {
      const result = await apiRequest<{ detail: string; mailto: string; email: string }>(
        "/reading/submit/",
        {
          method: "POST",
          body: JSON.stringify({ title: submissionTitle, note: submissionNote }),
        },
        token,
      );
      setMessage(result.detail);
      window.location.href = result.mailto;
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "投稿邮件发送失败。");
    }
  }

  async function exportReaderData() {
    const token = getStoredAccessToken();
    if (!token) return;
    const payload = await apiRequest<Record<string, unknown>>("/reading/export/", {}, token);
    const blob = new Blob([JSON.stringify(payload, null, 2)], {
      type: "application/json;charset=utf-8",
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `社会理论书库-个人数据-${new Date().toISOString().slice(0, 10)}.json`;
    link.click();
    URL.revokeObjectURL(url);
  }

  async function deleteRecord(kind: "saved" | "saved-topics" | "annotations" | "bookmarks", id: string) {
    const token = getStoredAccessToken();
    if (!token) return;
    if (!window.confirm("确定删除这条个人阅读记录吗？")) return;
    try {
      await apiRequest(`/reading/${kind}/${id}/`, { method: "DELETE" }, token);
      setReaderData((current) => ({
        ...current,
        saved: kind === "saved" ? current.saved.filter((item) => item.id !== id) : current.saved,
        savedTopics: kind === "saved-topics" ? current.savedTopics.filter((item) => item.id !== id) : current.savedTopics,
        annotations: kind === "annotations" ? current.annotations.filter((item) => item.id !== id) : current.annotations,
        bookmarks: kind === "bookmarks" ? current.bookmarks.filter((item) => item.id !== id) : current.bookmarks,
      }));
      if (kind === "annotations") {
        const groups = await apiRequest<Paginated<NoteGroupRow>>(
          "/reading/annotations/note-groups/",
          {},
          token,
        );
        setNoteGroups(groups.results);
      }
      setMessage("个人阅读记录已删除。");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "删除失败。");
    }
  }

  async function createReadingList(event: FormEvent) {
    event.preventDefault();
    const token = getStoredAccessToken();
    if (!token || !newListTitle.trim()) return;
    try {
      const created = await apiRequest<ReadingListRow>(
        "/reading/lists/",
        {
          method: "POST",
          body: JSON.stringify({ title: newListTitle.trim(), description: "", is_default: false }),
        },
        token,
      );
      setReaderData((current) => ({ ...current, lists: [created, ...current.lists] }));
      setNewListTitle("");
      setMessage("书单已创建。");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "书单创建失败。");
    }
  }

  async function addSavedWorkToList(listId: string, workId: string) {
    const token = getStoredAccessToken();
    if (!token || !workId) return;
    try {
      const item = await apiRequest<{ id: string; work: string; title: string }>(
        `/reading/lists/${listId}/add_item/`,
        { method: "POST", body: JSON.stringify({ work: workId }) },
        token,
      );
      setReaderData((current) => ({
        ...current,
        lists: current.lists.map((list) => (
          list.id === listId && !list.items.some((existing) => existing.id === item.id)
            ? { ...list, items: [...list.items, item] }
            : list
        )),
      }));
      setMessage("文献已加入书单。");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "加入书单失败。");
    }
  }

  async function deleteReadingList(id: string) {
    const token = getStoredAccessToken();
    if (!token) return;
    try {
      await apiRequest(`/reading/lists/${id}/`, { method: "DELETE" }, token);
      setReaderData((current) => ({ ...current, lists: current.lists.filter((list) => list.id !== id) }));
      setMessage("书单已删除。");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "书单删除失败。");
    }
  }

  async function updateProfile(event: FormEvent) {
    event.preventDefault();
    const token = getStoredAccessToken();
    if (!token) return;
    try {
      const updated = await apiRequest<{ display_name: string; email: string }>(
        "/auth/me/",
        { method: "PATCH", body: JSON.stringify({ display_name: profileName }) },
        token,
      );
      setUser(updated);
      setMessage("显示名称已更新。");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "账户更新失败。");
    }
  }

  if (loading || !user) {
    return <div className="account-loading">正在读取你的个人阅读资料……</div>;
  }

  return (
    <div className="reader-center">
      <aside className="account-sidebar">
        <div className="account-avatar">{user.display_name.slice(0, 1)}</div>
        <strong>{user.display_name}</strong>
        <span>{user.email}</span>
        <nav>
          {tabs.map(([Icon, label]) => (
            <button className={active === label ? "active" : ""} type="button" key={label} onClick={() => setActive(label)}>
              <Icon size={17} />{label}
            </button>
          ))}
        </nav>
        <button className="logout-button" type="button" onClick={logout}><LogOut size={16} /> 退出登录</button>
      </aside>
      <main className="account-content">
        <header>
          <p className="eyebrow">读者中心</p>
          <h1>{active}</h1>
          <p>个人阅读资料仅在你的账户中显示。</p>
        </header>

        {active === "概览" ? (
          <>
            <section className="account-stats">
              {[
                [String(readerData.progress.length), "正在阅读"],
                [String(readerData.saved.length + readerData.savedTopics.length), "收藏"],
                [String(readerData.bookmarks.length), "书签"],
                [String(readerData.annotations.filter((item) => item.kind !== "note").length), "高亮"],
                [String(readerData.annotations.filter((item) => item.kind === "note").length), "笔记"],
              ].map(([value, label]) => (
                <div key={label}><strong>{value}</strong><span>{label}</span></div>
              ))}
            </section>
            <section className="continue-reading panel">
              <SectionHeading title="继续阅读" />
              <p className="continue-reading-note">按最后阅读时间保留最近 5 项。</p>
              {recentProgress.length ? (
                <div className="continue-reading-list">
                  {recentProgress.map((progress) => {
                    const ratio = Math.round(progress.progress_ratio * 100);
                    return (
                      <article className="continue-reading-entry" key={progress.id}>
                        <BookCard work={adaptWork(progress.work)} dense />
                        <div className="continue-reading-progress">
                          <span>第 {progress.current_page} 页</span>
                          <i aria-label={`阅读进度 ${ratio}%`}><b style={{ width: `${ratio}%` }} /></i>
                          <strong>{ratio}%</strong>
                        </div>
                        <Link className="button" href={`/reader/${progress.asset}?page=${progress.current_page}`}>
                          继续阅读 <ArrowRight size={16} />
                        </Link>
                      </article>
                    );
                  })}
                </div>
              ) : <p className="empty-state">开始在线阅读后，最近进度会显示在这里。</p>}
            </section>
            <section className="account-books panel">
              <SectionHeading title="最近收藏" />
              <div>{savedWorks.slice(0, 3).map((work) => <BookCard work={work} dense key={work.id} />)}</div>
              {readerData.savedTopics.slice(0, 3).map((topic) => (
                <Link className="reader-saved-topic" href={`/topics/${topic.slug}`} key={topic.id}>
                  <strong>{topic.name}</strong><span>收藏主题</span><ArrowRight size={14} />
                </Link>
              ))}
              {!savedWorks.length && !readerData.savedTopics.length ? <p className="empty-state">你还没有收藏文献或主题。</p> : null}
            </section>
          </>
        ) : null}

        {active === "收藏" ? (
          <DataPanel title="收藏">
            {savedWorks.map((work, index) => {
              const saved = readerData.saved[index];
              const progress = saved.reading_progress;
              return (
                <div className="reader-saved-row" key={work.id}>
                  <BookCard work={work} dense />
                  <span className="reader-saved-actions">
                    {progress ? (
                      <Link href={`/reader/${progress.asset}?page=${progress.current_page}`}>
                        第 {progress.current_page} 页继续 <ArrowRight size={14} />
                      </Link>
                    ) : null}
                    <button type="button" onClick={() => deleteRecord("saved", saved.id)}>移除收藏</button>
                  </span>
                </div>
              );
            })}
            {readerData.savedTopics.map((topic) => (
              <article className="reader-data-row" key={topic.id}>
                <Bookmark size={17} />
                <div><strong>{topic.name}</strong><p>{topic.description || "馆藏主题"}</p></div>
                <span className="reader-data-actions">
                  <Link href={`/topics/${topic.slug}`}>打开 <ArrowRight size={14} /></Link>
                  <button type="button" onClick={() => deleteRecord("saved-topics", topic.id)}>移除收藏</button>
                </span>
              </article>
            ))}
            {!savedWorks.length && !readerData.savedTopics.length ? <p className="empty-state">你还没有收藏文献或主题。</p> : null}
          </DataPanel>
        ) : null}

        {active === "书签" ? (
          <DataPanel title="书签">
            {readerData.bookmarks.map((item) => (
              <article className="reader-data-row" key={item.id}>
                <Bookmark size={17} />
                <div><strong>{adaptWork(item.work).title}</strong><p>{item.label || "页面书签"}</p></div>
                <span className="reader-data-actions"><Link href={`/reader/${item.asset}?page=${item.page_index}`}>打开 <ArrowRight size={14} /></Link><button type="button" onClick={() => deleteRecord("bookmarks", item.id)}>删除</button></span>
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
                  <span className="reader-data-actions"><Link href={`/reader/${item.asset}?page=${item.selector.page_index ?? 1}&focus=${item.id}`}>打开 <ArrowRight size={14} /></Link><button type="button" onClick={() => deleteRecord("annotations", item.id)}>删除</button></span>
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
                          <Link href={`/reader/${item.asset}?page=${item.selector.page_index ?? 1}&focus=${item.id}`}>打开原页 <ArrowRight size={13} /></Link>
                          <button type="button" onClick={() => deleteRecord("annotations", item.id)}>删除</button>
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

        {active === "书单" ? (
          <DataPanel title="书单">
            <form className="reading-list-create" onSubmit={createReadingList}><input value={newListTitle} onChange={(event) => setNewListTitle(event.target.value)} placeholder="新书单名称" required /><button className="button secondary" type="submit">创建书单</button></form>
            {readerData.lists.map((list) => (
              <article className="reader-data-row" key={list.id}>
                <List size={17} /><div><strong>{list.title}</strong><p>{list.description}</p><small>{list.items.length} 部文献</small>{list.items.map((item) => <span className="reading-list-item" key={item.id}>{item.title}</span>)}</div>
                <span className="reader-data-actions">
                  {readerData.saved[0] ? <button type="button" onClick={() => addSavedWorkToList(list.id, readerData.saved[0].work_data.id)}>加入最近收藏</button> : null}
                  <button type="button" onClick={() => deleteReadingList(list.id)}>删除</button>
                </span>
              </article>
            ))}
            {!readerData.lists.length ? <p className="empty-state">你还没有创建书单。</p> : null}
          </DataPanel>
        ) : null}

        {active === "阅读历史" ? (
          <DataPanel title="阅读历史">
            {readerData.history.map((item) => (
              <article className="reader-data-row" key={item.id}>
                <Clock3 size={17} />
                <div><strong>{adaptWork(item.work).title}</strong><p>读到第 {item.page_index} 页</p><small>{new Date(item.created_at).toLocaleString("zh-CN", { timeZone: "Asia/Hong_Kong" })}</small></div>
                <Link href={`/reader/${item.asset}?page=${item.page_index}`}>继续 <ArrowRight size={14} /></Link>
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
            <button className="button" type="submit"><Mail size={16} /> 发送投稿邮件</button>
            {message ? <p className="form-message" aria-live="polite">{message}</p> : null}
          </form>
        ) : null}

        {active === "账户设置" ? (
          <DataPanel title="账户与数据">
            <article className="reader-data-row"><Settings size={17} /><div><strong>{user.display_name}</strong><p>{user.email}</p></div></article>
            <form className="profile-name-form" onSubmit={updateProfile}><label><span>显示名称</span><input value={profileName} onChange={(event) => setProfileName(event.target.value)} required /></label><button className="button secondary" type="submit">保存名称</button></form>
            <DisplayPreferences />
            <Link className="button secondary" href="/reset-password">重置密码</Link>
            <button className="button secondary" type="button" onClick={exportReaderData}><Download size={16} /> 导出个人数据</button>
          </DataPanel>
        ) : null}
        {message ? <p className="form-message reader-center-message" role="status">{message}</p> : null}
      </main>
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
