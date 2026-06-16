# Envio de WhatsApp com Supabase + Z-API

Busca pessoas cadastradas no Supabase e envia pelo WhatsApp:

```text
Olá, <nome_contato>. Tudo bem com você?
```

## Configuração

1. Crie e ative um ambiente virtual:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

2. Instale as dependências:

```powershell
pip install -r requirements.txt
```

3. Copie `.env.example` para `.env` e preencha suas credenciais.

No Supabase, a tabela configurada em `SUPABASE_TABLE` precisa ter pelo menos:

- uma coluna de nome, por padrão `nome_contato`
- uma coluna de telefone, por padrão `telefone`

O telefone deve ser enviado para a Z-API somente com números, no formato DDI + DDD + número. Exemplo: `5511999999999`.

## Uso

Para testar sem enviar mensagens:

```powershell
python main.py --dry-run
```

Para enviar de verdade:

```powershell
python main.py --send
```

Durante a execução, o script mostra logs no terminal em tempo real e também salva tudo em um arquivo dentro da pasta `logs`.

Exemplo de arquivo gerado:

```text
logs/envio_whatsapp_20260616_162500.log
```

Se uma mensagem falhar, o envio continua para os próximos contatos e o erro fica registrado no log com o telefone, nome e resposta retornada pela Z-API.

Também dá para limitar a quantidade:

```powershell
python main.py --dry-run --limit 5
```

## Filtro opcional

Se quiser buscar só pessoas ainda não contatadas, você pode adicionar um filtro simples:

```powershell
python main.py --dry-run --filter-column mensagem_enviada --filter-value false
```
