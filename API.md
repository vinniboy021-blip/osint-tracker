# API REST

FastAPI expõe o contrato completo em `/docs` (Swagger UI) e `/openapi.json`. O schema é a fonte de verdade para campos, enums e validações — não mantenha uma cópia manual divergente. Todas as rotas funcionais usam o prefixo `/api/v1`.

## Autenticação e sessão

| Método | Rota | Descrição |
|--------|------|-----------|
| `POST` | `/api/v1/auth/login` | Autentica e retorna cookie de sessão + `csrf_token` |
| `GET` | `/api/v1/auth/me` | Retorna usuário atual e renova `csrf_token` |
| `POST` | `/api/v1/auth/logout` | Revoga sessão atual |
| `POST` | `/api/v1/auth/logout-all` | Revoga todas as sessões do usuário |

Cookies de sessão são `HttpOnly`; requisições de escrita (`POST`, `PATCH`, `PUT`, `DELETE`) exigem o header `X-CSRF-Token` com o valor retornado em `/me` ou `/login`.

## Usuários e administração

| Método | Rota | Acesso |
|--------|------|--------|
| `GET` | `/api/v1/admin/users` | admin |
| `POST` | `/api/v1/admin/users` | admin |
| `GET` | `/api/v1/admin/connectors` | admin |
| `GET` | `/api/v1/admin/kali/health` | admin |

## Investigações e colaboradores

| Método | Rota | Descrição |
|--------|------|-----------|
| `GET` | `/api/v1/investigations` | Lista investigações do usuário |
| `POST` | `/api/v1/investigations` | Cria investigação |
| `GET` | `/api/v1/investigations/{id}` | Detalha investigação |
| `GET` | `/api/v1/investigations/{id}/members` | Lista colaboradores |
| `POST` | `/api/v1/investigations/{id}/members` | Adiciona colaborador (`editor`/`viewer`) por `user_id` ou `email` |
| `DELETE` | `/api/v1/investigations/{id}/members/{user_id}` | Remove colaborador |

Somente o proprietário ou `admin` podem gerenciar colaboradores.

## Conectores

| Método | Rota | Descrição |
|--------|------|-----------|
| `GET` | `/api/v1/connectors` | Lista conectores com status de saúde |
| `PATCH` | `/api/v1/connectors/{id}` | Habilita/desabilita conector (admin) |
| `PUT` | `/api/v1/connectors/{id}/configuration` | Configura credenciais criptografadas (admin) |

## Coleta e monitoramento

| Método | Rota | Descrição |
|--------|------|-----------|
| `POST` | `/api/v1/jobs` | Cria job de coleta |
| `GET` | `/api/v1/jobs` | Lista jobs (com filtros de status, conector, monitor) |
| `GET` | `/api/v1/jobs/{id}` | Detalha job e execuções |
| `POST` | `/api/v1/jobs/{id}/cancel` | Cancela job ativo |
| `POST` | `/api/v1/jobs/{id}/retry` | Reenfileira job cancelado ou com falha |
| `POST` | `/api/v1/monitors` | Cria monitor recorrente (intervalo ou cron UTC) |
| `GET` | `/api/v1/monitors` | Lista monitores |
| `PATCH` | `/api/v1/monitors/{id}` | Atualiza ou pausa monitor |
| `POST` | `/api/v1/monitors/{id}/run` | Dispara execução imediata |
| `POST` | `/api/v1/social-profiles` | Cria perfil social com monitor opcional |
| `GET` | `/api/v1/social-profiles` | Lista perfis sociais |

## Observações, entidades e busca

| Método | Rota | Descrição |
|--------|------|-----------|
| `GET` | `/api/v1/observations` | Lista observações de uma investigação |
| `POST` | `/api/v1/entities` | Cria entidade manualmente |
| `GET` | `/api/v1/entities` | Lista entidades |
| `GET` | `/api/v1/search` | Busca por entidades, observações e indicadores persistidos |
| `GET` | `/api/v1/timeline` | Timeline de eventos da investigação |

## Correlação e grafo

| Método | Rota | Descrição |
|--------|------|-----------|
| `GET` | `/api/v1/correlations` | Lista candidatos de correlação |
| `POST` | `/api/v1/correlations/suggest` | Gera sugestões automáticas de correlação |
| `POST` | `/api/v1/correlations/{id}/review` | Revisa candidato (confirmed/rejected/unverified) |
| `GET` | `/api/v1/graph` | Grafo de entidades e relações (paginado) |
| `GET` | `/api/v1/graph/path` | Caminho mais curto entre duas entidades (somente `confirmed`) |

## Evidências

| Método | Rota | Descrição |
|--------|------|-----------|
| `POST` | `/api/v1/evidence` | Upload de arquivo (multipart); retorna SHA-256 |
| `GET` | `/api/v1/evidence` | Lista evidências |
| `GET` | `/api/v1/evidence/{id}/download` | Download seguro com `Content-Disposition: attachment` |
| `POST` | `/api/v1/evidence/{id}/verify` | Verifica integridade SHA-256 |
| `GET` | `/api/v1/evidence/{id}/versions` | Lista versões |
| `POST` | `/api/v1/evidence/{id}/versions` | Adiciona nova versão |
| `DELETE` | `/api/v1/evidence/{id}` | Expurga evidência e todas as versões |

## Threat intelligence

| Método | Rota | Descrição |
|--------|------|-----------|
| `POST` | `/api/v1/threat-indicators` | Registra indicador (ip, domain, sha256, url) |
| `GET` | `/api/v1/threat-indicators` | Lista indicadores |
| `GET` | `/api/v1/threat-indicators/export` | Exporta em JSON ou CSV |

## Alertas

| Método | Rota | Descrição |
|--------|------|-----------|
| `GET` | `/api/v1/alerts` | Lista alertas (com filtro por investigação) |
| `PATCH` | `/api/v1/alerts/{id}` | Marca alerta como lido |
| `POST` | `/api/v1/alerts/{id}/deliver` | Envia alerta por e-mail (parâmetro `recipient` — endereço válido obrigatório) |

## Relatórios e IA

| Método | Rota | Descrição |
|--------|------|-----------|
| `POST` | `/api/v1/reports` | Gera relatório (json, csv, md) |
| `GET` | `/api/v1/reports` | Lista relatórios |
| `GET` | `/api/v1/reports/{id}/download` | Download do relatório |
| `POST` | `/api/v1/ai/analyze` | Análise extrativa com citações (Ollama opcional) |
| `GET` | `/api/v1/ai/runs` | Lista execuções de IA |

## Workspace e auditoria

| Método | Rota | Descrição |
|--------|------|-----------|
| `POST` | `/api/v1/workspace-items` | Cria item de workspace (hypothesis/observation/task) |
| `GET` | `/api/v1/workspace-items` | Lista itens |
| `GET` | `/api/v1/audit` | Log de auditoria da investigação ou do escopo do usuário |

## Saúde e métricas

| Rota | Descrição |
|------|-----------|
| `/health/live` ou `/live` | Liveness: verifica o processo |
| `/health/ready` ou `/ready` | Readiness: verifica PostgreSQL e Redis; retorna `503` se indisponível |
| `/metrics/prometheus` | Métricas Prometheus (proteger na rede operacional; não expor publicamente) |

## Convenções

- Paginação: parâmetros `skip`/`offset` e `limit` em rotas de listagem. Limite máximo varia por rota (50–200).
- Erros de validação: `422 Unprocessable Entity`.
- Sem autenticação: `401 Unauthorized`.
- Sem permissão ou fora do escopo: `403 Forbidden` ou `404 Not Found` (objetos fora do escopo retornam 404 para não confirmar existência).
- Indisponibilidade de dependência: `502` ou `503` com mensagem explícita.
- Tokens e credenciais nunca devem ser copiados para URLs, logs ou parâmetros de query string.
