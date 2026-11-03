"""Interface web para testar o agente SQL: streamlit run app_streamlit.py"""

import importlib
import os
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent))
agente = importlib.import_module("04_sql_agent")

PERGUNTAS_PRD = [
    "Qual categoria tem o maior valor em estoque, em reais?",
    "Quantos livros bem avaliados custam menos de £20?",
    "Quantos livros únicos temos na base?",
    "Qual o preço médio por faixa de preço?",
]


def limpar_conversa():
    st.session_state.conversa = []


def colunas_unicas(colunas):
    vistas = {}
    unicas = []
    for coluna in colunas:
        vistas[coluna] = vistas.get(coluna, 0) + 1
        unicas.append(coluna if vistas[coluna] == 1 else f"{coluna}_{vistas[coluna]}")
    return unicas


def valor_para_tabela(valor):
    if isinstance(valor, Decimal):
        return float(valor)
    if isinstance(valor, (date, datetime)):
        return valor.isoformat()
    return valor


def linhas_para_tabela(colunas, linhas):
    nomes = colunas_unicas(colunas)
    return [
        {nome: valor_para_tabela(valor) for nome, valor in zip(nomes, linha)}
        for linha in linhas
    ]


def mostrar_detalhes(resultado):
    if resultado.erros:
        with st.expander(f"Tentativas com erro ({len(resultado.erros)})"):
            for erro in resultado.erros:
                st.warning(erro)
    if resultado.sql:
        with st.expander("SQL e resultado", expanded=True):
            st.code(resultado.sql, language="sql")
            if resultado.colunas:
                st.dataframe(
                    linhas_para_tabela(resultado.colunas, resultado.linhas),
                    width="stretch",
                )
                if len(resultado.linhas) == agente.LIMITE_LINHAS:
                    st.caption(f"Resultado limitado a {agente.LIMITE_LINHAS} linhas.")


def mostrar_conversa():
    for item in st.session_state.conversa:
        with st.chat_message("user"):
            st.markdown(item["pergunta"])
        with st.chat_message("assistant"):
            if item["erro"]:
                st.error(item["erro"])
                continue
            st.markdown(item["resultado"].resposta)
            st.caption("Com contexto" if item["com_contexto"] else "Sem contexto")
            mostrar_detalhes(item["resultado"])


def montar_historico():
    historico = []
    for item in st.session_state.conversa:
        if item["resultado"]:
            historico += [
                {"role": "user", "content": item["pergunta"]},
                {"role": "assistant", "content": item["resultado"].resposta},
            ]
    return historico


def processar_pergunta(pergunta, com_contexto):
    item = {"pergunta": pergunta, "com_contexto": com_contexto, "resultado": None, "erro": None}
    with st.spinner("Consultando a base..."):
        try:
            item["resultado"] = agente.responder(
                pergunta,
                os.environ["DATABASE_URL"],
                com_contexto=com_contexto,
                historico=montar_historico(),
            )
        except Exception as erro:
            item["erro"] = f"Não foi possível responder: {erro}"
    st.session_state.conversa.append(item)


def montar_barra_lateral():
    with st.sidebar:
        st.header("Configuração")
        com_contexto = st.toggle(
            "Usar contexto (PRD e SPEC)",
            value=True,
            on_change=limpar_conversa,
            help="Desligado, o agente recebe só a instrução mínima e pode consultar a bronze.",
        )
        st.caption(f"Modelo: {os.getenv('LLM_PROVIDER')} / {os.getenv('LLM_MODEL')}")
        st.button("Limpar conversa", on_click=limpar_conversa, width="stretch")

        st.header("Perguntas do PRD")
        escolhida = None
        for pergunta in PERGUNTAS_PRD:
            if st.button(pergunta, width="stretch"):
                escolhida = pergunta
    return com_contexto, escolhida


def main():
    st.set_page_config(page_title="Livraria Inteligente", page_icon="📚")
    st.title("📚 Livraria Inteligente")
    st.caption("Pergunte em português sobre catálogo, estoque e avaliações.")

    agente.carregar_ambiente()
    faltando = agente.configuracao_faltante()
    if faltando:
        st.warning(
            "O agente ainda não pode rodar. Copie `.env.exemplo` para `.env` e preencha: "
            + ", ".join(f"`{nome}`" for nome in faltando)
        )
        st.stop()

    st.session_state.setdefault("conversa", [])
    com_contexto, escolhida = montar_barra_lateral()
    digitada = st.chat_input("Faça uma pergunta")
    pergunta = digitada or escolhida
    if pergunta:
        processar_pergunta(pergunta, com_contexto)
    mostrar_conversa()


main()
