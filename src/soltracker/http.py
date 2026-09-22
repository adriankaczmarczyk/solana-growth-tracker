"""Minimal stdlib HTTP client: retries, gzip, and an on-disk response cache."""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, Iterable, List, Optional, Tuple

USER_AGENT = "solana-growth-tracker/1.0 (+https://github.com/)"
DEFAULT_TIMEOUT = 45
DEFAULT_RETRIES = 3


class FetchError(RuntimeError):
    pass


def _cache_path(cache_dir: str, url: str) -> str:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:24]
    return os.path.join(cache_dir, digest + ".json")


def _read_cache(path: str, ttl: int) -> Optional[Any]:
    if ttl <= 0 or not os.path.exists(path):
        return None
    if time.time() - os.path.getmtime(path) > ttl:
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def _write_cache(path: str, payload: Any) -> None:
    tmp = path + ".tmp"
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(payload, fh)
        os.replace(tmp, path)
    except OSError:
        pass


def get_json(
    url: str,
    cache_dir: Optional[str] = None,
    cache_ttl: int = 0,
    timeout: int = DEFAULT_TIMEOUT,
    retries: int = DEFAULT_RETRIES,
) -> Any:
    """GET a JSON document, transparently caching it on disk for `cache_ttl` seconds."""
    path = _cache_path(cache_dir, url) if cache_dir else None
    if path:
        cached = _read_cache(path, cache_ttl)
        if cached is not None:
            return cached

    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json", "Accept-Encoding": "gzip"},
    )
    last_error: Optional[Exception] = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read()
                if response.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.decompress(raw)
                payload = json.loads(raw.decode("utf-8"))
            if path:
                _write_cache(path, payload)
            return payload
        except (urllib.error.URLError, ValueError, OSError) as exc:
            last_error = exc
            if attempt < retries - 1:
                time.sleep(1.5 * (attempt + 1))
    raise FetchError("failed to fetch {}: {}".format(url, last_error))


def get_json_many(
    urls: Iterable[str],
    workers: int = 8,
    **kwargs: Any,
) -> List[Tuple[str, Optional[Any], Optional[Exception]]]:
    """Fetch many URLs concurrently. Failures are returned, not raised."""
    url_list = list(urls)
    if not url_list:
        return []

    def _one(url: str) -> Tuple[str, Optional[Any], Optional[Exception]]:
        try:
            return url, get_json(url, **kwargs), None
        except Exception as exc:  # noqa: BLE001 - reported to the caller
            return url, None, exc

    with ThreadPoolExecutor(max_workers=max(1, min(workers, len(url_list)))) as pool:
        return list(pool.map(_one, url_list))


def cache_stats(cache_dir: str) -> Dict[str, Any]:
    if not os.path.isdir(cache_dir):
        return {"files": 0, "bytes": 0}
    files = [os.path.join(cache_dir, f) for f in os.listdir(cache_dir) if f.endswith(".json")]
    return {"files": len(files), "bytes": sum(os.path.getsize(f) for f in files)}
