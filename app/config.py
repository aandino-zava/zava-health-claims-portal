from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)
    environment: Literal["development", "test", "production"] = "production"
    auth_mode: Literal["development", "entra"] = "entra"
    database_url: str = "sqlite:///./claims.db"
    entra_tenant_id: str = ""
    entra_api_client_id: str = ""
    entra_spa_client_id: str = ""
    entra_allowed_client_ids: str = ""
    entra_authority_host: str = "https://login.microsoftonline.com"
    max_request_bytes: int = Field(default=65536, ge=1024, le=1048576)
    requests_per_minute: int = Field(default=120, ge=1, le=10000)
    concierge_enabled: bool = False
    concierge_dataverse_url: str = ""
    concierge_identity_client_id: str = ""
    concierge_reviewer_object_id: str = ""
    concierge_reviewer_user_id: str = ""
    concierge_allowed_claim_ids: str = ""
    concierge_poll_seconds: int = Field(default=20, ge=10, le=300)

    @model_validator(mode="after")
    def secure_defaults(self):
        if self.concierge_enabled:
            import re
            if not re.fullmatch(r"https://[a-z0-9-]+\.crm[0-9]*\.dynamics\.com/?", self.concierge_dataverse_url):
                raise ValueError("Concierge requires an HTTPS Dataverse environment")
            for value in (self.concierge_identity_client_id, self.concierge_reviewer_object_id,
                          self.concierge_reviewer_user_id):
                UUID(value)
            allowed = self.concierge_allowed_claim_ids.split(",")
            if not allowed or any(not re.fullmatch(r"CLM-\d{4}-[A-F0-9]{16}", v.strip()) for v in allowed):
                raise ValueError("Concierge requires explicitly allowed fictional portal claim IDs")
        if self.auth_mode == "development" and self.environment not in {"development", "test"}:
            raise ValueError("Development authentication is forbidden outside development/test")
        if self.auth_mode == "entra":
            for name in ("entra_tenant_id", "entra_api_client_id", "entra_spa_client_id"):
                try:
                    UUID(getattr(self, name))
                except ValueError:
                    raise ValueError(
                        f"AUTH_MODE=entra requires a valid {name.upper()}. "
                        "See docs/AUTH.md; for local development use Start-Local.ps1 or .env.example."
                    ) from None
            if not self.entra_allowed_client_ids.strip():
                raise ValueError("ENTRA_ALLOWED_CLIENT_IDS is required")
            for value in self.allowed_clients:
                try:
                    UUID(value)
                except ValueError:
                    raise ValueError("ENTRA_ALLOWED_CLIENT_IDS must contain comma-separated client GUIDs") from None
            if self.entra_authority_host not in {
                "https://login.microsoftonline.com",
                "https://login.microsoftonline.us",
                "https://login.chinacloudapi.cn",
            }:
                raise ValueError("Unsupported Entra authority host")
        if self.environment == "production" and not self.database_url.startswith("postgresql+psycopg://"):
            raise ValueError("Production requires an external PostgreSQL database")
        return self

    @property
    def allowed_clients(self):
        return {part.strip() for part in self.entra_allowed_client_ids.split(",") if part.strip()}

    @property
    def issuer(self):
        return f"{self.entra_authority_host}/{self.entra_tenant_id}/v2.0"
