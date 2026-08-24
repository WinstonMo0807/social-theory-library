"use client";

import { CheckCircle2, FlaskConical, Save, ServerCog, ShieldAlert } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { apiRequest, getServerSessionCredential } from "@/lib/api";
import { ActionButton, AsyncStatus, ToastHost, type ActionState } from "./action-feedback";

type ResearchSource = {
  key: string;
  label: string;
  category: string;
  purpose: string;
  affected_features: string[];
  metadata_formats: string[];
  execution_mode: string;
  usage_policy: string;
  configuration_requirements: string[];
  enabled: boolean;
  status: "configured" | "degraded" | "not_configured" | "disabled";
  configured_by: "database" | "environment";
  endpoint_configured: boolean;
  credential_configured: boolean;
  endpoint_alias_set: boolean;
  credential_alias_set: boolean;
  endpoint_alias_supported: boolean;
  credential_alias_supported: boolean;
  last_success_at: string | null;
  last_failure_at: string | null;
  last_error_code: string;
  last_error_category: string;
  secret_values_exposed: false;
};

type RegistryPayload = {
  version: string;
  generated_at: string;
  adapters: ResearchSource[];
  summary: {
    total: number;
    enabled: number;
    configured: number;
    degraded: number;
    chinese_extensions: number;
  };
  permissions: {
    can_edit: boolean;
    can_test: boolean;
    can_edit_sensitive_aliases: boolean;
  };
  secret_values_exposed: false;
};

type AliasDraft = { endpointAlias: string; credentialAlias: string };
type Feedback = { state: ActionState; actionKey: string; message: string };

const EMPTY_FEEDBACK: Feedback = { state: "idle", actionKey: "", message: "" };

const CATEGORY_LABELS: Record<string, string> = {
  authority: "Authority 与身份",
  bibliographic: "书目与版本",
  discovery: "Web discovery",
  evidence: "正文 Evidence",
  document: "文档结构",
  chinese_bibliographic: "中文公共来源扩展",
  licensed_chinese: "中文授权来源",
};

const STATUS_LABELS: Record<string, string> = {
  configured: "已配置",
  degraded: "降级",
  not_configured: "待配置",
  disabled: "已禁用",
};

function timeLabel(value: string | null) {
  if (!value) return "尚无成功记录";
  const parsed = new Date(value);
  return Number.isNaN(parsed.valueOf()) ? value : parsed.toLocaleString("zh-CN", { hour12: false });
}

export function ResearchSourceRegistryPanel({ revision = 0 }: { revision?: number }) {
  const [payload, setPayload] = useState<RegistryPayload | null>(null);
  const [drafts, setDrafts] = useState<Record<string, AliasDraft>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [pendingAction, setPendingAction] = useState("");
  const [feedback, setFeedback] = useState<Feedback>(EMPTY_FEEDBACK);
  const requestRef = useRef<Promise<void> | null>(null);

  const load = useCallback((): Promise<void> => {
    if (requestRef.current) return requestRef.current;
    const request = (async () => {
      const token = getServerSessionCredential();
      if (!token) {
        setError("登录状态尚未就绪，无法读取 Research Sources。");
        setLoading(false);
        return;
      }
      try {
        const result = await apiRequest<RegistryPayload>("/catalog/admin/research-sources/", {}, token);
        setPayload(result);
        setDrafts((current) => Object.fromEntries(result.adapters.map((row) => [
          row.key,
          current[row.key] ?? { endpointAlias: "", credentialAlias: "" },
        ])));
        setError("");
      } catch (reason) {
        setError(reason instanceof Error ? reason.message : "Research Sources 读取失败。");
      } finally {
        setLoading(false);
      }
    })();
    requestRef.current = request;
    void request.finally(() => {
      if (requestRef.current === request) requestRef.current = null;
    });
    return request;
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(timer);
  }, [load, revision]);

  const grouped = useMemo(() => {
    const result = new Map<string, ResearchSource[]>();
    for (const source of payload?.adapters ?? []) {
      const rows = result.get(source.category) ?? [];
      rows.push(source);
      result.set(source.category, rows);
    }
    return [...result.entries()];
  }, [payload?.adapters]);

  function actionState(actionKey: string): ActionState {
    if (pendingAction === actionKey) return "pending";
    return feedback.actionKey === actionKey ? feedback.state : "idle";
  }

  async function updateSource(source: ResearchSource, changes: Record<string, unknown>, actionKey: string) {
    const token = getServerSessionCredential();
    if (!token || pendingAction) return;
    setPendingAction(actionKey);
    setFeedback({ state: "pending", actionKey, message: `正在保存 ${source.label} 配置。` });
    try {
      const result = await apiRequest<RegistryPayload>(
        "/catalog/admin/research-sources/",
        {
          method: "PUT",
          body: JSON.stringify({ adapters: [{ key: source.key, ...changes }] }),
        },
        token,
      );
      setPayload(result);
      setDrafts((current) => ({ ...current, [source.key]: { endpointAlias: "", credentialAlias: "" } }));
      setFeedback({ state: "success", actionKey, message: `${source.label} 配置已保存。` });
    } catch (reason) {
      setFeedback({ state: "error", actionKey, message: reason instanceof Error ? reason.message : "来源配置保存失败。" });
    } finally {
      setPendingAction("");
    }
  }

  async function testSource(source: ResearchSource) {
    const token = getServerSessionCredential();
    const actionKey = `test:${source.key}`;
    if (!token || pendingAction) return;
    setPendingAction(actionKey);
    setFeedback({ state: "pending", actionKey, message: `正在测试 ${source.label}。` });
    try {
      const result = await apiRequest<{ status: string; productive: boolean | null; error_code: string }>(
        "/catalog/admin/research-sources/",
        {
          method: "POST",
          body: JSON.stringify({ action: "test", source_key: source.key }),
        },
        token,
      );
      setFeedback({
        state: result.status === "healthy" || result.status === "configured" ? "success" : "error",
        actionKey,
        message: result.status === "healthy" || result.status === "configured"
          ? `${source.label} 测试完成${result.productive === false ? "，连接可用但本次没有候选" : ""}。`
          : `${source.label} 当前${STATUS_LABELS[result.status] ?? result.status}${result.error_code ? `，${result.error_code}` : ""}。`,
      });
      await load();
    } catch (reason) {
      setFeedback({ state: "error", actionKey, message: reason instanceof Error ? reason.message : "来源测试失败。" });
    } finally {
      setPendingAction("");
    }
  }

  return (
    <section className="processing-diagnostics admin-panel" id="processing-research-sources" aria-labelledby="research-source-registry-title">
      <header>
        <div>
          <p>Research Sources</p>
          <h2 id="research-source-registry-title">研究来源与证据入口</h2>
          <span>先说明用途、配置和用户功能影响。测试只在明确点击后进行，密钥始终留在服务器环境中。</span>
        </div>
        {payload ? <span className={payload.summary.degraded ? "warning" : "healthy"}>{payload.summary.degraded ? `${payload.summary.degraded} 项降级` : `${payload.summary.configured} 项可用`}</span> : null}
      </header>

      <AsyncStatus state={loading && !payload ? "pending" : "idle"} message={loading && !payload ? "正在读取来源注册表……" : ""} />
      <AsyncStatus state="error" message={error} assertive />
      <ToastHost
        items={feedback.message ? [{ id: feedback.actionKey || "research-source", state: feedback.state === "idle" ? "success" : feedback.state, message: feedback.message }] : []}
        onDismiss={() => setFeedback(EMPTY_FEEDBACK)}
        label="Research Source 操作反馈"
      />

      {payload ? (
        <>
          <div className="processing-diagnostics-summary" aria-label="Research Source 摘要">
            <div><ServerCog size={17} /><span>已启用</span><strong>{payload.summary.enabled}</strong></div>
            <div><CheckCircle2 size={17} /><span>已配置</span><strong>{payload.summary.configured}</strong></div>
            <div><ShieldAlert size={17} /><span>降级</span><strong>{payload.summary.degraded}</strong></div>
            <div><FlaskConical size={17} /><span>中文扩展</span><strong>{payload.summary.chinese_extensions}</strong></div>
          </div>

          <div className="processing-diagnostic-sections">
            {grouped.map(([category, sources]) => (
              <section className="processing-diagnostic-section" key={category}>
                <header><div><ServerCog size={17} /><h3>{CATEGORY_LABELS[category] ?? category}</h3></div><span>{sources.length} 个 adapter</span><strong>{sources.filter((row) => row.enabled).length}</strong></header>
                <div className="processing-diagnostic-list">
                  {sources.map((source) => {
                    const draft = drafts[source.key] ?? { endpointAlias: "", credentialAlias: "" };
                    const saveChanges: Record<string, unknown> = {};
                    if (draft.endpointAlias.trim()) saveChanges.endpoint_alias = draft.endpointAlias.trim();
                    if (draft.credentialAlias.trim()) saveChanges.credential_alias = draft.credentialAlias.trim();
                    return (
                      <article className={`processing-diagnostic-item ${source.status === "configured" ? "info" : "warning"}`} key={source.key}>
                        <header><div><span>{source.category}</span><h4>{source.label}</h4></div><b>{STATUS_LABELS[source.status] ?? source.status}</b></header>
                        <p>{source.purpose}</p>
                        <dl>
                          <div><dt>受影响功能</dt><dd>{source.affected_features.join("、")}</dd></div>
                          <div><dt>配置需求</dt><dd>{source.configuration_requirements.join("、") || "无需额外配置"}</dd></div>
                          <div><dt>Endpoint</dt><dd>{source.endpoint_configured ? "已在服务器配置" : source.endpoint_alias_supported ? "未配置" : "固定来源或无需单独配置"}</dd></div>
                          <div><dt>Credential</dt><dd>{source.credential_configured ? "已在服务器配置" : source.credential_alias_set ? "alias 已设置，环境值缺失" : source.credential_alias_supported ? "未配置" : "无需 credential"}</dd></div>
                          <div><dt>最近成功</dt><dd>{timeLabel(source.last_success_at)}</dd></div>
                          <div><dt>最近错误</dt><dd>{source.last_error_category || "无持久化错误"}</dd></div>
                          <div><dt>使用边界</dt><dd>{source.usage_policy}</dd></div>
                          <div><dt>Metadata</dt><dd>{source.metadata_formats.join("、") || "不适用"}</dd></div>
                        </dl>
                        {payload.permissions.can_edit_sensitive_aliases ? (
                          <details>
                            <summary>配置服务器 alias</summary>
                            <div className="processing-runtime-rows">
                              {source.endpoint_alias_supported ? <label><span>Endpoint alias</span><input value={draft.endpointAlias} placeholder={source.endpoint_alias_set ? "已设置，留空保持不变" : "例如 ncpssd-public"} onChange={(event) => setDrafts((current) => ({ ...current, [source.key]: { ...draft, endpointAlias: event.target.value } }))} /></label> : null}
                              {source.credential_alias_supported ? <label><span>Credential alias</span><input value={draft.credentialAlias} placeholder={source.credential_alias_set ? "已设置，留空保持不变" : "只填环境变量别名"} onChange={(event) => setDrafts((current) => ({ ...current, [source.key]: { ...draft, credentialAlias: event.target.value } }))} /></label> : null}
                            </div>
                            <ActionButton className="button secondary" state={actionState(`save-alias:${source.key}`)} pendingLabel="正在保存" disabled={!Object.keys(saveChanges).length || Boolean(pendingAction)} onClick={() => void updateSource(source, saveChanges, `save-alias:${source.key}`)}><Save size={14} />保存 alias</ActionButton>
                          </details>
                        ) : <p><strong>敏感配置</strong>只有 System Owner 可以修改 endpoint 或 credential alias。</p>}
                        <footer>
                          {payload.permissions.can_test ? <ActionButton className="button secondary" state={actionState(`test:${source.key}`)} pendingLabel="测试中" disabled={Boolean(pendingAction)} onClick={() => void testSource(source)}><FlaskConical size={14} />测试</ActionButton> : null}
                          {payload.permissions.can_edit ? <ActionButton className="button secondary" state={actionState(`toggle:${source.key}`)} pendingLabel="正在保存" disabled={Boolean(pendingAction)} pressed={source.enabled} onClick={() => void updateSource(source, { enabled: !source.enabled }, `toggle:${source.key}`)}>{source.enabled ? "禁用" : "启用"}</ActionButton> : null}
                        </footer>
                      </article>
                    );
                  })}
                </div>
              </section>
            ))}
          </div>
        </>
      ) : null}
    </section>
  );
}
