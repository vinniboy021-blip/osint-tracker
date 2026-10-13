"""Official public/social APIs. No scraping, private APIs or identity inference."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote, urlsplit

from .base import LIMIT_SCHEMA, TOKEN_SCHEMA, Connector, NormalizedObservation, identifier_query, maximum
from .security import ConnectorError, validate_public_url


class GitHubConnector(Connector):
    id = "github"
    name = "GitHub Public API"
    description = "Perfis, repositórios e eventos públicos de um usuário explícito"
    token_env = "OSINT_GITHUB_TOKEN"
    capabilities = ["public_profile", "public_repositories", "public_events"]
    limitations = [
        "Sem token: até 60 requisições/hora por IP; com token sujeito à quota da API",
        "Nunca consulta conteúdo privado",
    ]
    config_schema = {
        "type": "object",
        "properties": {
            "token": TOKEN_SCHEMA,
            "mode": {"type": "string", "enum": ["profile", "repositories", "events", "repository"]},
            "limit": LIMIT_SCHEMA,
        },
    }

    def validate_query(self, query: str) -> str:
        parts = query.split("/")
        if len(parts) not in (1, 2):
            raise ConnectorError("Informe username ou owner/repository")
        for part in parts:
            identifier_query(part)
        return query

    def validate_config(self, config: dict[str, Any]) -> None:
        super().validate_config(config)
        if config.get("mode", "profile") not in ("profile", "repositories", "events", "repository"):
            raise ConnectorError("Modo GitHub inválido")

    def collect(self, query: str, config: dict[str, Any]) -> list[NormalizedObservation]:
        self.validate_config(config)
        query = self.validate_query(query)
        config = self.effective_config(config)
        mode = config.get("mode", "repository" if "/" in query else "profile")
        if mode == "repository" and "/" not in query:
            raise ConnectorError("Repositório exige owner/repository")
        if mode != "repository" and "/" in query:
            raise ConnectorError("Esse modo exige somente o username")
        path = f"/repos/{query}" if mode == "repository" else f"/users/{query}"
        if mode in ("repositories", "events"):
            path += "/repos" if mode == "repositories" else "/events/public"
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        if config.get("token"):
            headers["Authorization"] = f"Bearer {config['token']}"
        payload = self.http.json(
            "GET",
            f"https://api.github.com{path}",
            headers=headers,
            params={"per_page": maximum(config)},
            interval=1 if config.get("token") else 60,
        )
        rows = payload if isinstance(payload, list) else [payload]
        results = []
        for row in rows[: maximum(config)]:
            # Exclude sensitive and irrelevant user-contact fields; public profile metadata only.
            keys = (
                "id",
                "login",
                "name",
                "type",
                "bio",
                "company",
                "blog",
                "public_repos",
                "followers",
                "following",
                "created_at",
                "updated_at",
                "full_name",
                "description",
                "language",
                "stargazers_count",
                "forks_count",
                "pushed_at",
                "html_url",
                "repo",
                "actor",
            )
            data = {key: row[key] for key in keys if key in row}
            data["mode"] = mode
            repo = row.get("repo", {})
            url = row.get("html_url") or (
                f"https://github.com/{repo['name']}" if repo.get("name") else f"https://github.com/{query}"
            )
            value = row.get("full_name") or row.get("login") or query
            results.append(
                self.observation(
                    url,
                    str(row.get("id", value)),
                    data,
                    entity_type="repository" if mode in ("repository", "repositories") else "social_profile",
                    entity_value=str(value),
                    label=row.get("name") or str(value),
                )
            )
        return results


class GitLabConnector(Connector):
    id = "gitlab"
    name = "GitLab Public API"
    description = "Perfil público ou repositório explicitamente identificado em gitlab.com"
    token_env = "OSINT_GITLAB_TOKEN"
    capabilities = ["public_profile", "public_repositories"]
    limitations = [
        "Somente gitlab.com e dados públicos",
        "Não consulta repositórios privados mesmo com token",
    ]
    config_schema = {
        "type": "object",
        "properties": {
            "token": TOKEN_SCHEMA,
            "mode": {"type": "string", "enum": ["profile", "repository"]},
            "limit": LIMIT_SCHEMA,
        },
    }

    def validate_query(self, query: str) -> str:
        parts = query.split("/")
        if not 1 <= len(parts) <= 5:
            raise ConnectorError("Username ou namespace/projeto inválido")
        for part in parts:
            identifier_query(part)
        return query

    def validate_config(self, config: dict[str, Any]) -> None:
        super().validate_config(config)
        if config.get("mode", "profile") not in ("profile", "repository"):
            raise ConnectorError("Modo GitLab inválido")

    def collect(self, query: str, config: dict[str, Any]) -> list[NormalizedObservation]:
        self.validate_config(config)
        query = self.validate_query(query)
        config = self.effective_config(config)
        mode = config.get("mode", "repository" if "/" in query else "profile")
        headers = {"PRIVATE-TOKEN": config["token"]} if config.get("token") else {}
        if mode == "repository":
            if "/" not in query:
                raise ConnectorError("Repositório exige namespace/projeto")
            endpoint = f"https://gitlab.com/api/v4/projects/{quote(query, safe='')}"
            payload = self.http.json("GET", endpoint, headers=headers, interval=1)
            if payload.get("visibility") != "public":
                raise ConnectorError(
                    "Somente repositórios públicos são autorizados", category="authorization"
                )
            rows = [payload]
        else:
            if "/" in query:
                raise ConnectorError("Perfil exige somente o username")
            rows = self.http.json(
                "GET",
                "https://gitlab.com/api/v4/users",
                params={"username": query, "per_page": maximum(config)},
                headers=headers,
                interval=1,
            )
        keys = (
            "id",
            "username",
            "name",
            "web_url",
            "state",
            "description",
            "path_with_namespace",
            "visibility",
            "created_at",
            "last_activity_at",
            "star_count",
            "forks_count",
            "bio",
            "website_url",
        )
        return [
            self.observation(
                row["web_url"],
                str(row["id"]),
                {key: row[key] for key in keys if key in row},
                entity_type="repository" if mode == "repository" else "social_profile",
                entity_value=row.get("path_with_namespace", row.get("username")),
                label=row.get("name"),
            )
            for row in rows[: maximum(config)]
            if row.get("web_url")
        ]


class BlueskyConnector(Connector):
    id = "bluesky"
    name = "Bluesky / AT Protocol"
    description = "AppView oficial público: perfis, feed de autor e busca de posts públicos"
    capabilities = ["public_profile", "public_posts", "keywords", "hashtags"]
    limitations = [
        "Somente AppView público; sem dados privados ou bypass",
        "Busca depende da disponibilidade do endpoint oficial",
    ]
    config_schema = {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["profile", "feed", "search"]},
            "limit": LIMIT_SCHEMA,
        },
    }

    def validate_query(self, query: str) -> str:
        query = super().validate_query(query)
        if any(ord(char) < 32 for char in query):
            raise ConnectorError("Consulta Bluesky inválida")
        return query

    def validate_config(self, config: dict[str, Any]) -> None:
        super().validate_config(config)
        if config.get("mode", "profile") not in ("profile", "feed", "search"):
            raise ConnectorError("Modo Bluesky inválido")

    def collect(self, query: str, config: dict[str, Any]) -> list[NormalizedObservation]:
        self.validate_config(config)
        query = self.validate_query(query)
        mode = config.get("mode", "profile")
        if mode != "search" and not re.fullmatch(
            r"(?:[a-zA-Z0-9-]+\.)+[a-zA-Z0-9-]+|did:plc:[a-z2-7]{24}", query
        ):
            raise ConnectorError("Informe handle público completo ou DID PLC")
        method = {"profile": "getProfile", "feed": "getAuthorFeed", "search": "searchPosts"}[mode]
        params = {"q" if mode == "search" else "actor": query}
        if mode != "profile":
            params["limit"] = maximum(config)  # type: ignore[assignment]
        endpoint = (
            f"https://public.api.bsky.app/xrpc/app.bsky.actor.{method}"
            if mode == "profile"
            else f"https://public.api.bsky.app/xrpc/app.bsky.feed.{method}"
        )
        payload = self.http.json("GET", endpoint, params=params, interval=1)
        if mode == "profile":
            data = {
                key: payload[key]
                for key in (
                    "did",
                    "handle",
                    "displayName",
                    "description",
                    "followersCount",
                    "followsCount",
                    "postsCount",
                    "createdAt",
                )
                if key in payload
            }
            handle = payload.get("handle", query)
            return [
                self.observation(
                    f"https://bsky.app/profile/{handle}",
                    payload.get("did", handle),
                    data,
                    entity_type="social_profile",
                    entity_value=payload.get("did", handle),
                    label=payload.get("displayName", handle),
                )
            ]
        posts = (
            payload.get("posts", [])
            if mode == "search"
            else [entry.get("post", {}) for entry in payload.get("feed", [])]
        )
        results = []
        for post in posts[: maximum(config)]:
            author = post.get("author", {})
            uri = post.get("uri", "")
            if not uri.startswith("at://"):
                continue
            handle = author.get("handle", query)
            url = f"https://bsky.app/profile/{quote(handle, safe='')}/post/{quote(uri.rsplit('/', 1)[-1], safe='')}"
            data = {
                "uri": uri,
                "cid": post.get("cid"),
                "record": post.get("record", {}),
                "author": {key: author[key] for key in ("did", "handle", "displayName") if key in author},
                "indexedAt": post.get("indexedAt"),
                "replyCount": post.get("replyCount"),
                "repostCount": post.get("repostCount"),
                "likeCount": post.get("likeCount"),
            }
            results.append(
                self.observation(
                    url,
                    uri,
                    data,
                    entity_type="social_profile",
                    entity_value=author.get("did", handle),
                    label=author.get("displayName", handle),
                )
            )
        return results


class MastodonConnector(Connector):
    id = "mastodon"
    name = "Mastodon API oficial"
    description = "Conta e posts públicos de uma instância HTTPS explicitamente autorizada"
    token_env = "OSINT_MASTODON_TOKEN"
    capabilities = ["public_profile", "public_posts", "hashtags"]
    limitations = [
        "Exige confirmação de autorização da instância",
        "Somente posts públicos; políticas por instância",
        "URLs dinâmicas não usam proxy de ambiente e têm DNS fixado no TCP",
    ]
    config_schema = {
        "type": "object",
        "required": ["instance_url", "authorized"],
        "properties": {
            "instance_url": {"type": "string", "format": "uri"},
            "authorized": {"type": "boolean", "const": True},
            "mode": {"type": "string", "enum": ["profile", "posts", "hashtag"]},
            "token": TOKEN_SCHEMA,
            "limit": LIMIT_SCHEMA,
        },
    }

    def validate_config(self, config: dict[str, Any]) -> None:
        super().validate_config(config)
        if config.get("authorized") is not True or not config.get("instance_url"):
            raise ConnectorError(
                "Configure e autorize explicitamente a instância Mastodon", category="configuration"
            )
        validate_public_url(config["instance_url"])
        parsed = urlsplit(config["instance_url"])
        if parsed.path not in ("", "/") or parsed.query:
            raise ConnectorError("Informe somente a origem HTTPS da instância")
        if config.get("mode", "profile") not in ("profile", "posts", "hashtag"):
            raise ConnectorError("Modo Mastodon inválido")

    def validate_query(self, query: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9_@.-]{1,200}", query):
            raise ConnectorError("Informe ID de conta, username ou hashtag explícito")
        return query

    def collect(self, query: str, config: dict[str, Any]) -> list[NormalizedObservation]:
        self.validate_config(config)
        query = self.validate_query(query)
        config = self.effective_config(config)
        origin = config["instance_url"].rstrip("/")
        mode = config.get("mode", "profile")
        headers = {"Authorization": f"Bearer {config['token']}"} if config.get("token") else {}
        params: dict[str, Any] = {"limit": maximum(config, cap=40, default=20)}
        if mode == "profile":
            path = "/api/v1/accounts/lookup"
            params = {"acct": query}
        elif mode == "posts":
            if not query.isdigit():
                raise ConnectorError("Posts Mastodon exigem ID numérico da conta pública")
            path = f"/api/v1/accounts/{query}/statuses"
        else:
            if not re.fullmatch(r"[A-Za-z0-9_]{1,100}", query):
                raise ConnectorError("Hashtag inválida")
            path = f"/api/v1/timelines/tag/{quote(query, safe='')}"
        payload = self.http.json("GET", origin + path, params=params, headers=headers, interval=1)
        rows = payload if isinstance(payload, list) else [payload]
        results = []
        for row in rows[: maximum(config, cap=40, default=20)]:
            if mode != "profile" and row.get("visibility") != "public":
                continue
            keys = (
                "id",
                "username",
                "acct",
                "display_name",
                "note",
                "created_at",
                "followers_count",
                "following_count",
                "statuses_count",
                "content",
                "spoiler_text",
                "url",
                "visibility",
                "replies_count",
                "reblogs_count",
                "favourites_count",
                "edited_at",
            )
            data = {key: row[key] for key in keys if key in row}
            account = row if mode == "profile" else row.get("account", {})
            value = f"{origin}/accounts/{account.get('id', query)}"
            url = row.get("url") or f"{origin}/@{query}"
            results.append(
                self.observation(
                    url,
                    str(row.get("id", value)),
                    data,
                    entity_type="social_profile",
                    entity_value=value,
                    label=account.get("display_name"),
                )
            )
        return results


class MetaConnector(Connector):
    requires_credentials = True
    token_env = "OSINT_META_TOKEN"
    config_schema = {
        "type": "object",
        "required": ["authorized", "asset_id", "permissions"],
        "properties": {
            "token": TOKEN_SCHEMA,
            "authorized": {"type": "boolean", "const": True},
            "asset_id": {"type": "string", "pattern": "^[0-9]{1,30}$"},
            "permissions": {"type": "array", "items": {"type": "string"}},
            "api_version": {"type": "string", "pattern": "^v[0-9]{1,2}\\.[0-9]$", "default": "v25.0"},
            "limit": LIMIT_SCHEMA,
        },
    }
    required_permissions: set[str]

    def validate_config(self, config: dict[str, Any]) -> None:
        super().validate_config(config)
        if config.get("authorized") is not True:
            raise ConnectorError("O ativo Meta exige autorização oficial explícita", category="configuration")
        if not re.fullmatch(r"[0-9]{1,30}", str(config.get("asset_id", ""))):
            raise ConnectorError("Configure o ID numérico do ativo Meta autorizado", category="configuration")
        permissions = config.get("permissions", [])
        if (
            not isinstance(permissions, list)
            or not all(isinstance(item, str) for item in permissions)
            or not self.required_permissions <= set(permissions)
        ):
            raise ConnectorError("Permissões oficiais necessárias não configuradas", category="configuration")
        if not re.fullmatch(r"v[0-9]{1,2}\.[0-9]", config.get("api_version", "v25.0")):
            raise ConnectorError("Versão da Graph API inválida")

    def validate_query(self, query: str) -> str:
        if not re.fullmatch(r"[0-9]{1,30}", query):
            raise ConnectorError("Informe somente o ID do ativo Meta autorizado")
        return query

    def collect(self, query: str, config: dict[str, Any]) -> list[NormalizedObservation]:
        self.validate_config(config)
        query = self.validate_query(query)
        config = self.effective_config(config)
        if query != str(config["asset_id"]):
            raise ConnectorError(
                "A consulta não corresponde ao ativo oficialmente autorizado", category="authorization"
            )
        version = config.get("api_version", "v25.0")
        endpoint = f"https://graph.facebook.com/{version}/{query}"
        limit = maximum(config)
        fields = (
            f"id,username,name,biography,website,followers_count,media_count,media.limit({limit}){{id,caption,media_type,permalink,timestamp}}"
            if self.id == "instagram"
            else f"id,name,link,about,fan_count,posts.limit({limit}){{id,message,permalink_url,created_time}}"
        )
        payload = self.http.json(
            "GET",
            endpoint,
            params={"fields": fields},
            headers={"Authorization": f"Bearer {config['token']}"},
            interval=1,
        )
        if payload.get("error"):
            raise ConnectorError(
                "Graph API recusou as permissões do ativo autorizado", category="authorization"
            )
        edge = "media" if self.id == "instagram" else "posts"
        records = payload.pop(edge, {}).get("data", [])
        # Pagination links include access tokens on some responses; never persist them.
        payload.pop("paging", None)
        profile_url = (
            f"https://www.instagram.com/{payload.get('username', query)}/"
            if self.id == "instagram"
            else payload.get("link", f"https://www.facebook.com/{query}")
        )
        results = [
            self.observation(
                profile_url,
                query,
                payload,
                entity_type="social_profile",
                entity_value=f"{self.id}:{query}",
                label=payload.get("name"),
            )
        ]
        for row in records[:limit]:
            row.pop("paging", None)
            results.append(
                self.observation(
                    row.get("permalink") or row.get("permalink_url") or profile_url,
                    str(row["id"]),
                    row,
                    entity_type="social_profile",
                    entity_value=f"{self.id}:{query}",
                )
            )
        return results


class InstagramConnector(MetaConnector):
    id = "instagram"
    name = "Instagram API oficial / Meta"
    description = (
        "Metadados e mídia do próprio ativo profissional autorizado via Instagram API com Facebook Login"
    )
    required_permissions = {"instagram_basic", "pages_show_list", "pages_read_engagement"}
    capabilities = ["authorized_professional_profile", "authorized_professional_media"]
    limitations = [
        "Somente conta profissional vinculada à Página e autorizada",
        "Não pesquisa perfis pessoais, dados privados, seguidores individuais ou DMs",
        "Permissões declaradas não substituem revisão do app e concessão real da Meta",
    ]


class FacebookConnector(MetaConnector):
    id = "facebook"
    name = "Facebook Pages API oficial / Meta"
    description = "Metadados e posts de uma Página oficialmente autorizada"
    required_permissions = {"pages_show_list", "pages_read_engagement"}
    capabilities = ["authorized_page_profile", "authorized_page_posts"]
    limitations = [
        "Somente Página autorizada com Page access token",
        "Não pesquisa perfis pessoais ou conteúdo restrito",
        "App Review e permissões concedidas pela Meta podem ser necessárias",
    ]
