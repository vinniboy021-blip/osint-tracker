# Registro de validação

Registro atualizado em 2026-10-29. Nenhum check é aprovado por pressuposição; cada item abaixo corresponde a um comando ou fluxo executado.

| Check | Estado inicial |
|---|---|
| Compose config/build/start | `docker compose config --quiet` passou; PostgreSQL e Redis iniciaram. O build completo da API depende de acesso de rede do BuildKit ao índice Python neste executor. |
| Readiness de PostgreSQL/Redis | Implementado: `/ready` verifica as duas dependências e retorna `503` com diagnóstico quando alguma falha |
| Alembic upgrade/downgrade/upgrade | Passou em PostgreSQL real, incluindo `alembic check` |
| Ruff/mypy/pytest | Ruff e mypy passaram; 50 testes passaram |
| ESLint/TypeScript/Next build | Passou com Next.js 16.4.3 |
| Playwright fluxo real de API | Workflow CI configurado; execução depende do runner GitHub |
| Coleta pública remota e persistência | DNS de `example.com` coletado e persistido com sucesso |
| Monitor Beat/worker sem ação manual | Passou com Celery Beat, Redis, worker e PostgreSQL reais |
| Backup/restore | Scripts presentes; ensaio de restauração de desastre ainda pendente |
| Auditoria de dependências | `pip-audit`, Bandit e `npm audit` passaram sem achados bloqueadores |

Validação executada nesta revisão: dependências Python foram instaladas no `.venv`; `ruff check apps/api`, `mypy apps/api/app`, compilação Python, importação da aplicação com OpenAPI, 50 testes, migrações em PostgreSQL, readiness real, coleta DNS, monitor Celery, validação do Caddy e frontend (`typecheck`, `lint` e `build`) passaram. O build da imagem API não completou neste executor porque o isolamento de build do pip não recebeu acesso de rede; o Dockerfile já atualiza `pip/setuptools` para instalações normais. O fluxo Playwright permanece delegado ao CI.

Integrações que exigem credenciais oficiais Meta e modelo local não são marcadas validadas sem essas dependências. Testes de contrato usam fixtures explicitamente identificadas.
