from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.response import Response

from catalog.feedback_serializers import PublicFeedbackReceipt
from catalog.feedback_views import FeedbackBurstThrottle, FeedbackDailyThrottle

from . import email_links
from .cookies import clear_auth_cookies
from .models import RecoveryCode
from .user_management_views import StrictInput
from .views import AuthEntryView


class MailLinkInput(StrictInput):
    action = serializers.ChoiceField(choices=["inspect", "confirm"])
    token = serializers.CharField(max_length=100, trim_whitespace=False, write_only=True)
    confirmed = serializers.BooleanField(required=False)
    password = serializers.CharField(max_length=4096, trim_whitespace=False, write_only=True, required=False)

    def validate(self, data):
        reset = self.context.get("purpose") == RecoveryCode.Purpose.PASSWORD_LINK
        if data["action"] == "confirm" and (data.get("confirmed") is not True or not data.get("password")):
            raise serializers.ValidationError("请确认这是本人发起的操作，并填写必要信息。")
        if reset and data["action"] == "confirm" and not 10 <= len(data["password"]) <= 128:
            raise serializers.ValidationError({"password": "新密码需要10至128个字符。"})
        if data["action"] == "inspect" and "password" in data:
            raise serializers.ValidationError("此操作不接受密码。")
        return data


class MailLinkOutput(serializers.Serializer):
    state = serializers.ChoiceField(choices=["ready", "completed", "expired", "unavailable"])
    detail = serializers.CharField()
    expires_at = serializers.DateTimeField(required=False)


class MailRequestInput(StrictInput):
    email = serializers.EmailField(max_length=254)
    next = serializers.CharField(required=False, max_length=2000, default="/account")


class MailRequestOutput(serializers.Serializer):
    detail = serializers.CharField()


class PasswordLinkView(AuthEntryView):
    throttle_scope = "auth_link"
    purpose = RecoveryCode.Purpose.PASSWORD_LINK

    @extend_schema(request=MailLinkInput, responses=MailLinkOutput)
    def post(self, request):
        schema = MailLinkInput(data=request.data, context={"purpose": self.purpose})
        schema.is_valid(raise_exception=True)
        data = schema.validated_data
        result = email_links.operate(data["token"], self.purpose, data["action"], data.get("password"))
        response = Response(result)
        if self.purpose == RecoveryCode.Purpose.PASSWORD_LINK and data["action"] == "confirm" and result["state"] == "completed":
            clear_auth_cookies(response)
        return response


class EmailVerificationView(PasswordLinkView):
    purpose = RecoveryCode.Purpose.VERIFY_EMAIL


class EmailVerificationRequestView(AuthEntryView):
    throttle_scope = "password_reset"

    @extend_schema(request=MailRequestInput, responses={202: MailRequestOutput})
    def post(self, request):
        schema = MailRequestInput(data=request.data)
        schema.is_valid(raise_exception=True)
        data = schema.validated_data
        email_links.enqueue(data["email"], RecoveryCode.Purpose.VERIFY_EMAIL, data["next"])
        return Response({"detail": email_links.NOTICE}, status=202)


class AccountRecoveryAppealInput(StrictInput):
    request_id = serializers.UUIDField()
    username = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")
    contact = serializers.EmailField(max_length=254)
    note = serializers.CharField(min_length=4, max_length=300)
    consent = serializers.BooleanField()

    def validate_consent(self, value):
        if value is not True:
            raise serializers.ValidationError("请确认将填写内容交给管理员处理本次找回申请。")
        return value


class AccountRecoveryAppealView(AuthEntryView):
    throttle_classes = [FeedbackBurstThrottle, FeedbackDailyThrottle]

    @extend_schema(request=AccountRecoveryAppealInput, responses={200: PublicFeedbackReceipt, 201: PublicFeedbackReceipt})
    def post(self, request):
        from catalog.services.public_feedback import submit
        from catalog.models import PublicFeedback
        schema = AccountRecoveryAppealInput(data=request.data)
        schema.is_valid(raise_exception=True)
        data = schema.validated_data
        # No account existence lookup, password change or automatic contact-email reassignment.
        result, created = submit(None, {"request_id": data["request_id"], "category": PublicFeedback.Category.USAGE,
            "body": f"账户找回申请\n用户名（本人填写，未核实）：{data['username'] or '未填写'}\n情况说明：{data['note']}",
            "contact": data["contact"], "path": "/help/account", "consent": True})
        result["message"] = "申请已进入管理员反馈队列。账户归属仍需核实；提交申请不会改动邮箱、密码或权限。请保留编号，等待人工联系。"
        return Response(result, status=201 if created else 200)
