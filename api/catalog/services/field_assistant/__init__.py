from .contracts import FIELD_ASSISTANT_VERSION, FieldAssistantRequest, FieldAssistantResult
from .policies import AssistantFieldPolicy, available_field_policies, get_field_policy


def __getattr__(name):
    # Contracts are also imported by the canonical catalogue service. Resolve
    # the legacy facade lazily so importing those contracts cannot re-enter it.
    if name in {"FieldAssistantError", "FieldAssistantService"}:
        from . import service
        return getattr(service, name)
    raise AttributeError(name)

__all__ = [
    "AssistantFieldPolicy",
    "FIELD_ASSISTANT_VERSION",
    "FieldAssistantRequest",
    "FieldAssistantResult",
    "FieldAssistantError",
    "FieldAssistantService",
    "available_field_policies",
    "get_field_policy",
]
