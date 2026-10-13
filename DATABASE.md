# Banco de dados

PostgreSQL 16 é o banco de produção. Alembic controla versionamento; SQLite só pode ser habilitado explicitamente para testes isolados e não substitui os testes PostgreSQL.

```bash
docker compose run --rm migrate
# Estado e histórico
docker compose exec api alembic current
docker compose exec api alembic history
```

Modelos SQLAlchemy em `apps/api/app/models.py` são a referência das tabelas, índices, chaves estrangeiras e constraints. O esquema abrange usuários, papéis/permissões, sessões, investigações e membros; conectores/configurações; jobs/execuções/monitores; observações; entidades/aliases/relações/candidatos/revisões; evidências/versões; timelines/alertas/notificações; indicadores/relatórios/auditoria/análises de IA.

Cada registro ligado a investigação deve ser autorizado por associação do usuário. RBAC distingue administrador global dos papéis de investigação. JSONB guarda payloads heterogêneos e configuração; membros, entidades, relações e evidências têm modelagem relacional. Datas são UTC.

Deduplicação combina hashes de observações e chaves determinísticas de jobs; relações não devem ser convertidas em merges de pessoas por similaridade de nome. Exclusão de arquivos exige sincronização com o registro de evidência e política de retenção.

A migração inicial permite construir uma instalação vazia. Downgrades são destrutivos; use ambiente descartável para verificar `downgrade base` seguido de `upgrade head`. Não execute downgrade do banco de produção sem backup e plano de manutenção.

Backup/restauração preservam banco e filesystem em uma mesma janela de manutenção. Redis é volume persistente para reduzir perda da fila, mas o estado autoritativo dos jobs fica no PostgreSQL. Veja [DEPLOYMENT.md](DEPLOYMENT.md).
