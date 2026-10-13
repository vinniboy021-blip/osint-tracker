# Instalação reproduzível

## Docker

Instale Docker Engine e Compose 2.24.4 ou superior. Verifique `docker info` e `docker compose version`. Reserve aproximadamente 4 GB de RAM, espaço para imagens, banco, evidências e backups.

```bash
cp .env.example .env
python3 scripts/setup_env.py
docker compose config --quiet
docker compose up -d --build
docker compose ps
docker compose exec api python -m app.cli create-admin --email administrador@example.org
```

`setup_env.py` gera senha PostgreSQL e chave Fernet apenas para valores ainda vazios ou de exemplo, preserva valores existentes e grava `.env` com modo 0600. Não imprime segredos. Senhas PostgreSQL com caracteres reservados em URLs precisam de codificação; o gerador usa caracteres seguros para URL.

A ordem de inicialização é PostgreSQL/Redis saudáveis, migração concluída, API pronta, frontend; worker e Beat aguardam migração. Falha da migração impede subir os escritores. Dados sobrevivem a `docker compose down` e reinicializações. **`docker compose down -v` apaga os volumes**; não use para operação normal.

## Ambiente cloud gerenciado

Se builds utilizarem o proxy e a CA do ambiente, execute:

```bash
python3 scripts/cloud_compose.py up -d --build
```

O script usa um override temporário: a CA entra no build via segredo BuildKit e no runtime por mount somente leitura. Proxy e CA não são copiados às camadas da imagem. A validação TLS permanece ativa. Não é necessário fora desse tipo de ambiente.

## Desenvolvimento sem imagens da aplicação

Requisitos: Python 3.12+, Node.js 22, PostgreSQL 16 e Redis 7 disponíveis localmente. Defina `DATABASE_URL`, `REDIS_URL`, `EVIDENCE_PATH` e origens em variáveis de ambiente; nenhuma senha padrão de aplicação existe.

```bash
make install
.venv/bin/alembic upgrade head
cd apps/api
../../.venv/bin/uvicorn app.main:app --reload
```

Em outros terminais:

```bash
cd apps/api
../../.venv/bin/celery -A app.celery_app:celery_app worker --loglevel=INFO
../../.venv/bin/celery -A app.celery_app:celery_app beat --loglevel=INFO --schedule=/tmp/osint-beat
```

```bash
cd apps/web
API_INTERNAL_URL=http://localhost:8000 npm run dev
```

Variáveis definidas no arquivo `.env` da raiz não são automaticamente carregadas ao mudar o diretório para `apps/api`; exporte-as no terminal ou crie um `.env` local ignorado pelo Git. Para comandos Alembic a partir da raiz, `pip install -e apps/api` torna o pacote importável.
