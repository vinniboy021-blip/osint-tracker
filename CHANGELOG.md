# Changelog

## Unreleased

- Auditoria profunda: corrigido isolamento entre investigações em agregados, busca, alertas e auditoria; rota administrativa de conectores passou a exigir RBAC; webhooks passaram a rejeitar destinos internos.
- Auditoria de pré-produção: bloqueio de métricas ampliado no Caddy, endpoints de colaboradores adicionados com RBAC do proprietário e respostas administrativas sem hashes de senha.
- Documentação revisada: matriz de implementação, API de colaboração, métricas, pipeline de backup/restauração e critérios de validação alinhados ao código atual.
- Dependências Python e Next.js atualizadas e auditadas com `pip-audit`, Bandit e `npm audit` sem vulnerabilidades conhecidas.
- Validados PostgreSQL/Redis reais, migrações reversíveis, coleta DNS, Celery Beat/worker e monitor recorrente; relatório detalhado em `docs/AUDIT.md`.
- O endpoint `/ready` agora verifica PostgreSQL e Redis e retorna `503` quando uma dependência não está disponível.
- O CI usa `npm ci` e aguarda o servidor web antes dos testes Playwright, eliminando a condição de corrida na inicialização.
- Corrigida a configuração do Alembic e identificada formalmente a revisão inicial, permitindo `upgrade` e `downgrade` reproduzíveis.
- Revalidados Ruff, mypy, compilação Python, build/lint/typecheck do frontend e configuração do Compose.

## 0.1.0 — desenvolvimento inicial (2026-10-12)

- Inicialização de plataforma MIT com monólito modular FastAPI/Next.js e PostgreSQL/Redis/Celery.
- Docker Compose com serviço isolado de migração, volumes persistentes, worker e Beat.
- Configuração de HTTPS Caddy para produção e Prometheus opcional.
- Geração local de segredos, backup/restauração consistente de banco e evidências.
- Documentação de arquitetura, conectores autorizados, segurança, privacidade e operação.
- Funcionalidades de aplicação e resultados de checks estão detalhados na matriz de implementação e no registro de validação; esta entrada não certifica um release de produção.
# 0.1.0

- Licença MIT aplicada ao projeto backend e frontend.
- Dependências HTTP de teste fixadas em versões compatíveis com Starlette/FastAPI.
- Uploads de evidências corrigidos para leitura determinística e limitada em workers.
- Fixtures isoladas de PostgreSQL/Redis para testes locais e contratos de conectores.
- Logging JSON com `request_id`, usuário e contexto operacional de jobs.
- Busca global persistida, revogação global de sessões e configuração administrativa de conectores.
- CI agora inicia API, worker, Beat e executa smoke tests Playwright.
- Grafo web com filtros de escopo e exportação JSON.
- Configuração de notificações SMTP e webhooks HMAC para alertas.
- Revogação global de sessões e expurgo de evidências expiradas via `make purge`.
- Busca global por entidades, observações e indicadores.
