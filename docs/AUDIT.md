# Auditoria profunda de segurança e operação

Data da revisão: 29/10/2026 (BRT)
Escopo: backend FastAPI, workers Celery, PostgreSQL, Redis, frontend Next.js, Docker Compose, migrações, controles de acesso, conectores HTTP e cadeia de evidências.

## Resultado executivo

A revisão encontrou e corrigiu um vazamento de escopo entre investigações, uma autorização administrativa incompleta, um problema de exclusão em cascata de evidências e vulnerabilidades conhecidas nas dependências Python e JavaScript. Também foram corrigidos o estágio de build do frontend e o alvo local de auditoria do Makefile.

O fluxo funcional foi exercitado com PostgreSQL e Redis reais: autenticação, criação de investigação, coleta DNS pública, persistência de observações, execução recorrente por Celery Beat/worker e atualização do monitor. O repositório ainda não deve ser tratado como certificado para produção: não foi realizado pentest independente, DAST externo ou teste de restauração em ambiente de desastre.

## Achados corrigidos

| ID | Severidade | Achado | Correção |
|---|---|---|---|
| AUD-01 | Alta | Dashboard, busca, alertas e auditoria podiam consultar registros de outras investigações quando o usuário não informava um filtro. | Todos os agregados e consultas globais usam o conjunto de investigações do proprietário ou membro; administradores mantêm visão global. Teste dedicado cobre isolamento. |
| AUD-02 | Alta | A listagem de conectores administrativos aceitava qualquer usuário autenticado. | Rota protegida por `require_admin`; teste verifica resposta 403 para analista. |
| AUD-03 | Média | Exclusão de evidência removia versões explicitamente e também acionava cascata do banco, gerando bookkeeping inconsistente do ORM. | A exclusão do pai usa a cascata `ON DELETE CASCADE`; a cadeia de custódia permanece consistente. |
| AUD-04 | Alta | `starlette`, `next`/`eslint-config-next` e ferramentas de desenvolvimento tinham versões vulneráveis ou antigas. | Dependências atualizadas; `pip-audit` e `npm audit --audit-level=high` sem vulnerabilidades conhecidas. |
| AUD-05 | Média | Build de produção do frontend omitia dependências de desenvolvimento necessárias ao TypeScript/lint/build. | Dockerfile usa `npm ci` no estágio de build e mantém apenas o artefato standalone no runtime. |
| AUD-06 | Baixa | `make audit` tentava gravar cache em diretório não gravável no executor. | Cache direcionado para `XDG_CACHE_HOME` configurável, com fallback em `/tmp`. |
| AUD-07 | Média | Webhooks configurados no servidor podiam causar requisições para destinos internos em caso de configuração comprometida. | Destino passa pela mesma validação HTTPS/porta 443/endereço público usada pelos conectores antes do POST. |
| AUD-08 | Média | O bloqueio de métricas no Caddy não cobria o caminho montado `/metrics/prometheus`. | Matcher atualizado para bloquear `/metrics*` e `/api/metrics*` na borda pública. |
| AUD-09 | Média | O modelo de colaboradores existia, mas não havia API para o proprietário gerenciar membros. | Adicionados endpoints autenticados para listar, adicionar, atualizar e remover membros; respostas nunca incluem hashes de senha. |

## Evidências executadas

- `pytest apps/api/tests -q`: 50 testes aprovados.
- `ruff check apps/api`: aprovado.
- `mypy apps/api/app`: aprovado.
- `pip-audit --local`: nenhuma vulnerabilidade conhecida.
- `bandit -r apps/api/app --severity-level medium`: nenhum achado de severidade média ou alta.
- `npm run typecheck`, `npm run lint` e `npm run build`: aprovados com Next.js 16.
- `npm audit --audit-level=high`: 0 vulnerabilidades.
- Alembic em PostgreSQL real: `upgrade head`, `downgrade base`, `upgrade head` e `alembic check` aprovados.
- API real: `/ready` retornou PostgreSQL e Redis como `ok`.
- Coleta real: consulta DNS de `example.com` foi persistida como observações e finalizou como `succeeded`.
- Monitor real: Celery Beat agendou a execução, worker processou a tarefa e o próximo vencimento foi atualizado.
- `docker compose config --quiet` e configuração de produção passaram.
- `caddy:2-alpine caddy validate` aprovou a configuração da borda HTTPS e do bloqueio de métricas.

## Riscos residuais e próximos passos

1. Não houve pentest independente, DAST autenticado ou revisão externa de configuração de uma implantação pública.
2. O teste de backup e restauração ainda precisa ser executado em um ambiente descartável com PostgreSQL e armazenamento de evidências, incluindo restauração após falha.
3. A integração Meta depende de credenciais e permissões oficiais; não é declarada funcional sem elas. O adaptador Kali/MCP continua opcional e não concede privilégios de execução arbitrária.
4. O endpoint Prometheus está bloqueado no Caddy e deve continuar protegido pela rede/edge em produção; métricas não devem ser expostas diretamente à Internet.
5. A migração inicial usa `Base.metadata.create_all`; as próximas alterações devem ser migrações Alembic explícitas para garantir rollback e revisão de esquema.
6. O `TestClient` de Starlette emite aviso de depreciação para `httpx`; a suíte passa, mas a migração para o cliente recomendado deve ser planejada antes da próxima atualização major.
7. O transporte HTTP seguro usa um detalhe interno de `httpcore` para fixar resolução DNS. Uma atualização de `httpx/httpcore` deve ser acompanhada por testes de SSRF e de conexão TLS.
8. A interface web ainda precisa expor todas as operações de colaboração adicionadas à API; o backend já aplica autorização do proprietário.

## Conclusão

Os controles críticos verificados nesta rodada estão cobertos por código e testes automatizados. O release pode avançar como versão de desenvolvimento/RC após revisar os riscos residuais acima; a classificação como produção deve aguardar teste de restauração, DAST e revisão operacional dos segredos, backups, Caddy e políticas de retenção.
