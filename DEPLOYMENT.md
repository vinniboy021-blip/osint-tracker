# Implantação e manutenção

## HTTPS em servidor próprio

Use um domínio sob seu controle com DNS apontando ao host; disponibilize portas 80/443 para Caddy obter certificados. Não publique PostgreSQL, Redis ou porta da API. Gere segredos, configure `HOSTNAME` e `ACME_EMAIL` no `.env`, e revise as origens/hosts.

```bash
python3 scripts/setup_env.py
docker compose -f docker-compose.yml -f docker-compose.prod.yml config --quiet
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
docker compose exec api python -m app.cli create-admin --email administrador@example.org
```

O override usa cookies Secure, ambiente production e porta pública apenas no Caddy. Compose >=2.24.4 é necessário para `!reset`. Configure firewall e atualização do host. O build cria tags locais; para releases reproduzíveis, fixe também digests das imagens-base e mantenha artefatos assinados conforme seu processo. Não há claim de supply chain completa nesta versão.

## Backup e recuperação

```bash
make backup
# Antes de restaurar, revise diretório e manifest.json.
make restore BACKUP=/caminho/do/backup
```

O backup pausa web/API/workers/Beat, usa `pg_dump -Fc`, arquiva o volume de evidências e grava hashes SHA-256. Os serviços retornam após concluir o backup ou após falha; monitore os logs. O operador deve preservar segredos em armazenamento separado protegido. Backups não incluem tokens em arquivos de configuração, mas o banco contém configurações criptografadas; precisam da chave original.

Restauração verifica hashes, pausa os escritores, substitui banco e evidências, reaplica migrações e reinicia os serviços. Falha mantém escritores parados para evitar uso de dados parcialmente restaurados. `pg_restore --clean` é destrutivo. Teste periodicamente em ambiente isolado; ter um arquivo de backup não comprova recuperação.

Os scripts usam `docker compose` padrão. Para manutenção de produção, defina a seleção dos arquivos com a variável `COMPOSE_FILE=docker-compose.yml:docker-compose.prod.yml` no ambiente ao executar os scripts; em Windows, o separador de paths difere. O mesmo projeto/nome deve ser usado para não criar volumes diferentes.

## Observabilidade

```bash
docker compose --profile observability up -d prometheus
```

Prometheus fica apenas no loopback 9090 e consulta API internamente. Grafana pode ser adicionado pelo operador, sem serviço obrigatório. Métricas não podem expor tokens, senhas, consultas sensíveis ou dados pessoais como labels.

Verifique readiness, backlog, jobs falhos, dead letters, tempos de fonte, 429, espaço de evidências e persistência do Redis. Um worker saudável no nível do processo pode estar incapaz de coletar uma fonte; confira execuções reais.

## Atualização

Faça backup, consulte CHANGELOG, teste upgrade no clone do backup e execute `docker compose up -d --build`. Migrações passam pelo serviço isolado. Não execute mais de um Beat; ampliação de workers exige medidas reais de rate limit, memória e conexões do banco. Não foi incluída configuração de cluster/HA.
