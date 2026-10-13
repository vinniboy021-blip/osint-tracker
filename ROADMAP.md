# Roadmap

A primeira entrega prioriza um fluxo executável de login, investigação, coleta pública, monitoramento, observações, relações revisadas, evidências e relatórios. [docs/IMPLEMENTATION_MATRIX.md](docs/IMPLEMENTATION_MATRIX.md) acompanha cobertura efetiva.

Evoluções dependem de validação real, não de telas ou promessas:

- Avaliar escalabilidade com volume, latência e quotas reais; HA PostgreSQL/Redis e coordenação distribuída do Beat antes de cluster.
- Rotação de chaves com recriptografia e armazenamento de segredos self-hosted opcional.
- MinIO/S3 completo, antivírus self-hosted opcional, expurgo seguro e políticas de retenção por finalidade.
- Notificações SMTP e webhooks autenticados com retries/supressão, caso não estejam concluídos na matriz.
- Exportação STIX 2.1 e indicadores de interoperabilidade testados.
- Melhorar explicabilidade/calibração de score; nenhuma inferência automática de identidade por similaridade.
- Expandir modalidades oficiais Meta apenas com permissões concedidas e testes remotos autorizados.
- Internacionalização completa de todos os textos, acessibilidade auditada e testes de navegador adicionais.
- Benchmark, pentest independente, documentação de SLOs e simulação de recuperação de desastre.

Não se inclui scraping privado, evasão de CAPTCHA/anti-bot, acesso não autorizado ou dependência comercial obrigatória.
