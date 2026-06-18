import argparse
import logging
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv
from supabase import Client, create_client


@dataclass(frozen=True)
class Settings:
    """Armazena as configurações do sistema carregadas do ambiente."""

    supabase_url: str
    supabase_key: str
    supabase_table: str
    name_column: str
    phone_column: str
    select_columns: str
    zapi_instance_id: str
    zapi_instance_token: str
    zapi_client_token: str
    send_interval_seconds: float
    log_dir: str


def load_settings() -> Settings:
    """Carrega, valida e centraliza as variáveis de ambiente."""
    load_dotenv(encoding="utf-8-sig")

    # Validação de variáveis obrigatórias
    required_vars = [
        "SUPABASE_URL",
        "SUPABASE_KEY",
        "ZAPI_INSTANCE_ID",
        "ZAPI_INSTANCE_TOKEN",
        "ZAPI_CLIENT_TOKEN",
    ]
    missing = [key for key in required_vars if not os.getenv(key)]
    if missing:
        missing_text = ", ".join(missing)
        raise RuntimeError(f"Variaveis de ambiente ausentes: {missing_text}")

    # Definição de colunas e valores padrões
    name_column = os.getenv("SUPABASE_NAME_COLUMN", "nome_contato")
    phone_column = os.getenv("SUPABASE_PHONE_COLUMN", "telefone")
    select_columns = os.getenv("SUPABASE_SELECT_COLUMNS", f"{name_column},{phone_column}")

    return Settings(
        supabase_url=os.environ["SUPABASE_URL"],
        supabase_key=os.environ["SUPABASE_KEY"],
        supabase_table=os.getenv("SUPABASE_TABLE", "pessoas"),
        name_column=name_column,
        phone_column=phone_column,
        select_columns=select_columns,
        zapi_instance_id=os.environ["ZAPI_INSTANCE_ID"],
        zapi_instance_token=os.environ["ZAPI_INSTANCE_TOKEN"],
        zapi_client_token=os.environ["ZAPI_CLIENT_TOKEN"],
        send_interval_seconds=float(os.getenv("SEND_INTERVAL_SECONDS", "1.0")),
        log_dir=os.getenv("LOG_DIR", "logs"),
    )


def normalize_phone(phone: Any) -> str:
    """Remove todos os caracteres não numéricos de uma string de telefone."""
    return re.sub(r"\D", "", str(phone or ""))


def build_message(name: str) -> str:
    """Gera o texto personalizado da mensagem para o cliente."""
    return f"Ol\u00e1, {name}. Tudo bem com voc\u00ea?"


def fetch_contacts(
    supabase: Client,
    settings: Settings,
    limit: int | None = None,
    filter_column: str | None = None,
    filter_value: str | None = None,
) -> list[dict[str, Any]]:
    """Busca os contatos no banco de dados do Supabase aplicando filtros opcionais."""
    query = supabase.table(settings.supabase_table).select(settings.select_columns)

    # Aplica filtro dinâmico se ambos os parâmetros forem fornecidos
    if filter_column is not None and filter_value is not None:
        query = query.eq(filter_column, parse_filter_value(filter_value))

    if limit is not None:
        query = query.limit(limit)

    response = query.execute()
    return response.data or []


def parse_filter_value(value: str) -> Any:
    """Converte strings de filtro do CLI para seus respectivos tipos booleanos ou None."""
    normalized = value.strip().lower()

    if normalized == "true":
        return True
    if normalized == "false":
        return False
    if normalized == "null":
        return None
    return value


def send_text_message(settings: Settings, phone: str, message: str) -> dict[str, Any]:
    """Realiza a requisição HTTP POST para enviar a mensagem de texto via Z-API."""
    url = (
        "https://api.z-api.io/instances/"
        f"{settings.zapi_instance_id}/token/{settings.zapi_instance_token}/send-text"
    )
    headers = {
        "Client-Token": settings.zapi_client_token,
        "Content-Type": "application/json",
    }
    payload = {"phone": phone, "message": message}

    response = requests.post(url, json=payload, headers=headers, timeout=30)
    response.raise_for_status()
    return response.json()


def setup_logger(log_dir: str) -> tuple[logging.Logger, Path]:
    """Configura o sistema de logs para gravar em arquivo e exibir no console."""
    # Garante a existência do diretório de logs
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    log_file = Path(log_dir) / f"envio_whatsapp_{datetime.now():%Y%m%d_%H%M%S}.log"

    logger = logging.getLogger("whatsapp_sender")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    # Formato padrão: Data/Hora | Nível do Log | Mensagem
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Handler para exibição no terminal
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    # Handler para salvamento em arquivo físico
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(formatter)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    return logger, log_file


def describe_request_error(error: requests.RequestException) -> str:
    """Trata erros de requisição HTTP e limita o tamanho da resposta no log."""
    if error.response is None:
        return str(error)

    # Trunca o corpo da resposta se exceder 1000 caracteres
    response_text = error.response.text.strip()
    if len(response_text) > 1000:
        response_text = f"{response_text[:1000]}..."

    return (
        f"HTTP {error.response.status_code} | "
        f"Resposta Z-API: {response_text or '<sem corpo>'}"
    )


def process_contacts(
    contacts: list[dict[str, Any]],
    settings: Settings,
    should_send: bool,
    logger: logging.Logger,
) -> None:
    """Itera sobre a lista de contatos, valida dados e gerencia o fluxo de envios."""
    sent_count = 0
    skipped_count = 0
    failed_count = 0

    for index, contact in enumerate(contacts, start=1):
        name = str(contact.get(settings.name_column) or "").strip()
        phone = normalize_phone(contact.get(settings.phone_column))

        # 1. Validação de presença: verifica se os campos não estão vazios
        if not name or not phone:
            skipped_count += 1
            logger.warning(
                "[%s/%s] IGNORADO | Registro sem nome ou telefone preenchido | dados=%s",
                index,
                len(contacts),
                contact,
            )
            continue

        # 2. Validação de formato: verifica se o número está incompleto ou incorreto
        # Padrão Brasil: DDI(2) + DDD(2) + Número(8 ou 9) = 12 ou 13 dígitos numéricos
        if len(phone) not in (12, 13):
            skipped_count += 1
            logger.warning(
                "[%s/%s] IGNORADO | Telefone incompleto ou formato invalido (%s) | nome=%s",
                index,
                len(contacts),
                phone,
                name,
            )
            continue

        message = build_message(name)

        # Validação do modo simulado (Dry-Run)
        if not should_send:
            logger.info("[%s/%s] DRY-RUN | telefone=%s | mensagem=%s", index, len(contacts), phone, message)
            continue

        logger.info("[%s/%s] ENVIANDO | nome=%s | telefone=%s", index, len(contacts), name, phone)

        # Fluxo de disparo com tratamento individual de exceções
        try:
            result = send_text_message(settings, phone, message)
        except requests.RequestException as error:
            failed_count += 1
            logger.error(
                "[%s/%s] FALHA | nome=%s | telefone=%s | erro=%s",
                index,
                len(contacts),
                name,
                phone,
                describe_request_error(error),
            )
            continue
        except Exception:
            failed_count += 1
            logger.exception(
                "[%s/%s] FALHA_INESPERADA | nome=%s | telefone=%s",
                index,
                len(contacts),
                name,
                phone,
            )
            continue

        sent_count += 1
        logger.info("[%s/%s] ENVIADO | telefone=%s | resposta=%s", index, len(contacts), phone, result)

        # Intervalo antipolítica de spam entre envios (ignorado no último registro)
        if settings.send_interval_seconds > 0 and index < len(contacts):
            time.sleep(settings.send_interval_seconds)

    # Resumo consolidado da execução corrente
    logger.info(
        "Finalizado. Enviadas: %s. Falhas: %s. Ignoradas: %s.",
        sent_count,
        failed_count,
        skipped_count,
    )


def parse_args() -> argparse.Namespace:
    """Define e processa os argumentos aceitos via linha de comando (CLI)."""
    parser = argparse.ArgumentParser(
        description="Envia mensagem de WhatsApp para pessoas cadastradas no Supabase."
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--send",
        action="store_true",
        help="Envia as mensagens de verdade pela Z-API.",
    )
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Mostra as mensagens sem enviar. Este e o comportamento padrao.",
    )
    parser.add_argument("--limit", type=int, help="Limita a quantidade de contatos.")
    parser.add_argument("--filter-column", help="Coluna para filtro simples no Supabase.")
    parser.add_argument("--filter-value", help="Valor do filtro simples no Supabase.")
    return parser.parse_args()


def main() -> None:
    """Ponto de entrada principal do script."""
    args = parse_args()
    settings = load_settings()
    
    # Inicializa serviços e logs
    logger, log_file = setup_logger(settings.log_dir)
    logger.info("Log desta execucao: %s", log_file)
    logger.info("Modo: %s", "envio real" if args.send else "dry-run")

    supabase = create_client(settings.supabase_url, settings.supabase_key)

    # Coleta de dados
    contacts = fetch_contacts(
        supabase=supabase,
        settings=settings,
        limit=args.limit,
        filter_column=args.filter_column,
        filter_value=args.filter_value,
    )

    logger.info("Contatos encontrados: %s", len(contacts))
    
    # Execução principal do pipeline de envios
    process_contacts(contacts, settings, should_send=args.send, logger=logger)


if __name__ == "__main__":
    main()