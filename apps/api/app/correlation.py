"""Explainable suggestions; association decisions always remain reversible."""

from collections import deque
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any

from app.intelligence import normalize_identifier


@dataclass(frozen=True)
class Match:
    score: float
    rule: str
    explanation: str


EXACT_TYPES = {"domain", "subdomain", "ip", "email", "username", "repository", "website", "sha256"}


def compare_entities(left: Any, right: Any) -> Match | None:
    if left.id == right.id or left.type != right.type:
        return None
    try:
        a = normalize_identifier(left.type, left.canonical_value)
        b = normalize_identifier(right.type, right.canonical_value)
    except ValueError:
        return None
    if a == b and left.type in EXACT_TYPES:
        score = 0.75 if left.type in {"username", "email"} else 0.99
        return Match(
            score,
            "exact_public_identifier",
            "Identificadores públicos normalizados iguais. Isto não comprova identidade pessoal; revisão necessária.",
        )
    # Names, biographies and images never trigger identity suggestions.
    if left.type in {"repository", "website", "document", "organization"}:
        ratio = SequenceMatcher(None, a.casefold(), b.casefold()).ratio()
        if ratio >= 0.9 and len(a) >= 8 and len(b) >= 8:
            return Match(
                round(min(ratio * 0.65, 0.65), 4),
                "similar_non_person_identifier",
                f"Similaridade textual {ratio:.1%}; hipótese não verificada, sem fusão automática.",
            )
    return None


def bounded_path(source: str, target: str, edges: list[Any], max_depth: int = 6) -> list[str]:
    if source == target:
        return [source]
    adjacency: dict[str, set[str]] = {}
    for edge in edges:
        if edge.status != "confirmed":
            continue
        a, b = str(edge.source_entity_id), str(edge.target_entity_id)
        adjacency.setdefault(a, set()).add(b)
        adjacency.setdefault(b, set()).add(a)
    visited = {source}
    queue = deque([[source]])
    while queue:
        path = queue.popleft()
        if len(path) - 1 >= max_depth:
            continue
        for neighbor in sorted(adjacency.get(path[-1], set())):
            if neighbor == target:
                return [*path, neighbor]
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append([*path, neighbor])
    return []
