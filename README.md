# OSINT Tracker

Plataforma open source sob a licença MIT, em português brasileiro, para investigações sobre fontes públicas e autorizadas. Monólito modular em FastAPI, PostgreSQL, Redis/Celery e Next.js. Fontes, observações, decisões e evidências mantêm proveniência. Não há dependência obrigatória de serviços pagos.

Este repositório contém software executável. A matriz em [docs/IMPLEMENTATION_MATRIX.md](docs/IMPLEMENTATION_MATRIX.md) distingue implementação, validação e limitações. A existência de um conector não concede autorização para uma API: Meta e fontes que exigem credenciais permanecem condicionadas às permissões oficiais.

## Executar localmente

Requisitos: Docker Engine, Docker Compose **2.24.4+**, 4 GB de RAM livres. Python 3.12+ é necessário para os scripts de manutenção.

```bash
cp .env.example .env
python3 scripts/setup_env.py
docker compose up -d --build
docker compose exec api python -m app.cli create-admin --email administrador@example.org
```

O último comando solicita a senha sem registrá-la. Não existe administrador ou senha padrão. A interface está em http://localhost:3000; a documentação OpenAPI, em http://localhost:8000/docs. PostgreSQL e Redis não publicam portas no host. O processo `migrate` aplica Alembic antes de liberar API, workers e scheduler.

Também é possível iniciar apenas com `cp .env.example .env` e `docker compose up -d --build` em desenvolvimento; execute o gerador de segredos antes de configurar credenciais externas ou publicar o ambiente. Não use a senha de exemplo em produção.

## Fluxo verificável

1. Autentique-se e crie uma investigação com objetivo, escopo e base de autorização.
2. Selecione GitHub e consulte o repositório público `psf/requests`.
3. Acompanhe a coleta no Monitoring Center; consulte as observações persistidas e suas URLs.
4. Configure um monitor recorrente. Beat deve despachar sem ação manual; o worker registra cada execução.
5. Revise os vínculos propostos e examine as relações persistidas no grafo.
6. Adicione uma evidência de teste identificada como teste, verifique seu SHA-256 e exporte o relatório.

Para colaborar, o responsável pode adicionar usuários por e-mail ou ID na API de membros da investigação; papéis `editor` e `viewer` são aplicados em todas as consultas e mutações.

Uma fonte estável pode não mudar durante o teste: ausência de mudança não deve gerar alerta falso. A demonstração automatizada [scripts/demo_public.py](scripts/demo_public.py) consulta uma fonte real; os testes com fixtures permanecem separados. Veja [TESTING.md](TESTING.md).

## Operação e desenvolvimento

```bash
make health
make logs
make migrate
make backup
make restore BACKUP=/caminho/do/backup
make down
make up
```

`make restore` substitui os dados configurados e pressupõe uma revisão do backup pelo operador. Backups pausam brevemente os serviços escritores para preservar consistência entre arquivos e banco. A chave de criptografia das configurações deve ser guardada separadamente.

Para desenvolver, use Python 3.12+, Node.js 22 e `make install`. Consulte [INSTALLATION.md](INSTALLATION.md), [CONFIGURATION.md](CONFIGURATION.md), [API.md](API.md), [ARCHITECTURE.md](ARCHITECTURE.md), [DEPLOYMENT.md](DEPLOYMENT.md), [SECURITY.md](SECURITY.md) e [ROADMAP.md](ROADMAP.md).

O estado auditado, os comandos executados e os limites conhecidos estão em [docs/AUDIT.md](docs/AUDIT.md), [docs/VALIDATION.md](docs/VALIDATION.md) e [docs/IMPLEMENTATION_MATRIX.md](docs/IMPLEMENTATION_MATRIX.md).
