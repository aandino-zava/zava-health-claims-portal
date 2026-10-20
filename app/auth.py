from dataclasses import dataclass

import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

bearer = HTTPBearer(auto_error=False)


@dataclass
class Principal:
    subject: str
    roles: set[str]


class EntraVerifier:
    def __init__(self, settings):
        self.settings = settings
        self.keys = jwt.PyJWKClient(
            f"{settings.entra_authority_host}/{settings.entra_tenant_id}/discovery/v2.0/keys",
            timeout=5,
        )

    def verify(self, token):
        key = self.keys.get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            key.key,
            algorithms=["RS256"],
            audience=self.settings.entra_api_client_id,
            issuer=self.settings.issuer,
            options={"require": ["exp", "iat", "nbf", "iss", "aud", "sub", "tid", "azp"]},
        )
        if (
            claims["tid"] != self.settings.entra_tenant_id
            or claims["azp"] not in self.settings.allowed_clients
        ):
            raise jwt.InvalidTokenError("Tenant or client not allowed")
        # Delegated calls need the exposed scope AND app role. App-only calls need app roles.
        if "scp" in claims and "Claims.Access" not in claims["scp"].split():
            raise jwt.InvalidTokenError("Missing delegated scope")
        roles = claims.get("roles", [])
        if not isinstance(roles, list) or not all(isinstance(role, str) for role in roles):
            raise jwt.InvalidTokenError("Invalid role claim")
        return Principal(claims["sub"], set(roles))


def current_user(request: Request, credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
    if request.app.state.settings.auth_mode == "development":
        return Principal("local-demo", {"Claims.Reader", "Claims.Writer", "Claims.Reviewer"})
    if credentials is None:
        raise HTTPException(401, "Sign in to continue", headers={"WWW-Authenticate": "Bearer"})
    try:
        return request.app.state.verifier.verify(credentials.credentials)
    except jwt.PyJWKClientConnectionError:
        raise HTTPException(503, "Identity provider temporarily unavailable") from None
    except jwt.PyJWTError:
        raise HTTPException(
            401, "Invalid or expired access token", headers={"WWW-Authenticate": "Bearer"}
        ) from None


def require(role):
    def check(user: Principal = Depends(current_user)):
        if role not in user.roles:
            raise HTTPException(403, f"Requires {role}")
        return user

    return check
