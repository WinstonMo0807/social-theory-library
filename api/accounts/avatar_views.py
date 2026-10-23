from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from common.capabilities import Capability, has_capability
from common.private_responses import PrivateAccountResponses
from . import avatars
from .models import User


class AvatarState(serializers.Serializer):
    owner_id = serializers.CharField()
    has_avatar = serializers.BooleanField()
    revision = serializers.IntegerField()
    expected_version = serializers.CharField()
    updated_at = serializers.DateTimeField(allow_null=True)
    notice = serializers.CharField()


class AvatarReceipt(AvatarState):
    request_id = serializers.UUIDField()
    state = serializers.ChoiceField(choices=["applied", "cancelled"])


class AvatarCommand(serializers.Serializer):
    action = serializers.ChoiceField(choices=["set", "remove"])
    request_id = serializers.UUIDField()
    expected_version = serializers.CharField(min_length=64, max_length=64)
    confirmed = serializers.BooleanField()
    image = serializers.FileField(required=False, write_only=True)

    def validate(self, data):
        if set(self.initial_data) - set(self.fields) or data["confirmed"] is not True:
            raise serializers.ValidationError("请核对头像操作并明确确认。")
        if (data["action"] == "set") != ("image" in data):
            raise serializers.ValidationError("请为更换头像选择图片，移除时不提交图片。")
        return data


class AvatarBase(PrivateAccountResponses, APIView):
    permission_classes = [IsAuthenticated]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if request.headers.get("X-Reader-Owner") != str(request.user.pk):
            raise PermissionDenied("请重新核对当前登录账户。")


class AvatarView(AvatarBase):
    def get_throttles(self):
        self.throttle_scope = "profile_avatar" if self.request.method == "POST" else None
        return super().get_throttles()

    @extend_schema(responses=AvatarState)
    def get(self, request):
        return Response(avatars.state(request.user))

    @extend_schema(request=AvatarCommand, responses=AvatarReceipt)
    def post(self, request):
        data = AvatarCommand(data=request.data)
        data.is_valid(raise_exception=True)
        values = dict(data.validated_data)
        upload = values.pop("image", None)
        return Response(avatars.command(request.user, values, upload))


class AvatarImageView(AvatarBase):
    @extend_schema(responses={(200, "image/png"): bytes})
    def get(self, request, user_id):
        if request.user.pk != user_id and not has_capability(request.user, Capability.MANAGE_USERS):
            raise PermissionDenied("只能查看本人的头像。")
        data = avatars.image_data(get_object_or_404(User, pk=user_id))
        response = HttpResponse(data, content_type="image/png")
        response["X-Content-Type-Options"] = "nosniff"
        response["Content-Disposition"] = 'inline; filename="profile-avatar.png"'
        return response


class StopAvatar(serializers.Serializer):
    action = serializers.ChoiceField(choices=["cancel_pending"])


class AvatarReceiptView(AvatarBase):
    @extend_schema(responses=AvatarReceipt)
    def get(self, request, request_id):
        return Response(avatars.receipt(request.user, request_id))

    @extend_schema(request=StopAvatar, responses=AvatarReceipt)
    def post(self, request, request_id):
        if request.data != {"action": "cancel_pending"}:
            raise serializers.ValidationError("只支持停止尚未执行的原头像操作。")
        return Response(avatars.stop(request.user, request_id))
