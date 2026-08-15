from rest_framework.permissions import BasePermission


class IsLibraryStaff(BasePermission):
    message = "仅管理员或编辑可执行此操作。"

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role in {"admin", "editor", "reviewer"}
        )


class IsLibraryAdmin(BasePermission):
    message = "仅管理员可执行此操作。"

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role == "admin"
        )


class IsCatalogEditor(BasePermission):
    message = "仅管理员或编辑可执行入库写操作。"

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role in {"admin", "editor"}
        )


class IsKnowledgeEditor(BasePermission):
    message = "仅管理员、编辑或审核者可维护知识内容。"

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role in {"admin", "editor", "reviewer"}
        )


class IsKnowledgeReviewer(BasePermission):
    message = "仅管理员或审核者可执行审核。"

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role in {"admin", "reviewer"}
        )
