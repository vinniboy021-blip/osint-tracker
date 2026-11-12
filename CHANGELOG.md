# Changelog

## Unreleased

### Correções de segurança (2026-11-12)

- **`notifications.py`** — corrigido `hmac.new` (inexistente) para `hmac.HMAC`; webhook estava inoperante e nunca enviava assinatura válida.
- **`notifications.py`** — webhook HTTPS passa agora por `PublicNetworkBackend` com DNS pin no momento da conexão TCP, prevenindo ataques de DNS rebinding (consistência com todos os conectores públicos).
- **`notifications.py`** — adicionado `_validate_recipient()` com regex e proteção contra header injection via endereço de e-mail malformado.
- **`routes/core.py`** — parâmetro `recipient` em `POST /alerts/{id}/deliver` trocado de `str` livre para `EmailStr` (Pydantic), garantindo validação de formato na borda da API; `ValueError` agora retorna 422 em vez de 502.
- **`main.py`** — `_RealIPMiddleware` agora só lê `X-Forwarded-For` quando o peer TCP direto é loopback ou RFC-1918/ULA; sem essa guarda qualquer cliente podia falsificar o próprio IP e escapar do throttle de login e requisições gerais.
- **`observability.py`** — `X-Request-ID` fornecido pelo cliente é sanitizado (apenas `[A-Za-z0-9\-_]`, máximo 64 caracteres) antes de ser refletido no response header e gravado no log estruturado; previne log injection e response-header injection.

### Auditoria anterior

- Auditoria profunda: corrigido isolamento entre investigações em agregados, busca, alertas e auditoria; rota administrativa de conectores passou a exigir RBAC; webhooks passaram a rejeitar destinos internos.
- Auditoria de pré-produção: bloqueio de métricas ampliado no Caddy, endpoints de colaboradores adicionados com RBAC do proprietário e respostas administrativas sem hashes de senha.
- Documentação revisada: matriz de implementação, API de colaboração, métricas, pipeline de backup/restauração e critérios de validação alinhados ao código atual.
- Dependências Python e Next.js atualizadas e auditadas com `pip-audit`, Bandit e `npm audit` sem vulnerabilidades conhecidas.
- Validados PostgreSQL/Redis reais, migrações reversíveis, coleta DNS, Celery Beat/worker e monitor recorrente.
- O endpoint `/ready` agora verifica PostgreSQL e Redis e retorna `503` quando uma dependência não está disponível.
- O CI usa `npm ci` e aguarda o servidor web antes dos testes Playwright, eliminando a condição de corrida na inicialização.
- Corrigida a configuração do Alembic e identificada formalmente a revisão inicial, permitindo `upgrade` e `downgrade` reproduzíveis.
- Revalidados Ruff, mypy, compilação Python, build/lint/typecheck do frontend e configuração do Compose.

## 0.1.0 — desenvolvimento inicial (2026-10-12)

- Inicialização de plataforma MIT com monólito modular FastAPI/Next.js e PostgreSQL/Redis/Celery.
- Docker Compose com serviço isolado de migração, volumes persistentes, worker e Beat.
- Configuração de HTTPS Caddy para produção e Prometheus opcional.
- Geração local de segredos, backup/restauração consistente de banco e evidências.
- Logging JSON com `request_id`, usuário e contexto operacional de jobs.
- Busca global persistida, revogação global de sessões e configuração administrativa de conectores.
- CI inicia API, worker, Beat e executa smoke tests Playwright.
- Grafo web com filtros de escopo e exportação JSON.
- Notificações SMTP e webhooks HMAC SHA-256 para alertas.
- Revogação global de sessões e expurgo de evidências expiradas via `make purge`.
- Documentação de arquitetura, conectores autorizados, segurança, privacidade e operação.
