"""Tiny HTTPS GET helper with retry and rate limiting (stdlib only)."""

from __future__ import annotations

import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping

Fetcher = Callable[[str, Mapping[str, str]], str]

USER_AGENT = "aesculap-asi-knowledge/0.1"
_RETRY_CODES = {429, 500, 502, 503, 504}
_last_request = 0.0


def http_get(
    url: str,
    params: Mapping[str, str],
    *,
    retries: int = 3,
    timeout: float = 30.0,
    min_interval: float = 0.34,
) -> str:
    """GET ``url`` with ``params``. HTTPS only. Retries transient failures."""
    global _last_request
    if not url.startswith("https://"):
        raise ValueError(f"refusing non-HTTPS url: {url}")
    full = f"{url}?{urllib.parse.urlencode(params)}" if params else url
    request = urllib.request.Request(full, headers={"User-Agent": USER_AGENT})
    for attempt in range(retries):
        wait = min_interval - (time.monotonic() - _last_request)
        if wait > 0:
            time.sleep(wait)
        _last_request = time.monotonic()
        try:
            with urllib.request.urlopen(request, timeout=timeout) as resp:
                return str(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code in _RETRY_CODES and attempt < retries - 1:
                time.sleep(2**attempt)
                continue
            raise
        except urllib.error.URLError:
            if attempt < retries - 1:
                time.sleep(2**attempt)
                continue
            raise
    raise RuntimeError("unreachable")
