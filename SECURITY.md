# Segurança

OSINT Tracker destina-se a coleta pública **autorizada** e inteligência defensiva. Não implementa invasão, contorno de autenticação, CAPTCHA, anti-bot ou restrições de privacidade. A existência de conteúdo publicamente acessível não elimina obrigações de finalidade, autorização e retenção.

## Controles arquiteturais

| Área | Implementação |
|------|---------------|
| Senhas | Argon2id (time=3, mem=64 MB, threads=4) |
| Sessões | Token opaco armazenado como SHA-256; HttpOnly, `SameSite=Lax`, Secure em produção |
| CSRF | Header `X-CSRF-Token` validado em todas as escritas; token vinculado à sessão |
| RBAC | Papéis `admin`, `analyst`, `viewer`; escopo por investigação com papéis `editor`/`viewer` |
| Origens | CORS com lista explícita; `TrustedHostMiddleware`; origens verificadas no login |
| Rate limiting | Tentativas de login por IP+email com janela Redis atômica; throttle geral por IP |
| IP real | `_RealIPMiddleware` lê `X-Forwarded-For` **somente** quando o peer TCP direto é loopback ou RFC-1918/ULA, impedindo spoofing de IP por clientes externos |
| Validação | Pydantic em toda entrada da API; consultas parametrizadas via SQLAlchemy ORM |
| SSRF (conectores) | DNS pin no TCP connect via `PublicNetworkBackend`; RFC-1918, loopback, multicast e Teredo bloqueados; somente porta 443/HTTPS |
| SSRF (webhook) | `alert_webhook_url` validado estaticamente **e** conexão usa `PublicNetworkBackend` para prevenir DNS rebinding |
| Credenciais em repouso | Fernet (AES-128-CBC + HMAC-SHA256) com `CONNECTOR_SECRET_KEY`; nunca copiadas para jobs ou logs |
| Evidências | Chaves alfanuméricas de 32 chars; `O_EXCL + O_NOFOLLOW`; symlinks bloqueados; SHA-256 verificável |
| Upload | Spooled temporário com limite configurável; content-type preservado sem execução |
| Download | `Content-Disposition: attachment`; `X-Content-Type-Options: nosniff`; `Content-Security-Policy: sandbox` |
| Assinatura webhook | `hmac.HMAC(key, body, sha256)` em cabeçalho `X-OSINT-Signature: sha256=…` |
| Log injection | `X-Request-ID` sanitizado (`[A-Za-z0-9\-_]`, máx 64 chars) antes de ser refletido ou gravado |
| XXE | `defusedxml` com `forbid_dtd=True`, `forbid_entities=True`, `forbid_external=True` no conector RSS |
| CSV injection | Células com `=`, `+`, `-`, `@`, `\t`, `\r` prefixadas com `'` antes do export |
| Auditoria | Toda ação de escrita registrada em `audit_logs` com usuário, objeto e investigação |

## Produção

Cookies Secure e HTTPS são obrigatórios em produção; o `Settings.production_safety` valida na inicialização. API, worker e frontend executam sem root, sem capabilities e com filesystem somente leitura mais volumes/tmpfs necessários. PostgreSQL e Redis ficam sem publicação de portas no host. O proxy Caddy bloqueia `/metrics/prometheus` na borda pública; operadores acessam pela rede interna ou por túnel autorizado.

## Dados de fontes externas

Dados recebidos de conectores são **não confiáveis**. Conteúdo HTML não deve ser renderizado como HTML executável; previews de arquivos precisam de disposição segura, content-type permitido e sandbox CSP. Downloads exigem autenticação e autorização pela investigação. Não use URLs públicas de fontes como URLs de evidência. A camada de IA recebe contexto persistido como dados, sem ferramentas para alterar evidências silenciosamente.

## Segredos e dependências

Não versionar `.env`, tokens, senhas ou backups. `setup_env.py` gera valores localmente com fonte criptográfica. Restrinja acesso ao host e ao socket Docker, que tem poder equivalente a root. Proteja `CONNECTOR_SECRET_KEY`; a perda da chave impede recuperar credenciais criptografadas sem reconfiguração.

```bash
make audit
```

O pipeline executa linters, verificações de tipo, testes e auditoria de dependências. Vulnerabilidades precisam de avaliação/correção; não suprima alertas para declarar aprovação. Mantenha imagens e dependências atualizadas; teste migrações antes de aplicar.

## Rotação de chave

Rotacionar `CONNECTOR_SECRET_KEY` sem recriptografar as configurações existentes torna os tokens indecifráveis. Procedimento recomendado:

1. Descriptografar todas as `ConnectorConfiguration` com a chave antiga.
2. Gerar nova chave com `python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.
3. Recriptografar com a nova chave e atualizar o banco.
4. Substituir `CONNECTOR_SECRET_KEY` no ambiente.
5. Reiniciar todos os processos.

Guarde uma cópia offline protegida da chave usada em cada backup.

## Relatar vulnerabilidade

Não publique tokens, evidências privadas ou um exploit contra instâncias de terceiros. Use o canal privado de segurança do mantenedor quando disponível (GitHub Private vulnerability reporting). Inclua: versão afetada, passos para reproduzir, impacto estimado e, se possível, sugestão de correção. Não existe endereço de contato fictício ou serviço de triagem externo nesta distribuição.

## Limites conhecidos

Não há certificação, pentest independente, proteção DDoS dedicada, KMS externo, antivírus ou alta disponibilidade incluídos. A primeira implantação deve passar pela revisão operacional em [DEPLOYMENT.md](DEPLOYMENT.md). A documentação distingue implementação e validação; presença de testes não equivale a garantia de ausência de falhas.
