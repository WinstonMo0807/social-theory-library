"""Schema metadata; API access rules stay on the original views."""
from django.conf import settings
from drf_spectacular.extensions import OpenApiAuthenticationExtension
from drf_spectacular.views import SpectacularAPIView
from catalog.editorial_read import AdminPrivateResponseMixin


class AdminSchemaView(AdminPrivateResponseMixin, SpectacularAPIView):
    pass


class LibraryJWTAuthenticationSchema(OpenApiAuthenticationExtension):
    target_class = "accounts.authentication.VersionedJWTAuthentication"
    name = "libraryCookie"

    def get_security_definition(self, auto_schema):
        return {"type": "apiKey", "in": "cookie", "name": settings.JWT_ACCESS_COOKIE_NAME}
