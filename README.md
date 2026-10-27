# Gestão Fiscal — SMS Campo Maior

Sistema web para conferir notas fiscais contra contratos do Fundo Municipal de Saúde de Campo Maior (CNPJ 11.753.492/0001-02), controlar saldos item a item e gerar ordens de fornecimento (OF) em PDF.

## Pilha Tecnológica

- **Backend**: Python 3.12 + Django 5.2 LTS
- **Banco**: PostgreSQL 16 com extensão `pg_trgm`
- **Frontend**: Templates Django + Tailwind CSS + HTMX
- **Tarefas assíncronas**: Celery + Redis
- **PDF**: xhtml2pdf (geração), pdfplumber (leitura)
- **Excel**: openpyxl, xlrd
- **Proxy reverso**: Caddy (TLS automático)
- **Containers**: Docker Compose com limites de memória

## Requisitos

- Docker Engine ≥ 24.0 e Docker Compose ≥ 2.20
- Hardware mínimo: Orange Pi 3 LTS (ARM64, 2 GB RAM) ou equivalente
- SSD recomendado (mínimo 32 GB livres)

## Desenvolvimento Local

```bash
# Subir o ambiente
docker compose up

# Rodar migrações
docker compose run --rm web python manage.py migrate

# Criar superusuário
docker compose run --rm web python manage.py createsuperuser

# Rodar testes
docker compose run --rm web pytest
```

Acesse em <http://localhost:8000>.

## Produção

Consulte [DEPLOYMENT.md](DEPLOYMENT.md) para instruções completas de implantação, incluindo configuração do Caddy, variáveis de ambiente e procedimentos de backup.

## Estrutura do Projeto

| App | Responsabilidade |
|---|---|
| `contratos` | Cadastro de contratos e itens contratuais |
| `notas` | Importação, validação e registro de notas fiscais |
| `ordens` | Geração de ordens de fornecimento (OF) em PDF |
| `relatorios` | Relatórios, busca global e exportação Excel |
| `importacao` | Processamento de arquivos PDF/XML/Excel |
| `auditoria` | Registro de auditoria de operações (RN20) |
| `seguranca` | Throttle de login, gestão de sessões, auditoria de acesso |

## Regras de Negócio Principais

- Dinheiro e quantidade sempre em `Decimal` (nunca `float`)
- Saldo calculado dinamicamente: contratada − faturada − reservada
- Preço unitário da nota deve ser exatamente igual ao preço vigente na data de emissão
- Upload limitado a 20 MB com deduplicação SHA-256 (RN25)
- Todas as operações relevantes geram registro de auditoria (RN20)
- Login com throttle e bloqueio temporário após tentativas excessivas

## Testes

```bash
# Todos os testes
docker compose run --rm web pytest

# Testes específicos por app
docker compose run --rm web pytest notas/
docker compose run --rm web pytest seguranca/

# Testes E2E (apenas em máquina de desenvolvimento)
docker compose run --rm web pytest tests/e2e/ --slow
```

## Licença

Projeto interno da Prefeitura Municipal de Campo Maior — PI.