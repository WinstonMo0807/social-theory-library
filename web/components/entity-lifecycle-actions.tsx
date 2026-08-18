"use client";

import { Archive, ExternalLink, RefreshCw, Trash2 } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { apiRequest, getServerSessionCredential } from "@/lib/api";
import { ConfirmDialog } from "./confirm-dialog";

type Dependency = {
  key: string;
  label: string;
  count: number;
  delete_rule: string;
};

type LifecycleSnapshot = {
  kind: string;
  id: string;
  name: string;
  status: string;
  is_public: boolean;
  dependency_count: number;
  dependencies: Dependency[];
  actions: {
    archive: boolean;
    restore: boolean;
    delete: boolean;
  };
  guidance: string;
};

export function EntityLifecycleActions({
  kind,
  id,
  name,
  status,
  previewHref,
  onChanged,
  onDeleted,
}: {
  kind: string;
  id: string;
  name: string;
  status: string;
  previewHref?: string;
  onChanged?: (snapshot: LifecycleSnapshot) => void;
  onDeleted?: () => void;
}) {
  const [snapshot, setSnapshot] = useState<LifecycleSnapshot | null>(null);
  const [message, setMessage] = useState("");
  const [working, setWorking] = useState(false);
  const [confirmation, setConfirmation] = useState<"archive" | "restore" | "delete" | null>(null);

  async function loadImpact() {
    const token = getServerSessionCredential();
    if (!token) return;
    setWorking(true);
    try {
      const payload = await apiRequest<LifecycleSnapshot>(`/catalog/admin/lifecycle/${kind}/${id}/`, {}, token);
      setSnapshot(payload);
      setMessage("");
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "影响范围读取失败。");
    } finally {
      setWorking(false);
    }
  }

  async function changeStatus(action: "archive" | "restore") {
    const label = action === "archive" ? "下线" : "恢复为草稿";
    const token = getServerSessionCredential();
    if (!token) return;
    setWorking(true);
    try {
      const payload = await apiRequest<LifecycleSnapshot>(
        `/catalog/admin/lifecycle/${kind}/${id}/`,
        { method: "POST", body: JSON.stringify({ action }) },
        token,
      );
      setSnapshot(payload);
      setConfirmation(null);
      setMessage(action === "archive" ? "内容已经下线，普通读者将不再看到。" : "内容已恢复为草稿，可继续编辑后发布。");
      onChanged?.(payload);
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : `${label}失败。`);
    } finally {
      setWorking(false);
    }
  }

  async function permanentlyDelete() {
    if (!snapshot) {
      await loadImpact();
      setMessage("请先核对影响范围，再执行永久删除。");
      return;
    }
    if (snapshot.is_public) {
      setMessage("公开内容必须先下线。下线后可以保留旧链接和关系，也可以继续永久删除。");
      return;
    }
    const token = getServerSessionCredential();
    if (!token) return;
    setWorking(true);
    try {
      await apiRequest<void>(
        `/catalog/admin/lifecycle/${kind}/${id}/`,
        { method: "POST", body: JSON.stringify({ action: "delete", confirmed: true }) },
        token,
      );
      setMessage("内容已经永久删除。");
      setConfirmation(null);
      onDeleted?.();
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "永久删除失败。");
    } finally {
      setWorking(false);
    }
  }

  const currentStatus = snapshot?.status ?? status;
  const archived = currentStatus === "archived";

  return (
    <section className="entity-lifecycle-box" aria-label="下线与删除">
      <header>
        <div><strong>发布与数据安全</strong><span>公开内容先下线。永久删除前会展示关联数据和保护规则。</span></div>
        {previewHref ? <Link href={previewHref} target="_blank">预览前台 <ExternalLink size={14} /></Link> : null}
      </header>
      <div className="entity-lifecycle-actions">
        <button type="button" disabled={working} onClick={() => void loadImpact()}><RefreshCw size={14} />查看影响范围</button>
        <button type="button" disabled={working} onClick={() => setConfirmation(archived ? "restore" : "archive")}><Archive size={14} />{archived ? "恢复为草稿" : "下线"}</button>
        <button className="danger" type="button" disabled={working} onClick={() => snapshot ? setConfirmation("delete") : void permanentlyDelete()}><Trash2 size={14} />永久删除</button>
      </div>
      {snapshot ? (
        <div className="entity-impact-preview">
          <p><strong>{snapshot.dependency_count}</strong> 条关联记录可能受影响。{snapshot.guidance}</p>
          {snapshot.dependencies.length ? <ul>{snapshot.dependencies.map((item) => <li key={item.key}><span>{item.label}</span><b>{item.count}</b><small>{item.delete_rule === "CASCADE" ? "随实体删除" : "受保护或需先调整"}</small></li>)}</ul> : <p>没有发现关联记录。</p>}
        </div>
      ) : null}
      {message ? <p className="form-message" role="status">{message}</p> : null}
      <ConfirmDialog
        open={confirmation === "archive" || confirmation === "restore"}
        title={confirmation === "archive" ? `下线“${name}”` : `恢复“${name}”为草稿`}
        description={confirmation === "archive" ? "确认后普通读者将不再看到此内容，关联数据仍会保留。" : "确认后内容回到草稿状态，可以继续编辑再发布。"}
        confirmLabel={confirmation === "archive" ? "确认下线" : "恢复为草稿"}
        tone={confirmation === "archive" ? "danger" : "default"}
        pending={working}
        onCancel={() => setConfirmation(null)}
        onConfirm={() => void changeStatus(confirmation === "restore" ? "restore" : "archive")}
      />
      <ConfirmDialog
        open={confirmation === "delete"}
        title={`永久删除“${snapshot?.name ?? name}”`}
        description="该操作会删除可级联的关系记录，受保护的馆藏关系仍会阻止删除。无需输入名称。"
        details={snapshot ? [`当前发现 ${snapshot.dependency_count} 条关联记录。`, snapshot.guidance] : []}
        confirmLabel="确认永久删除"
        tone="danger"
        pending={working}
        onCancel={() => setConfirmation(null)}
        onConfirm={() => void permanentlyDelete()}
      />
    </section>
  );
}
