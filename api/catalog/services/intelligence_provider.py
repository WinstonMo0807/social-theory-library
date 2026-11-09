"""Fixed DocETL map operator, delegating transport and budgets to STL.

The API adapter intentionally bypasses DocETL APIWrapper: its truncate_messages,
cloud embedding defaults, cache, gleaning and retry loops are never entered.
Only the worker imports DocETL. There is no LiteLLM proxy or extra credential.
"""
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


def map_analysis(config, prompt, data, schema):
    from common.docetl_map import run_map
    client = AIClient(config=config)
    return run_map(config.model,prompt,data,schema,lambda text:client.generate_json(
        task="STL Intelligence",system_prompt=SYSTEM,document_text=text,
        schema=schema,prompt_version=PROMPT_VERSION,strict=True))
