# Contribuindo

Contribuições são distribuídas sob MIT. Discuta alterações que mudem contratos ou esquema, preserve fontes autorizadas e mantenha compatibilidade de dados. Não inclua credenciais reais, dados pessoais desnecessários ou fixtures aparentando ser coletas reais.

```bash
make install
make lint
make test
```

Inclua migração Alembic para qualquer mudança de banco e teste PostgreSQL para constraints/concorrência. Mudanças nos conectores precisam de contrato, validação, provenance, rate limit, timeout, SSRF e fixtures com identificação de teste. Mudanças de permissão precisam verificar usuário sem acesso e outro membro de investigação.

Mantenha interface em português e strings organizadas para internacionalização. Botões devem executar backend ou ficar explicitamente indisponíveis com motivo. Não substitua erro remoto por dados inventados. Testes de UI verificam caminhos reais com backend de teste.

Atualize CHANGELOG, documentação relevante e matriz de implementação com evidência de validação. Não afirme prontidão de produção com checks não executados. Para problemas de segurança, veja SECURITY.md.
