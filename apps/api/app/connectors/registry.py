"""Adding a source requires implementing Connector and registering one instance here."""

from .base import Connector
from .domain import CertificateTransparencyConnector, DNSConnector, RDAPConnector
from .public import OpenStreetMapConnector, RSSConnector, URLhausConnector
from .social import (
    BlueskyConnector,
    FacebookConnector,
    GitHubConnector,
    GitLabConnector,
    InstagramConnector,
    MastodonConnector,
)

registry: dict[str, Connector] = {
    connector.id: connector
    for connector in (
        RDAPConnector(),
        DNSConnector(),
        CertificateTransparencyConnector(),
        GitHubConnector(),
        GitLabConnector(),
        BlueskyConnector(),
        MastodonConnector(),
        RSSConnector(),
        OpenStreetMapConnector(),
        URLhausConnector(),
        InstagramConnector(),
        FacebookConnector(),
    )
}
