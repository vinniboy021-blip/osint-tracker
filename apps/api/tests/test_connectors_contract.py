"""Contract tests that never contact remote services."""

import pytest

from app.connectors.registry import registry


@pytest.mark.parametrize("connector_id", sorted(registry))
def test_connector_descriptor_is_safe(connector_id):
    connector = registry[connector_id]
    descriptor = connector.descriptor()
    assert descriptor["id"] == connector_id
    assert descriptor["name"]
    assert "writeOnly" in str(descriptor) or "token" not in str(descriptor).lower()


@pytest.mark.parametrize("connector_id", ["instagram", "facebook", "mastodon"])
def test_authorized_connectors_do_not_claim_configuration(connector_id):
    connector = registry[connector_id]
    health = connector.health({})
    assert health["status"] in {"needs_configuration", "unconfigured", "error"}
