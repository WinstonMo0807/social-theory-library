"use client";

import { AlertTriangle, CheckCircle2, Eye, EyeOff, RefreshCw, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { apiRequest, getStoredAccessToken } from "@/lib/api";
import { ConfirmDialog } from "./confirm-dialog";

export type PublicationPreflight = {
  blockers: string[];
  warnings: string[];
  background_tasks: string[];
};

type Props = {
  itemId: string;
  editionId: string;
  publicationState: string;
  ocrStatus: string;
  semanticStatus: string;
  pageLabelStatus: string;
  reviewStatus: string;
  reviewProgress: number;
  readerPolicy: "auto" | "original" | "ocr";
  initialPreflight: PublicationPreflight;
  canManagePublication: boolean;
  onChanged: () => Promise<void> | void;
  onMessage: (message: string) => void;
};

const stateLabels: Record<string, string> = {
  draft: "草稿",
  ready: "待发布",
  published: "已发布",
  withdrawn: "已下架",
  pending: "等待",
  running: "处理中",
  succeeded: "已完成",
  failed: "失败",
  not_required: "无需处理",
  not_indexed: "未建立",
  needs_review: "待校对",
  completed: "已完成",
};

export function ItemPublicationControl({
  itemId,
  editionId,
  publicationState,
  ocrStatus,
  semanticStatus,
  pageLabelStatus,
  reviewStatus,
  reviewProgress,
  readerPolicy,
  initialPreflight,
  canManagePublication,
  onChanged,
  onMessage,
}: Props) {
  const [preflight, setPreflight] = useState(initialPreflight);
  const [confirming, setConfirming] = useState(false);
  const [pending, setPending] = useState(false);
  const [policy, setPolicy] = useState(readerPolicy);
  const [withdrawing, setWithdrawing] = useState(false);

  async function refreshPreflight() {
    const token = getStoredAccessToken();
    if (!token) return;
    setPending(true);
    try {
      const result = await apiRequest<PublicationPreflight>(
        `/ingestion/items/${itemId}/publish/`,
        {},
        token,
      );
      setPreflight(result);
      onMessage("发布前检查已刷新。");
    } catch (reason) {
      onMessage(reason instanceof Error ? reason.message : "发布前检查失败。");
    } finally {
      setPending(false);
    }
  }

  async function publish(confirmWarnings: boolean) {
    const token = getStoredAccessToken();
    if (!token) return;
    if (preflight.blockers.length) {
      onMessage("仍有技术问题阻止发布，请先恢复原始 PDF 或公开阅读文件。");
      return;
    }
    if (preflight.warnings.length && !confirmWarnings) {
      setConfirming(true);
      return;
    }
    setPending(true);
    try {
      const result = await apiRequest<{
        detail: string;
        preflight: PublicationPreflight;
        index_warning?: string;
        scheduled_tasks?: { type: string; status: string }[];
        background_warnings?: string[];
      }>(
        `/ingestion/items/${itemId}/publish/`,
        {
          method: "POST",
          body: JSON.stringify({ confirm_warnings: confirmWarnings }),
        },
        token,
      );
      setConfirming(false);
      const queued = (result.scheduled_tasks ?? []).map((item) => ({
        ocr: "OCR",
        page_labels: "引用页码",
        semantic_index: "语义索引",
      }[item.type] ?? item.type));
      const warnings = [result.index_warning, ...(result.background_warnings ?? [])].filter(Boolean);
      onMessage(warnings.length
        ? `图书已经发布，公开状态不受后台故障影响。${warnings.join("；")}`
        : queued.length
          ? `图书已经发布，${queued.join("、")}已进入后台处理。`
          : "图书已经发布，当前处理状态已同步。"
      );
      await onChanged();
    } catch (reason) {
      onMessage(reason instanceof Error ? reason.message : "发布失败。");
    } finally {
      setPending(false);
    }
  }

  async function withdraw(reason: string) {
    const token = getStoredAccessToken();
    if (!token) return;
    setPending(true);
    try {
      await apiRequest(`/ingestion/items/${itemId}/withdraw/`, {
        method: "POST",
        body: JSON.stringify({ reason }),
      }, token);
      setWithdrawing(false);
      onMessage("图书已经下架。文件、处理结果和稳定地址均已保留，可随时重新发布。");
      await onChanged();
    } catch (reasonValue) {
      onMessage(reasonValue instanceof Error ? reasonValue.message : "下架失败。");
    } finally {
      setPending(false);
    }
  }

  async function updatePolicy(next: "auto" | "original" | "ocr") {
    const token = getStoredAccessToken();
    if (!token) return;
    setPending(true);
    try {
      const result = await apiRequest<{
        policy: "auto" | "original" | "ocr";
        fallback_active: boolean;
      }>(`/catalog/admin/editions/${editionId}/reader-rendition/`, {
        method: "PUT",
        body: JSON.stringify({ policy: next }),
      }, token);
      setPolicy(result.policy);
      onMessage(result.fallback_active
        ? "已保存 OCR PDF 偏好，但当前没有通过验证的 OCR PDF，阅读器会安全回退到原始 PDF。"
        : "阅读器文件策略已经保存。原始 PDF 始终保留。"
      );
      await onChanged();
    } catch (reason) {
      onMessage(reason instanceof Error ? reason.message : "阅读器策略保存失败。");
    } finally {
      setPending(false);
    }
  }

  const published = publicationState === "published";
  return (
    <section className="admin-panel publication-control">
      <header>
        <div><p>发布管理</p><h2>管理员最终发布权</h2></div>
        <div className="publication-main-actions">
          <button className="button secondary" type="button" onClick={() => void refreshPreflight()} disabled={pending}><RefreshCw size={15} />重新检查</button>
          {published
            ? <button className="button danger" type="button" onClick={() => setWithdrawing(true)} disabled={pending || !canManagePublication} title={!canManagePublication ? "只有管理员可以下架" : undefined}><EyeOff size={15} />下架</button>
            : <button className="button" type="button" onClick={() => void publish(false)} disabled={pending || preflight.blockers.length > 0 || !canManagePublication} title={!canManagePublication ? "只有管理员可以发布" : undefined}><Eye size={15} />发布</button>}
        </div>
      </header>

      <div className="publication-status-grid">
        <StatusCard label="出版状态" value={publicationState} />
        <StatusCard label="人工复核" value={reviewStatus} detail={`${reviewProgress}%`} />
        <StatusCard label="OCR" value={ocrStatus} />
        <StatusCard label="引用页码" value={pageLabelStatus} />
        <StatusCard label="语义索引" value={semanticStatus} />
      </div>

      {!canManagePublication ? <p className="publication-permission-note">当前角色可以复核内容并查看发布检查，最终发布、下架和阅读副本切换由管理员执行。</p> : null}

      <div className="preflight-columns">
        <PreflightGroup title="Technical blockers" values={preflight.blockers} empty="没有技术阻止项" tone="blocker" />
        <PreflightGroup title="Warnings" values={preflight.warnings} empty="没有发布警告" tone="warning" />
        <PreflightGroup title="Background tasks" values={preflight.background_tasks} empty="没有待运行任务" tone="task" />
      </div>

      {confirming ? (
        <div className="publication-confirmation" role="dialog" aria-label="确认带警告发布">
          <AlertTriangle size={19} />
          <div><strong>这些警告不会阻止管理员发布</strong><p>确认后图书立即公开。OCR、页码识别和语义索引继续在后台运行，失败也不会替换或删除原始 PDF。</p></div>
          <button className="button" type="button" onClick={() => void publish(true)} disabled={pending}>确认发布</button>
          <button className="button secondary" type="button" onClick={() => setConfirming(false)} disabled={pending}>取消</button>
        </div>
      ) : null}

      <label className="reader-policy-control">
        <span>阅读器文件策略</span>
        <select value={policy} onChange={(event) => void updatePolicy(event.target.value as "auto" | "original" | "ocr")} disabled={pending || !canManagePublication}>
          <option value="auto">自动，以原始 PDF 为视觉层</option>
          <option value="original">强制原始 PDF</option>
          <option value="ocr">优先已验证 OCR PDF，不可用时回退</option>
        </select>
        <small>默认策略不会让 OCR 任务覆盖原始文件。扫描件可以先发布，OCR 成功后只补充可选择文字层。</small>
      </label>
      <ConfirmDialog
        open={withdrawing}
        title="确认下架这项馆藏"
        description="公开列表、检索与新的阅读访问会停止展示。PDF、OCR、页码、索引历史和稳定地址全部保留，可随时重新发布。"
        confirmLabel="确认下架"
        tone="danger"
        pending={pending}
        reasonLabel="下架原因（可选）"
        reasonDefault="管理员决定下架"
        onCancel={() => setWithdrawing(false)}
        onConfirm={(reason) => void withdraw(reason)}
      />
    </section>
  );
}

function StatusCard({ label, value, detail = "" }: { label: string; value: string; detail?: string }) {
  const okay = ["published", "succeeded", "ready", "completed", "not_required"].includes(value);
  return <article className={okay ? "ready" : "pending"}>{okay ? <CheckCircle2 size={15} /> : <ShieldCheck size={15} />}<span>{label}</span><strong>{stateLabels[value] ?? value}</strong>{detail ? <small>{detail}</small> : null}</article>;
}

function PreflightGroup({ title, values, empty, tone }: { title: string; values: string[]; empty: string; tone: string }) {
  return <section className={`preflight-group ${tone}`}><h3>{title}</h3>{values.length ? <ul>{values.map((value) => <li key={value}>{value}</li>)}</ul> : <p>{empty}</p>}</section>;
}
