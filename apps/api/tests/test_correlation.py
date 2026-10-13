from types import SimpleNamespace

from app.correlation import bounded_path, compare_entities


def entity(identifier, kind, value):
    return SimpleNamespace(id=identifier, type=kind, canonical_value=value)


def edge(a, b, status="confirmed"):
    return SimpleNamespace(source_entity_id=a, target_entity_id=b, status=status)


def test_normalized_domain_match_is_only_a_reviewable_candidate():
    match = compare_entities(entity("a", "domain", "EXAMPLE.ORG."), entity("b", "domain", "example.org"))
    assert match and match.rule == "exact_public_identifier" and match.score == 0.99
    assert "revisão" in match.explanation


def test_person_and_profile_similarity_never_proves_identity():
    assert (
        compare_entities(entity("a", "person", "Maria Silva"), entity("b", "person", "Maria Silva")) is None
    )
    assert (
        compare_entities(
            entity("a", "social_profile", "Maria Silva"), entity("b", "social_profile", "Maria Silva")
        )
        is None
    )
    match = compare_entities(entity("a", "username", "maria"), entity("b", "username", "MARIA"))
    assert match and match.score < 0.8


def test_probabilistic_non_person_rule_is_explainable_and_low_confidence():
    match = compare_entities(
        entity("a", "organization", "Example Corporation A"),
        entity("b", "organization", "Example Corporation B"),
    )
    assert match and match.rule == "similar_non_person_identifier" and match.score <= 0.65
    assert "sem fusão" in match.explanation


def test_path_uses_confirmed_relationships_and_respects_depth():
    edges = [edge("a", "b"), edge("b", "c"), edge("c", "d", "unverified"), edge("a", "x", "rejected")]
    assert bounded_path("a", "c", edges, max_depth=2) == ["a", "b", "c"]
    assert bounded_path("a", "c", edges, max_depth=1) == []
    assert bounded_path("a", "d", edges) == []
    assert bounded_path("a", "x", edges) == []


def test_invalid_domains_cannot_generate_candidates():
    assert compare_entities(entity("a", "domain", "*.bad"), entity("b", "domain", "*.bad")) is None
