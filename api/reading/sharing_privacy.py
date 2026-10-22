"""Original privacy operations also manage grants, groups and notifications."""
from django.utils import timezone

from . import research, reader_groups, reader_shares
from .sharing_models import ReaderGroup, COLLABORATION_CATEGORIES as CATEGORIES


def export(user, category, row):
    common = {"id": str(row.pk), "created_at": row.created_at.isoformat(), "updated_at": row.updated_at.isoformat()}
    if category == "reader_groups":
        return {**common, **reader_groups.summary(row, user),
            "members": [{"user_id": str(value.user_id), "name": value.user.display_name or value.user.username} for value in row.memberships.select_related("user").all()],
            "invitations": [{key: value for key, value in reader_groups.invite_output(invite).items() if key != "token"}
                for invite in row.invitations.select_related("user").filter(revoked_at__isnull=True)]}
    if category == "group_memberships":
        return {**common, "group_id": str(row.group_id), "group_title": research.unpack(row.group).get("title", "已关闭小组")}
    if category == "group_invitations":
        return {**common, **{key: value for key, value in reader_groups.invite_output(row).items() if key != "token"}}
    if category == "reader_shares":
        payload = research.unpack(row)
        return {**common, **reader_shares.brief(row, user), "selection": payload.get("specification", {}),
            "recipient_bindings": payload.get("recipient_bindings", [])}
    return {**common, "share_id": str(row.share_id), "read_at": row.read_at.isoformat() if row.read_at else None}


def impact(category, row):
    counts = {}
    if category == "reader_groups":
        counts = {"members": row.memberships.count(), "invitations": row.invitations.filter(revoked_at__isnull=True).count()}
    messages = {
        "reader_groups": "关闭本人创建的小组，移除成员并撤销邀请，所有依赖此小组的分享立即失效；成员原研究、书单、笔记及账户保留。",
        "group_memberships": "退出该小组并撤销本人的待处理邀请，原小组分享不再可访问；以后重新加入也不会恢复旧成员身份的分享权限。",
        "group_invitations": "撤销这项本人邀请并清除邀请凭证；已经加入的成员关系需单独退出，不删除账户或其他资料。",
        "reader_shares": "撤销这项本人分享或策划提案，清除范围与留言、链接凭证及站内通知；原研究、书单和笔记保留，只留防止旧提交复活的最少回执。",
        "share_notices": "删除这条本人站内通知；原分享的授权与有效期不变。",
    }
    return {"message": messages[category], "memories": [], "scope_count": 0, **counts}


def describe(user, category, row):
    title = {"reader_groups": research.unpack(row).get("title", "小组") if category == "reader_groups" else "",
        "group_memberships": "本人小组成员关系", "group_invitations": "本人小组邀请", "reader_shares": "本人分享与策划提案", "share_notices": "本人站内通知"}[category]
    return title, {"title": title, "path": "/account/groups" if category in CATEGORIES[:3] else "/account/sharing"}


def erase(category, row):
    if category == "reader_groups":
        reader_groups.archive(row)
    elif category == "reader_shares":
        reader_shares.revoke_record(row)
    elif category == "group_invitations":
        row.revoked_at, row.token_ciphertext = timezone.now(), b""
        row.save(update_fields=["revoked_at", "token_ciphertext", "updated_at"])
        group = ReaderGroup.objects.select_for_update().get(pk=row.group_id)
        group.revision += 1
        group.save(update_fields=["revision", "updated_at"])
    elif category == "group_memberships":
        group = ReaderGroup.objects.select_for_update().get(pk=row.group_id)
        group.invitations.filter(user=row.user, accepted_at__isnull=True).update(revoked_at=timezone.now(), token_ciphertext=b"")
        row.delete()
        group.revision += 1
        group.save(update_fields=["revision", "updated_at"])
    else:
        row.delete()
