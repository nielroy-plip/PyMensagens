# Envio de WhatsApp (Supabase + Z-API)

Script em Python para automação de disparos de mensagens personalizadas via Z-API utilizando uma base de contatos armazenada no Supabase.

---

## 1. Setup da Tabela (Supabase)

A tabela no Supabase (nome padrão: `pessoas`) precisa conter, no mínimo, as seguintes colunas:
* **nome_contato**: Texto com o nome do cliente (usado na personalização).
* **telefone**: Texto contendo apenas números no formato **DDI + DDD + Número** (Exemplo: `5511999999999`).

---

## 2. Variáveis de Ambiente (`.env`)

Crie um arquivo chamado `.env` na raiz do projeto e configure as credenciais abaixo:

```env
# Credenciais Obrigatórias
SUPABASE_URL=sua_url_do_supabase
SUPABASE_KEY=sua_chave_do_supabase
ZAPI_INSTANCE_ID=seu_id_da_instancia_zapi
ZAPI_INSTANCE_TOKEN=seu_token_da_instancia_zapi
ZAPI_CLIENT_TOKEN=seu_client_token_da_zapi

# Configurações Opcionais (Valores padrão abaixo se omitidos)
SUPABASE_TABLE=pessoas
SUPABASE_NAME_COLUMN=nome_contato
SUPABASE_PHONE_COLUMN=telefone
SEND_INTERVAL_SECONDS=1.0
LOG_DIR=logs

---

## 3. Como executar

# Instalar dependências
pip install -r requirements.txt

# --- MODO SIMULAÇÃO (DRY-RUN) ---
# Apenas testa a busca e exibe as mensagens no terminal sem enviar de verdade
python main.py --dry-run

# --- MODO ENVIO REAL ---
# Dispara as mensagens oficiais para o WhatsApp dos clientes
python main.py --send

# --- EXEMPLOS COM FILTROS E LIMITES ---
# Limita a execução para apenas os 5 primeiros contatos encontrados
python main.py --dry-run --limit 5

# Filtra contatos (Ex: busca apenas registros onde a coluna 'mensagem_enviada' seja 'false')
python main.py --dry-run --filter-column mensagem_enviada --filter-value false

# Combinando tudo (Envio real, limitado a 10 contatos e filtrando por status)
python main.py --send --limit 10 --filter-column status_ativo --filter-value true

--

## 4. Observações do código

#Validação de Telefone: O script possui um filtro automático de comprimento. Para o padrão nacional, o número precisa ter exatamente 12 ou 13 dígitos (DDI 55 + DDD + Número). Se o telefone no banco estiver incompleto ou incorreto, o script vai registrá-lo como IGNORADO no log e pulará para o próximo contato, economizando requisições e créditos na Z-API.