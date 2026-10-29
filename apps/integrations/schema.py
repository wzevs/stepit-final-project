from drf_spectacular.extensions import OpenApiAuthenticationExtension

from .authentication import ApiKeyAuthentication


class ApiKeyAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = ApiKeyAuthentication
    name = "ApiKey"

    def get_security_definition(self, auto_schema):
        return {"type": "apiKey", "in": "header", "name": "X-API-Key"}
