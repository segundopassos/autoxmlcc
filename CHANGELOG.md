# Changelog

Todas as mudanças notáveis deste projeto serão documentadas neste arquivo.

## [Não Lançado] — 2026-10-27

### Corrigido
- Substituído WeasyPrint por xhtml2pdf para geração de PDF (CLAUDE.md, compatibilidade ARM64)
- Removidas dependências GTK/Pango desnecessárias do Dockerfile
- Gunicorn reduzido para 1 worker (limite de 2 GB RAM do Orange Pi 3 LTS)
- Celery worker com concurrency=1 para respeitar orçamento de memória

### Adicionado
- Caddy como reverse proxy com TLS automático via Let's Encrypt
- Limites de memória (`mem_limit`) em todos os serviços do docker-compose.prod.yml
- App `seguranca` com modelos `TentativaLogin` (throttle de login) e `SessaoAtiva` (expiração de sessão)
- DEPLOYMENT.md com guia completo de implantação para Orange Pi 3 LTS
- README.md com instruções de desenvolvimento e produção
- Variáveis de segurança no .env.example: `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, `DOMAIN`

### Segurança
- Cookies seguros (`Secure`, `HttpOnly`, `SameSite=Lax`) configuráveis via env
- Upload limitado a 20 MB no Caddy (RN17)
- Auditoria de tentativas de login e sessões ativas (RN20)
- Containers configurados para rodar como usuário não-root