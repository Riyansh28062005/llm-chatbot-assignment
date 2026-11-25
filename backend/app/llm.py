import os
import time
import hashlib
import json

import litellm


class AllProvidersUnavailable(Exception):
    pass


_CACHE = {}


def get_keys():
    raw = os.getenv("LLM_API_KEYS", "")
    return [k.strip() for k in raw.split(",") if k.strip()]


def cache_enabled():
    return os.getenv("CACHE_ENABLED", "true").lower() == "true"


def parse_simulation(header):
    if not header:
        return {}

    if os.getenv("ENABLE_FAILURE_SIMULATION", "false").lower() != "true":
        return {}

    result = {}

    for part in header.split(","):
        if "=" not in part:
            continue

        key, value = part.split("=", 1)

        try:
            result[key.strip()] = int(value.strip())
        except ValueError:
            pass

    return result


def _cache_key(messages, model):
    payload = json.dumps(
        {"messages": messages, "model": model},
        sort_keys=True,
        ensure_ascii=False,
    )

    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def complete(messages, simulation=None):
    simulation = simulation or {}

    model = os.getenv(
        "LLM_MODEL",
        "gemini/gemini-3.5-flash-lite",
    )

    mock = os.getenv("LLM_MOCK", "false").lower() == "true"

    cache_key = _cache_key(messages, model)

    if cache_enabled() and cache_key in _CACHE:
        cached = dict(_CACHE[cache_key])
        cached["cache_hit"] = True
        return cached

    keys = get_keys()

    if mock:
        reply = "[mock] " + messages[-1]["content"]

        result = {
            "reply": reply,
            "model": model,
            "input_tokens": 10,
            "output_tokens": 20,
            "key_id": "mock",
            "fallback_attempts": 0,
            "cache_hit": False,
        }

        if cache_enabled():
            _CACHE[cache_key] = dict(result)

        return result

    if not keys:
        raise AllProvidersUnavailable()

    fallback_attempts = 0

    for index, api_key in enumerate(keys, start=1):
        key_id = f"key_{index}"

        try:
            if key_id in simulation:
                code = simulation[key_id]
                raise RuntimeError(f"simulated provider failure {code}")

            response = litellm.completion(
                model=model,
                messages=messages,
                api_key=api_key,
                timeout=30,
            )

            reply = response.choices[0].message.content

            usage = getattr(response, "usage", None)

            input_tokens = (
                getattr(usage, "prompt_tokens", 0)
                if usage
                else 0
            )

            output_tokens = (
                getattr(usage, "completion_tokens", 0)
                if usage
                else 0
            )

            result = {
                "reply": reply,
                "model": model,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "key_id": key_id,
                "fallback_attempts": fallback_attempts,
                "cache_hit": False,
            }

            if cache_enabled():
                _CACHE[cache_key] = dict(result)

            return result

        except Exception as exc:
            print(f"WARNING: {key_id} failed: {type(exc).__name__}: {exc}")
            fallback_attempts += 1

    raise AllProvidersUnavailable()