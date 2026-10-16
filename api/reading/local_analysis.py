"""Private structured analysis through the existing AI client, local hosts only."""
import ipaddress
import json
import socket
from urllib.parse import urlsplit

import httpx
from django.conf import settings

from ingestion.services.ai_client import AIClient, AIServiceError, AIServiceUnavailable, current_ai_configuration
from common.ai_runtime import AICapability


def require_local_endpoint(base_url, *, allowed_hosts=None):
    try:
        parsed = urlsplit(base_url)
        host = (parsed.hostname or "").casefold()
        if (parsed.scheme not in {"http", "https"} or not host or parsed.username or parsed.password
                or parsed.query or parsed.fragment or (parsed.port is not None and parsed.port < 1)):
            raise ValueError
    except ValueError as exc:
        raise AIServiceUnavailable("私人分析模型地址无效。") from exc
    allowed = allowed_hosts if allowed_hosts is not None else getattr(settings, "RESEARCH_LOCAL_AI_HOSTS", ("localhost", "127.0.0.1", "::1", "ollama", "vllm", "host.docker.internal", "discovery-inference"))
    if isinstance(allowed, str):
        allowed = [part.strip() for part in allowed.split(",")]
    def local_address(value):
        address = ipaddress.ip_address(value)
        networks = ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16") if address.version == 4 else ("fc00::/7",)
        return address.is_loopback or any(address in ipaddress.ip_network(network) for network in networks)
    try:
        local_ip = local_address(host)
    except ValueError:
        local_ip = False
    if host not in allowed and not local_ip:
        raise AIServiceUnavailable("私人分析仅允许本地模型；远程配置未使用。")
    if not local_ip:
        try:
            addresses = {item[4][0] for item in socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)}
            if not addresses or not all(local_address(address) for address in addresses):
                raise AIServiceUnavailable("私人分析模型地址未解析到本地网络。")
        except (OSError, ValueError) as exc:
            raise AIServiceUnavailable("本地模型主机暂不可解析。") from exc
        return sorted(addresses)[0]
    return host


class PrivateLocalTransport(httpx.HTTPTransport):
    """Pin one verified private origin while retaining its HTTP and TLS identity."""

    def __init__(self, base_url, *, allowed_hosts=None):
        self._address = require_local_endpoint(base_url, allowed_hosts=allowed_hosts)
        self._origin = httpx.URL(base_url)
        super().__init__(trust_env=False, verify=True)

    def handle_request(self, request):
        if (request.url.scheme, request.url.host, request.url.port) != (
                self._origin.scheme, self._origin.host, self._origin.port):
            raise AIServiceUnavailable("私人分析禁止跨来源请求。")
        request.headers["Host"] = self._origin.netloc.decode("ascii")
        request.extensions["sni_hostname"] = self._origin.host
        request.url = request.url.copy_with(host=self._address)
        return super().handle_request(request)


def generate_local(*, capability, task, prompt, payload, schema):
    config = current_ai_configuration(capability)
    if not config.enabled:
        raise AIServiceUnavailable("本地结构化模型未配置。")
    body = json.dumps(payload, ensure_ascii=False)
    if len(body) > config.max_input_chars:
        raise AIServiceUnavailable("材料超过本地模型上下文预算，已保留未分析状态。")
    # A supplied transport disables environment proxies and second hostname lookup.
    transport = PrivateLocalTransport(config.base_url)
    try:
        result = AIClient(config=config, transport=transport).generate_json(task=task,
            system_prompt=prompt, document_text=body, schema=schema, prompt_version="private-research-v1")
        return result.data, {"provider": result.provider, "model": result.model, "prompt_version": result.prompt_version}
    finally:
        transport.close()


def analyze_local_relations(statement, candidates):
    properties = {"reference_id": {"type": "string"}, "relation": {"type": "string", "enum": [
        "support", "different_conclusion", "qualification", "reframe", "insufficient_evidence"]},
        "reason": {"type": "string"}, "attribution": {"type": "string"}, "scope_difference": {"type": "string"}}
    schema = {"type": "object", "additionalProperties": False, "required": ["candidates"], "properties": {
        "candidates": {"type": "array", "items": {"type": "object", "additionalProperties": False,
        "required": list(properties), "properties": properties}}}}
    try:
        output, model = generate_local(capability=AICapability.CLAIM_STANCE, task="private_claim_relations",
            prompt="逐项比较命题与提供的原文。保留否定、时间、地域、对象和条件。区分作者主张、引述、转述与被批评观点。"
                   "引用 reference_id，不补写来源或原话。相似不等于支持或反证；材料不足时返回 insufficient_evidence。所有结果是待本人核对候选。",
            payload={"statement": statement, "evidence": candidates}, schema=schema)
    except AIServiceError:
        return [], {"status": "unavailable", "message": "本地关系分析未完成；原文与规则线索保留待核实。"}
    allowed = {row["reference_id"] for row in candidates}
    rows = [row for row in output["candidates"] if row["reference_id"] in allowed]
    return rows, {"status": "candidate", **model}


def propose_plan_labels(plan_data, memory_reminders):
    properties = {"item_id": {"type": "string"}, "stage": {"type": "string"},
        "reason": {"type": "string"}, "learning_goal": {"type": "string"}}
    schema = {"type": "object", "additionalProperties": False, "required": ["items"], "properties": {
        "items": {"type": "array", "items": {"type": "object", "additionalProperties": False,
        "required": list(properties), "properties": properties}}}}
    try:
        output, model = generate_local(capability=AICapability.READING_PATH_GENERATION,
            task="private_plan_labels", prompt="仅为已选材料建议阶段名、学习目标与推荐理由。引用给定 item_id。"
            "不新造书名、阅读时间、先修关系或本人已经理解的内容；私人认识仅作可解释提醒，不视为正确答案。",
            payload={"goal": plan_data["goal"], "background": plan_data.get("background", ""),
                "time_budget": plan_data.get("time_budget", ""),
                "items": [{"item_id": row["id"], "title": row["title"], "reason": row["reason"]} for row in plan_data["items"][:30]],
                "memory_reminders": memory_reminders}, schema=schema)
    except AIServiceError:
        return [], {"status": "unavailable", "message": "本地模型未补充阶段建议；已保存规则生成的材料顺序。"}
    allowed = {row["id"] for row in plan_data["items"][:30]}
    return [{key: str(value)[:2000] for key, value in row.items()} for row in output["items"] if row["item_id"] in allowed], {"status": "candidate", **model}


def plan_followup(question, history, selected_evidence):
    schema = {"type": "object", "additionalProperties": False, "required": ["query", "reason"],
        "properties": {"query": {"type": "string"}, "reason": {"type": "string"}}}
    try:
        output, model = generate_local(capability=AICapability.LIBRARY_QA, task="private_followup_query",
            prompt="把当前追问解析为可检索的问题，只使用所给相关历史与当前选材澄清指代。保留否定、对象、时间、地域和条件。"
                   "不得添加历史或材料中没有的书名、人物或结论，不改变搜索范围。只返回 query 与简短 reason。",
            payload={"question": question, "history": history, "selected_evidence": selected_evidence}, schema=schema)
        query = output["query"].strip()
        if 2 <= len(query) <= 1200:
            return {"query": query, "method": "local_model", "reason": output["reason"][:1000], "model": model}
    except AIServiceError:
        pass
    previous = history[-1]["question"] if history else ""
    query = (previous + "\n" + question) if previous and previous != question and len(previous) + len(question) < 1200 else question
    return {"query": query, "method": "explicit_history_fallback",
        "reason": "本地指代解析未完成，保留原追问与可容纳的上一轮问题；范围不变。"}
