"use client";

import Link from "next/link";
import { FormEvent, useEffect, useRef, useState } from "react";
import {
  Activity,
  ArrowRight,
  BookOpen,
  CheckCircle2,
  Cloud,
  KeyRound,
  Layers3,
  LoaderCircle,
  MessageCircle,
  Plus,
  Send,
  Settings2,
  ShieldCheck,
  Square,
  UserRound,
} from "lucide-react";
import { ApiRequestError, apiRequest, apiStreamRequest, getServerSessionCredential } from "@/lib/api";
import { useSessionBootstrap } from "@/lib/use-session-bootstrap";

type AssistMode = "auto" | "on" | "off";

type AssistantStatus = {
  configured: boolean;
  available: boolean;
  provider?: string;
  model?: string;
  detail?: string;
  user_configured?: boolean;
  api_key_configured?: boolean;
  base_url?: string;
  status?: string;
  effective_source?: "reader" | "server" | "reader_required" | "reader_optional";
  server_fallback_available?: boolean;
  personal_connection?: {
    configured?: boolean;
    status?: string;
    api_key_configured?: boolean;
  };
};

type ReaderConnectionDraft = {
  provider: string;
  base_url: string;
  model: string;
  api_key: string;
};

type Conversation = {
  id: string;
  title?: string;
  assist_mode?: AssistMode;
  scope?: LibraryScope;
  created_at?: string;
  updated_at?: string;
};

type LibraryMessage = {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  status?: string;
  retrieval_used?: boolean;
  source_count?: number;
  evidence_count?: number;
  insufficient_evidence?: boolean;
  query_type?: string;
  created_at?: string;
};

type LibrarySource = {
  id?: string;
  source_id?: string;
  citation_number?: number;
  ordinal?: number;
  title?: string;
  work_title?: string;
  page_index?: number;
  printed_label?: string;
  printed_page_label?: string;
  quote?: string;
  snippet?: string;
  reader_url?: string;
  available?: boolean;
  cited?: boolean;
  passage_language?: string;
  document_id?: string;
};

export type LibraryScope = {
  context: "global" | "works" | "scholars" | "disciplines" | "subdisciplines" | "theories" | "topics" | "reading_paths";
  ids?: string[];
  asset_id?: string;
  visibility?: "public";
};

const GLOBAL_LIBRARY_SCOPE: LibraryScope = { context: "global" };

type Collection<T> = T[] | { results?: T[]; configured?: boolean; available?: boolean };

type StreamEvent = "meta" | "delta" | "sources" | "done" | "error" | "message";

function collectionResults<T>(payload: Collection<T>) {
  return Array.isArray(payload) ? payload : payload.results ?? [];
}

function AskModeSwitch({ query }: { query: string }) {
  const suffix = query ? `?q=${encodeURIComponent(query)}` : "";
  return (
    <nav className="search-mode-switch" aria-label="检索方式">
      <Link href={`/explore/original${suffix}`}><span><strong>原文检索</strong></span></Link>
      <Link href={`/explore/opinions${suffix}`}><span><strong>观点检索</strong></span></Link>
      <Link className="active" href={`/explore/ask${suffix}`} aria-current="page"><span><strong>向书库提问</strong></span></Link>
    </nav>
  );
}

function AskLibraryIntro({ query }: { query: string }) {
  return (
    <section className="ask-library-intro">
      <div>
        <AskModeSwitch query={query} />
        <h1>向书库提问</h1>
        <span aria-hidden="true" />
        <p>基于已发布馆藏继续追问，并逐条核对回答所依据的来源。</p>
      </div>
      <div className="ask-library-intro-note">
        <strong>回答必须保留出处</strong>
        <p>书库问答只使用当前可访问的已发布馆藏。引用前仍需打开来源核对页码与上下文。</p>
      </div>
    </section>
  );
}

async function readEventStream(
  response: Response,
  onEvent: (event: StreamEvent, payload: Record<string, unknown>) => void,
) {
  if (!response.body) throw new Error("服务器没有返回可读取的流式响应。");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  const flush = (block: string) => {
    let event: StreamEvent = "message";
    const data: string[] = [];
    block.split(/\r?\n/).forEach((line) => {
      if (line.startsWith("event:")) event = line.slice(6).trim() as StreamEvent;
      if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
    });
    if (!data.length) return;
    let payload: Record<string, unknown> = {};
    try {
      const parsed = JSON.parse(data.join("\n"));
      payload = parsed && typeof parsed === "object" ? parsed as Record<string, unknown> : { text: String(parsed) };
    } catch {
      payload = { text: data.join("\n") };
    }
    onEvent(event, payload);
  };

  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value, { stream: !done }).replace(/\r\n/g, "\n");
    const blocks = buffer.split("\n\n");
    buffer = blocks.pop() ?? "";
    blocks.forEach(flush);
    if (done) break;
  }
  if (buffer.trim()) flush(buffer);
}

function responseError(payload: unknown, fallback: string) {
  if (!payload || typeof payload !== "object") return fallback;
  const record = payload as Record<string, unknown>;
  const detail = record.detail ?? record.error;
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object") {
    const nested = detail as Record<string, unknown>;
    if (typeof nested.detail === "string") return nested.detail;
  }
  return fallback;
}

function ReaderConnectionForm({
  draft,
  busy,
  onChange,
  onSave,
  onDelete,
}: {
  draft: ReaderConnectionDraft;
  busy: string;
  onChange: (field: keyof ReaderConnectionDraft, value: string) => void;
  onSave: () => void;
  onDelete: () => void;
}) {
  return (
    <div className="ask-reader-connection-form">
      <label><span>服务类型</span><select value={draft.provider} onChange={(event) => onChange("provider", event.target.value)}><option value="openai_compatible">OpenAI 兼容接口</option><option value="ollama">Ollama</option><option value="vllm">vLLM</option></select></label>
      <label><span>服务地址</span><input type="url" name="reader-ai-base-url" autoComplete="url" placeholder="https://api.example.com" value={draft.base_url} onChange={(event) => onChange("base_url", event.target.value)} /></label>
      <label><span>模型名称</span><input type="text" name="reader-ai-model" autoComplete="off" placeholder="例如 gpt-4o-mini" value={draft.model} onChange={(event) => onChange("model", event.target.value)} /></label>
      <label><span>API Key（Ollama 可留空）</span><input type="password" name="reader-ai-key" autoComplete="new-password" placeholder="只在保存时提交，不会回显" value={draft.api_key} onChange={(event) => onChange("api_key", event.target.value)} /></label>
      <div className="ask-reader-connection-actions"><button className="button" type="button" disabled={Boolean(busy) || !draft.base_url || !draft.model} onClick={onSave}>{busy === "save" ? "正在测试…" : "保存并测试"}</button><button className="button secondary" type="button" disabled={Boolean(busy)} onClick={onDelete}>删除个人配置</button></div>
    </div>
  );
}

export function ExploreAskClient({
  initialQuestion = "",
  initialScope = GLOBAL_LIBRARY_SCOPE,
}: {
  initialQuestion?: string;
  initialScope?: LibraryScope;
}) {
  const { state: sessionState, retry: retrySession } = useSessionBootstrap();
  const [state, setState] = useState<"checking" | "unauthenticated" | "forbidden" | "unconfigured" | "unavailable" | "ready" | "error">("checking");
  const [statusDetail, setStatusDetail] = useState("");
  const [modelLabel, setModelLabel] = useState("");
  const [effectiveSource, setEffectiveSource] = useState<AssistantStatus["effective_source"]>("reader_required");
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeConversationId, setActiveConversationId] = useState("");
  const [messages, setMessages] = useState<LibraryMessage[]>([]);
  const [draft, setDraft] = useState(initialQuestion);
  const [assistMode, setAssistMode] = useState<AssistMode>("auto");
  const [scope, setScope] = useState<LibraryScope>(initialScope);
  const [isSending, setIsSending] = useState(false);
  const [error, setError] = useState("");
  const [sources, setSources] = useState<{ messageId: string; loading: boolean; items: LibrarySource[] } | null>(null);
  const [streamingMessageId, setStreamingMessageId] = useState("");
  const [connectionDraft, setConnectionDraft] = useState<ReaderConnectionDraft>({
    provider: "openai_compatible",
    base_url: "",
    model: "",
    api_key: "",
  });
  const [connectionBusy, setConnectionBusy] = useState("");
  const abortRef = useRef<AbortController | null>(null);

  async function loadMessages(conversationId: string, token: string) {
    const payload = await apiRequest<Collection<LibraryMessage>>(
      `/reading/library-conversations/${conversationId}/messages/`,
      {},
      token,
    );
    setMessages(collectionResults(payload));
  }

  async function loadConversationList(token: string, selectFirst = false) {
    const payload = await apiRequest<Collection<Conversation>>("/reading/library-conversations/", {}, token);
    const items = collectionResults(payload);
    setConversations(items);
    if (selectFirst && items[0]) {
      setActiveConversationId(items[0].id);
      setAssistMode(items[0].assist_mode === "on" ? "on" : "auto");
      setScope(items[0].scope ?? initialScope);
      await loadMessages(items[0].id, token);
    }
  }

  useEffect(() => {
    let cancelled = false;
    if (sessionState.status === "loading" || sessionState.status === "unknown") {
      queueMicrotask(() => { if (!cancelled) setState("checking"); });
      return () => { cancelled = true; };
    }
    if (sessionState.status === "unauthenticated") {
      queueMicrotask(() => { if (!cancelled) setState("unauthenticated"); });
      return () => { cancelled = true; };
    }
    if (sessionState.status === "forbidden") {
      queueMicrotask(() => {
        if (!cancelled) {
          setState("forbidden");
          setStatusDetail(sessionState.message ?? "当前账户没有使用 Ask Library 的权限。");
        }
      });
      return () => { cancelled = true; };
    }
    if (sessionState.status === "temporary_error") {
      queueMicrotask(() => {
        if (!cancelled) {
          setState("error");
          setStatusDetail(sessionState.message ?? "认证服务暂时不可用。");
        }
      });
      return () => { cancelled = true; };
    }
    const token = getServerSessionCredential();
    if (!token || sessionState.status !== "authenticated") return () => { cancelled = true; };
    (async () => {
      let serviceState: typeof state = "ready";
      try {
        const service = await apiRequest<AssistantStatus>("/reading/library-assistant/status/", {}, token);
        if (cancelled) return;
        setStatusDetail(service.detail ?? "");
        setModelLabel([service.provider, service.model].filter(Boolean).join(" · "));
        setEffectiveSource(service.effective_source ?? (service.user_configured ? "reader" : "server"));
        if (service.user_configured || service.base_url || service.model) {
          setConnectionDraft((current) => ({
            ...current,
            provider: service.provider || current.provider,
            base_url: service.base_url || current.base_url,
            model: service.model || current.model,
          }));
        }
        if (!service.configured || service.status === "not_tested") {
          serviceState = "unconfigured";
        } else if (!service.available) {
          serviceState = "unavailable";
        }
      } catch (reason) {
        if (cancelled) return;
        if (reason instanceof ApiRequestError && reason.status === 401) {
          retrySession();
          setState("unauthenticated");
          return;
        }
        if (reason instanceof ApiRequestError && reason.status === 403) {
          setState("forbidden");
          setStatusDetail(reason.message);
          return;
        }
        if (reason instanceof ApiRequestError && reason.status === 404) {
          serviceState = "unconfigured";
          setStatusDetail("问答服务尚未启用，或当前版本没有配置模型接口。");
        } else if (reason instanceof ApiRequestError && reason.status === 503) {
          serviceState = "unavailable";
          setStatusDetail(reason.message);
        } else {
          serviceState = "error";
          setStatusDetail(reason instanceof Error ? reason.message : "暂时无法读取问答服务状态。");
        }
      }
      try {
        const conversationPayload = await apiRequest<Collection<Conversation>>(
          "/reading/library-conversations/",
          {},
          token,
        );
        const conversationItems = collectionResults(conversationPayload);
        if (cancelled) return;
        setConversations(conversationItems);
        if (conversationItems[0]) {
          const messagePayload = await apiRequest<Collection<LibraryMessage>>(
            `/reading/library-conversations/${conversationItems[0].id}/messages/`,
            {},
            token,
          );
          if (cancelled) return;
          setActiveConversationId(conversationItems[0].id);
          setAssistMode(conversationItems[0].assist_mode === "on" ? "on" : "auto");
          setScope(conversationItems[0].scope ?? initialScope);
          setMessages(collectionResults(messagePayload));
        }
        setState(serviceState);
      } catch (reason) {
        if (cancelled) return;
        if (reason instanceof ApiRequestError && reason.status === 401) {
          retrySession();
          setState("unauthenticated");
        } else if (reason instanceof ApiRequestError && reason.status === 403) {
          setState("forbidden");
          setError(reason.message);
        } else {
          setState(serviceState === "ready" ? "error" : serviceState);
          setError(reason instanceof Error ? reason.message : "暂时无法读取已保存会话。");
        }
      }
    })();
    return () => {
      cancelled = true;
      abortRef.current?.abort();
    };
  }, [initialScope, retrySession, sessionState.message, sessionState.status, sessionState.user?.role]);

  async function savePersonalConnection() {
    const token = getServerSessionCredential();
    if (!token) {
      setState("unauthenticated");
      return;
    }
    setConnectionBusy("save");
    setError("");
    try {
      const saved = await apiRequest<AssistantStatus>(
        "/reading/library-assistant/connection/",
        { method: "PUT", body: JSON.stringify({ ...connectionDraft, enabled: true }) },
        token,
      );
      setConnectionDraft((current) => ({ ...current, api_key: "" }));
      const tested = await apiRequest<AssistantStatus>(
        "/reading/library-assistant/connection/test/",
        { method: "POST" },
        token,
      );
      setStatusDetail(tested.detail || saved.detail || "已保存个人模型服务。");
      setModelLabel([tested.provider, tested.model].filter(Boolean).join(" · "));
      setEffectiveSource("reader");
      setState(tested.available ? "ready" : "unavailable");
    } catch (reason) {
      if (reason instanceof ApiRequestError && reason.status === 401) {
        retrySession();
        setState("unauthenticated");
      } else {
        setError(reason instanceof Error ? reason.message : "个人模型服务保存失败。");
      }
    } finally {
      setConnectionBusy("");
    }
  }

  async function removePersonalConnection() {
    const token = getServerSessionCredential();
    if (!token) return;
    setConnectionBusy("delete");
    try {
      await apiRequest("/reading/library-assistant/connection/", { method: "DELETE" }, token);
      setConnectionDraft({ provider: "openai_compatible", base_url: "", model: "", api_key: "" });
      setStatusDetail("个人模型服务已删除。");
      setEffectiveSource("reader_required");
      setState("unconfigured");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "个人模型服务删除失败。");
    } finally {
      setConnectionBusy("");
    }
  }

  async function chooseConversation(conversation: Conversation) {
    const token = getServerSessionCredential();
    if (!token) return setState("unauthenticated");
    setError("");
    setSources(null);
    setActiveConversationId(conversation.id);
    setAssistMode(conversation.assist_mode === "on" ? "on" : "auto");
    setScope(conversation.scope ?? initialScope);
    try {
      await loadMessages(conversation.id, token);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "会话读取失败。");
    }
  }

  async function createConversation(question?: string) {
    const token = getServerSessionCredential();
    if (!token) {
      setState("unauthenticated");
      return null;
    }
    const title = question?.trim().slice(0, 36) || "新对话";
    const conversation = await apiRequest<Conversation>(
      "/reading/library-conversations/",
      { method: "POST", body: JSON.stringify({ title, assist_mode: assistMode, scope }) },
      token,
    );
    setConversations((current) => [conversation, ...current.filter((item) => item.id !== conversation.id)]);
    setActiveConversationId(conversation.id);
    setMessages([]);
    setSources(null);
    return conversation;
  }

  async function startEmptyConversation() {
    if (state !== "ready") return;
    setError("");
    try {
      await createConversation();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "新建会话失败。");
    }
  }

  async function showSources(messageId: string) {
    const token = getServerSessionCredential();
    if (!token) return setState("unauthenticated");
    setSources({ messageId, loading: true, items: [] });
    try {
      const payload = await apiRequest<Collection<LibrarySource> & { evidence?: LibrarySource[] }>(
        `/reading/library-messages/${messageId}/sources/`,
        {},
        token,
      );
      const items = !Array.isArray(payload) && Array.isArray(payload.evidence)
        ? payload.evidence
        : collectionResults(payload);
      setSources({ messageId, loading: false, items });
    } catch (reason) {
      setSources({ messageId, loading: false, items: [] });
      setError(reason instanceof Error ? reason.message : "来源读取失败。");
    }
  }

  async function showSourceDetail(messageId: string, source: LibrarySource) {
    const token = getServerSessionCredential();
    const sourceId = source.id ?? source.source_id;
    if (!token) return setState("unauthenticated");
    if (!sourceId) return;
    try {
      const detail = await apiRequest<LibrarySource>(
        `/reading/library-messages/${messageId}/sources/${sourceId}/`,
        {},
        token,
      );
      setSources((current) => current && current.messageId === messageId ? {
        ...current,
        items: current.items.map((item) => (
          (item.id ?? item.source_id) === sourceId ? { ...item, ...detail } : item
        )),
      } : current);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "来源摘录读取失败。");
    }
  }

  async function stopGeneration() {
    const token = getServerSessionCredential();
    if (token && streamingMessageId && !streamingMessageId.startsWith("assistant-")) {
      try {
        await apiRequest(
          `/reading/library-messages/${streamingMessageId}/cancel/`,
          { method: "POST", body: JSON.stringify({}) },
          token,
        );
      } catch (reason) {
        setError(reason instanceof Error ? reason.message : "服务器未确认停止请求，已关闭本地连接。");
      }
    }
    abortRef.current?.abort();
  }

  async function submitQuestion(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const question = draft.trim();
    if (!question || isSending || state !== "ready") return;
    const token = getServerSessionCredential();
    if (!token) return setState("unauthenticated");
    setError("");
    setSources(null);
    setIsSending(true);
    setDraft("");
    try {
      const conversation = activeConversationId
        ? conversations.find((item) => item.id === activeConversationId) ?? { id: activeConversationId }
        : await createConversation(question);
      if (!conversation) return;
      const temporaryUserId = `user-${Date.now()}`;
      const temporaryAssistantId = `assistant-${Date.now()}`;
      setStreamingMessageId(temporaryAssistantId);
      setMessages((current) => [
        ...current,
        { id: temporaryUserId, role: "user", content: question, status: "complete" },
        { id: temporaryAssistantId, role: "assistant", content: "", status: "streaming" },
      ]);

      const controller = new AbortController();
      abortRef.current = controller;
      const response = await apiStreamRequest(`/reading/library-conversations/${conversation.id}/messages/stream/`, {
        method: "POST",
        signal: controller.signal,
        headers: {
          "Accept": "text/event-stream",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ question, assist_mode: assistMode, scope }),
      }, token);
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        if (response.status === 401) {
          retrySession();
          setState("unauthenticated");
        } else if (response.status === 403) {
          setState("forbidden");
        } else if (response.status === 429) {
          throw new Error("提问过于频繁，请稍后再试。登录状态未受影响。 ");
        }
        throw new Error(responseError(payload, `提问失败（${response.status}）。`));
      }

      let assistantId = temporaryAssistantId;
      let streamFailure = "";
      await readEventStream(response, (streamEvent, payload) => {
        if (streamEvent === "meta" && typeof payload.message_id === "string") {
          assistantId = payload.message_id;
          setStreamingMessageId(assistantId);
          setMessages((current) => current.map((message) => (
            message.id === temporaryAssistantId ? { ...message, id: assistantId } : message
          )));
        }
        if (streamEvent === "delta") {
          const text = typeof payload.text === "string" ? payload.text : "";
          setMessages((current) => current.map((message) => (
            [temporaryAssistantId, assistantId].includes(message.id)
              ? { ...message, content: message.content + text }
              : message
          )));
        }
        if (streamEvent === "sources") {
          const count = typeof payload.count === "number" ? payload.count : 0;
          const evidence = Array.isArray(payload.evidence)
            ? payload.evidence.filter((row): row is LibrarySource => Boolean(row && typeof row === "object"))
            : [];
          setMessages((current) => current.map((message) => (
            [temporaryAssistantId, assistantId].includes(message.id)
              ? { ...message, source_count: count, evidence_count: evidence.length }
              : message
          )));
          if (evidence.length) setSources({ messageId: assistantId, loading: false, items: evidence });
        }
        if (streamEvent === "done") {
          setMessages((current) => current.map((message) => (
            [temporaryAssistantId, assistantId].includes(message.id)
              ? { ...message, status: typeof payload.status === "string" ? payload.status : "complete" }
              : message
          )));
        }
        if (streamEvent === "error") {
          const code = typeof payload.code === "string" ? payload.code : "";
          streamFailure = typeof payload.detail === "string" ? payload.detail : "回答生成失败。";
          if (code === "ai_provider_rate_limited") {
            streamFailure = "模型服务请求频率受限，请稍后重试。登录状态未受影响。";
          }
        }
      });
      if (streamFailure) throw new Error(streamFailure);
      await Promise.all([
        loadMessages(conversation.id, token),
        loadConversationList(token),
      ]);
    } catch (reason) {
      setMessages((current) => current.map((message) => (
        message.status === "streaming" ? { ...message, status: "failed" } : message
      )));
      if (reason instanceof DOMException && reason.name === "AbortError") {
        setError("已停止本次生成，已经接收的内容仍会保留在会话中。");
      } else {
        setError(reason instanceof Error ? reason.message : "回答生成失败。");
      }
    } finally {
      abortRef.current = null;
      setStreamingMessageId("");
      setIsSending(false);
    }
  }

  if (state === "checking") {
    return <><AskLibraryIntro query={initialQuestion} /><section className="ask-library-state" aria-live="polite"><LoaderCircle className="spin" /><h2>正在检查问答服务…</h2></section></>;
  }

  if (state === "unauthenticated") {
    return (
      <>
        <AskLibraryIntro query={initialQuestion} />
        <section className="ask-library-state">
          <MessageCircle size={34} />
          <p>读者账户用于保存会话与来源记录。</p>
          <h2>登录后向书库提问</h2>
          <p>回答只在模型服务可用时生成，并保留可核查的馆藏来源。</p>
          <Link className="button" href="/login?next=/explore/ask">登录读者账户 <ArrowRight size={16} /></Link>
        </section>
      </>
    );
  }

  if (state === "forbidden") {
    return (
      <>
        <AskLibraryIntro query={initialQuestion} />
        <section className="ask-library-state" role="alert">
          <ShieldCheck size={34} />
          <h2>当前账户没有使用权限</h2>
          <p>{statusDetail || "你仍保持登录，可以继续阅读馆藏或返回账户中心。"}</p>
          <Link className="button secondary" href="/account">返回账户中心</Link>
        </section>
      </>
    );
  }

  if (state === "unconfigured" && !conversations.length) {
    return (
      <section className="ask-configuration-workspace" aria-labelledby="ask-configuration-heading">
        <aside className="ask-configuration-steps">
          <AskModeSwitch query={initialQuestion} />
          <h1 id="ask-configuration-heading">向书库提问</h1>
          <span aria-hidden="true" />
          <p>注册读者可以在本页配置自己的云端模型。密钥只会在本次请求中提交给书库服务器，并以加密形式保存，页面不会回显。</p>
          <p className="ask-configuration-step-label">启用步骤</p>
          <ol>
            <li><UserRound size={20} aria-hidden="true" /><p><strong>第 1 步　准备模型服务</strong><span>确认服务账户、使用范围与数据处理边界。</span></p></li>
            <li><Layers3 size={20} aria-hidden="true" /><p><strong>第 2 步　选择兼容接口</strong><span>可使用项目已支持的本地或兼容服务。</span></p></li>
            <li><KeyRound size={20} aria-hidden="true" /><p><strong>第 3 步　保存个人连接</strong><span>密钥只写入你的加密连接记录，不进入共享后台配置。</span></p></li>
            <li><Activity size={20} aria-hidden="true" /><p><strong>第 4 步　测试连接</strong><span>测试通过后即可直接询问已发布馆藏。</span></p></li>
            <li><CheckCircle2 size={20} aria-hidden="true" /><p><strong>第 5 步　开始馆藏问答</strong><span>回答保留馆藏来源，并允许返回原文。</span></p></li>
          </ol>
          <div className="ask-configuration-policy"><ShieldCheck size={18} aria-hidden="true" /><p><strong>安全边界</strong><span>密钥不会写入 Local Storage、会话正文或公开 API。书库只保存加密凭据摘要。</span></p></div>
        </aside>

        <div className="ask-configuration-panel">
          <header>
            <div><Cloud size={21} aria-hidden="true" /><p><strong>配置你的模型服务</strong><span>支持 OpenAI 兼容接口、Ollama 和 vLLM。书库只负责把馆藏证据交给你选择的模型。</span></p></div>
            <div className="ask-configuration-status" role="status"><span aria-hidden="true" /><p><strong>尚未配置</strong><small>{statusDetail || "服务端尚未提供可用的问答模型。"}</small></p></div>
          </header>
          <ReaderConnectionForm
            draft={connectionDraft}
            busy={connectionBusy}
            onChange={(field, value) => setConnectionDraft((current) => ({ ...current, [field]: value }))}
            onSave={() => void savePersonalConnection()}
            onDelete={() => void removePersonalConnection()}
          />
          <section className="ask-configuration-guidance">
            <Settings2 size={22} aria-hidden="true" />
            <div><h3>由你本人控制</h3><p>管理员不接收你的 API Key。保存并测试通过后，模型只会收到本次问题和已筛选的馆藏证据。</p></div>
          </section>
          <footer>
            <Link className="button secondary" href="/explore/opinions">暂用观点检索</Link>
            <p className="ask-configuration-contact">模型服务由你本人配置；管理员只负责书库权限和运行边界。</p>
          </footer>
          <small>已有会话与来源仍可在服务恢复后继续查看。管理员也可以随时更换服务器端配置。</small>
        </div>
      </section>
    );
  }

  const canGenerate = state === "ready";
  const degradedHeading = state === "unconfigured"
    ? "问答模型尚未配置"
    : state === "unavailable"
      ? "问答模型暂时不可用"
      : state === "error"
        ? "问答服务状态暂时无法确认"
        : "";

  return (
    <>
      <AskLibraryIntro query={initialQuestion} />
      <details className="ask-reader-connection-settings">
        <summary><Settings2 size={16} />个人模型设置{modelLabel ? ` · ${modelLabel}` : ""}</summary>
        <p>当前问答来源：{effectiveSource === "reader" ? "你的个人连接" : effectiveSource === "server" ? "书库默认服务" : "尚未配置个人连接"}。密钥只提交到书库服务器并加密保存，不写入浏览器存储。</p>
        <ReaderConnectionForm
          draft={connectionDraft}
          busy={connectionBusy}
          onChange={(field, value) => setConnectionDraft((current) => ({ ...current, [field]: value }))}
          onSave={() => void savePersonalConnection()}
          onDelete={() => void removePersonalConnection()}
        />
      </details>
      <div className="ask-library-workspace">
      <aside className="ask-conversation-list" aria-label="书库问答会话">
        <header>
          <div><span>会话列表</span>{modelLabel ? <small>{modelLabel}</small> : null}</div>
          <button type="button" disabled={!canGenerate} onClick={() => void startEmptyConversation()}><Plus size={16} />新建</button>
        </header>
        <div>
          {conversations.map((conversation) => (
            <button
              className={conversation.id === activeConversationId ? "active" : ""}
              type="button"
              onClick={() => void chooseConversation(conversation)}
              key={conversation.id}
            >
              <strong>{conversation.title || "未命名会话"}</strong>
              <small>{conversation.updated_at ? new Date(conversation.updated_at).toLocaleDateString("zh-CN") : "继续阅读"}</small>
            </button>
          ))}
          {!conversations.length ? <p>还没有会话。输入问题即可开始。</p> : null}
        </div>
      </aside>

      <main className="ask-chat-panel">
        <header>
          <div><p>向书库提问</p><h2>{conversations.find((item) => item.id === activeConversationId)?.title || "新对话"}</h2></div>
          <label>
            <span>馆藏辅助</span>
            <select value={assistMode} onChange={(event) => setAssistMode(event.target.value as AssistMode)} disabled={isSending || !canGenerate}>
              <option value="auto">自动</option>
              <option value="on">始终检索</option>
            </select>
          </label>
          <small className="ask-scope-label">范围 {scope.context === "global" ? "全馆" : scope.context}</small>
        </header>
        {!canGenerate ? (
          <div className="ask-service-notice" role="status">
            <strong>{degradedHeading}</strong>
            <span>{statusDetail || "已有会话与来源仍可查看，新提问暂时停用。"}</span>
            <Link href="/explore/opinions">转到观点检索 <ArrowRight size={14} /></Link>
          </div>
        ) : null}
        <section className="ask-message-list" aria-live="polite">
          {!messages.length ? (
            <div className="ask-empty-message">
              <MessageCircle size={28} />
              <h3>从馆藏中的一个问题开始</h3>
              <p>回答会在适用时检索已发布馆藏。引用前请打开来源核对上下文。</p>
            </div>
          ) : null}
          {messages.map((message) => (
            <article className={`ask-message ${message.role}`} key={message.id}>
              <span>{message.role === "user" ? "你" : "STL"}</span>
              <div>
                <p>{message.content || (message.status === "streaming" ? "正在生成……" : "暂无内容")}</p>
                {message.role === "assistant" ? (
                  <footer>
                    {message.insufficient_evidence ? <small>馆藏证据不足，未使用模型常识补答</small> : null}
                    {message.evidence_count || message.source_count ? (
                      <button type="button" onClick={() => void showSources(message.id)}>
                        <BookOpen size={14} />查看 {message.evidence_count ?? message.source_count} 条馆藏证据
                      </button>
                    ) : null}
                  </footer>
                ) : null}
              </div>
            </article>
          ))}
        </section>
        {error ? <p className="ask-error" role="alert">{error}</p> : null}
        <form className="ask-composer" onSubmit={submitQuestion}>
          <label htmlFor="library-question">继续提问</label>
          <textarea
            id="library-question"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            placeholder="输入问题，或继续追问馆藏中的概念与论证……"
            rows={3}
            disabled={isSending || !canGenerate}
          />
          <div>
            <small>模型输出可能有误，引用前请核对来源原文。</small>
            {isSending ? (
              <button type="button" className="button secondary" onClick={() => void stopGeneration()}><Square size={15} />停止</button>
            ) : (
              <button type="submit" className="button" disabled={!draft.trim() || !canGenerate}><Send size={15} />发送</button>
            )}
          </div>
        </form>
      </main>

      <aside className="ask-source-panel" aria-label="回答来源">
        <header><p>证据来源</p><h2>{sources ? `${sources.items.length} 条` : "按回答查看"}</h2></header>
        {!sources ? <p>点击回答下方的来源按钮，在这里核对馆藏、页码与原文片段。</p> : null}
        {sources?.loading ? <p>正在读取来源……</p> : null}
        {sources && !sources.loading && !sources.items.length ? <p>这条回答没有可展示的馆藏来源。</p> : null}
        <div>
          {sources?.items.map((source, index) => {
            const sourceId = source.id ?? source.source_id ?? String(index);
            const printedLabel = source.printed_label ?? source.printed_page_label;
            return (
              <article key={sourceId}>
                <span>[{source.citation_number ?? source.ordinal ?? index + 1}]</span>
                <h3>{source.work_title ?? source.title ?? "馆藏原文"}</h3>
                <p>{printedLabel ? `书页 ${printedLabel}` : source.page_index ? `PDF 第 ${source.page_index} 页` : "页码待核对"}</p>
                {source.passage_language ? <small>原文语言 {source.passage_language}</small> : null}
                {source.quote || source.snippet ? <blockquote>{source.quote ?? source.snippet}</blockquote> : null}
                {!source.quote && !source.snippet && source.available !== false && source.id ? (
                  <button type="button" onClick={() => void showSourceDetail(sources.messageId, source)}>查看摘录</button>
                ) : null}
                {source.available === false ? <small>该来源当前已下架或不可访问。</small> : null}
                {source.reader_url ? <Link href={source.reader_url}>查看原文 <ArrowRight size={14} /></Link> : null}
              </article>
            );
          })}
        </div>
      </aside>
      </div>
    </>
  );
}
