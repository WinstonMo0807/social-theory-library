"use client";

import { Plus, RefreshCw } from "lucide-react";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { apiRequest, getServerSessionCredential } from "@/lib/api";
import { ActionButton, AsyncStatus, type ActionState } from "./action-feedback";
import { ConfirmDialog } from "./confirm-dialog";

type PromptRegistryRow = {
  id: string;
  key: string;
  version: number;
  capability: string;
  task_profile_key: string;
  content: string;
  output_schema: Record<string, unknown>;
  provider_guidance: Record<string, unknown>;
  content_hash: string;
  schema_hash: string;
  status: "draft" | "active" | "retired";
  activated_at: string | null;
  created_at: string;
};

type TaskProfileChoice = {
  key: string;
  version: number;
  name: string;
  prompt_key: string;
  required_capability: string;
};

type PromptRegistryPayload = {
  immutable_revisions: true;
  activation_requires_superadmin: true;
  results: PromptRegistryRow[];
  active_task_profiles: TaskProfileChoice[];
};

type PromptDraft = {
  key: string;
  capability: string;
  taskProfileKey: string;
  content: string;
  outputSchema: string;
  providerGuidance: string;
};

const EMPTY_DRAFT: PromptDraft = {
  key: "",
  capability: "claim_extraction",
  taskProfileKey: "",
  content: "",
  outputSchema: "{}",
  providerGuidance: "{}",
};

const CAPABILITY_LABELS: Record<string, string> = {
  metadata_extraction: "元数据提取",
  library_qa: "书库问答",
  field_enrichment_optional: "联网补全判断",
  entity_reasoning: "实体推理",
  claim_extraction: "Claim 提取",
  claim_attribution: "Claim 归属",
  claim_stance: "Claim 立场",
  rerank: "结果重排",
  theory_reasoning: "理论推理",
  knowledge_relation_reasoning: "知识关系推理",
  debate_discovery: "Debate 发现",
  reading_path_generation: "Reading Path 生成",
  curation_reasoning: "策展推理",
};

function parseObject(value: string, fieldLabel: string) {
  let parsed: unknown;
  try {
    parsed = JSON.parse(value || "{}");
  } catch {
    throw new Error(`${fieldLabel}必须是有效 JSON。`);
  }
  if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") {
    throw new Error(`${fieldLabel}必须是 JSON 对象。`);
  }
  return parsed as Record<string, unknown>;
}

function timeLabel(value: string | null) {
  if (!value) return "尚未启用";
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? value : date.toLocaleString("zh-CN", { hour12: false });
}

export function PromptRegistryAdmin() {
  const [payload, setPayload] = useState<PromptRegistryPayload | null>(null);
  const [draft, setDraft] = useState<PromptDraft>(EMPTY_DRAFT);
  const [activationTarget, setActivationTarget] = useState<PromptRegistryRow | null>(null);
  const [loading, setLoading] = useState(true);
  const [pending, setPending] = useState("");
  const [message, setMessage] = useState("");
  const [messageState, setMessageState] = useState<ActionState>("idle");

  const loadRegistry = useCallback(async () => {
    const token = getServerSessionCredential();
    if (!token) {
      setMessage("登录状态尚未就绪，无法读取 Prompt Registry。");
      setMessageState("error");
      setLoading(false);
      return false;
    }
    setLoading(true);
    try {
      const result = await apiRequest<PromptRegistryPayload>(
        "/catalog/admin/prompt-registry/?limit=200",
        {},
        token,
      );
      setPayload(result);
      setMessage("");
      setMessageState("idle");
      return true;
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "Prompt Registry 读取失败。");
      setMessageState("error");
      return false;
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadRegistry();
  }, [loadRegistry]);

  const capabilities = useMemo(() => {
    const values = new Set(Object.keys(CAPABILITY_LABELS));
    payload?.active_task_profiles.forEach((profile) => values.add(profile.required_capability));
    return [...values].sort((left, right) => (
      (CAPABILITY_LABELS[left] ?? left).localeCompare(CAPABILITY_LABELS[right] ?? right, "zh-CN")
    ));
  }, [payload?.active_task_profiles]);

  function selectTaskProfile(taskProfileKey: string) {
    const profile = payload?.active_task_profiles.find((row) => row.key === taskProfileKey);
    setDraft((current) => ({
      ...current,
      taskProfileKey,
      key: profile?.prompt_key || current.key,
      capability: profile?.required_capability || current.capability,
    }));
  }

  function reviseFrom(row: PromptRegistryRow) {
    setDraft({
      key: row.key,
      capability: row.capability,
      taskProfileKey: row.task_profile_key,
      content: row.content,
      outputSchema: JSON.stringify(row.output_schema || {}, null, 2),
      providerGuidance: JSON.stringify(row.provider_guidance || {}, null, 2),
    });
  }

  async function createRevision(event: FormEvent) {
    event.preventDefault();
    const token = getServerSessionCredential();
    if (!token || pending) return;
    let outputSchema: Record<string, unknown>;
    let providerGuidance: Record<string, unknown>;
    try {
      outputSchema = parseObject(draft.outputSchema, "输出 schema");
      providerGuidance = parseObject(draft.providerGuidance, "Provider 指引");
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "Prompt 配置格式无效。");
      setMessageState("error");
      return;
    }
    setPending("create");
    setMessage("正在建立不可变 Prompt 修订。");
    setMessageState("pending");
    try {
      const created = await apiRequest<PromptRegistryRow>(
        "/catalog/admin/prompt-registry/",
        {
          method: "POST",
          body: JSON.stringify({
            action: "create_revision",
            key: draft.key.trim(),
            capability: draft.capability,
            task_profile_key: draft.taskProfileKey,
            content: draft.content.trim(),
            output_schema: outputSchema,
            provider_guidance: providerGuidance,
          }),
        },
        token,
      );
      if (await loadRegistry()) {
        setMessage(`${created.key} v${created.version} 已保存为草稿，尚未影响运行任务。`);
        setMessageState("success");
      }
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "Prompt 修订创建失败。");
      setMessageState("error");
    } finally {
      setPending("");
    }
  }

  async function activateRevision() {
    const target = activationTarget;
    const token = getServerSessionCredential();
    if (!target || !token || pending) return;
    setPending(`activate:${target.id}`);
    setMessage(`正在启用 ${target.key} v${target.version}。`);
    setMessageState("pending");
    try {
      const activated = await apiRequest<PromptRegistryRow>(
        "/catalog/admin/prompt-registry/",
        {
          method: "POST",
          body: JSON.stringify({ action: "activate", prompt_id: target.id }),
        },
        token,
      );
      setActivationTarget(null);
      if (await loadRegistry()) {
        setMessage(`${activated.key} v${activated.version} 已启用；同 key 的旧 active 修订已进入 retired。`);
        setMessageState("success");
      }
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "Prompt 修订启用失败。");
      setMessageState("error");
    } finally {
      setPending("");
    }
  }

  return (
    <section className="admin-panel prompt-registry-settings">
      <header>
        <div><h2>Prompt Registry</h2><p>仅 Superadmin 可管理。每次修改都会建立新版本，只有明确启用后才会被任务消费。</p></div>
        <ActionButton className="button secondary" state={loading ? "pending" : "idle"} pendingLabel="读取中" disabled={Boolean(pending)} onClick={() => void loadRegistry()}><RefreshCw size={14} />刷新</ActionButton>
      </header>
      <AsyncStatus state={messageState} message={message} />
      {payload ? (
        <>
          <form className="prompt-registry-form" onSubmit={createRevision}>
            <label><span>Research Task Profile</span><select value={draft.taskProfileKey} onChange={(event) => selectTaskProfile(event.target.value)}><option value="">不限定 Task Profile</option>{payload.active_task_profiles.map((profile) => <option key={profile.key} value={profile.key}>{profile.name} · {profile.key} v{profile.version}</option>)}</select></label>
            <label><span>Prompt key</span><input required maxLength={160} value={draft.key} onChange={(event) => setDraft({ ...draft, key: event.target.value })} placeholder="research.claim_stance" /></label>
            <label><span>AI capability</span><select value={draft.capability} onChange={(event) => setDraft({ ...draft, capability: event.target.value })}>{capabilities.map((capability) => <option key={capability} value={capability}>{CAPABILITY_LABELS[capability] ?? capability}</option>)}</select></label>
            <label className="prompt-registry-wide"><span>Prompt 内容</span><textarea required rows={10} value={draft.content} onChange={(event) => setDraft({ ...draft, content: event.target.value })} /></label>
            <label><span>输出 schema，JSON 对象</span><textarea rows={8} value={draft.outputSchema} onChange={(event) => setDraft({ ...draft, outputSchema: event.target.value })} /></label>
            <label><span>Provider 指引，JSON 对象</span><textarea rows={8} value={draft.providerGuidance} onChange={(event) => setDraft({ ...draft, providerGuidance: event.target.value })} /></label>
            <div className="prompt-registry-wide prompt-registry-form-actions"><ActionButton className="button" type="submit" state={pending === "create" ? "pending" : "idle"} pendingLabel="正在建立修订" disabled={Boolean(pending) || !draft.key.trim() || !draft.content.trim()}><Plus size={14} />建立草稿修订</ActionButton><small>保存草稿不会切换 active Prompt，也不会静默改变已经运行的任务。</small></div>
          </form>
          <div className="prompt-registry-revisions">
            {payload.results.map((row) => (
              <article key={row.id}>
                <header><div><strong>{row.key}</strong><span>v{row.version} · {CAPABILITY_LABELS[row.capability] ?? row.capability}</span></div><b className={row.status}>{row.status}</b></header>
                <p>{row.task_profile_key || "未限定 Task Profile"} · {row.content_hash.slice(0, 12)}</p>
                <small>{row.status === "active" ? `启用于 ${timeLabel(row.activated_at)}` : `建立于 ${timeLabel(row.created_at)}`}</small>
                <footer><button className="button secondary" type="button" onClick={() => reviseFrom(row)}>以此建立修订</button>{row.status !== "active" ? <button className="button" type="button" disabled={Boolean(pending)} onClick={() => setActivationTarget(row)}>启用此版本</button> : null}</footer>
              </article>
            ))}
            {!payload.results.length ? <p className="empty-state">尚无 Prompt 修订。可先运行 3.0 registry seed，再在这里建立新版本。</p> : null}
          </div>
        </>
      ) : loading ? <p className="admin-help">正在读取 Prompt Registry。</p> : null}
      <ConfirmDialog
        open={Boolean(activationTarget)}
        title={`启用 ${activationTarget?.key || "Prompt"} v${activationTarget?.version || ""}`}
        description="新任务会开始使用这一不可变修订，同 key 的当前 active 版本会进入 retired。已有 DerivedClaim 不会被改写。"
        confirmLabel="确认启用"
        pending={Boolean(activationTarget && pending === `activate:${activationTarget.id}`)}
        details={["不会修改 Canonical Knowledge", "不会自动重跑全馆 Claim", "需要重算时由增量任务明确触发"]}
        onCancel={() => setActivationTarget(null)}
        onConfirm={() => void activateRevision()}
      />
    </section>
  );
}
