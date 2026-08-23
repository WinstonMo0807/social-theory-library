"""Research orchestration package.

Callers import the concrete module they need. Keeping this package initializer
side-effect free prevents the legacy suggestion adapter from creating an
import cycle while it reads the shared field contract registry.
"""

__all__ = [
    "context",
    "contracts",
    "diagnostics",
    "entity_discovery",
    "orchestrator",
    "planner",
    "ranking",
    "recovery",
]
