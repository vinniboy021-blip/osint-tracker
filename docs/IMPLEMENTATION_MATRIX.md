# Matriz de requisitos e implementação

Revisão de estado em 2026-10-29. A coluna de implementação descreve o código presente; a coluna de validação distingue testes locais, CI e dependências externas.

| Fase / requisito | Inicial | Implementação nesta entrega | Validação |
|---|---|---|---|
| Fundação, MIT, Compose, PostgreSQL, Redis, API e web | Ausente | Implementado | Ver docs/VALIDATION.md |
| Auth, Argon2id, sessões, RBAC, CSRF | Ausente | Implementado | Ver testes e registro |
| Migrações Alembic e esquema normalizado | Ausente | Implementado; migração inicial e roundtrip reproduzível | PostgreSQL real + `alembic check` |
| Registry, conectores públicos, normalização, proveniência | Ausente | Implementado | Mocks não certificam acesso remoto |
| Monitores, Beat, workers, retries, recuperação/DLQ | Ausente | Implementado | Requer Redis/PG reais |
| Social tracker e comparação | Ausente | Sobre observações/monitores de conectores sociais | Meta exige permissão não fornecida |
| Entidades, correlação explicável e revisão | Ausente | Implementado | Testes específicos e autorização |
| Grafo real, filtros/path/exportações | Ausente | Implementado com limites, filtros e exportação JSON | Relações persistidas; E2E visual adicional recomendado |
| Investigation workspace / colaboração | Ausente | Implementado; membros com RBAC do proprietário | 50 testes; UI completa de colaboração ainda pendente |
| Evidências privadas, versões, SHA-256 | Ausente | Implementado | Testes de integridade/isolamento |
| Relatórios e exportação | Ausente | CSV/JSON e autorização implementados; PDF/template avançado é evolução | Testes de autorização; cobertura visual adicional |
| IA opcional local com fontes | Ausente | Ollama opcional, sem dependência obrigatória | Validar apenas com modelo local configurado |
| Threat intelligence gratuita | Ausente | Feed público e histórico de indicadores | Disponibilidade/licença dependem da fonte |
| Alertas internos e supressão | Ausente | Alertas internos, SMTP e webhook HMAC | Webhook validado contra SSRF; SMTP externo pendente |
| Observabilidade e segurança de implantação | Ausente | Health/readiness, Prometheus opcional, TLS, nonroot, headers e Caddy | Caddy validado; revisão operacional externa pendente |
| Backup e restore | Ausente | Scripts DB+evidências, hashes e smoke test no CI | Recuperação de desastre com armazenamento externo pendente |
| Unitário, integração, E2E e CI | Ausente | 50 testes, PostgreSQL/Redis/Celery/Beat, Playwright e CI | Último workflow deve estar verde antes do release |
| Documentação e demonstração pública | Ausente | Documentação e fluxo reproduzível | Coleta real distinta das fixtures |

Primeiro release exige satisfazer os 18 critérios de aceite do pedido. Limitações de permissão, ambiente ou escopo devem continuar explícitas; este checklist não substitui pentest, DAST autenticado ou ensaio de desastre em infraestrutura real.
