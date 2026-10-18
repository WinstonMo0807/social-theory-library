import Link from "next/link";
import type { TurnData } from "@/lib/api/research.client";

/** Personal reminders remain separate from the publicly verifiable evidence list. */
export function ResearchMemoryReminders({ turn }: { turn?: TurnData }) {
  const rows = turn?.memory_reminders || [];
  return <section className="stl4-research-memory-reminders" aria-label="本人笔记提醒">
    <h3>选定笔记</h3>
    {rows.length ? <><p>以下是你确认并授权给本研究的认识。</p><ul>{rows.map(row => <li key={row.id}><p>{row.body}</p><small>{row.notice || "本人笔记，供本轮思考时参考。"}</small></li>)}</ul></> : <p>{turn?.memory_reminders_status === "authorization_changed" ? "笔记或使用范围已变化，旧提醒已收起。已保存的研究材料保留。" : "本轮没有使用个人笔记。"}</p>}
    <Link href="/account/confirmed-notes">查看笔记与使用范围</Link>
  </section>;
}
