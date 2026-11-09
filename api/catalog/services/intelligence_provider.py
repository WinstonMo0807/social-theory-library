"""Fixed DocETL map operator, delegating transport and budgets to STL.

The API adapter intentionally bypasses DocETL APIWrapper: its truncate_messages,
cloud embedding defaults, cache, gleaning and retry loops are never entered.
Only the worker imports DocETL. There is no LiteLLM proxy or extra credential.
"""
import io
from types import SimpleNamespace
from importlib.metadata import version
from ingestion.services.ai_client import AIClient, AIInvalidOutput, current_ai_configuration
from common.ai_runtime import AICapability

PROMPT_VERSION = "stl-intelligence-v1"
SYSTEM = "你是有来源约束的学术编纂助手。区分主张者、作者、被引述和被批评者。只输出给定结构中的候选。没有证据则保留空数组，不补造身份、引文、偏移或关系。"


def configuration(profile_key=""):
    return current_ai_configuration(AICapability.CURATION_REASONING, profile_key or None)


def identity(config):
    from catalog.services.knowledge_sources import digest
    return {"provider": config.provider, "model": config.model, "profile_key": config.profile_key,
            "transport_fingerprint": digest(config.base_url), "reasoning": config.reasoning,
            "capability": config.capability, "max_input_chars": config.max_input_chars,
            "max_output_tokens": config.max_output_tokens, "temperature": config.temperature}


class STLMapAPI:
    def __init__(self, config, schema):
        self.client = AIClient(config=config)
        self.schema = schema
        self.results = []

    def call_llm(self, model, op_type, messages, output_schema, **kwargs):
        from docetl.operations.utils.llm import LLMResult
        if model != self.client.config.model or op_type != "map":
            raise AIInvalidOutput("DocETL试图使用未指定的模型或操作。")
        if kwargs.get("tools") or kwargs.get("gleaning_config") or kwargs.get("agent_config"):
            raise AIInvalidOutput("本任务未启用工具、代理或附加推理。")
        text = "\n".join(m["content"] for m in messages)
        result = self.client.generate_json(task="STL Intelligence", system_prompt=SYSTEM, document_text=text,
            schema=self.schema, prompt_version=PROMPT_VERSION, strict=True)
        self.results.append(result)
        # DocETL cost accounting is not authoritative for this transport.
        # Actual usage is returned separately; unknown monetary cost stays null.
        return LLMResult(response=result.data, total_cost=0.0, validated=True)


def map_analysis(config, prompt, data, schema):
    if version("docetl") != "0.3.0":
        raise AIInvalidOutput("策展执行器需要已验证的DocETL 0.3.0。")
    from rich.console import Console
    from docetl.operations.map import MapOperation
    api = STLMapAPI(config, schema)
    runner = SimpleNamespace(config={"bypass_cache": True}, api=api, is_cancelled=False)
    operation = MapOperation(runner, {"name": "stl_chapter", "type": "map", "model": config.model,
        "prompt": prompt + "\n<source_data>{{ input.source }}</source_data>",
        "output": {"schema": {key: "string" for key in schema.get("properties", {})}},
        "max_batch_size": 1, "num_retries_on_validate_failure": 0, "max_retries_per_timeout": 0,
        "skip_on_error": False, "calibrate": False, "bypass_cache": True},
        default_model=config.model, max_threads=1, console=Console(file=io.StringIO()))
    rows, _ = operation.execute([{"source": data}])
    if len(rows) != 1 or len(api.results) != 1:
        raise AIInvalidOutput("DocETL没有返回完整单窗口结果。")
    return api.results[0]
