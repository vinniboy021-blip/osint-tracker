# Testes e critérios de aceite

Os testes separam contratos com mocks de coleta remota real. Fixtures são identificadas como testes e nunca servem de evidência de disponibilidade de API externa.

```bash
make install
make lint
make test
make integration
cd apps/web
npx playwright install --with-deps chromium
npm run test:e2e
```

Backend: Pytest, Ruff e mypy. Frontend: ESLint, TypeScript strict, build Next.js e Playwright. O CI provisiona PostgreSQL/Redis reais, executa API, worker e Beat, verifica Alembic, constrói as imagens Docker e exercita backup/restauração. O caminho de integração precisa de `DATABASE_URL`, `REDIS_URL`, `EVIDENCE_PATH` e `RUN_INTEGRATION=1`. Use banco isolado descartável; testes podem criar/apagar registros.

Critérios críticos: login/CSRF/brute force; isolamento por investigação; coletas/normalização/proveniência; jobs deduplicados; cron/intervalos/recuperação; retries e erro persistente; revisão/revogação de vínculos; arquivos/integridade; exportações e IA sem fontes inventadas. SSRF inclui loopback, IPv6, IPs privados, metadata, DNS e redirecionamentos.

## Demonstração com fonte real

Instale a stack, crie o administrador e execute:

```bash
python3 scripts/demo_public.py --email administrador@example.org
```

O script pede a senha por getpass e cria uma investigação chamada `Teste de integração pública`. Coleta o repositório público GitHub `psf/requests`. Nenhuma informação é apresentada como coleta real antes da conclusão do worker e persistência das observações. O arquivo de evidência sintético do fluxo tem nome e descrição de teste; isso não é uma captura da fonte.

Disponibilidade de terceiros não faz parte de testes determinísticos. Falha de rede/permissão é reportada como tal. Integrações Meta não são declaradas funcionalmente validadas sem tokens e concessões oficiais. Um teste mockado não confirma App Review ou quota externa.

Consulte [docs/VALIDATION.md](docs/VALIDATION.md) para os comandos realmente executados nesta entrega e suas limitações. Antes de um release, aguarde o workflow CI do commit final e complete o ensaio de desastre com volumes externos.
