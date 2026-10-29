# API REST e OpenAPI

FastAPI disponibiliza `/docs` e `/openapi.json`. O contrato exato de rotas, campos, enums e validações pode ser inspecionado nesses endpoints; não mantenha uma cópia manual divergente do schema. As rotas funcionais usam `/api/v1`.

O Next.js encaminha chamadas da mesma origem para a API pelo endereço interno. Cookies de sessão são HttpOnly; requisições de escrita usam o mecanismo CSRF exigido pelo backend. Tokens e credenciais não devem ser copiados para URLs, logs ou parâmetros de linha de comando.

Grupos de recursos: autenticação/sessão; usuários/administração; investigações e colaboradores; conectores; jobs/coletas/execuções; monitores; observações e pesquisa; entidades/correlações/revisões/grafo; evidências/versões/integridade/download; timeline/alertas; threat intelligence; análises de IA; relatórios/auditoria.

Respostas de listagem têm limites e paginação definidos pelo contrato. Erros de validação são 422; ausência de autenticação, 401; falta de permissão, 403 ou 404 para objetos fora do escopo; indisponibilidade de dependência ou integração deve aparecer como erro explícito, sem dados fictícios.

Health sem dados sensíveis: `/health/live` verifica o processo; `/health/ready` verifica dependências. Os aliases `/live` e `/ready` simplificam operação. `/metrics/prometheus` fornece Prometheus quando habilitado; mantenha esse endpoint dentro da rede de operação e bloqueado na borda pública.

Colaboração usa `GET /api/v1/investigations/{id}/members`, `POST /api/v1/investigations/{id}/members` com `email` ou `user_id` e papel `editor`/`viewer`, e `DELETE /api/v1/investigations/{id}/members/{user_id}`. Somente o proprietário da investigação ou administrador pode alterar membros; o backend nunca retorna hashes de senha.

O script [scripts/demo_public.py](scripts/demo_public.py) usa o contrato de autenticação e coleta para uma demonstração real. Cliente e testes E2E mantêm os mesmos nomes dos endpoints.
