import logging
from uuid import uuid4

from rest_framework.response import Response
from rest_framework.views import exception_handler


logger = logging.getLogger("library.api")


def api_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is None:
        error_id = uuid4().hex[:12]
        logger.exception(
            "Unhandled API error %s at %s",
            error_id,
            context.get("view"),
        )
        return Response(
            {
                "error": {
                    "status": 500,
                    "code": "internal_error",
                    "detail": f"服务器处理失败。错误编号 {error_id}",
                }
            },
            status=500,
        )

    if response.status_code in {401, 403}:
        request = context.get("request")
        reason = getattr(request, "library_auth_failure_reason", "")
        if not reason:
            reason = "permission_denied" if response.status_code == 403 else "invalid_session"
        logger.info(
            "Authentication outcome reason=%s method=%s path=%s",
            reason,
            getattr(request, "method", ""),
            getattr(request, "path", ""),
        )

    detail = response.data
    response.data = {
        "error": {
            "status": response.status_code,
            "detail": detail,
        }
    }
    return response
