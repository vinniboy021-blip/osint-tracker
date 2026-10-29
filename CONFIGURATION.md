# Configuração

O arquivo `.env.example` descreve o ambiente Compose. Pydantic valida as variáveis do backend. Nenhuma credencial é embarcada na imagem; configurações secretas de conectores são criptografadas com `CONNECTOR_SECRET_KEY`.

| Variável | Finalidade |
|---|---|
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | Banco da implantação Compose; senha gerada pelo setup |
| `DATABASE_URL` | Conexão SQLAlchemy em desenvolvimento fora do Compose |
| `REDIS_URL` | Redis para fila, sessão e limitação |
| `ENVIRONMENT` | `development` ou `production` |
| `CONNECTOR_SECRET_KEY` | Chave Fernet base64 de 32 bytes; obrigatória em produção |
| `COOKIE_SECURE` | Cookie enviado somente por HTTPS; obrigatório em produção |
| `CORS_ORIGINS` | Origens explícitas separadas por vírgula |
| `TRUSTED_HOSTS` | Hosts aceitos pelo backend |
| `SESSION_TTL_SECONDS` | Duração máxima de sessão |
| `LOGIN_MAX_ATTEMPTS`, `LOGIN_WINDOW_SECONDS` | Controle de tentativas de login |
| `RATE_LIMIT_PER_MINUTE` | Limite operacional HTTP |
| `EVIDENCE_PATH`, `EVIDENCE_MAX_BYTES` | Diretório privado e tamanho máximo de evidências |
| `COLLECTION_MAX_RECORDS`, `COLLECTION_MAX_ATTEMPTS` | Limites por coleta e retries |
| `WORKER_CONCURRENCY`, `SCHEDULER_TICK_SECONDS` | Concorrência e frequência do scheduler |
| `AI_ENABLED`, `OLLAMA_URL`, `OLLAMA_MODEL` | Modelo local opcional; desabilitado por padrão |
| `METRICS_ENABLED` | Habilita `/metrics/prometheus`; mantenha protegido na rede operacional |
| `KALI_MCP_URL` | Endpoint MCP Kali administrado pelo operador; vazio desabilita a integração |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_STARTTLS`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM` | Entrega opcional de alertas por e-mail |
| `ALERT_WEBHOOK_URL`, `ALERT_WEBHOOK_SECRET` | Webhook opcional com assinatura HMAC SHA-256 |
| `HOSTNAME`, `ACME_EMAIL` | TLS automático no Caddy para domínio controlado |
| `API_PORT`, `WEB_PORT` | Portas somente loopback no desenvolvimento |

Configure tokens exclusivamente na administração de conectores, após definir a chave. Ausência de credenciais não impede fontes públicas que não as exigem. Campos aceitos por cada fonte, permissões e limitações estão em [CONNECTORS.md](CONNECTORS.md) e no registry retornado pela API.

Rotacionar a chave sem recriptografar as configurações existentes torna os tokens indecifráveis. Guarde uma cópia offline protegida da chave usada por cada backup. A implantação não fornece uma rotina automática de rotação de chave: planeje a migração/reconfiguração antes da troca.
# Kali Linux / MCP (opcional)

Defina `KALI_MCP_URL` somente para um endpoint MCP administrado pelo operador e
protegido por rede privada ou autenticação forte. O Tracker expõe apenas o
health check administrativo; execução de ferramentas e allowlist permanecem no
servidor MCP. Não configure endpoints públicos desconhecidos.
