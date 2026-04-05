"""
File-based LLM response cache.

Keyed by sha256(prompt_string) so identical prompts across eval runs
return immediately without hitting the API.

Cache file: evals/utils/.cache.json  (add to .gitignore)

Usage:
    cache = LLMCache()
    key = cache.make_key(prompt_str)
    if (hit := cache.get(key)) is not None:
        return hit
    response = llm.invoke(...)
    cache.set(key, response.content)
    return response.content
"""
import hashlib
import json
import os

CACHE_PATH = os.path.join(os.path.dirname(__file__), ".cache.json")


class LLMCache:
    def __init__(self, path: str = CACHE_PATH):
        self._path = path
        self._data: dict = {}
        if os.path.exists(self._path):
            with open(self._path) as f:
                self._data = json.load(f)

    def make_key(self, prompt: str) -> str:
        return hashlib.sha256(prompt.encode()).hexdigest()

    def get(self, key: str) -> str | None:
        return self._data.get(key)

    def set(self, key: str, value: str) -> None:
        self._data[key] = value
        with open(self._path, "w") as f:
            json.dump(self._data, f, indent=2)

    def __len__(self) -> int:
        return len(self._data)
