# Conectores públicos e autorizados

O registry expõe IDs, capabilities, schema de configuração, limitações e estado operacional. Cada conector implementa validação de configuração/consulta, `collect`, resultados normalizados e indicador de saúde. `configured` significa configuração válida; disponibilidade remota só é comprovada por execução bem-sucedida. Respostas vazias e erros jamais são preenchidos com fixtures.

| ID | Consulta e configuração | Autorização e limites |
|---|---|---|
| `rdap` | Domínio exato, bootstrap IANA/registro | Registro público; contatos pessoais minimizados; disponibilidade por TLD |
| `dns` | Domínio exato; `record_type` A/AAAA/MX/NS/TXT/CNAME/SOA/CAA | DNS over HTTPS; não conecta aos IPs retornados, não faz AXFR |
| `crtsh` | Domínio exato; `limit` até 100 | CT público, sem wildcard; disponibilidade não garantida; certificado não prova controle atual |
| `github` | Username ou owner/repository; `mode` profile/repositories/events/repository | API pública; sem token até 60 requisições/hora por IP; credencial opcional gratuita |
| `gitlab` | Username ou namespace/projeto; `mode` profile/repository | gitlab.com; repositórios privados recusados mesmo com token |
| `bluesky` | Handle/DID; `mode` profile/feed/search | AppView público; palavras-chave/hashtags somente no endpoint oficial |
| `mastodon` | Conta/ID/hashtag; origem `instance_url`, `authorized=true`, `mode` | Políticas da instância; HTTPS público; posts somente públicos; até 40 por consulta |
| `rss` | URL HTTPS de feed RSS/Atom autorizado | Sem HTML scraping; destino público validado; limites de resposta e itens |
| `news` | Feed público de notícias autorizado | Mesmos controles RSS/Atom; licenciamento da fonte continua aplicável |
| `osm` | Consulta geográfica pública; configuração conforme registry | Política Nominatim, identificador de contato e limites; não extrai localização de pessoas |
| `threat_feed` | Fonte pública suportada conforme registry | Indicadores defensivos, fonte/versionamento; respeite licença do feed |
| `instagram` | ID do ativo profissional autorizado | Somente API oficial com Facebook Login, token e permissões reais; sem busca arbitrária de perfis |
| `facebook` | ID da Página autorizada | Somente Graph API e Page access token autorizado |

Os nomes e schemas de `news`, `osm` e `threat_feed` devem ser conferidos no registry da versão instalada. Tokens opcionais também podem ser fornecidos por `OSINT_GITHUB_TOKEN`, `OSINT_GITLAB_TOKEN`, `OSINT_MASTODON_TOKEN` e `OSINT_META_TOKEN` em ambientes de worker explicitamente configurados. A instalação padrão não depende deles.

## Meta

Configuração exige `authorized=true`, `asset_id`, `permissions`, `token` e versão `api_version` suportada pela Meta (default da implementação: `v25.0`). As permissões declaradas devem corresponder às concessões efetivas; a Graph API é a autoridade final, podendo exigir App Review, tipo correto de token e vínculo profissional/Página.

- Instagram: `instagram_basic`, `pages_show_list`, `pages_read_engagement`; consulta conta profissional vinculada à Página e sua mídia autorizada.
- Facebook: `pages_show_list`, `pages_read_engagement`; consulta a Página e posts autorizados.

Não se consultam DMs, perfis privados, seguidores individuais ou contas pessoais arbitrárias. Não há scraping nem API privada. Esta integração fica não validada remotamente sem credenciais e permissões oficiais; testes de contrato com mocks não comprovam autorização externa.

## Limites e segurança

O cliente aplica timeouts, retry limitado com backoff, limites de resposta e de resultados. URLs fornecidas por usuários precisam ser HTTPS, públicas, sem credenciais na URL, portas inseguras ou destinos internos/metadata. Redirecionamentos exigem revalidação. SSRF não é resolvido por blacklist textual; IPs resolvidos também devem ser públicos, e destinos dinâmicos usam pinning da resolução na conexão.

As quotas oficiais mudam. Observe 429/Retry-After e headers de limite; configure intervalos conservadores e reduza concorrência quando necessário. A fila não deve executar coleta massiva indiscriminada. Não tente evadir limites distribuindo requisições entre identidades ou proxies.

Para adicionar uma fonte, implemente o contrato em `app/connectors/base.py`, registre a classe, inclua fixtures explicitamente de teste e testes de erro, timeout, autorização, SSRF e normalização. Não altere o núcleo de agendamento para cada nova fonte.
