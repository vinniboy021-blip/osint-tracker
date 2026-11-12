# Configuração

O arquivo `.env.example` documenta o ambiente Compose. Pydantic valida todas as variáveis ao iniciar o backend — erros de configuração impedem a subida. Nenhuma credencial é embutida na imagem; configurações secretas de conectores são criptografadas com `CONNECTOR_SECRET_KEY`.

## Variáveis de ambiente

### Banco de dados e fila

| Variável | Padrão (Compose) | Descrição |
|---|---|---|
| `POSTGRES_DB` | `osint` | Nome do banco (usado internamente pelo Compose) |
| `POSTGRES_USER` | `osint` | Usuário PostgreSQL |
| `POSTGRES_PASSWORD` | — | Gerado por `setup_env.py`; nunca use valor de exemplo |
| `DATABASE_URL` | (derivado) | URL SQLAlchemy; em desenvolvimento fora do Compose |
| `REDIS_URL` | `redis://redis:6379/0` | URL do Redis para fila, sessão e rate limiting |

### Segurança

| Variável | Padrão | Descrição |
|---|---|---|
| `ENVIRONMENT` | `development` | `development` ou `production`; `production` impõe verificações extras |
| `CONNECTOR_SECRET_KEY` | — | Chave Fernet base64 de 32 bytes; **obrigatória em produção** |
| `COOKIE_SECURE` | `false` | Cookie enviado somente por HTTPS; **obrigatório em produção** |
| `CORS_ORIGINS` | `http://localhost:3000` | Origens explícitas separadas por vírgula; `*` bloqueado em produção |
| `TRUSTED_HOSTS` | `localhost,127.0.0.1,api,testserver` | Hosts aceitos pelo backend |
| `SESSION_TTL_SECONDS` | `28800` (8h) | Duração máxima de sessão (300–604800) |
| `LOGIN_MAX_ATTEMPTS` | `5` | Tentativas de login por IP+email antes do bloqueio |
| `LOGIN_WINDOW_SECONDS` | `900` (15 min) | Janela de contagem das tentativas de login |
| `RATE_LIMIT_PER_MINUTE` | `120` | Limite geral de requisições HTTP por IP por minuto |

### Evidências

| Variável | Padrão | Descrição |
|---|---|---|
| `EVIDENCE_PATH` | `/data/evidence` | Diretório privado de armazenamento; criado com modo `0700` |
| `EVIDENCE_MAX_BYTES` | `20971520` (20 MB) | Tamanho máximo por arquivo de evidência |

### Coleta e workers

| Variável | Padrão | Descrição |
|---|---|---|
| `COLLECTION_MAX_RECORDS` | `100` | Limite de observações por execução de coleta |
| `COLLECTION_MAX_ATTEMPTS` | `3` | Número máximo de tentativas antes de `dead_letter` |
| `WORKER_CONCURRENCY` | `4` | Concorrência do Celery worker |
| `SCHEDULER_TICK_SECONDS` | `15` | Frequência de varredura do Beat para monitores e recuperação |
| `CONNECTOR_TIMEOUT_SECONDS` | `20` | Timeout HTTP por requisição de conector |

### IA (opcional)

| Variável | Padrão | Descrição |
|---|---|---|
| `AI_ENABLED` | `false` | Habilita modelo Ollama local; desabilitado por padrão |
| `OLLAMA_URL` | `http://ollama:11434` | URL do serviço Ollama (rede interna; não validado por SSRF) |
| `OLLAMA_MODEL` | `llama3.2` | Modelo a usar para hipóteses |

### Observabilidade

| Variável | Padrão | Descrição |
|---|---|---|
| `METRICS_ENABLED` | `true` | Habilita `/metrics/prometheus`; **proteger na rede operacional** |

### Integração Kali MCP (opcional)

| Variável | Padrão | Descrição |
|---|---|---|
| `KALI_MCP_URL` | `` (vazio) | Endpoint MCP administrado pelo operador; vazio desabilita a integração |

Configure somente para um endpoint protegido por rede privada ou autenticação forte. O Tracker expõe apenas o health check administrativo; execução de ferramentas e allowlist permanecem no servidor MCP.

### Notificações (opcional)

| Variável | Padrão | Descrição |
|---|---|---|
| `SMTP_HOST` | `` | Host SMTP para alertas por e-mail |
| `SMTP_PORT` | `587` | Porta SMTP |
| `SMTP_STARTTLS` | `true` | Usar STARTTLS |
| `SMTP_USERNAME` | `` | Usuário SMTP (opcional) |
| `SMTP_PASSWORD` | `` | Senha SMTP |
| `SMTP_FROM` | `osint-tracker@localhost` | Endereço de remetente |
| `ALERT_WEBHOOK_URL` | `` | URL HTTPS do webhook (validada e com DNS pin) |
| `ALERT_WEBHOOK_SECRET` | `` | Segredo para assinatura HMAC-SHA256 (`X-OSINT-Signature`) |

### TLS (produção com Caddy)

| Variável | Descrição |
|---|---|
| `HOSTNAME` | Domínio público para TLS automático via ACME |
| `ACME_EMAIL` | E-mail para notificações do certificado |

### Desenvolvimento local

| Variável | Descrição |
|---|---|
| `API_PORT` | Porta da API (somente loopback em desenvolvimento) |
| `WEB_PORT` | Porta do frontend (somente loopback em desenvolvimento) |

## Notas importantes

**Credenciais de conectores** devem ser configuradas exclusivamente via `PUT /api/v1/connectors/{id}/configuration` após `CONNECTOR_SECRET_KEY` estar definida. Ausência de credenciais não impede fontes públicas que não as exigem.

**Rotação de `CONNECTOR_SECRET_KEY`** sem recriptografar as configurações existentes torna os tokens ilegíveis. Veja o procedimento de rotação em [SECURITY.md](SECURITY.md).

**`ALLOW_TEST_SQLITE`** permite SQLite em testes (`true`); nunca ative em produção.

**PostgreSQL com caracteres especiais na senha** exige codificação de URL na `DATABASE_URL`. O gerador `setup_env.py` usa caracteres seguros para evitar esse problema.
