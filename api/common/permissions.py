from rest_framework.permissions import BasePermission

from .capabilities import Capability, capability_snapshot, has_capability


class RequiresCapability(BasePermission):
    capability = ""

    def has_permission(self, request, view):
        return bool(self.capability and has_capability(request.user, self.capability))


class CanAccessBackOffice(RequiresCapability):
    capability = Capability.ACCESS_BACK_OFFICE
    message = "当前账户不能访问管理后台。"


class CanViewEvidence(RequiresCapability):
    capability = Capability.VIEW_EVIDENCE
    message = "当前账户不能查看审核证据。"


class CanReviewCandidate(RequiresCapability):
    capability = Capability.REVIEW_CANDIDATE
    message = "仅 Editor 或 Administrator 可以决定候选。"


class CanReviewCandidateOrCreateAuthority(BasePermission):
    """Allow the explicit draft-creation branch to editors without granting review."""

    message = "当前账户不能执行该候选审核动作。"

    def has_permission(self, request, view):
        if has_capability(request.user, Capability.REVIEW_CANDIDATE):
            return True
        return (
            str(request.data.get("action") or "").strip().casefold() == "create_draft"
            and has_capability(request.user, Capability.CREATE_AUTHORITY)
        )


class CanManageQueryLexicon(RequiresCapability):
    capability = Capability.MANAGE_QUERY_LEXICON
    message = "只有 System Owner 可以执行 QueryLexicon reconciliation。"


class CanViewQueryLexicon(RequiresCapability):
    capability = Capability.VIEW_QUERY_LEXICON
    message = "当前账户不能查看 QueryLexicon 状态。"


class CanViewSystemStatus(RequiresCapability):
    capability = Capability.VIEW_SYSTEM_STATUS
    message = "当前账户不能查看系统状态。"


class CanRunBackup(RequiresCapability):
    capability = Capability.RUN_BACKUP
    message = "只有 System Owner 可以运行正式备份。"


class CanUpload(RequiresCapability):
    capability = Capability.UPLOAD
    message = "当前账户不能上传馆藏文件。"


class CanEditMetadata(RequiresCapability):
    capability = Capability.EDIT_METADATA
    message = "当前账户不能编辑馆藏元数据。"


class CanCreateAuthority(RequiresCapability):
    capability = Capability.CREATE_AUTHORITY
    message = "当前账户不能创建 authority 草稿。"


class CanPublishWork(RequiresCapability):
    capability = Capability.PUBLISH_WORK
    message = "当前账户不能发布馆藏。"


class CanPublishAuthority(RequiresCapability):
    capability = Capability.PUBLISH_AUTHORITY
    message = "当前账户不能发布 authority。"


class CanRunEnrichment(RequiresCapability):
    capability = Capability.RUN_ENRICHMENT
    message = "当前账户不能运行 enrichment。"


class CanRetryJobs(RequiresCapability):
    capability = Capability.RETRY_JOBS
    message = "当前账户不能重试处理任务。"


class CanManageSemanticIndex(RequiresCapability):
    capability = Capability.MANAGE_SEMANTIC_INDEX
    message = "只有 System Owner 可以切换 semantic index。"


class CanViewSemanticIndex(RequiresCapability):
    capability = Capability.VIEW_SEMANTIC_INDEX
    message = "当前账户不能查看 semantic index 状态。"


class CanManageAI(RequiresCapability):
    capability = Capability.MANAGE_AI
    message = "当前账户不能管理非敏感 AI runtime 配置。"


class CanConfigureProviders(RequiresCapability):
    capability = Capability.CONFIGURE_PROVIDERS
    message = "当前账户不能配置非敏感 Provider 参数。"


class CanManageProviders(RequiresCapability):
    capability = Capability.MANAGE_AI_PROVIDERS
    message = "只有 System Owner 可以执行 Provider 删除或敏感管理。"


class CanManageModels(RequiresCapability):
    capability = Capability.MANAGE_AI_MODELS
    message = "只有 System Owner 可以管理 AI 模型。"


class CanManagePromptRegistry(RequiresCapability):
    capability = Capability.MANAGE_PROMPT_REGISTRY
    message = "只有 System Owner 可以管理 Prompt Registry。"


class CanManageGlobalProjection(RequiresCapability):
    capability = Capability.MANAGE_GLOBAL_PROJECTION
    message = "只有 System Owner 可以执行全局 Projection 操作。"


class CanMergeAuthority(RequiresCapability):
    capability = Capability.MERGE_AUTHORITY
    message = "只有 System Owner 可以合并 Authority。"


class CanRunSystemRecovery(RequiresCapability):
    capability = Capability.RUN_SYSTEM_RECOVERY
    message = "只有 System Owner 可以执行全局系统恢复。"


class CanRunDestructiveMaintenance(RequiresCapability):
    capability = Capability.DESTRUCTIVE_MAINTENANCE
    message = "只有 System Owner 可以执行破坏性维护。"


class CanManageUsers(RequiresCapability):
    capability = Capability.MANAGE_USERS
    message = "只有具备用户管理权限的管理员可以执行此操作。"


class IsLibraryStaff(BasePermission):
    message = "仅管理员或编辑可执行此操作。"

    def has_permission(self, request, view):
        return has_capability(request.user, Capability.ACCESS_BACK_OFFICE)


class IsLibraryAdmin(BasePermission):
    message = "仅管理员可执行此操作。"

    def has_permission(self, request, view):
        # Compatibility permission for ordinary administrative surfaces.  It
        # must never be inferred from a content capability such as publishing:
        # Editors deliberately publish Works in 3.0 but are not system admins.
        return capability_snapshot(request.user).access_level in {"admin", "superadmin"}


class IsCatalogEditor(BasePermission):
    message = "仅管理员或编辑可执行入库写操作。"

    def has_permission(self, request, view):
        return has_capability(request.user, Capability.EDIT_METADATA)


class IsKnowledgeEditor(BasePermission):
    message = "仅 Editor 或 Administrator 可维护知识内容。"

    def has_permission(self, request, view):
        return has_capability(request.user, Capability.EDIT_DRAFT_AUTHORITY)


class IsKnowledgeReviewer(BasePermission):
    message = "仅 Editor 或 Administrator 可执行候选决策。"

    def has_permission(self, request, view):
        return has_capability(request.user, Capability.REVIEW_CANDIDATE)
