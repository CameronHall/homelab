from __future__ import annotations

from functools import lru_cache

import httpx

from ..config import Settings, get_settings


class InfisicalError(RuntimeError):
    pass


class InfisicalClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._base_url = settings.infisical_base_url.rstrip("/")

    def get_access_token(self) -> str:
        try:
            response = httpx.post(
                f"{self._base_url}/api/v1/auth/universal-auth/login",
                json={
                    "clientId": self.settings.infisical_client_id,
                    "clientSecret": self.settings.infisical_client_secret,
                },
                timeout=10.0,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise InfisicalError(f"Infisical auth failed: {exc.response.status_code}") from exc
        except httpx.HTTPError as exc:
            raise InfisicalError("Infisical auth request failed") from exc

        token = response.json().get("accessToken")
        if not token:
            raise InfisicalError("Infisical auth response missing accessToken")
        return token

    def list_secrets(self, access_token: str) -> dict[str, str]:
        try:
            response = httpx.get(
                f"{self._base_url}/api/v3/secrets/raw",
                params={
                    "workspaceId": self.settings.infisical_project_id,
                    "environment": self.settings.infisical_environment,
                    "secretPath": self.settings.infisical_secret_path,
                },
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=10.0,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise InfisicalError(f"Infisical secrets fetch failed: {exc.response.status_code}") from exc
        except httpx.HTTPError as exc:
            raise InfisicalError("Infisical secrets request failed") from exc

        return {s["secretKey"]: s["secretValue"] for s in response.json().get("secrets", [])}

    @property
    def is_configured(self) -> bool:
        return bool(
            self.settings.infisical_client_id
            and self.settings.infisical_client_secret
            and self.settings.infisical_project_id
        )


@lru_cache(maxsize=1)
def get_infisical_client() -> InfisicalClient:
    return InfisicalClient(get_settings())
