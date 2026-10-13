# Matriz de requisitos e implementação

Inspeção inicial em 2026-10-12: `/workspace` não continha repositório de aplicação. O projeto foi inicializado; não havia funcionalidades existentes a preservar. A tabela registra o ponto inicial e deve ser revisada usando código e checks efetivos antes de anunciar release.

| Fase / requisito | Inicial | Implementação nesta entrega | Validação |
|---|---|---|---|
| Fundação, MIT, Compose, PostgreSQL, Redis, API e web | Ausente | Implementado | Ver docs/VALIDATION.md |
| Auth, Argon2id, sessões, RBAC, CSRF | Ausente | Implementado | Ver testes e registro |
| Migrações Alembic e esquema normalizado | Ausente | Modelos/migração em desenvolvimento | Ver roundtrip e integração |
| Registry, conectores públicos, normalização, proveniência | Ausente | Implementado | Mocks não certificam acesso remoto |
| Monitores, Beat, workers, retries, recuperação/DLQ | Ausente | Implementado | Requer Redis/PG reais |
| Social tracker e comparação | Ausente | Sobre observações/monitores de conectores sociais | Meta exige permissão não fornecida |
| Entidades, correlação explicável e revisão | Ausente | Implementado | Testes específicos e autorização |
| Grafo real, filtros/path/exportações | Ausente | Frontend/backend em desenvolvimento | Sem relações fictícias |
| Investigation workspace / colaboração | Ausente | Implementação em desenvolvimento | API e E2E |
| Evidências privadas, versões, SHA-256 | Ausente | Implementado | Testes de integridade/isolamento |
| Relatórios e exportação | Ausente | Implementação em desenvolvimento | CSV/JSON e autorização |
| IA opcional local com fontes | Ausente | Implementação em desenvolvimento | Sem servidor Ollama remoto presumido |
| Threat intelligence gratuita | Ausente | Implementação em desenvolvimento | Feed com licença/permissão |
| Alertas internos e supressão | Ausente | Implementação em desenvolvimento | Notificações externas não presumidas |
| Observabilidade e segurança de implantação | Ausente | Health/readiness, Prometheus opcional, TLS, nonroot | Build/runtime a verificar |
| Backup e restore | Ausente | Scripts DB+evidências e hashes | Ensaio de recuperação a executar |
| Unitário, integração, E2E e CI | Ausente | Testes/pipeline em desenvolvimento | Resultados reais somente em VALIDATION |
| Documentação e demonstração pública | Ausente | Documentação e fluxo reproduzível | Coleta real distinta das fixtures |

Primeiro release exige satisfazer os 18 critérios de aceite do pedido. Limitações de permissão, ambiente ou escopo devem continuar explícitas; este checklist não substitui validação.
