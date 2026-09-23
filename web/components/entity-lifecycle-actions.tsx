"use client";

import { Archive, ExternalLink, RefreshCw } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { apiRequest, getServerSessionCredential } from "@/lib/api";
import { RecycleControl } from "./admin/recycle-control";
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

type LifecycleRevisionResponse = {
  detail: string;
  impact: LifecycleSnapshot;
  editorial_revision: {
    id: string;
    revision: number;
    status: string;
    publish_url: string;
  };
};

function isRevisionResponse(
  payload: LifecycleSnapshot | LifecycleRevisionResponse,
): payload is LifecycleRevisionResponse {
  return "editorial_revision" in payload;
}

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
  const [confirmation, setConfirmation] = useState<"archive" | "restore" | null>(null);

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
      const payload = await apiRequest<LifecycleSnapshot | LifecycleRevisionResponse>(
        `/catalog/admin/lifecycle/${kind}/${id}/`,
        { method: "POST", body: JSON.stringify({ action }) },
        token,
      );
      if (isRevisionResponse(payload)) {
        setSnapshot(payload.impact);
        setConfirmation(null);
        setMessage("下线草稿已保存，读者页面尚未改变。请在内容管理中预览，再确认发布。");
        return;
      }
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

  const currentStatus = snapshot?.status ?? status;
  const archived = currentStatus === "archived";

  return (
    <section className="entity-lifecycle-box" aria-label="下架与删除">
      <header>
        <div><strong>发布与数据安全</strong><span>下架后仍可管理；删除后可从回收站恢复。</span></div>
        {previewHref ? <Link href={previewHref} target="_blank">打开读者页面 <ExternalLink size={14} /></Link> : null}
      </header>
      <div className="entity-lifecycle-actions">
        <button type="button" disabled={working} onClick={() => void loadImpact()}><RefreshCw size={14} />查看影响范围</button>
        <button type="button" disabled={working} onClick={() => setConfirmation(archived ? "restore" : "archive")}><Archive size={14} />{archived ? "恢复为草稿" : "下线"}</button>
        <RecycleControl kind={kind} id={id} name={name} disabled={working} onDeleted={onDeleted} />
      </div>
      {snapshot ? (
        <div className="entity-impact-preview">
          <p><strong>{snapshot.dependency_count}</strong> 条关联记录会保留。{snapshot.guidance}</p>
          {snapshot.dependencies.length ? <ul>{snapshot.dependencies.map((item) => <li key={item.key}><span>{item.label}</span><b>{item.count}</b><small>原记录保留</small></li>)}</ul> : <p>没有发现关联记录。</p>}
        </div>
      ) : null}
      {message ? <p className="form-message" role="status">{message}</p> : null}
      <ConfirmDialog
        open={confirmation === "archive" || confirmation === "restore"}
        title={confirmation === "archive" ? `下线“${name}”` : `恢复“${name}”为草稿`}
        description={confirmation === "archive" ? "已公开内容会先保存下线草稿，正式发布后读者才不再看到。关联数据仍会保留。" : "确认后内容回到草稿状态，可以继续编辑再发布。"}
        confirmLabel={confirmation === "archive" ? "确认下线" : "恢复为草稿"}
        tone={confirmation === "archive" ? "danger" : "default"}
        pending={working}
        onCancel={() => setConfirmation(null)}
        onConfirm={() => void changeStatus(confirmation === "restore" ? "restore" : "archive")}
      />

    </section>
  );
}
