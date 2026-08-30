"""Denormalize Voyager's Rest.li "decorated" responses.

A Voyager response is a normalized object graph, not a nested document:

  {
    "data":     { ... references entities by URN ... },
    "included": [ {"entityUrn": "urn:li:fsd_profile:ABC", "$type": "...Profile", ...},
                  {"entityUrn": "urn:li:fsd_profilePosition:(ABC,1)", ...}, ... ]
  }

Everything real lives in `included[]`, keyed by `entityUrn`; `data` (and nested objects)
point at those URNs with `"*fieldName": "urn:..."` or `"*elements": ["urn:...", ...]`.
This helper indexes `included[]` so the parser can resolve those references by URN and
by type — which is exactly the step naive parsers skip.
"""
from __future__ import annotations

from collections.abc import Iterable
from typing import Any


class VoyagerGraph:
    def __init__(self, response: dict[str, Any]) -> None:
        self.response = response or {}
        self.data: dict[str, Any] = self.response.get("data") or {}
        self.included: list[dict[str, Any]] = self.response.get("included") or []
        self._by_urn: dict[str, dict[str, Any]] = {}
        for entity in self.included:
            urn = entity.get("entityUrn")
            if isinstance(urn, str):
                self._by_urn[urn] = entity

    def resolve(self, urn: str | None) -> dict[str, Any] | None:
        if not urn:
            return None
        return self._by_urn.get(urn)

    def resolve_many(self, urns: Iterable[str] | None) -> list[dict[str, Any]]:
        if not urns:
            return []
        out = []
        for urn in urns:
            entity = self._by_urn.get(urn)
            if entity is not None:
                out.append(entity)
        return out

    def by_type(self, type_suffix: str) -> list[dict[str, Any]]:
        """All included entities whose $type ends with the given suffix (case-insensitive)."""
        suffix = type_suffix.lower()
        return [
            e for e in self.included
            if isinstance(e.get("$type"), str) and e["$type"].lower().endswith(suffix)
        ]

    def first_of_type(self, type_suffix: str) -> dict[str, Any] | None:
        matches = self.by_type(type_suffix)
        return matches[0] if matches else None

    def deref(self, container: dict[str, Any], key: str) -> Any:
        """Resolve a "*key" URN reference (single or list) from a container object."""
        star = container.get(f"*{key}")
        if isinstance(star, str):
            return self.resolve(star)
        if isinstance(star, list):
            return self.resolve_many(star)
        return container.get(key)
