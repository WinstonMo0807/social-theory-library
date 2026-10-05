"use client";

import { ChevronRight, FlaskConical, Save, Info } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
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
  credential_updated_at: string | null;
  credential_last_tested_at: string | null;
  credential_last_test_status: string;
  credential_last_test_message: string;
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

type AliasDraft = { endpointAlias: string; credentialAlias: string; credentialValue: string };
type Feedback = { state: ActionState; actionKey: string; message: string };

type ProviderSecretRegistry = {
  secrets: Array<{
    alias: string;
    purpose: "research_source" | "ai_runtime";
    provider_key: string;
    configured: boolean;
    updated_at: string;
    last_tested_at: string | null;
    last_test_status: string;
    secret_values_exposed: false;
  }>;
  secret_values_exposed: false;
};

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

function credentialTimeLabel(value: string | null, emptyLabel: string) {
  if (!value) return emptyLabel;
  const parsed = new Date(value);
  return Number.isNaN(parsed.valueOf()) ? value : parsed.toLocaleString("zh-CN", { hour12: false });
}

export function ResearchSourceRegistryPanel({ revision = 0 }: { revision?: number }) {
  const [selectedKey, setSelectedKey] = useState("");
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
        let storedAliases: Record<string, string> = {};
        if (result.permissions.can_edit_sensitive_aliases) {
          const secretRegistry = await apiRequest<ProviderSecretRegistry>(
            "/catalog/admin/provider-secrets/",
            {},
            token,
          );
          storedAliases = Object.fromEntries(
            secretRegistry.secrets
              .filter((row) => row.purpose === "research_source" && row.configured && row.provider_key)
              .map((row) => [row.provider_key, row.alias]),
          );
        }
        setDrafts((current) => Object.fromEntries(result.adapters.map((row) => [
          row.key,
          current[row.key] ?? {
            endpointAlias: "",
            credentialAlias: storedAliases[row.key] ?? "",
            credentialValue: "",
          },
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
      setDrafts((current) => ({
        ...current,
        [source.key]: {
          endpointAlias: "",
          credentialAlias: current[source.key]?.credentialAlias ?? "",
          credentialValue: "",
        },
      }));
      setFeedback({ state: "success", actionKey, message: `${source.label} 配置已保存。` });
    } catch (reason) {
      setFeedback({ state: "error", actionKey, message: reason instanceof Error ? reason.message : "来源配置保存失败。" });
    } finally {
      setPendingAction("");
    }
  }

  async function storeCredential(source: ResearchSource) {
    const token = getServerSessionCredential();
    const draft = drafts[source.key];
    const actionKey = `credential:${source.key}`;
    if (!token || !draft?.credentialValue || pendingAction) return;
    const alias = draft.credentialAlias.trim() || `source-${source.key.replaceAll("_", "-")}`;
    setPendingAction(actionKey);
    setFeedback({ state: "pending", actionKey, message: `正在安全保存 ${source.label} 凭据。` });
    try {
      await apiRequest<ProviderSecretRegistry>(
        "/catalog/admin/provider-secrets/",
        {
          method: "POST",
          body: JSON.stringify({
            action: "set",
            alias,
            purpose: "research_source",
            provider_key: source.key,
            secret: draft.credentialValue,
          }),
        },
        token,
      );
      const result = await apiRequest<RegistryPayload>(
        "/catalog/admin/research-sources/",
        {
          method: "PUT",
          body: JSON.stringify({ adapters: [{ key: source.key, enabled: true, credential_alias: alias }] }),
        },
        token,
      );
      setPayload(result);
      setDrafts((current) => ({
        ...current,
        [source.key]: { ...current[source.key], credentialAlias: alias, credentialValue: "" },
      }));
      setFeedback({ state: "success", actionKey, message: `${source.label} 凭据已加密保存，浏览器不会读取原值。` });
    } catch (reason) {
      setFeedback({ state: "error", actionKey, message: reason instanceof Error ? reason.message : "凭据保存失败。" });
    } finally {
      setPendingAction("");
    }
  }

  async function deleteCredential(source: ResearchSource) {
    const token = getServerSessionCredential();
    const alias = drafts[source.key]?.credentialAlias.trim();
    const actionKey = `credential-delete:${source.key}`;
    if (!token || !alias || pendingAction) return;
    if (!window.confirm(`确认删除 ${source.label} 的服务器凭据吗？删除后，依赖该凭据的研究功能会降级，原值无法从浏览器恢复。`)) return;
    setPendingAction(actionKey);
    setFeedback({ state: "pending", actionKey, message: `正在删除 ${source.label} 的服务器凭据。` });
    try {
      await apiRequest<ProviderSecretRegistry>(
        "/catalog/admin/provider-secrets/",
        { method: "POST", body: JSON.stringify({ action: "delete", alias }) },
        token,
      );
      setDrafts((current) => ({
        ...current,
        [source.key]: { ...current[source.key], credentialAlias: "", credentialValue: "" },
      }));
      setFeedback({ state: "success", actionKey, message: `${source.label} 的服务器凭据已删除。` });
      await load();
    } catch (reason) {
      setFeedback({ state: "error", actionKey, message: reason instanceof Error ? reason.message : "凭据删除失败。" });
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

  const source = payload?.adapters.find(row => row.key === selectedKey) ?? payload?.adapters[0];
  const draft = source ? drafts[source.key] ?? { endpointAlias: "", credentialAlias: "", credentialValue: "" } : null;
  const saveChanges: Record<string, unknown> = {};
  if (draft?.endpointAlias.trim()) saveChanges.endpoint_alias = draft.endpointAlias.trim();
  if (draft?.credentialAlias.trim()) saveChanges.credential_alias = draft.credentialAlias.trim();

  return <section className="source-reference" id="processing-research-sources" aria-label="资料来源">
    <div className="source-reference-intro"><p>配置和管理外部资料来源，用于在查找书目信息时获取作者、书名、出版社等数据。<br/>这些来源的结果仅作为填写建议，不会直接在网站前台显示。</p><aside><Info size={19}/><div><strong>读者影响</strong><p>来源提供的书目信息仅用于编辑时的填写参考，不会直接显示在网站上。</p></div></aside></div>
    <AsyncStatus state={loading && !payload ? "pending" : "idle"} message={loading && !payload ? "正在读取资料来源…" : ""}/>
    <AsyncStatus state="error" message={error} assertive/>
    <ToastHost items={feedback.message ? [{ id: feedback.actionKey || "research-source", state: feedback.state === "idle" ? "success" : feedback.state, message: feedback.message }] : []} onDismiss={() => setFeedback(EMPTY_FEEDBACK)} label="资料来源操作反馈"/>
    {payload ? <div className="source-reference-columns">
      <section className="source-reference-list"><header><h2>来源列表（{payload.adapters.length}）</h2><button type="button" className="button" disabled title="当前接口不支持添加自定义来源">＋ 添加来源</button></header>
        <div role="list" aria-label="已登记资料来源">{payload.adapters.map(row => <button role="listitem" type="button" key={row.key} className={source?.key === row.key ? "selected" : ""} onClick={() => setSelectedKey(row.key)} aria-pressed={source?.key === row.key}>
          <span><strong>{row.label}</strong><small>{CATEGORY_LABELS[row.category] ?? row.category}</small></span><span><b className={`source-state ${row.status}`}>{STATUS_LABELS[row.status] ?? row.status}</b><small>上次检查：{credentialTimeLabel(row.credential_last_tested_at, "未检查")}</small></span><ChevronRight size={16}/>
        </button>)}</div>
      </section>
      {source && draft ? <section className="source-reference-detail" aria-label={`${source.label}设置`}>
        <header><div><h2>{source.label}</h2><b className={`source-state ${source.status}`}>{STATUS_LABELS[source.status] ?? source.status}</b></div>{payload.permissions.can_edit ? <ActionButton className="button secondary" state={actionState(`toggle:${source.key}`)} pendingLabel="正在保存" disabled={Boolean(pendingAction)} onClick={() => void updateSource(source, { enabled: !source.enabled }, `toggle:${source.key}`)}>{source.enabled ? "禁用" : "启用"}</ActionButton> : null}</header>
        <p>{source.purpose}</p>
        <section className="source-reference-status"><h3>当前状态</h3><div><dl><div><dt>上次检查</dt><dd>{credentialTimeLabel(source.credential_last_tested_at, "未检查")}</dd></div><div><dt>连接状态</dt><dd>{source.credential_last_test_status || "—"}</dd></div><div><dt>返回结果</dt><dd>{source.credential_last_test_message || "—"}</dd></div></dl>{payload.permissions.can_test ? <ActionButton className="button" state={actionState(`test:${source.key}`)} pendingLabel="检查中" disabled={Boolean(pendingAction)} onClick={() => void testSource(source)}><FlaskConical size={15}/>检查连接</ActionButton> : null}</div></section>
        <section className="source-reference-settings"><h3>设置</h3><label><input type="checkbox" checked={source.enabled} disabled={!payload.permissions.can_edit || Boolean(pendingAction)} onChange={event => void updateSource(source, { enabled: event.target.checked }, `toggle:${source.key}`)}/><span>启用此来源<small>启用后，将在查找书目信息时使用此来源。</small></span></label><label><input type="checkbox" checked={false} disabled/><span>在查找结果中优先显示此来源的内容<small>—</small></span></label></section>
        <details className="source-reference-advanced"><summary>高级设置<span>技术地址、访问凭据等</span></summary>
          <dl><div><dt>受影响功能</dt><dd>{source.affected_features.join("、") || "—"}</dd></div><div><dt>配置需求</dt><dd>{source.configuration_requirements.join("、") || "无需额外配置"}</dd></div><div><dt>技术地址</dt><dd>{source.endpoint_configured ? "已在服务器配置" : source.endpoint_alias_supported ? "未配置" : "无需单独配置"}</dd></div><div><dt>访问凭据</dt><dd>{source.credential_configured ? "已安全保存" : source.credential_alias_supported ? "未配置" : "无需凭据"}</dd></div><div><dt>最近成功</dt><dd>{timeLabel(source.last_success_at)}</dd></div><div><dt>最近错误</dt><dd>{source.last_error_category || "—"}</dd></div><div><dt>使用边界</dt><dd>{source.usage_policy}</dd></div></dl>
          {payload.permissions.can_edit_sensitive_aliases ? <div className="processing-runtime-rows">
            {source.endpoint_alias_supported ? <label><span>地址别名</span><input value={draft.endpointAlias} placeholder={source.endpoint_alias_set ? "已设置，留空保持不变" : "服务器地址别名"} onChange={event => setDrafts(current => ({ ...current, [source.key]: { ...draft, endpointAlias: event.target.value } }))}/></label> : null}
            {source.credential_alias_supported ? <label><span>凭据别名</span><input value={draft.credentialAlias} placeholder="只填服务器凭据别名" onChange={event => setDrafts(current => ({ ...current, [source.key]: { ...draft, credentialAlias: event.target.value } }))}/></label> : null}
            <ActionButton className="button secondary" state={actionState(`save-alias:${source.key}`)} pendingLabel="正在保存" disabled={!Object.keys(saveChanges).length || Boolean(pendingAction)} onClick={() => void updateSource(source, saveChanges, `save-alias:${source.key}`)}><Save size={14}/>保存设置</ActionButton>
            {source.credential_alias_supported ? <><label><span>访问凭据</span><input type="password" autoComplete="new-password" value={draft.credentialValue} placeholder={source.credential_configured ? "输入新值可更新，原值不会显示" : "输入 API Key 或 Token"} onChange={event => setDrafts(current => ({ ...current, [source.key]: { ...draft, credentialValue: event.target.value } }))}/></label><div className="admin-action-row"><ActionButton className="button secondary" state={actionState(`credential:${source.key}`)} pendingLabel="正在保存" disabled={!draft.credentialValue || Boolean(pendingAction)} onClick={() => void storeCredential(source)}>加密保存凭据</ActionButton>{source.credential_configured && draft.credentialAlias ? <ActionButton className="button secondary" state={actionState(`credential-delete:${source.key}`)} disabled={Boolean(pendingAction)} onClick={() => void deleteCredential(source)}>删除服务器凭据</ActionButton> : null}</div></> : null}
          </div> : <p>当前账户不能修改技术地址或访问凭据。</p>}
        </details>
        <aside className="source-reference-note"><Info size={19}/><div><strong>使用提示</strong><p>如果连接检查失败，请确认网络是否正常，或稍后再试。频繁检查可能会被对方服务暂时限制。</p></div></aside>
      </section> : <p className="empty-state">—</p>}
    </div> : null}
  </section>;
}
