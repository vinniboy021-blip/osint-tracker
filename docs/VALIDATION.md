# Registro de validação

Registro inicial, 2026-10-12. Nenhum check é aprovado por pressuposição. Este arquivo será atualizado com comandos executados, resultado e limitações observadas após integração dos módulos.

| Check | Estado inicial |
|---|---|
| Compose config/build/start | `docker compose config --quiet` passou com `POSTGRES_PASSWORD` temporária; build/start bloqueado no ambiente porque o socket Docker retornou `operation not permitted` |
| Readiness de PostgreSQL/Redis | Implementado: `/ready` verifica as duas dependências e retorna `503` com diagnóstico quando alguma falha |
| Alembic PostgreSQL upgrade/downgrade/upgrade | A executar |
| Ruff/mypy/pytest | Ruff e mypy passaram; 41 testes unitários/contrato passaram. Testes que usam `TestClient` ficam bloqueados pelo runtime anyio deste executor |
| ESLint/TypeScript/Next build | Passou: `npm ci`, `npm run typecheck`, `npm run lint` e `npm run build` |
| Playwright fluxo real de API | A executar |
| Coleta pública remota e persistência | A executar |
| Monitor Beat/worker sem ação manual | A executar |
| Backup/restore | A executar |
| Auditoria de dependências | A executar no CI/release |

Validação executada nesta revisão: dependências Python foram instaladas no `.venv`; `ruff check apps/api`, `mypy apps/api/app`, `python -m compileall apps/api/app`, importação da aplicação com OpenAPI, 30 testes unitários/contrato selecionados e o frontend (`typecheck`, `lint` e `build`) passaram. O Docker continua indisponível no executor. A criação de `TestClient` bloqueia neste runtime mesmo para uma aplicação FastAPI vazia; os testes de API devem ser executados no CI.

Integrações que exigem credenciais oficiais Meta e modelo local não são marcadas validadas sem essas dependências. Testes de contrato usam fixtures explicitamente identificadas.
