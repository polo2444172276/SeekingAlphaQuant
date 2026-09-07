"""Thin wrapper around the Financial Modeling Prep REST API.

Every response is cached to disk as JSON so a backtest re-run (or a unit
test with FMP_DISABLE_NETWORK set) doesn't re-hit a paid, rate-limited API.
No network call is made until FMP_API_KEY is set — see config.py.
"""

import hashlib
import json
import os
import time

import requests

from seekingalpha_quant import config


class SymbolNotEntitled(Exception):
    """Raised when FMP 402s a specific symbol — the free/current plan doesn't
    cover it (observed: an inconsistent per-symbol allowlist, not a rate
    limit — e.g. AAPL works but PG/MA/HD/MRK/... don't, across every
    fundamentals-class endpoint). Callers should skip the symbol, not treat
    it as a transient failure."""


class FMPClient:
    def __init__(self, api_key=None, base_url=None, cache_dir=None, session=None):
        self.api_key = api_key if api_key is not None else config.FMP_API_KEY
        self.base_url = base_url or config.FMP_BASE_URL
        self.cache_dir = cache_dir or config.CACHE_DIR
        self.session = session or requests.Session()
        os.makedirs(self.cache_dir, exist_ok=True)

    def _cache_path(self, path, params):
        key = json.dumps({"path": path, "params": params}, sort_keys=True)
        digest = hashlib.sha256(key.encode()).hexdigest()
        return os.path.join(self.cache_dir, f"{digest}.json")

    def get(self, path, params=None, use_cache=True, max_retries=3):
        """GET a stable/v3-style FMP endpoint, e.g. path='/stable/ratios'."""
        params = dict(params or {})
        cache_path = self._cache_path(path, params)

        if use_cache and os.path.exists(cache_path):
            with open(cache_path, "r") as f:
                cached = json.load(f)
            if isinstance(cached, dict) and cached.get("__fmp_error__") == "symbol_not_entitled":
                raise SymbolNotEntitled(cached["message"])
            return cached

        if not self.api_key:
            raise RuntimeError(
                "FMP_API_KEY is not set. Set it in .env before making live "
                "FMP requests, or pre-populate the .cache/ dir with fixtures."
            )

        params["apikey"] = self.api_key
        url = f"{self.base_url}{path}"

        last_error = None
        for attempt in range(max_retries):
            response = self.session.get(url, params=params, timeout=30)
            if response.status_code == 429:
                last_error = RuntimeError(f"FMP rate limited (attempt {attempt + 1})")
                time.sleep(2 ** attempt)
                continue
            if response.status_code == 402:
                message = f"{path} symbol={params.get('symbol')}: not available under the current FMP plan"
                # Cache the gate itself (not just successes) so re-runs don't
                # keep burning quota re-probing symbols already known to be
                # blocked. If the FMP plan is later upgraded, clear .cache/
                # (or the specific entries) to re-probe.
                with open(cache_path, "w") as f:
                    json.dump({"__fmp_error__": "symbol_not_entitled", "message": message}, f)
                raise SymbolNotEntitled(message)
            response.raise_for_status()
            data = response.json()
            with open(cache_path, "w") as f:
                json.dump(data, f)
            return data

        raise last_error
