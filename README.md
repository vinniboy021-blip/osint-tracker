# OSINT Tracker

Plataforma open source (MIT) em português brasileiro para investigações sobre fontes públicas e autorizadas. Monólito modular em **FastAPI**, **PostgreSQL**, **Redis/Celery** e **Next.js**. Fontes, observações, decisões e evidências mantêm proveniência auditável. Não há dependência obrigatória de serviços pagos.

> **Uso autorizado.** A existência de conteúdo publicamente acessível não elimina obrigações legais de finalidade, autorização e retenção. Veja [PRIVACY.md](PRIVACY.md) e [SECURITY.md](SECURITY.md).

## Requisitos

| Componente | Versão mínima |
|---|---|
| Docker Engine | 24+ |
| Docker Compose | 2.24.4+ |
| RAM disponível | 4 GB |
| Python (scripts) | 3.12+ |

## Início rápido

```bash
cp .env.example .env
python3 scripts/setup_env.py        # gera senhas e chave Fernet — não imprime segredos
docker compose up -d --build
docker compose exec api python -m app.cli create-admin --email admin@example.org
```

A senha é solicitada interativamente e não é registrada. **Não existe administrador ou senha padrão.**

- Interface web: http://localhost:3000
- Documentação OpenAPI: http://localhost:8000/docs
- PostgreSQL e Redis **não** publicam portas no host.

O serviço `migrate` aplica as migrações Alembic antes de liberar API, workers e scheduler.

## Fluxo de uso básico

1. Autentique-se e crie uma investigação com objetivo, escopo e base de autorização.
2. Selecione um conector (ex.: `github`) e consulte um perfil ou repositório público.
3. Acompanhe a coleta no Monitoring Center; consulte as observações persistidas e suas URLs de origem.
4. Configure um monitor recorrente — Beat despacha sem ação manual; o worker registra cada execução.
5. Revise os vínculos propostos pelo motor de correlação e examine as relações no grafo.
6. Adicione uma evidência de teste, verifique seu SHA-256 e exporte o relatório em JSON, CSV ou Markdown.

Colaboradores podem ser adicionados por e-mail ou ID via `POST /api/v1/investigations/{id}/members` com papel `editor` ou `viewer`; o RBAC é aplicado em todas as consultas e mutações.

## Comandos de operação

```bash
make health      # verifica saúde dos serviços
make logs        # acompanha logs em tempo real
make migrate     # aplica migrações pendentes
make backup      # backup consistente de banco + evidências
make restore BACKUP=/caminho/do/backup
make purge       # expurga evidências com retenção expirada
make audit       # linters, tipos, testes e auditoria de dependências
make down        # para os containers
make up          # sobe os containers
```

> `make restore` substitui os dados configurados e pressupõe revisão prévia do backup pelo operador. Backups pausam brevemente os serviços escritores para preservar consistência. **`docker compose down -v` apaga os volumes permanentemente.**

## Segurança — resumo

- Argon2id para senhas; sessões opacas com token armazenado como hash; CSRF em todas as escritas.
- DNS pin no TCP connect para todos os conectores e webhooks externos — previne SSRF e DNS rebinding.
- `X-Forwarded-For` aceito somente de peers loopback/RFC-1918 (proxy Caddy).
- Credenciais de conectores criptografadas em repouso com Fernet (`CONNECTOR_SECRET_KEY`).
- Auditoria completa de todas as ações de escrita.

Detalhes completos em [SECURITY.md](SECURITY.md).

## Documentação

| Documento | Conteúdo |
|-----------|----------|
| [INSTALLATION.md](INSTALLATION.md) | Docker, desenvolvimento local, cloud com proxy CA |
| [CONFIGURATION.md](CONFIGURATION.md) | Variáveis de ambiente e referência de configuração |
| [API.md](API.md) | Visão geral dos grupos de rotas REST |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Diagrama de componentes e fluxo de coleta |
| [CONNECTORS.md](CONNECTORS.md) | Fontes disponíveis, limitações e configuração |
| [DEPLOYMENT.md](DEPLOYMENT.md) | Produção com Caddy, TLS e hardening |
| [SECURITY.md](SECURITY.md) | Controles, boas práticas e reporte de vulnerabilidades |
| [PRIVACY.md](PRIVACY.md) | Princípios de privacidade e minimização de dados |
| [TESTING.md](TESTING.md) | Suíte de testes, fixtures e CI |
| [MONITORING.md](MONITORING.md) | Prometheus, alertas e observabilidade |
| [TROUBLESHOOTING.md](TROUBLESHOOTING.md) | Problemas comuns e diagnóstico |
| [CHANGELOG.md](CHANGELOG.md) | Histórico de versões e correções |
| [ROADMAP.md](ROADMAP.md) | Próximas funcionalidades planejadas |
| [docs/AUDIT.md](docs/AUDIT.md) | Registro de auditoria e evidências de validação |
| [docs/IMPLEMENTATION_MATRIX.md](docs/IMPLEMENTATION_MATRIX.md) | O que está implementado vs. validado vs. limitado |

## Desenvolvimento

```bash
make install     # instala dependências Python e Node.js
make lint        # Ruff + ESLint
make typecheck   # mypy + tsc
make test        # pytest com fixtures PostgreSQL/Redis reais
```

Veja [CONTRIBUTING.md](CONTRIBUTING.md) e [TESTING.md](TESTING.md) para o fluxo completo.

A demonstração automatizada [scripts/demo_public.py](scripts/demo_public.py) consulta uma fonte pública real; os testes com fixtures permanecem separados.
