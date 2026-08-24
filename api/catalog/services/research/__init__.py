"""Research orchestration package.

Callers import the concrete module they need. Keeping this package initializer
side-effect free prevents the legacy suggestion adapter from creating an
import cycle while it reads the shared field contract registry.
"""

__all__ = [
    "context",
    "contracts",
    "candidate_adoption",
    "diagnostics",
    "evidence_pack",
    "entity_discovery",
    "feedback",
    "orchestrator",
    "planner",
    "prompt_registry",
    "ranking",
    "recovery",
    "task_profiles",
]
