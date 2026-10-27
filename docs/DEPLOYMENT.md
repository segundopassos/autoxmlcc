# Guia de Deployment — Gestão Fiscal SMS Campo Maior

## Etapa E9 — Piloto

Este documento descreve os passos para colocar o sistema em produção e iniciar o piloto com dados reais.

## Pré-requisitos

- Servidor Linux (Ubuntu 22.04+ recomendado) com 2 GB RAM mínimo
- Docker Engine 24+ e Docker Compose v2 instalados
- Domínio ou IP público configurado
- Certificado SSL (Let's Encrypt recomendado)
- Acesso SSH ao servidor

## Configuração de Produção

### 1. Preparar o ambiente

```bash
# Clonar o repositório no servidor
git clone <repositorio> /opt/gestao-fiscal
cd /opt/gestao-fiscal

# Criar arquivo de variáveis de produção
cp .env.example .env.production
```

### 2. Editar variáveis de produção

Edite `.env.production` com valores seguros:

```bash
# Django
SECRET_KEY=<chave-secreta-longa-e-aleatoria>
DEBUG=False
ALLOWED_HOSTS=gestao.saude.campomaior.pi.gov.br,www.gestao.saude.campomaior.pi.gov.br

# Banco de dados
DB_NAME=gestao_fiscal_prod
DB_USER=gestao_fiscal
DB_PASSWORD=<senha-forte-do-banco>
DB_HOST=db
DB_PORT=5432

# Redis / Celery
REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/0
```

### 3. Build e inicialização

```bash
# Construir imagens de produção
docker compose -f docker-compose.prod.yml build

# Aplicar migrações
docker compose -f docker-compose.prod.yml run --rm web python manage.py migrate

# Criar superusuário inicial
docker compose -f docker-compose.prod.yml run --rm web python manage.py createsuperuser

# Coletar arquivos estáticos
docker compose -f docker-compose.prod.yml run --rm web python manage.py collectstatic --noinput

# Iniciar serviços
docker compose -f docker-compose.prod.yml up -d
```

### 4. Verificar saúde dos serviços

```bash
# Status dos containers
docker compose -f docker-compose.prod.yml ps

# Logs da aplicação
docker compose -f docker-compose.prod.yml logs -f web

# Logs do worker Celery
docker compose -f docker-compose.prod.yml logs -f worker
```

## Importação dos Dados Reais (Piloto)

### Passo 1: Backup das planilhas atuais

Antes de importar, faça cópia de segurança de todas as planilhas de controle atuais.

### Passo 2: Importar contratos via interface

1. Acesse `/contratos/novo/` → aba "Importar planilha mestre"
2. Para cada fornecedor ativo:
   - Selecione a planilha correspondente
   - Confirme o mapeamento de colunas na pré-visualização
   - Aguarde a importação completar (progresso visível na tela)
3. Verifique que todos os itens e histórico de notas foram importados

### Passo 3: Validar saldos

Para cada contrato importado:
1. Abra o contrato e verifique os totais (contratado, faturado, saldo)
2. Compare com a planilha original
3. Se houver divergência, use o menu Opções → "Subir ou substituir planilha" para corrigir

### Passo 4: Uso em paralelo

Durante o primeiro mês de piloto:
- Continue usando as planilhas como fonte primária
- Lance todas as notas novas também no sistema
- Ao final de cada semana, compare os saldos do sistema com as planilhas
- Registre qualquer divergência encontrada

**Critério de sucesso do piloto:** após 30 dias, os saldos do sistema batem com as planilhas para todos os contratos ativos.

## Backup Automático

O backup diário automático é executado pelo Celery Beat às 02:00 (horário local).

### Backup manual sob demanda

```bash
docker compose -f docker-compose.prod.yml exec web python manage.py backup_dados
```

Os backups ficam em `/app/backups/` dentro do container. Para copiar para fora:

```bash
docker compose -f docker-compose.prod.yml cp web:/app/backups/ ./backups/
```

### Restaurar backup

```bash
# Parar serviços
docker compose -f docker-compose.prod.yml down

# Restaurar banco (substitua pelo nome do arquivo)
docker compose -f docker-compose.prod.yml exec -T db psql -U gestao_fiscal gestao_fiscal_prod < backups/backup_YYYYMMDD_HHMMSS.sql

# Reiniciar
docker compose -f docker-compose.prod.yml up -d
```

## Monitoramento

### Logs

```bash
# Todos os serviços
docker compose -f docker-compose.prod.yml logs -f

# Apenas erros
docker compose -f docker-compose.prod.yml logs -f --level=error
```

### Auditoria

Acesse `/admin/auditoria/registroauditoria/` para ver todas as alterações registradas (RN20).

### Métricas de desempenho

- Painel deve abrir em menos de 2 segundos (CA20)
- Conferência de nota deve completar em menos de 10 segundos (RNF06)
- Importação de planilha grande mostra progresso sem travar (CA20)

## Rollback

Se o piloto precisar ser interrompido:

1. Pare os serviços: `docker compose -f docker-compose.prod.yml down`
2. As planilhas continuam sendo a fonte primária durante todo o piloto
3. Os dados do sistema ficam preservados no volume `pgdata` para análise posterior

## Suporte

- Documentação completa: `PRD.md`
- Regras de negócio: seção 6 do PRD (RN01 a RN20)
- Critérios de aceite: seção 15 do PRD (CA01 a CA20)