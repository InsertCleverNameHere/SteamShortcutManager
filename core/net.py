"""
core/net.py
Hardened HTTP networking layer for Steam Shortcut Manager.
Enforces HTTPS-only, host allowlists across redirect hops,
granular retries with Retry-After, and typed search results.
"""

from dataclasses import dataclass
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

from core.log import get_logger
from core.version import __version__

logger = get_logger("net")

USER_AGENT = f"SteamShortcutManager/{__version__}"

ALLOWED_STEAM_DOMAINS = (
    "steampowered.com",
    "steamstatic.com",
    "steamcommunity.com",
    "steamcontent.com",
    "akamaihd.net",
)

DEFAULT_TIMEOUT = (4.0, 8.0)  # (connect_timeout, read_timeout)


class NetworkError(Exception):
    """Base network exception."""


class NetworkUnavailableError(NetworkError):
    """Raised when Steam endpoints are unreachable (offline or DNS failure)."""


class RateLimitedError(NetworkError):
    """Raised when Steam returns HTTP 429 Too Many Requests."""

    def __init__(self, retry_after: int | None = None):
        super().__init__(
            f"Rate limited by Steam. Retry after {retry_after}s."
            if retry_after
            else "Rate limited by Steam."
        )
        self.retry_after = retry_after


class ResourceNotFoundError(NetworkError):
    """Raised when an asset returns HTTP 404."""


class UntrustedHostError(NetworkError):
    """Raised when a request or redirect attempts to access a non-Steam host."""


def is_trusted_steam_url(url: str) -> bool:
    """Validates that a URL uses HTTPS and points strictly to an approved Steam CDN domain."""
    if not url:
        return False
    try:
        parsed = urlparse(url)
        if parsed.scheme.lower() != "https":
            return False
        netloc = parsed.hostname.lower() if parsed.hostname else ""
        return any(
            netloc == d or netloc.endswith("." + d) for d in ALLOWED_STEAM_DOMAINS
        )
    except Exception:
        return False


def _verify_redirect(response: requests.Response, *args, **kwargs) -> None:
    """Response hook to enforce the host allowlist on every redirect hop."""
    if response.is_redirect:
        location = response.headers.get("Location")
        if location and not is_trusted_steam_url(location):
            raise UntrustedHostError(f"Blocked redirect to untrusted host: {location}")


def create_steam_session() -> requests.Session:
    """Builds a configured requests.Session with connection pooling, retries, and domain guards."""
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    # Retry on transient server errors and 429; NEVER on 404/403/410
    retries = Retry(
        total=2,
        backoff_factor=0.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "HEAD"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retries, pool_connections=5, pool_maxsize=10)
    session.mount("https://", adapter)

    # Attach redirect validation hook
    session.hooks["response"].append(_verify_redirect)
    return session


def is_network_available(timeout: float = 3.0) -> bool:
    """Resilient HTTPS connectivity check."""
    try:
        r = requests.head(
            "https://store.steampowered.com",
            headers={"User-Agent": USER_AGENT},
            timeout=timeout,
        )
        return r.status_code < 500
    except Exception:
        return False


@dataclass(frozen=True)
class SearchItem:
    appid: str
    name: str
    thumb_url: str | None


@dataclass(frozen=True)
class SearchResult:
    status: str  # "ok" | "none" | "error"
    item: SearchItem | None = None
    error_message: str | None = None


def search_steam_store(
    query: str, session: requests.Session | None = None
) -> SearchResult:
    """
    Queries Steam Store Search using RFC 3986 parameter encoding.
    Returns a typed SearchResult.
    """
    clean_query = query.replace("-", " ").replace(":", " ").strip()
    if not clean_query:
        return SearchResult(status="none")

    url = "https://store.steampowered.com/api/storesearch/"
    params = {
        "term": clean_query,
        "l": "english",
        "cc": "US",
    }

    client = session or requests
    try:
        resp = client.get(url, params=params, timeout=DEFAULT_TIMEOUT)
        if resp.status_code == 429:
            retry_after = resp.headers.get("Retry-After")
            sec = int(retry_after) if retry_after and retry_after.isdigit() else None
            msg = (
                f"Search rate limited by Steam. Try again in {sec}s."
                if sec
                else "Search rate limited by Steam. Try again shortly."
            )
            return SearchResult(
                status="error",
                error_message=msg,
            )
        resp.raise_for_status()

        data = resp.json()
        items = data.get("items", [])
        # Guard against total > 0 when items array is empty
        if data.get("total", 0) > 0 and items and len(items) > 0:
            top_match = items[0]
            thumb = top_match.get("tiny_image")
            if thumb and thumb.startswith("//"):
                thumb = "https:" + thumb
            return SearchResult(
                status="ok",
                item=SearchItem(
                    appid=str(top_match.get("id")),
                    name=top_match.get("name", ""),
                    thumb_url=thumb,
                ),
            )
        return SearchResult(status="none")

    except requests.exceptions.Timeout:
        return SearchResult(
            status="error",
            error_message="Steam Store Search timed out.",
        )
    except requests.exceptions.ConnectionError:
        return SearchResult(
            status="error",
            error_message="Could not reach Steam. Check your network.",
        )
    except Exception as exc:
        logger.warning(f"Store search error for '{query}': {exc}")
        return SearchResult(
            status="error",
            error_message=f"Search failed: {exc}",
        )
