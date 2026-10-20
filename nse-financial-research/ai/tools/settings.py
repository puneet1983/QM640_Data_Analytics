"""Load deployer-controlled settings, prompts and response schemas."""

import hashlib
import json
from pathlib import Path


def validate_lookup(config):
    provider = config.get("provider", "http_json")
    if provider == "fallback":
        if not config.get("providers"):
            raise ValueError("Fallback lookup requires at least one provider")
        for entry in config["providers"]:
            if entry.get("provider") == "fallback":
                raise ValueError("Nested fallback lookup is not supported")
            validate_lookup({**config, **entry})
    elif provider == "ddgs":
        if not config.get("backend"):
            raise ValueError("DDGS lookup requires a backend")
        if type(config["web_search"]["max_results"]) is not int or config["web_search"]["max_results"] < 1:
            raise ValueError("Web search max_results must be positive")
    elif provider == "wikipedia":
        limit = config["wikipedia"]["search_limit"]
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("Wikipedia search_limit must be between 1 and 100")
    elif provider == "http_json":
        for name in ("symbol", "company_name", "industry", "sector"):
            if not config["fields"].get(name):
                raise ValueError(f"Lookup config requires a field path for {name}")
    else:
        raise ValueError("Unsupported lookup provider")
    if config["timeout_seconds"] <= 0 or config.get("delay_seconds", 0) < 0:
        raise ValueError("Lookup timeout must be positive and delay must be nonnegative")


def load_settings(path):
    path = Path(path)
    config = json.loads(path.read_text(encoding="utf-8"))
    llm = config["llm"]
    if type(llm["batch_size"]) is not int or llm["batch_size"] < 1:
        raise ValueError("LLM batch_size must be a positive integer")
    if type(llm["max_completion_tokens"]) is not int or llm["max_completion_tokens"] < 1:
        raise ValueError("LLM max_completion_tokens must be a positive integer")
    llm["prompt"] = (path.parent / llm["prompt_file"]).read_text(encoding="utf-8")
    llm["schema"] = json.loads((path.parent / llm["schema_file"]).read_text(encoding="utf-8"))
    validate_lookup(config["lookup"])
    # Tuning request grouping/budgets must not invalidate completed classifications.
    cache_config = {**config, "llm": {key: value for key, value in llm.items()
                     if key not in ("batch_size", "max_completion_tokens", "timeout_seconds", "max_retries")}}
    digest = hashlib.sha256(json.dumps(cache_config, sort_keys=True).encode()).hexdigest()[:12]
    config["cache_version"] = config["version"] + ":" + digest
    return config
