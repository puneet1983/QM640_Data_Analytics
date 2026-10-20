"""Retrieve structured company classifications independently of the LLM."""

import time
from urllib.parse import urlencode


class LookupFailure(ValueError):
    """Controlled lookup diagnostic without raw response payloads."""


def field_value(payload, path):
    value = payload
    for part in path.split("."):
        value = value.get(part) if isinstance(value, dict) else None
    return value.strip() if isinstance(value, str) else ""


class CompanyLookup:
    """A configurable symbol search against a structured JSON source.

    The source returns values. This tool neither guesses labels nor invokes an LLM.
    """

    def __init__(self, config, session=None):
        self.config = config
        if session is None:
            import requests
            session = requests.Session()
        self.session = session
        self.session.headers.update(config.get("headers", {}))
        self.initialized = False
        self.last_request = None

    def _get(self, url):
        import requests
        if self.last_request is not None:
            delay = self.config.get("delay_seconds", 0) - (time.monotonic() - self.last_request)
            if delay > 0:
                time.sleep(delay)
        try:
            response = self.session.get(url, timeout=self.config["timeout_seconds"])
            if response.status_code >= 400:
                raise LookupFailure(f"Lookup: HTTP {response.status_code}; source access failed")
            return response
        except requests.RequestException as error:
            raise LookupFailure(f"Lookup: {type(error).__name__}; check source connectivity") from error
        finally:
            self.last_request = time.monotonic()

    def search(self, company):
        if not self.initialized:
            if self.config.get("session_url"):
                self._get(self.config["session_url"])
            self.initialized = True
        query = urlencode({self.config["symbol_parameter"]: company["NSE_SYMBOL"]})
        separator = "&" if "?" in self.config["endpoint"] else "?"
        source_url = self.config["endpoint"] + separator + query
        response = self._get(source_url)
        try:
            payload = response.json()
        except ValueError as error:
            raise LookupFailure("Lookup: source returned non-JSON data; no classification extracted") from error
        if not isinstance(payload, dict):
            raise LookupFailure("Lookup: expected a JSON object; check configured source and field paths")
        record = {name: field_value(payload, path) for name, path in self.config["fields"].items()}
        record.update(taxonomy=self.config["taxonomy"], source_url=source_url)
        return record


def create_lookup(config, session=None):
    provider = config.get("provider", "http_json")
    if provider == "http_json":
        return CompanyLookup(config, session)
    if provider == "wikipedia":
        from ai.tools.wikipedia_lookup import WikipediaLookup
        return WikipediaLookup(config, session)
    if provider == "ddgs":
        from ai.tools.web_search_lookup import WebSearchLookup
        return WebSearchLookup(config, session)
    if provider == "fallback":
        from ai.tools.fallback_lookup import FallbackLookup
        tools = []
        for entry in config["providers"]:
            if entry["provider"] == "fallback":
                raise ValueError("Nested fallback tools are not supported")
            settings = {**config, **entry}
            tools.append((entry.get("backend", entry["provider"]), create_lookup(settings)))
        return FallbackLookup(tools)
    raise ValueError("Unsupported lookup provider")
