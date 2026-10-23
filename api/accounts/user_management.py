"""M25 account administration, without access to readers' private content."""
import copy
import json

from django.contrib.auth import password_validation
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils.crypto import constant_time_compare, salted_hmac
from rest_framework.exceptions import APIException, NotFound, PermissionDenied, ValidationError

from common.capabilities import Capability, ROLE_CAPABILITIES, OWNER_CAPABILITIES, capability_snapshot, has_capability
from ingestion.models import AuditEvent
from .models import User
from .ownership import is_library_owner, is_library_owner_identity, library_owner_display_name

ROLE_LABELS = {"reader": "读者", "editor": "内容编辑", "reviewer": "内容编辑（原审核角色）", "admin": "系统管理员", "owner": "馆长"}
CAPABILITY_LABELS = {
    "access_back_office": "访问管理后台", "can_upload": "收件与上传", "can_edit_metadata": "编辑书目",
    "can_view_evidence": "核对馆藏证据", "can_edit_draft_authority": "编辑知识草稿", "can_create_authority": "创建知识条目",
    "can_review_candidate": "审核候选与明确提交的提案", "can_publish_work": "发布馆藏", "can_withdraw_work": "撤下馆藏",
    "can_publish_authority": "发布知识内容", "can_run_enrichment": "生成候选建议", "can_retry_jobs": "重试处理任务",
    "can_manage_search_runtime": "管理检索服务", "can_view_query_lexicon": "查看查询词", "can_manage_query_lexicon": "维护查询词",
    "can_view_semantic_index": "查看检索索引", "can_manage_semantic_index": "管理检索索引", "can_manage_ai": "管理智能服务",
    "can_configure_providers": "配置服务提供方", "can_manage_ai_providers": "管理模型提供方", "can_manage_ai_models": "管理模型",
    "can_manage_prompt_registry": "管理提示模板", "can_manage_global_projection": "管理全站公开投影",
    "can_merge_authority": "归并规范身份", "can_run_system_recovery": "执行系统恢复", "can_manage_users": "管理账户",
    "can_manage_roles": "变更账户角色", "can_view_system_status": "查看系统状态", "can_view_audit_log": "查看操作记录",
    "can_run_backup": "执行备份", "can_run_destructive_maintenance": "执行已批准的维护", "can_view_migrations": "查看迁移状态",
}
PUBLIC_ACCESS = "公开检索、阅读、下载、复制与引用"
PRIVATE_ACCESS = "管理本人的研究、笔记、书单、计划与隐私资料"


class AccountConflict(APIException):
    status_code = 409
    default_detail = "账户资料已经变化，请重新读取并预览后确认。"


def digest(value):
    # Keyed digest: password input and credential-derived versions are not
    # exposed as unkeyed hashes that could become offline password oracles.
    return salted_hmac("stl-account-management-v1", json.dumps(value, sort_keys=True, ensure_ascii=False, default=str), algorithm="sha256").hexdigest()


def version(user):
    return digest({name: getattr(user, name) for name in ("id", "username", "email", "display_name", "role", "is_active", "is_staff", "is_superuser", "token_version", "password")})


def check_actor(user):
    if not user.is_active or not has_capability(user, Capability.MANAGE_USERS):
        raise PermissionDenied("当前账户没有管理账户的权限。")


def record(user, actor, invitation=None):
    from . import account_activation
    owner = is_library_owner_identity(user)
    can_edit = (not owner and user.role != "admin") or user.pk == actor.pk or is_library_owner(actor)
    return {"id": user.pk, "username": user.username, "email": user.email,
        "display_name": library_owner_display_name() if owner else user.display_name,
        "role": user.role, "role_label": ROLE_LABELS["owner" if owner else user.role], "is_active": user.is_active,
        "is_owner": owner, "date_joined": user.date_joined, "last_login": user.last_login,
        "version": version(user), "can_edit": can_edit, "can_change_role": is_library_owner(actor) and not owner and not user.is_superuser and user.pk != actor.pk,
        "capabilities": list(capability_snapshot(user).capabilities) if user.is_active else [],
        "activation_state": account_activation.status(user, invitation),
        "can_renew_invitation": can_edit and (user.role == "reader" or is_library_owner(actor)) and account_activation.can_renew(user, invitation),
        "can_revoke_invitation": can_edit and account_activation.can_renew(user, invitation),
        "avatar_revision": getattr(user, "_avatar_revision", None),
        "notice": "账户管理权限不授予阅读他人私人研究、笔记、密钥或资料导出的权限。"}


def roles():
    return [{"id": key, "label": ROLE_LABELS[key], "capabilities": [{"id": cap, "label": CAPABILITY_LABELS[cap]} for cap in sorted(values)],
        "public_access": PUBLIC_ACCESS, "private_access": PRIVATE_ACCESS,
        "assignable": key != "owner"} for key, values in {"reader": set(), "editor": ROLE_CAPABILITIES["editor"], "admin": ROLE_CAPABILITIES["admin"], "owner": OWNER_CAPABILITIES}.items()]


def authority(actor, target, role, active):
    check_actor(actor)
    owner = is_library_owner(actor)
    if (is_library_owner_identity(target) or target.role == "admin") and target.pk != actor.pk and not owner:
        raise PermissionDenied("此管理账户只能由馆长管理。")
    if is_library_owner_identity(target) and (role != "admin" or not active):
        raise ValidationError("馆长账户不能被停用或降级。")
    if target.is_superuser and role != "admin":
        raise ValidationError("该账户仍有系统超级用户身份，不能仅修改业务角色制造已降权状态。")
    if role != target.role and not owner:
        raise PermissionDenied("只有馆长可以变更账户角色。")
    if target.pk == actor.pk and (role != "admin" or not active):
        raise ValidationError("不能停用当前账户或撤销自己的管理角色。")
    if target.role == "admin" and target.is_active and (role != "admin" or not active) and User.objects.filter(role="admin", is_active=True).count() <= 1:
        raise ValidationError("系统必须保留至少一个有效管理员。")


def account_data(actor, data):
    check_actor(actor)
    if data["operation"] == "create":
        values = registration_input(data)
        values.is_valid(raise_exception=True)
        if data["role"] != "reader" and not is_library_owner(actor):
            raise PermissionDenied("只有馆长可以为新账户分配管理角色。")
        target = User(**{key: value for key, value in values.validated_data.items() if key != "password"}, role=data["role"], is_active=data["is_active"])
        if data.get("invite"):
            target.set_unusable_password()
            if target.is_active:
                raise ValidationError("待激活账户必须先由本人设置密码，不能同时启用。")
        else:
            try:
                password_validation.validate_password(data["password"], target)
            except DjangoValidationError as exc:
                raise ValidationError({"password": exc.messages}) from exc
        return None, target
    original = User.objects.filter(pk=data["user_id"]).first()
    if original is None:
        raise NotFound("该账户已不存在。")
    if not constant_time_compare(version(original), data["expected_version"]):
        raise AccountConflict()
    proposed = copy.copy(original)
    if data["operation"] == "update":
        if is_library_owner_identity(original) and "display_name" in data and data["display_name"] != original.display_name:
            raise ValidationError("馆长显示名称由既有身份配置管理，不能在此覆盖。")
        for name in ("display_name", "role", "is_active"):
            if name in data:
                setattr(proposed, name, data[name])
    authority(actor, original, proposed.role, proposed.is_active)
    if data["operation"] in {"invite", "revoke_invite"}:
        from . import account_activation
        if not account_activation.can_renew(original, account_activation.latest(original)):
            raise ValidationError("只有尚未激活的邀请账户可重新生成或撤销邀请；已有账户请沿密码与状态管理。")
        if data["operation"] == "invite" and original.role != "reader" and not is_library_owner(actor):
            raise PermissionDenied("只有馆长可以重新发出带管理角色的邀请。")
    if data["operation"] == "update" and not original.is_active and proposed.is_active and not original.has_usable_password():
        raise ValidationError("此账户尚未设置密码，请由本人完成邀请激活，或先明确设置新密码再启用。")
    if data["operation"] == "password":
        try:
            password_validation.validate_password(data["password"], original)
        except DjangoValidationError as exc:
            raise ValidationError({"password": exc.messages}) from exc
    return original, proposed


def registration_input(data):
    from .serializers import InvitationRegistrationSerializer, RegisterSerializer
    serializer = InvitationRegistrationSerializer if data.get("invite") else RegisterSerializer
    return serializer(data={name: data[name] for name in ("username", "email", "display_name", "password") if name in data})


def preview(actor, data):
    original, proposed = account_data(actor, data)
    before = set(capability_snapshot(original).capabilities) if original and original.is_active else set()
    after = set(capability_snapshot(proposed).capabilities) if proposed.is_active else set()
    values = lambda keys: [{"id": key, "label": CAPABILITY_LABELS[key]} for key in sorted(keys)]
    inviting = bool(data.get("invite") or data["operation"] == "invite")
    activated = copy.copy(proposed)
    activated.is_active = True
    return {"actor_id": str(actor.pk), "target": {"id": original.pk if original else None, "display_name": library_owner_display_name() if is_library_owner_identity(proposed) else proposed.display_name,
        "username": proposed.username, "email": proposed.email, "role": proposed.role,
        "role_label": ROLE_LABELS["owner" if is_library_owner_identity(proposed) else proposed.role], "is_active": proposed.is_active},
        "retained": values(before & after), "gained": values(after - before), "lost": values(before - after),
        "activation_capabilities": values(capability_snapshot(activated).capabilities) if inviting else [],
        "public_access": PUBLIC_ACCESS, "private_access": PRIVATE_ACCESS if proposed.is_active else "由本人设置密码并激活后，按所选角色登录；现有本人资料保留。" if inviting else "停用后不能登录；原本人资料保留。",
        "sessions_revoked": bool(original and (data["operation"] in {"password", "invite", "revoke_invite"} or (original.role, original.is_active) != (proposed.role, proposed.is_active))),
        "notice": ("生成24小时有效的邀请，由本人设置密码后启用选定角色。旧邀请同时失效；请自行将链接交给本人，系统不自动发送邮件。" if data.get("invite") or data["operation"] == "invite" else "撤销邀请，账户保持未启用；本人资料保留。" if data["operation"] == "revoke_invite" else "只修改明确列出的账户资料，不读取私人内容，不发送邮件。角色/启用状态或密码变化后旧登录凭证失效。"),
        "preview_hash": digest({"actor": actor.pk, "actor_version": version(actor), "data": data})}


def lookup(actor, request_id):
    check_actor(actor)
    event = AuditEvent.objects.filter(pk=request_id, actor=actor, action__startswith="account_", object_type="User").first()
    if event is None:
        raise NotFound("尚未找到本次账户操作，请保留原请求核对。")
    if event.action == "account_stop":
        return {"actor_id": str(actor.pk), "request_id": str(event.pk), "user_id": None, "exists": False,
            "version": None, "operation": "stop", "state": "cancelled", "created_at": event.created_at}
    user = User.objects.filter(pk=event.object_id).first()
    return {"actor_id": str(actor.pk), "request_id": str(event.pk), "user_id": int(event.object_id), "exists": user is not None,
        "version": version(user) if user else None, "operation": event.action.removeprefix("account_"), "state": "applied", "created_at": event.created_at}


@transaction.atomic
def stop_pending(actor, request_id):
    # The original command also locks this actor before checking its receipt.
    current = User.objects.select_for_update().filter(pk=actor.pk).first()
    if current is None:
        raise PermissionDenied("当前账户已不存在。")
    check_actor(current)
    if not constant_time_compare(version(current), version(actor)):
        raise AccountConflict("操作账户的权限或凭证已变化，请重新登录并核对。")
    prior = AuditEvent.objects.filter(pk=request_id).first()
    if prior:
        if prior.actor_id != actor.pk or prior.object_type != "User" or not prior.action.startswith("account_"):
            raise AccountConflict("此请求标识属于另一项操作，不能停止或清除。")
    else:
        AuditEvent.objects.create(pk=request_id, actor=current, action="account_stop", object_type="User",
            object_id="", before={}, after={}, request_id=str(request_id))
    return lookup(current, request_id)


@transaction.atomic
def command(actor, data):
    identity = data["request_id"]
    # A stable lock order serializes concurrent operators and role/status changes.
    ids = {actor.pk, data.get("user_id", actor.pk)}
    locked = {value.pk: value for value in User.objects.select_for_update().filter(pk__in=ids).order_by("pk")}
    current_actor = locked.get(actor.pk)
    if current_actor is None:
        raise PermissionDenied("当前账户已不存在。")
    check_actor(current_actor)
    if not constant_time_compare(version(current_actor), version(actor)):
        raise AccountConflict("操作账户的权限或凭证已变化，请重新登录并核对。")
    fingerprint = digest(data)
    prior = AuditEvent.objects.filter(pk=identity).first()
    if prior:
        if prior.actor_id == actor.pk and prior.action == "account_stop" and prior.object_type == "User":
            raise AccountConflict("原请求已停止，没有再次修改账户。")
        if prior.actor_id != actor.pk or prior.action != "account_" + data["operation"] or prior.after.get("command_fingerprint") != fingerprint:
            raise AccountConflict("此请求标识已经用于其他操作，请查回原结果。")
        return lookup(current_actor, identity)
    if data["confirmed"] is not True:
        raise ValidationError("请先核对能力变化和影响，再明确确认。")
    input_data = {key: value for key, value in data.items() if key not in {"request_id", "confirmed", "preview_hash"}}
    rendered = preview(current_actor, input_data)
    if not constant_time_compare(rendered["preview_hash"], data["preview_hash"]):
        raise AccountConflict("预览已失效，请重新核对当前账户和能力变化。")
    original, proposed = account_data(current_actor, input_data)
    before = {key: getattr(original, key) for key in ("display_name", "role", "is_active")} if original else {}
    if original is None:
        values = registration_input(input_data)
        values.is_valid(raise_exception=True)
        target = values.save()
        target.role, target.is_active = proposed.role, proposed.is_active
        target.save(update_fields=["role", "is_active"])
    else:
        target = locked.get(original.pk)
        if target is None or version(target) != data["expected_version"]:
            raise AccountConflict()
        if data["operation"] == "password":
            target.set_password(data["password"])
        else:
            target.display_name, target.role, target.is_active = proposed.display_name, proposed.role, proposed.is_active
        if rendered["sessions_revoked"]:
            target.token_version += 1
        target.save(update_fields=["display_name", "role", "is_active", "password", "token_version"])
    after = {key: getattr(target, key) for key in ("display_name", "role", "is_active")}
    after.update(command_fingerprint=fingerprint, password_reset=data["operation"] == "password", sessions_revoked=rendered["sessions_revoked"])
    if input_data.get("invite") or data["operation"] == "invite":
        from .account_activation import issue_metadata
        after.update(issue_metadata(target))
    elif data["operation"] == "revoke_invite":
        after["invited"] = True
    AuditEvent.objects.create(pk=identity, actor=current_actor, action="account_" + data["operation"], object_type="User", object_id=str(target.pk),
        before=before, after=after, request_id=str(identity))
    return {"actor_id": str(actor.pk), "request_id": str(identity), "user_id": target.pk, "exists": True,
        "version": version(target), "operation": data["operation"], "state": "applied", "created_at": AuditEvent.objects.only("created_at").get(pk=identity).created_at}


def audit_rows():
    return AuditEvent.objects.filter(object_type="User", action__in=["account_create", "account_update", "account_password", "account_invite", "account_revoke_invite", "account_activate", "admin_update_user", "admin_set_password"]).select_related("actor").order_by("-created_at", "-id")


def audit_record(row):
    fields = ("display_name", "role", "is_active")
    return {"id": str(row.pk), "created_at": row.created_at, "actor": row.actor.display_name if row.actor else "原操作账户已删除",
        "user_id": row.object_id, "action": {"account_create": "新建待激活账户" if row.after.get("invited") else "新建账户", "account_update": "更新账户", "account_password": "设置新密码", "account_invite": "重新生成邀请", "account_revoke_invite": "撤销邀请", "account_activate": "本人激活账户", "admin_update_user": "更新账户", "admin_set_password": "设置新密码"}[row.action],
        "before": {key: row.before[key] for key in fields if key in row.before}, "after": {key: row.after[key] for key in fields if key in row.after},
        "sessions_revoked": row.after.get("sessions_revoked"), "password_reset": bool(row.after.get("password_reset"))}
