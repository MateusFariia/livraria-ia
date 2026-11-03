"""Raspa books.toscrape.com e grava os textos crus em bronze.livros (append-only).

Com --saida-sql, gera um arquivo .sql para ser executado pelo MCP do Supabase.
Sem --saida-sql, grava direto no banco usando DATABASE_URL do .env.
"""

import argparse
import json
import os
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

URL_LISTAGEM = "https://books.toscrape.com/catalogue/page-{n}.html"
USER_AGENT = "livraria-inteligente-scraper/1.0"
MAX_REQUISICOES_PARALELAS = 8
TIMEOUT_SEGUNDOS = 30
ARQUIVO_DDL = Path(__file__).parent / "sql" / "00_bronze.sql"


def baixar_html(sessao, url):
    resposta = sessao.get(url, timeout=TIMEOUT_SEGUNDOS)
    resposta.raise_for_status()
    return BeautifulSoup(resposta.text, "html.parser")


def listar_urls_da_pagina(sessao, numero_pagina):
    url_pagina = URL_LISTAGEM.format(n=numero_pagina)
    html = baixar_html(sessao, url_pagina)
    links = html.select("article.product_pod h3 a")
    return [urljoin(url_pagina, link["href"]) for link in links]


def ler_tabela_produto(html):
    return {
        linha.th.get_text(): linha.td.get_text()
        for linha in html.select("table.table tr")
    }


def ler_descricao(html):
    paragrafo = html.select_one("#product_description + p")
    return paragrafo.get_text() if paragrafo else None


def raspar_livro(sessao, url):
    html = baixar_html(sessao, url)
    tabela = ler_tabela_produto(html)
    return {
        "url": url,
        "titulo": html.select_one("div.product_main h1").get_text(),
        "preco_raw": html.select_one("div.product_main p.price_color").get_text(),
        "rating_raw": " ".join(html.select_one("p.star-rating")["class"]),
        "estoque_raw": tabela["Availability"],
        "upc": tabela["UPC"],
        "n_reviews_raw": tabela["Number of reviews"],
        "categoria_raw": html.select("ul.breadcrumb a")[2].get_text(),
        "descricao": ler_descricao(html),
    }


def raspar_catalogo(paginas):
    with requests.Session() as sessao:
        sessao.headers["User-Agent"] = USER_AGENT
        with ThreadPoolExecutor(MAX_REQUISICOES_PARALELAS) as executor:
            urls_por_pagina = executor.map(
                lambda n: listar_urls_da_pagina(sessao, n), range(1, paginas + 1)
            )
            urls = [url for urls_pagina in urls_por_pagina for url in urls_pagina]
            return list(executor.map(lambda url: raspar_livro(sessao, url), urls))


def montar_sql_insercao(livros, execucao_id):
    payloads = json.dumps(livros, ensure_ascii=True, separators=(",", ":"))
    if "$payload$" in payloads:
        raise ValueError("Os dados raspados contêm o delimitador $payload$.")
    return (
        "insert into bronze.livros (fonte_url, payload, _execucao_id)\n"
        f"select item->>'url', item, '{execucao_id}'\n"
        f"from jsonb_array_elements($payload${payloads}$payload$::jsonb) as item;\n"
    )


def gravar_arquivo_sql(caminho, sql):
    Path(caminho).write_text(sql, encoding="utf-8")


def gravar_no_banco(database_url, sql):
    import psycopg

    with psycopg.connect(database_url) as conexao:
        conexao.execute(sql)


def ler_argumentos():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--paginas", type=int, default=50, help="20 livros por página")
    parser.add_argument(
        "--saida-sql", help="gera este arquivo .sql em vez de gravar no banco"
    )
    return parser.parse_args()


def main():
    load_dotenv()
    argumentos = ler_argumentos()
    database_url = os.getenv("DATABASE_URL")
    if not argumentos.saida_sql and not database_url:
        sys.exit("Defina DATABASE_URL no .env ou use --saida-sql para gravar pelo MCP.")

    execucao_id = uuid.uuid4().hex
    livros = raspar_catalogo(argumentos.paginas)
    sql = ARQUIVO_DDL.read_text(encoding="utf-8") + montar_sql_insercao(livros, execucao_id)

    if argumentos.saida_sql:
        gravar_arquivo_sql(argumentos.saida_sql, sql)
        print(f"{len(livros)} livros raspados. SQL em {argumentos.saida_sql}")
    else:
        gravar_no_banco(database_url, sql)
        print(f"{len(livros)} linhas gravadas em bronze.livros")
    print(f"_execucao_id: {execucao_id}")


if __name__ == "__main__":
    main()
