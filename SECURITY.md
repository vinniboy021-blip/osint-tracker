# Segurança

OSINT Tracker destina-se a coleta pública autorizada e inteligência defensiva. Não implementa invasão, contorno de autenticação, CAPTCHA, anti-bot ou restrições de privacidade. A existência de conteúdo publicamente acessível não elimina obrigações de finalidade, autorização e retenção.

Controles arquiteturais: Argon2id para senhas; sessões opacas com token armazenado como hash; RBAC e associação por investigação; CSRF em escrita com sessão cookie; origens e hosts explícitos; limitação de tentativas; validação Pydantic e consultas parametrizadas SQLAlchemy; auditoria; criptografia de configurações secretas; files privados; validação de URLs e IPs para SSRF; limites de arquivos e respostas externas.

Produção exige cookies Secure e HTTPS. API, worker e frontend executam sem root, sem capabilities e com filesystem somente leitura mais volumes/tmpfs necessários. PostgreSQL e Redis ficam sem publicação de portas. O proxy Caddy bloqueia métricas na borda; operadores acessam pela rede interna ou por túnel autorizado.

Dados da fonte são não confiáveis. Conteúdo HTML não deve ser renderizado como HTML executável; previews de arquivos precisam usar disposição segura, conteúdo permitido e sandbox. Downloads exigem autenticação e autorização pela investigação. Não use URLs públicas para evidências. A camada de IA recebe texto como dados e não tem ferramentas para alterar evidências silenciosamente.

## Segredos e dependências

Não versionar `.env`, tokens, senhas ou backups. `setup_env.py` gera valores localmente com fonte criptográfica. Restrinja acesso ao host e ao socket Docker, que tem poder equivalente a root. Proteja `CONNECTOR_SECRET_KEY`; perda da chave impede recuperar credenciais criptografadas.

```bash
make audit
```

O pipeline executa linters, verificações de tipo, testes e auditoria de dependências. Vulnerabilidades precisam de avaliação/correção; não suprima alertas para declarar aprovação. Mantenha imagens e dependências atualizadas, teste migrações antes de aplicar.

## Relatar vulnerabilidade

Não publique tokens, evidências privadas ou um exploit contra instâncias de terceiros. Use o canal privado de segurança do mantenedor/projeto quando disponível. Se o repositório for publicado no GitHub, habilite Private vulnerability reporting antes de receber relatos. Não existe endereço de contato fictício ou serviço de triagem externo nesta distribuição.

## Limites

Não há certificação, pentest independente, proteção DDoS dedicada, KMS externo, antivírus ou alta disponibilidade incluídos. A primeira implantação deve passar pela revisão operacional em [DEPLOYMENT.md](DEPLOYMENT.md). A documentação distingue implementação e validação; presença de testes não equivale a garantia de ausência de falhas.
