# Gestão Fiscal — SMS Campo Maior

Sistema web para conferir notas fiscais contra contratos do Fundo Municipal de Saúde de Campo Maior (CNPJ 11.753.492/0001-02), controlar saldos item a item e gerar ordens de fornecimento (OF) em PDF.

A especificação completa está em `docs/PRD.md`. Leia o PRD antes de qualquer etapa. Em caso de dúvida ou conflito, o PRD vale; se o PRD não cobrir o caso, pergunte antes de decidir.

## Pilha

- Python 3 + Django (versão LTS)
- PostgreSQL com extensão `pg_trgm`
- Templates Django + Tailwind CSS + HTMX
- Celery + Redis para tarefas em segundo plano
- pdfplumber (PDF), lxml (XML), openpyxl e xlrd (Excel), rapidfuzz (semelhança de texto)
- WeasyPrint para PDF da OF e relatórios
- pytest + pytest-django + Playwright
- Docker Compose para todo o ambiente

Não adicione dependências fora desta lista sem perguntar antes e explicar o motivo.

## Comandos

- Subir o ambiente: `docker compose up`
- Rodar os testes: `docker compose run --rm web pytest`
- Criar migrações: `docker compose run --rm web python manage.py makemigrations`
- Aplicar migrações: `docker compose run --rm web python manage.py migrate`

Mantenha esta seção atualizada se os comandos mudarem.

## Regras inegociáveis

1. **Dinheiro e quantidade sempre em `Decimal`.** Nunca use `float` em valores, preços ou quantidades, nem em cálculos intermediários. No banco: preço unitário com 4 casas, quantidade com 4 casas, valores em reais com 2 casas.
2. **Saldo nunca é armazenado.** Saldo é sempre calculado: contratada − faturada − reservada (RN07).
3. **Valor unitário sem tolerância.** O preço da nota precisa ser exatamente igual ao preço vigente na data de emissão (RN05, RN06).
4. **Totais da nota são gravados como vieram.** Diferença de centavo entre quantidade × preço e o total da linha gera aviso, não bloqueio (RN10).
5. **Integridade no banco, não só no código.** Use `UniqueConstraint` e `CheckConstraint` para as regras de unicidade e valores válidos descritas no PRD (seção 14).
6. **Operações de nota são atômicas.** Lançar, editar ou excluir nota acontece dentro de `transaction.atomic()`.
7. **Toda alteração relevante gera registro de auditoria** (RN20).
8. **Tarefas que podem passar de alguns segundos rodam no Celery**, com progresso visível na tela. A interface nunca fica travada esperando.

## Testes

- Uma etapa só termina quando **todos** os testes passam. Nunca apague, desative ou afrouxe um teste para fazê-lo passar; corrija o código.
- Cada critério de aceite do PRD (CA01 a CA20) vira pelo menos um teste com o ID no nome, por exemplo `test_ca06_preco_divergente_bloqueia_nota`.
- Regras de negócio citadas no código e nos testes usam o ID do PRD (RN01 a RN20) em comentário.
- Os arquivos reais de exemplo ficam em `tests/fixtures/` (notas em PDF, planilhas, modelo de OF, logo). Use-os nos testes; não os altere.

## Forma de trabalhar

- O projeto é construído em etapas (E0 a E9, PRD seção 16). Trabalhe só na etapa atual.
- Antes de escrever código, apresente um plano curto da etapa: arquivos que vai criar ou alterar, modelos, telas e testes. Espere aprovação.
- Ao terminar, rode todos os testes e mostre o resultado. Liste o que foi feito e o que o usuário deve testar no navegador.
- Mudanças pequenas e focadas. Não refatore partes fora do escopo da etapa sem perguntar.

## Interface

- Todo texto de interface em português do Brasil, em frases curtas, sem pontos de exclamação.
- Números no formato brasileiro: `R$ 1.288,00`, `1.234,567`. Datas em `dd/mm/aaaa`.
- Uma única cor de ação principal por tela; demais botões neutros.
- Cores com significado fixo: verde (ativo, saldo), amarelo (a vencer, aviso), vermelho (vencido, bloqueado, exclusão), azul (faturado).
- Nomes nunca são cortados com reticências: quebram linha.
- Tabelas com cabeçalho fixo e rolagem horizontal dentro do próprio quadro em telas menores.
- Ações destrutivas sempre pedem confirmação.
- O protótipo anterior serve só como referência visual; não copie código dele.

## Código

- Código, nomes de variáveis e funções em inglês; textos de interface, mensagens e comentários de regra de negócio em português.
- Siga as convenções do Django (apps por domínio: `contratos`, `notas`, `ordens`, `relatorios`, `importacao`, `auditoria`).
- Nunca coloque senhas ou chaves no código; use variáveis de ambiente.
