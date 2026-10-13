# Integração opcional com Kali Linux e MCP

Não há um servidor MCP oficial único distribuído pelo Kali Linux. O OSINT
Tracker aceita um endpoint MCP administrado pelo operador através de
`KALI_MCP_URL` e disponibiliza apenas o health check autenticado em
`GET /api/v1/admin/kali/health`.

O Tracker não executa comandos arbitrários, não faz bypass de controles e não
inicia scans ativos automaticamente. Ferramentas expostas pelo servidor MCP
devem ser limitadas a coleta pública/autorizada e configuradas no próprio Kali.

No Kali, execute o servidor MCP escolhido pelo administrador e publique-o apenas
em uma rede privada ou túnel autenticado. Depois configure `KALI_MCP_URL` no
`.env`. Use mTLS ou rede privada em produção e registre cada ação no servidor
MCP com usuário, investigação e finalidade.
