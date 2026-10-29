# Documentação do OSINT Tracker

Este diretório contém os registros de implementação e validação. A documentação operacional completa está na raiz do repositório para ficar visível no GitHub:

- [README](../README.md): visão geral e fluxo rápido.
- [INSTALLATION](../INSTALLATION.md): Docker, desenvolvimento local e ambiente gerenciado.
- [CONFIGURATION](../CONFIGURATION.md): variáveis, segredos, IA local e Kali/MCP.
- [ARCHITECTURE](../ARCHITECTURE.md): módulos e diagramas Mermaid.
- [DATABASE](../DATABASE.md): entidades, índices e migrações.
- [API](../API.md): REST e OpenAPI.
- [CONNECTORS](../CONNECTORS.md): fontes, limites e credenciais oficiais.
- [MONITORING](../MONITORING.md): Celery, Beat, retries, DLQ e alertas.
- [CORRELATION_ENGINE](../CORRELATION_ENGINE.md): normalização, scores e revisão humana.
- [SECURITY](../SECURITY.md) e [PRIVACY](../PRIVACY.md): controles e LGPD.
- [DEPLOYMENT](../DEPLOYMENT.md): produção, TLS, backup e restauração.
- [TESTING](../TESTING.md): testes e pipeline CI.
- [TROUBLESHOOTING](../TROUBLESHOOTING.md): diagnóstico.
- [CONTRIBUTING](../CONTRIBUTING.md), [CHANGELOG](../CHANGELOG.md) e [ROADMAP](../ROADMAP.md).
- [AUDIT](AUDIT.md): auditoria profunda, achados corrigidos e riscos residuais.
- [IMPLEMENTATION_MATRIX](IMPLEMENTATION_MATRIX.md): estado por requisito.

O estado verificável dos checks está em [VALIDATION.md](VALIDATION.md). Nenhum check remoto é marcado como aprovado sem execução real.
