"""Private browser responses stay bound to the account that initiated the action."""
from django.utils.cache import patch_cache_control, patch_vary_headers
from rest_framework.exceptions import PermissionDenied


class PrivateAccountResponses:
    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        expected = request.headers.get("X-Reader-Owner")
        if expected is not None and expected != str(request.user.pk):
            raise PermissionDenied("登录账户已变化，请重新读取当前账户的资料。")

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        patch_cache_control(response, private=True, no_store=True)
        patch_vary_headers(response, ("Cookie", "Authorization"))
        return response
