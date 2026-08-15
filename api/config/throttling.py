from __future__ import annotations

import hmac

from django.conf import settings
from rest_framework.throttling import AnonRateThrottle, ScopedRateThrottle, UserRateThrottle


def is_trusted_internal_request(request) -> bool:
    """Recognize only server-to-server requests carrying the shared secret."""

    expected = getattr(settings, "INTERNAL_API_TOKEN", "")
    supplied = request.META.get("HTTP_X_INTERNAL_API_TOKEN", "")
    if not expected or len(expected) < 32 or not supplied:
        return False
    return hmac.compare_digest(str(expected), str(supplied))


class _InternalServiceThrottleMixin:
    def allow_request(self, request, view):
        if is_trusted_internal_request(request):
            return True
        return super().allow_request(request, view)


class InternalAwareAnonRateThrottle(_InternalServiceThrottleMixin, AnonRateThrottle):
    pass


class InternalAwareUserRateThrottle(_InternalServiceThrottleMixin, UserRateThrottle):
    pass


class InternalAwareScopedRateThrottle(_InternalServiceThrottleMixin, ScopedRateThrottle):
    pass
