from __future__ import annotations

from dataclasses import dataclass

from accounts.ownership import is_library_owner


class Capability:
    ACCESS_BACK_OFFICE = "access_back_office"
    UPLOAD = "can_upload"
    EDIT_METADATA = "can_edit_metadata"
    VIEW_EVIDENCE = "can_view_evidence"
    EDIT_DRAFT_AUTHORITY = "can_edit_draft_authority"
    CREATE_AUTHORITY = "can_create_authority"
    REVIEW_CANDIDATE = "can_review_candidate"
    PUBLISH_WORK = "can_publish_work"
    PUBLISH_AUTHORITY = "can_publish_authority"
    RUN_ENRICHMENT = "can_run_enrichment"
    RETRY_JOBS = "can_retry_jobs"
    MANAGE_SEARCH_RUNTIME = "can_manage_search_runtime"
    VIEW_QUERY_LEXICON = "can_view_query_lexicon"
    MANAGE_QUERY_LEXICON = "can_manage_query_lexicon"
    VIEW_SEMANTIC_INDEX = "can_view_semantic_index"
    MANAGE_SEMANTIC_INDEX = "can_manage_semantic_index"
    MANAGE_AI = "can_manage_ai"
    MANAGE_USERS = "can_manage_users"
    MANAGE_ROLES = "can_manage_roles"
    VIEW_SYSTEM_STATUS = "can_view_system_status"
    VIEW_AUDIT_LOG = "can_view_audit_log"
    RUN_BACKUP = "can_run_backup"
    DESTRUCTIVE_MAINTENANCE = "can_run_destructive_maintenance"
    VIEW_MIGRATIONS = "can_view_migrations"


STAFF_BASE = {
    Capability.ACCESS_BACK_OFFICE,
    Capability.VIEW_EVIDENCE,
}

ROLE_CAPABILITIES = {
    "reader": set(),
    "editor": STAFF_BASE
    | {
        Capability.UPLOAD,
        Capability.EDIT_METADATA,
        Capability.EDIT_DRAFT_AUTHORITY,
        Capability.CREATE_AUTHORITY,
        Capability.RUN_ENRICHMENT,
    },
    "reviewer": STAFF_BASE
    | {
        Capability.EDIT_METADATA,
        Capability.EDIT_DRAFT_AUTHORITY,
        Capability.REVIEW_CANDIDATE,
    },
    "admin": STAFF_BASE
    | {
        Capability.UPLOAD,
        Capability.EDIT_METADATA,
        Capability.EDIT_DRAFT_AUTHORITY,
        Capability.CREATE_AUTHORITY,
        Capability.REVIEW_CANDIDATE,
        Capability.PUBLISH_WORK,
        Capability.PUBLISH_AUTHORITY,
        Capability.RUN_ENRICHMENT,
        Capability.RETRY_JOBS,
        Capability.MANAGE_SEARCH_RUNTIME,
        Capability.VIEW_QUERY_LEXICON,
        Capability.VIEW_SEMANTIC_INDEX,
        Capability.VIEW_SYSTEM_STATUS,
        Capability.VIEW_AUDIT_LOG,
    },
}

SUPERADMIN_CAPABILITIES = ROLE_CAPABILITIES["admin"] | {
    Capability.MANAGE_QUERY_LEXICON,
    Capability.MANAGE_SEMANTIC_INDEX,
    Capability.MANAGE_AI,
    Capability.MANAGE_USERS,
    Capability.MANAGE_ROLES,
    Capability.RUN_BACKUP,
    Capability.DESTRUCTIVE_MAINTENANCE,
    Capability.VIEW_MIGRATIONS,
}


@dataclass(frozen=True, slots=True)
class CapabilitySnapshot:
    access_level: str
    capabilities: tuple[str, ...]

    def as_dict(self) -> dict:
        return {
            "access_level": self.access_level,
            "capabilities": list(self.capabilities),
        }


def capability_snapshot(user) -> CapabilitySnapshot:
    if not user or not getattr(user, "is_authenticated", False):
        return CapabilitySnapshot("anonymous", ())
    if getattr(user, "is_superuser", False) or is_library_owner(user):
        return CapabilitySnapshot("superadmin", tuple(sorted(SUPERADMIN_CAPABILITIES)))
    role = str(getattr(user, "role", "reader") or "reader")
    return CapabilitySnapshot(role, tuple(sorted(ROLE_CAPABILITIES.get(role, set()))))


def has_capability(user, capability: str) -> bool:
    return capability in capability_snapshot(user).capabilities
