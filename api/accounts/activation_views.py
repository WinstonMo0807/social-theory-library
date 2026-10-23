from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.response import Response

from . import account_activation
from .models import User
from .user_management_views import ManagementBase, StrictInput
from .views import AuthEntryView


class InvitationOutput(serializers.Serializer):
    actor_id = serializers.CharField()
    user_id = serializers.IntegerField()
    state = serializers.CharField()
    token = serializers.CharField(allow_blank=True)
    expires_at = serializers.DateTimeField(allow_null=True)
    can_renew = serializers.BooleanField()
    notice = serializers.CharField()


class InvitationView(ManagementBase):
    @extend_schema(responses=InvitationOutput)
    def get(self, request, user_id):
        return Response(account_activation.management_output(request.user, get_object_or_404(User, pk=user_id)))


class ActivationInput(StrictInput):
    action = serializers.ChoiceField(choices=["inspect", "activate"])
    token = serializers.CharField(max_length=240, trim_whitespace=False, write_only=True)
    password = serializers.CharField(min_length=10, max_length=128, trim_whitespace=False, write_only=True, required=False)
    confirmed = serializers.BooleanField(required=False)

    def validate(self, data):
        if data["action"] == "activate":
            if not data.get("password") or data.get("confirmed") is not True:
                raise serializers.ValidationError("请设置密码，并确认这是本人账户。")
        elif "password" in data or "confirmed" in data:
            raise serializers.ValidationError("核对邀请时不提交密码。")
        return data


class ActivationOutput(serializers.Serializer):
    state = serializers.ChoiceField(choices=["ready", "activated", "expired", "unavailable"])
    detail = serializers.CharField()
    username = serializers.CharField(required=False)
    email = serializers.EmailField(required=False)
    display_name = serializers.CharField(required=False)
    role_label = serializers.CharField(required=False)
    expires_at = serializers.DateTimeField(required=False)


class ActivationView(AuthEntryView):
    throttle_scope = "register"

    @extend_schema(request=ActivationInput, responses=ActivationOutput)
    def post(self, request):
        values = ActivationInput(data=request.data)
        values.is_valid(raise_exception=True)
        data = values.validated_data
        return Response(account_activation.inspect(data["token"]) if data["action"] == "inspect" else
            account_activation.activate(data["token"], data["password"]))
