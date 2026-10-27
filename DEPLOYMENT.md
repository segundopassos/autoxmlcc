# Guia de Implantação — Gestão Fiscal SMS Campo Maior

## Requisitos do Servidor

- **Hardware mínimo**: Orange Pi 3 LTS (ARM64, 2 GB RAM) ou equivalente
- **Armazenamento**: SSD via USB3 (mínimo 32 GB livres)
- **SO**: Debian 12 / Ubuntu 22.04 LTS (ARM64)
- **Docker Engine** ≥ 24.0 e **Docker Compose** ≥ 2.20

## Variáveis de Ambiente

Copie `.env.example` para `.env.production` e preencha todos os valores:

```bash
cp .env.example .env.production
nano .env.production
```

| Variável | Descrição | Exemplo |
|---|---|---|
| `SECRET_KEY` | Chave secreta Django (≥50 chars, aleatória) | Gerar com `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"` |
| `DEBUG` | Sempre `False` em produção | `False` |
| `ALLOWED_HOSTS` | Domínio(s) separados por vírgula | `gestao.smscampomaior.pi.gov.br` |
| `DOMAIN` | Domínio usado pelo Caddy para TLS automático | `gestao.smscampomaior.pi.gov.br` |
| `DB_PASSWORD` | Senha forte do PostgreSQL | Aleatória, ≥20 chars |
| `SESSION_COOKIE_SECURE` | Cookie de sessão apenas HTTPS | `True` |
| `CSRF_COOKIE_SECURE` | Cookie CSRF apenas HTTPS | `True` |

## Implantação

### 1. Clonar o repositório

```bash
git clone <repositorio> /opt/gestao-fiscal
cd /opt/gestao-fiscal
```

### 2. Configurar variáveis

```bash
cp .env.example .env.production
nano .env.production
```

### 3. Subir os serviços

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production up -d
```

### 4. Aplicar migrações e coletar estáticos

```bash
docker compose -f docker-compose.prod.yml exec web python manage.py migrate
docker compose -f docker-compose.prod.yml exec web python manage.py collectstatic --noinput
```

### 5. Criar superusuário

```bash
docker compose -f docker-compose.prod.yml exec web python manage.py createsuperuser
```

### 6. Verificar saúde

```bash
curl -I https://gestao.smscampomaior.pi.gov.br
docker compose -f docker-compose.prod.yml ps
```

## Arquitetura dos Serviços

| Serviço | Memória | Função |
|---|---|---|
| `caddy` | 64 MB | Reverse proxy HTTPS (TLS automático) |
| `web` | 512 MB | Django + Gunicorn (1 worker) |
| `worker` | 256 MB | Celery worker (concurrency=1) |
| `beat` | 128 MB | Celery beat (agendador) |
| `db` | 256 MB | PostgreSQL 16 |
| `redis` | 64 MB | Broker Celery + cache |

**Total**: ~1.28 GB — dentro do limite de 2 GB do Orange Pi 3 LTS.

## Caddy (Reverse Proxy)

O Caddy obtém e renova certificados TLS automaticamente via Let's Encrypt.
Configuração em `Caddyfile`:

- Proxy reverso para `web:8000`
- Compressão gzip/zstd
- Cache de estáticos com `immutable` (1 ano)
- Limite de upload: 20 MB (RN17)
- Logs no stdout (visíveis via `docker logs`)

Para usar sem domínio público (rede interna), defina `DOMAIN=:80` no `.env.production`
e o Caddy servirá HTTP puro na porta 80.

## Manutenção

### Backup do banco

```bash
docker compose -f docker-compose.prod.yml exec db pg_dump -U autoxmlcc autoxmlcc > backup_$(date +%Y%m%d).sql
```

### Atualização

```bash
git pull origin main
docker compose -f docker-compose.prod.yml build web worker
docker compose -f docker-compose.prod.yml up -d
docker compose -f docker-compose.prod.yml exec web python manage.py migrate
```

### Logs

```bash
docker compose -f docker-compose.prod.yml logs -f web      # Django/Gunicorn
docker compose -f docker-compose.prod.yml logs -f worker   # Celery
docker compose -f docker-compose.prod.yml logs -f caddy    # Access/error logs
```

## Segurança

- Login com throttle: bloqueio temporário após tentativas excessivas (modelo `TentativaLogin`)
- Sessões expiram por inatividade (modelo `SessaoAtiva`)
- Cookies seguros (`Secure`, `HttpOnly`, `SameSite=Lax`)
- Containers rodam como usuário não-root
- Upload limitado a 20 MB com validação SHA-256 contra duplicatas (RN25)
- Auditoria de todas as operações relevantes (RN20)