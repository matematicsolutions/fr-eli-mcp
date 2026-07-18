"""Async httpx client for the French Legifrance API behind PISTE (piste.gouv.fr).

Unlike the keyless connectors in this line, Legifrance requires OAuth2:

- ``POST {oauth_url}`` with ``grant_type=client_credentials`` + ``client_id`` +
  ``client_secret`` + ``scope=openid`` returns an ``access_token`` valid for
  ``expires_in`` seconds (3600 in the sandbox).
- Every API call is ``POST {base_url}{path}`` JSON with a ``Bearer`` header.

Credentials come from the environment ONLY (FR_ELI_CLIENT_ID / FR_ELI_CLIENT_SECRET),
never from source. The token is cached in-process (never written to disk) and refreshed
on expiry or on a 401. Search / consult responses are cached on disk like the other
connectors (public legal data, no secrets).
"""

from __future__ import annotations

import json
import os
import time

import anyio
import httpx

from . import runtime
from .cache import HttpCache

DEFAULT_OAUTH_URL = "https://sandbox-oauth.piste.gouv.fr/api/oauth/token"
DEFAULT_BASE_URL = "https://sandbox-api.piste.gouv.fr/dila/legifrance/lf-engine-app"
DEFAULT_TIMEOUT = httpx.Timeout(40.0, connect=10.0)
USER_AGENT = "fr-eli-mcp/0.3.0 (+https://github.com/matematicsolutions/fr-eli-mcp)"

_RETRY_STATUS = frozenset({429, 500, 502, 503, 504})
_MAX_ATTEMPTS = 3
_TOKEN_SKEW_S = 60.0  # refresh this many seconds before nominal expiry


class CredentialsError(RuntimeError):
    """PISTE OAuth credentials are not configured in the environment."""


def _env_oauth_url() -> str:
    return os.environ.get("FR_ELI_OAUTH_URL", DEFAULT_OAUTH_URL)


def _env_base_url() -> str:
    return os.environ.get("FR_ELI_BASE_URL", runtime.base_url("eli", DEFAULT_BASE_URL)).rstrip("/")


def _env_credentials() -> tuple[str, str]:
    cid = os.environ.get("FR_ELI_CLIENT_ID", "").strip()
    secret = os.environ.get("FR_ELI_CLIENT_SECRET", "").strip()
    if not cid or not secret:
        raise CredentialsError(
            "PISTE credentials missing: set FR_ELI_CLIENT_ID and FR_ELI_CLIENT_SECRET "
            "(from your piste.gouv.fr application, section OAuth Credentials)."
        )
    return cid, secret


class TokenManager:
    """In-process OAuth2 client_credentials token cache (never persisted to disk)."""

    def __init__(self, oauth_url: str, client_id: str, client_secret: str) -> None:
        self._oauth_url = oauth_url
        self._client_id = client_id
        self._client_secret = client_secret
        self._token: str | None = None
        self._expires_at: float = 0.0
        self._lock = anyio.Lock()

    async def get_token(self, http: httpx.AsyncClient, *, force: bool = False) -> str:
        async with self._lock:
            now = time.monotonic()
            if not force and self._token is not None and now < self._expires_at - _TOKEN_SKEW_S:
                return self._token
            resp = await http.post(
                self._oauth_url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "scope": "openid",
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            resp.raise_for_status()
            data = resp.json()
            token = data.get("access_token")
            if not token:
                raise CredentialsError("PISTE OAuth returned no access_token.")
            self._token = token
            self._expires_at = now + float(data.get("expires_in", 3600))
            return token

    def invalidate(self) -> None:
        self._token = None
        self._expires_at = 0.0


# Module-level token managers keyed by (oauth_url, client_id) so a single token is
# reused across tool calls for the lifetime of the server process.
_TOKEN_MANAGERS: dict[tuple[str, str], TokenManager] = {}


def _token_manager() -> TokenManager:
    oauth_url = _env_oauth_url()
    client_id, client_secret = _env_credentials()
    key = (oauth_url, client_id)
    mgr = _TOKEN_MANAGERS.get(key)
    if mgr is None:
        mgr = TokenManager(oauth_url, client_id, client_secret)
        _TOKEN_MANAGERS[key] = mgr
    return mgr


class LegifranceClient:
    """Async client. Use as ``async with LegifranceClient() as c: ...``."""

    def __init__(
        self,
        base_url: str | None = None,
        cache: HttpCache | None = None,
        timeout: httpx.Timeout = DEFAULT_TIMEOUT,
    ) -> None:
        self.base_url = (base_url or _env_base_url()).rstrip("/")
        self._cache = cache or HttpCache()
        self._tokens = _token_manager()
        self._http = httpx.AsyncClient(
            timeout=timeout,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        )

    async def __aenter__(self) -> LegifranceClient:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._http.aclose()
        self._cache.close()

    @staticmethod
    def _cache_key(path: str, payload: dict[str, object]) -> str:
        body = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        return f"POST {path} {body}"

    async def _post(self, path: str, payload: dict[str, object], *, category: str) -> dict:
        url = f"{self.base_url}{path}"
        key = self._cache_key(path, payload)
        cached = self._cache.get(key)
        if cached is not None and isinstance(cached, dict):
            return cached

        last_exc: Exception | None = None
        forced_refresh = False
        for attempt in range(_MAX_ATTEMPTS):
            try:
                token = await self._tokens.get_token(self._http, force=forced_refresh)
                resp = await self._http.post(
                    url, json=payload, headers={"Authorization": f"Bearer {token}"}
                )
                if resp.status_code == 401 and not forced_refresh:
                    # Token expired/revoked - drop it and retry once with a fresh one.
                    self._tokens.invalidate()
                    forced_refresh = True
                    continue
                resp.raise_for_status()
                data = resp.json()
                self._cache.set(key, data, ttl=HttpCache.ttl_for(category))
                return data
            except httpx.HTTPStatusError as exc:
                last_exc = exc
                if exc.response.status_code not in _RETRY_STATUS or attempt == _MAX_ATTEMPTS - 1:
                    raise
            except (httpx.TransportError, httpx.TimeoutException) as exc:
                last_exc = exc
                if attempt == _MAX_ATTEMPTS - 1:
                    raise
            await anyio.sleep(0.5 * (2**attempt))
        assert last_exc is not None
        raise last_exc

    # -- API surface -------------------------------------------------------

    async def search(self, payload: dict[str, object]) -> dict:
        return await self._post("/search", payload, category="search")

    async def consult_law_decree(self, text_id: str, date: str) -> dict:
        return await self._post(
            "/consult/lawDecree", {"textId": text_id, "date": date}, category="act"
        )

    async def consult_article(self, article_id: str) -> dict:
        return await self._post("/consult/getArticle", {"id": article_id}, category="act")

    async def consult_juri(self, text_id: str) -> dict:
        return await self._post("/consult/juri", {"textId": text_id}, category="act")

    async def consult_cnil(self, text_id: str) -> dict:
        return await self._post("/consult/cnil", {"textId": text_id}, category="act")

    async def consult_kali_text(self, text_id: str) -> dict:
        return await self._post("/consult/kaliText", {"id": text_id}, category="act")

    async def consult_acco(self, agreement_id: str) -> dict:
        return await self._post("/consult/acco", {"id": agreement_id}, category="act")
