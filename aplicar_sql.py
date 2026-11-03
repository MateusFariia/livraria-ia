"""Executa um arquivo .sql ou imprime o resultado de uma consulta.

python aplicar_sql.py sql/arquivo.sql
python aplicar_sql.py --query "select ..."
"""

import argparse
import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv


def imprimir_resultado(cursor):
    colunas = [coluna.name for coluna in cursor.description]
    print(" | ".join(colunas))
    for linha in cursor.fetchall():
        print(" | ".join(str(valor) for valor in linha))


def executar(database_url, sql):
    with psycopg.connect(database_url) as conexao:
        cursor = conexao.execute(sql)
        if cursor.description:
            imprimir_resultado(cursor)
        else:
            print("OK")


def ler_argumentos():
    parser = argparse.ArgumentParser(description=__doc__)
    grupo = parser.add_mutually_exclusive_group(required=True)
    grupo.add_argument("arquivo", nargs="?", help="arquivo .sql a executar")
    grupo.add_argument("--query", help="consulta a executar")
    return parser.parse_args()


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    load_dotenv()
    argumentos = ler_argumentos()
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        sys.exit("Defina DATABASE_URL no .env.")

    sql = argumentos.query or Path(argumentos.arquivo).read_text(encoding="utf-8")
    executar(database_url, sql)


if __name__ == "__main__":
    main()
