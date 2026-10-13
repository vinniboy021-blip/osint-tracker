# Resolução de problemas

| Sintoma | Verificação e ação |
|---|---|
| API não sobe | `docker compose logs migrate api`; PostgreSQL pronto e migração completa? |
| Erro de cookie/CSRF | Acesse pela origem configurada; sessão válida e token de escrita; HTTPS se Secure |
| Fontes sem credenciais | Registry mostra configuração pendente; use fonte pública ou configure autorização oficial |
| Coleta fica pendente | Logs de worker/Beat, `celery inspect ping`, conexão Redis e job persistido |
| Monitor não dispara | Ativo, próxima execução UTC, Beat único, agenda válida e relógio do host |
| Resultados repetidos sem alertas | Conteúdo pode estar idêntico; compare fingerprint e horário das observações |
| 429 da fonte | Reduza frequência/concorrência; respeite quota e Retry-After; não evade limites |
| Falha TLS em cloud | Build secret CA e mount runtime; não desative verificação SSL |
| SSRF bloqueado | URL deve apontar a destino público permitido; não liberar metadata/privados |
| Evidência inválida | Compare hash/versão; não sobrescreva o original para esconder falha |
| Redis sem memória | `noeviction` falha explicitamente; reduza carga e amplie capacidade com diagnóstico |
| Senha PostgreSQL mudou | Volume antigo guarda credenciais anteriores; alterar `.env` não altera automaticamente usuário existente |
| `!reset` desconhecido | Atualize Compose para >=2.24.4 |
| Restore falhou | Escritores ficam parados; examine logs, restaure novamente do backup íntegro, então reinicie |

```bash
docker compose ps
docker compose logs --tail=100 migrate api worker beat
docker compose exec api alembic current
curl --fail http://localhost:8000/ready
```

Não publique `.env`, dump do ambiente, config Docker ou logs com tokens. IDs de correlação ajudam identificar requisições sem divulgar credenciais. Se o daemon Docker do ambiente não está acessível, recupere o ambiente; a aplicação não pode corrigir permissões do host durante runtime.
