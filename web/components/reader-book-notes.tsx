"use client";

import Link from "next/link";
import { ArrowLeft, ArrowRight, BookOpen, StickyNote, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { apiRequest, getStoredAccessToken } from "@/lib/api";
import { adaptWork, type ApiWork } from "@/lib/server-api";
import { BookCover } from "./ui";

type AnnotationRow = {
  id: string;
  asset: string;
  work: ApiWork;
  kind: "note";
  quote: string;
  body_text: string;
  selector: { page_index?: number };
  created_at: string;
};

type Paginated<T> = {
  count: number;
  next: string | null;
  results: T[];
};

async function loadAllBookNotes(assetId: string, token: string) {
  const collected: AnnotationRow[] = [];
  let page = 1;
  let total = 1;
  while (collected.length < total && page <= 100) {
    const payload = await apiRequest<Paginated<AnnotationRow>>(
      `/reading/annotations/?asset=${encodeURIComponent(assetId)}&kind=note&p=${page}`,
      {},
      token,
    );
    total = payload.count;
    collected.push(...payload.results);
    if (!payload.next) break;
    page += 1;
  }
  return collected;
}

export function ReaderBookNotes({ assetId }: { assetId: string }) {
  const [notes, setNotes] = useState<AnnotationRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");

  useEffect(() => {
    const token = getStoredAccessToken();
    if (!token) {
      window.location.replace(`/login?next=/account/notes/${assetId}`);
      return;
    }
    loadAllBookNotes(assetId, token)
      .then(setNotes)
      .catch((error: unknown) => setMessage(error instanceof Error ? error.message : "笔记读取失败。"))
      .finally(() => setLoading(false));
  }, [assetId]);

  async function deleteNote(id: string) {
    if (!window.confirm("确定删除这条笔记吗？")) return;
    const token = getStoredAccessToken();
    if (!token) return;
    try {
      await apiRequest(`/reading/annotations/${id}/`, { method: "DELETE" }, token);
      setNotes((current) => current.filter((item) => item.id !== id));
      setMessage("笔记已删除。");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "笔记删除失败。");
    }
  }

  if (loading) {
    return <main className="account-loading">正在读取这本书的笔记……</main>;
  }

  const work = notes[0] ? adaptWork(notes[0].work) : null;
  return (
    <main className="reader-book-notes page-shell">
      <Link className="back-link" href="/account"><ArrowLeft size={15} /> 返回读者中心</Link>
      <header className="reader-book-notes-header">
        {work ? <BookCover work={work} size="small" /> : <BookOpen size={34} />}
        <div>
          <p className="eyebrow">个人阅读资料</p>
          <h1>{work?.title ?? "作品笔记"}</h1>
          <p>{notes.length} 条笔记。点击一条记录可回到 PDF 的对应页面。</p>
        </div>
      </header>
      <section className="reader-book-note-list">
        {notes.map((note) => (
          <article id={`note-${note.id}`} key={note.id}>
            <StickyNote size={19} />
            <div>
              <header>
                <strong>第 {note.selector.page_index ?? 1} 页</strong>
                <time>{new Date(note.created_at).toLocaleString("zh-CN")}</time>
              </header>
              <blockquote>{note.quote || "未保存所选原文"}</blockquote>
              <p>{note.body_text || "这条笔记没有补充文字。"}</p>
            </div>
            <span className="reader-data-actions">
              <Link href={`/reader/${note.asset}?page=${note.selector.page_index ?? 1}&focus=${note.id}`}>打开原页 <ArrowRight size={14} /></Link>
              <button type="button" onClick={() => void deleteNote(note.id)}><Trash2 size={13} /> 删除</button>
            </span>
          </article>
        ))}
        {!notes.length ? <p className="empty-state">这本书目前没有笔记，可能已经被删除。</p> : null}
      </section>
      {message ? <p className="form-message" role="status">{message}</p> : null}
    </main>
  );
}
