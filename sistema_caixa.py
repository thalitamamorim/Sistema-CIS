import streamlit as st
import sqlite3
from datetime import datetime
import pandas as pd
import re

# --- Configuração da página ---
st.set_page_config(
    page_title="Sistema EventoCaixa",
    page_icon="💰",
    layout="wide"
)

# --- Conexão com SQLite ---
conn = sqlite3.connect("evento.db", check_same_thread=False)
c = conn.cursor()

# --- Criar tabelas se não existirem ---
c.execute("""CREATE TABLE IF NOT EXISTS caixa (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    data TEXT,
    hora_abertura TEXT,
    hora_fechamento TEXT,
    nome_funcionario TEXT,
    dinheiro REAL,
    maquineta REAL,
    retiradas REAL DEFAULT 0,
    observacoes TEXT
)""")

c.execute("""CREATE TABLE IF NOT EXISTS estoque (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    data TEXT,
    produto TEXT,
    quantidade INTEGER,
    responsavel TEXT
)""")

c.execute("""CREATE TABLE IF NOT EXISTS fornecedor (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT,
    valor REAL,
    valor_pago REAL DEFAULT 0,
    pago BOOLEAN DEFAULT FALSE,
    data_pagamento TEXT,
    observacoes TEXT
)""")

c.execute("""CREATE TABLE IF NOT EXISTS investimento (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    data TEXT,
    descricao TEXT,
    tipo TEXT,
    valor REAL
)""")

# Adicione esta criação de tabela após as outras
c.execute("""CREATE TABLE IF NOT EXISTS investidores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT,
    valor_investido REAL,
    valor_devolvido REAL DEFAULT 0,
    devolvido BOOLEAN DEFAULT FALSE,
    data_devolucao TEXT
)""")

# --- Verificar e corrigir estrutura das tabelas ---
try:
    c.execute("PRAGMA table_info(caixa)")
    colunas_caixa = [col[1] for col in c.fetchall()]
    if 'retiradas' not in colunas_caixa:
        c.execute("ALTER TABLE caixa ADD COLUMN retiradas REAL DEFAULT 0")

    c.execute("PRAGMA table_info(fornecedor)")
    colunas_fornecedor = [col[1] for col in c.fetchall()]
    if 'valor_pago' not in colunas_fornecedor:
        c.execute("ALTER TABLE fornecedor ADD COLUMN valor_pago REAL DEFAULT 0")
    if 'data_pagamento' not in colunas_fornecedor:
        c.execute("ALTER TABLE fornecedor ADD COLUMN data_pagamento TEXT")

except sqlite3.OperationalError:
    pass

conn.commit()

# --- Funções auxiliares ---


def formatar_moeda(valor):
    if valor == 0:
        return "R$ 0,00"
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def calcular_totais_investimentos():
    """Calcula totais relacionados aos investimentos"""
    # Total investido
    c.execute("SELECT SUM(valor_investido) FROM investidores")
    total_investido = c.fetchone()[0] or 0

    # Total já devolvido
    c.execute("SELECT SUM(valor_devolvido) FROM investidores")
    total_devolvido = c.fetchone()[0] or 0

    # Total a devolver
    c.execute(
        "SELECT SUM(valor_investido - valor_devolvido) FROM investidores WHERE NOT devolvido")
    total_a_devolver = c.fetchone()[0] or 0

    return {
        'total_investido': total_investido,
        'total_devolvido': total_devolvido,
        'total_a_devolver': total_a_devolver
    }


def calcular_totais():
    """Calcula todos os totais financeiros"""
    # Total de caixa (dinheiro + maquineta - retiradas)
    c.execute(
        "SELECT SUM(dinheiro + maquineta - retiradas) FROM caixa WHERE hora_fechamento IS NOT NULL")
    total_caixa = c.fetchone()[0] or 0

    # Total de fornecedores (valor total)
    c.execute("SELECT SUM(valor) FROM fornecedor")
    total_fornecedores = c.fetchone()[0] or 0

    # Total já pago aos fornecedores
    c.execute("SELECT SUM(valor_pago) FROM fornecedor")
    total_pago = c.fetchone()[0] or 0

    # Total a pagar (valor total - valor pago)
    total_a_pagar = total_fornecedores - total_pago

    # Calcular totais de investimentos
    totais_invest = calcular_totais_investimentos()

    # Saldo disponível (caixa - total a pagar - total a devolver)
    saldo_disponivel = total_caixa - total_a_pagar - \
        totais_invest['total_a_devolver']

    return {
        'total_caixa': total_caixa,
        'total_fornecedores': total_fornecedores,
        'total_pago': total_pago,
        'total_a_pagar': total_a_pagar,
        'saldo_disponivel': saldo_disponivel,
        'total_investido': totais_invest['total_investido'],
        'total_devolvido': totais_invest['total_devolvido'],
        'total_a_devolver': totais_invest['total_a_devolver']
    }


def entrada_monetaria(label, key, valor_minimo=0.0):
    if key not in st.session_state:
        st.session_state[key] = ""

    valor_input = st.text_input(
        label,
        value=st.session_state[key],
        key=f"text_{key}",
        placeholder="0,00"
    )

    valor_processado = 0.0
    if valor_input:
        valor_limpo = re.sub(r'[^\d,.]', '', valor_input)

        if valor_limpo:
            if ',' in valor_limpo and '.' in valor_limpo:
                valor_limpo = valor_limpo.replace('.', '').replace(',', '.')
            elif ',' in valor_limpo:
                valor_limpo = valor_limpo.replace(',', '.')

            try:
                valor_processado = float(valor_limpo)
                if valor_processado < valor_minimo:
                    valor_processado = valor_minimo
            except ValueError:
                valor_processado = 0.0
                st.session_state[key] = ""
        else:
            valor_processado = 0.0
            st.session_state[key] = ""
    else:
        st.session_state[key] = ""

    return valor_processado


# --- Interface ---
st.title("💰 Sistema EventoCaixa")

# Verificar login para área admin
if "admin_logado" not in st.session_state:
    st.session_state.admin_logado = False

if "admin_usuario" not in st.session_state:
    st.session_state.admin_usuario = ""

# Abas: Caixa, Admin e Suporte
abas = st.tabs(["📋 Caixa", "👤 Admin", "🆘 Suporte"])

# --- ABA CAIXA ---
with abas[0]:
    st.header("📋 Controle de Caixa")

    modo_caixa = st.radio("Modo de operação:", [
                          "Abrir Novo Caixa", "Editar Caixa Existente"], horizontal=True, key="modo_caixa")

    if modo_caixa == "Abrir Novo Caixa":
        col1, col2 = st.columns(2)

        with col1:
            nome_func = st.text_input(
                "👤 Nome da Funcionária", key="nome_funcionaria")

            data_hoje = datetime.now().date().isoformat()
            c.execute("SELECT id FROM caixa WHERE data = ? AND nome_funcionario = ? AND hora_fechamento IS NULL",
                      (data_hoje, nome_func))
            caixa_aberto = c.fetchone()

            if not caixa_aberto:
                if st.button("🟢 Abrir Caixa", type="primary", key="abrir_caixa"):
                    if nome_func:
                        hora_abertura = datetime.now().time().strftime("%H:%M:%S")
                        c.execute("INSERT INTO caixa (data, hora_abertura, nome_funcionario, dinheiro, maquineta) VALUES (?, ?, ?, ?, ?)",
                                  (data_hoje, hora_abertura, nome_func, 0.0, 0.0))
                        conn.commit()
                        st.success(f"✅ Caixa aberto às {hora_abertura}!")
                        st.rerun()
                    else:
                        st.error("❌ Digite o nome da funcionária")
            else:
                st.info("ℹ️ Você já tem un caixa aberto hoje")

        with col2:
            c.execute(
                "SELECT id, nome_funcionario, data, hora_abertura FROM caixa WHERE hora_fechamento IS NULL")
            caixas_abertos = c.fetchall()

            if caixas_abertos:
                st.subheader("Caixas Abertos")
                for caixa in caixas_abertos:
                    st.write(f"{caixa[1]} - {caixa[2]} ({caixa[3]})")
            else:
                st.info("ℹ️ Nenhum caixa aberto no momento")

        st.divider()

        if caixas_abertos:
            st.subheader("🔒 Fechamento de Caixa")

            caixa_selecionado = st.selectbox("Selecione o caixa para fechar",
                                             [f"{x[1]} - {x[2]}" for x in caixas_abertos],
                                             key="select_caixa")
            idx = caixas_abertos[[
                f"{x[1]} - {x[2]}" for x in caixas_abertos].index(caixa_selecionado)][0]

            col3, col4 = st.columns(2)

            with col3:
                st.write("### 💰 Valores de Fechamento")
                dinheiro = entrada_monetaria(
                    "💵 Valor em dinheiro", "dinheiro_input")
                maquineta = entrada_monetaria(
                    "💳 Valor na maquineta", "maquineta_input")
                retiradas = entrada_monetaria(
                    "↗️ Retiradas do caixa", "retiradas_input")

                if dinheiro > 0 or maquineta > 0:
                    st.info(
                        f"**Valor digitado:** {formatar_moeda(dinheiro + maquineta - retiradas)}")

            with col4:
                st.write("### 📊 Resumo")
                if dinheiro > 0 or maquineta > 0:
                    col_a, col_b, col_c = st.columns(3)
                    with col_a:
                        st.metric("💵 Dinheiro", formatar_moeda(dinheiro))
                    with col_b:
                        st.metric("💳 Maquineta", formatar_moeda(maquineta))
                    with col_c:
                        st.metric("↗️ Retiradas", formatar_moeda(retiradas))

                    st.metric("💰 Total Líquido",
                              formatar_moeda(dinheiro + maquineta - retiradas),
                              delta=formatar_moeda(dinheiro + maquineta - retiradas))
                else:
                    st.info("ℹ️ Digite os valores para ver o resumo")

            observacoes = st.text_area("📝 Observações", key="obs_caixa")

            if st.button("🔒 Fechar Caixa", type="primary", key="fechar_caixa"):
                if dinheiro == 0 and maquineta == 0:
                    st.warning("⚠️ Valores zerados. Confirme se está correto.")
                else:
                    hora_fechamento = datetime.now().time().strftime("%H:%M:%S")
                    c.execute("UPDATE caixa SET dinheiro=?, maquineta=?, observacoes=?, hora_fechamento=? WHERE id=?",
                              (dinheiro, maquineta, observacoes, hora_fechamento, idx))
                    conn.commit()

                    for key in ["dinheiro_input", "maquineta_input", "retiradas_input"]:
                        if key in st.session_state:
                            st.session_state[key] = ""

                    st.success(f"✅ Caixa fechado às {hora_fechamento}!")
                    st.rerun()

    else:
        st.subheader("✏️ Editar Caixa Existente")

        nome_func_editar = st.text_input(
            "👤 Seu nome para buscar caixas", key="nome_editar")

        if nome_func_editar:
            c.execute("""
                SELECT id, data, hora_abertura, hora_fechamento, dinheiro, maquineta, observacoes 
                FROM caixa 
                WHERE nome_funcionario = ? 
                ORDER BY data DESC, hora_abertura DESC
            """, (nome_func_editar,))

            caixas_funcionaria = c.fetchall()

            if caixas_funcionaria:
                opcoes_caixas = [
                    f"{c[1]} - {c[2]} - R$ {c[4] + c[5]:.2f} {'(Fechado)' if c[3] else '(Aberto)'}" for c in caixas_funcionaria]
                caixa_editar = st.selectbox(
                    "Selecione o caixa para editar", opcoes_caixas, key="select_editar_caixa_user")

                idx = caixas_funcionaria[opcoes_caixas.index(caixa_editar)][0]
                caixa_dados = caixas_funcionaria[opcoes_caixas.index(
                    caixa_editar)]

                st.write("---")
                st.write("### 📝 Editar Valores do Caixa")

                col_edit1, col_edit2 = st.columns(2)

                with col_edit1:
                    novo_dinheiro = st.number_input("💵 Valor em dinheiro", value=float(
                        caixa_dados[4]), format="%.2f", key="edit_dinheiro_user")
                    novo_maquineta = st.number_input("💳 Valor na maquineta", value=float(
                        caixa_dados[5]), format="%.2f", key="edit_maquineta_user")
                    novas_retiradas = st.number_input(
                        "↗️ Retiradas do caixa", value=0.0, format="%.2f", key="edit_retiradas_user")

                with col_edit2:
                    st.metric("💰 Total Atual", formatar_moeda(
                        caixa_dados[4] + caixa_dados[5]))
                    st.metric("💰 Total Novo", formatar_moeda(
                        novo_dinheiro + novo_maquineta - novas_retiradas))
                    st.metric("📆 Data", caixa_dados[1])
                    st.metric("⏰ Hora Abertura", caixa_dados[2])
                    if caixa_dados[3]:
                        st.metric("🔒 Hora Fechamento", caixa_dados[3])

                nova_observacao = st.text_area(
                    "📝 Observações", value=caixa_dados[6] or "", key="edit_observacao_user")

                col_btn_edit, col_btn_cancel = st.columns(2)
                with col_btn_edit:
                    if st.button("💾 Salvar Alterações", type="primary", key="save_edit_caixa"):
                        c.execute("UPDATE caixa SET dinheiro=?, maquineta=?, observacoes=? WHERE id=?",
                                  (novo_dinheiro, novo_maquineta, nova_observacao, idx))
                        conn.commit()
                        st.success("✅ Caixa atualizado com sucesso!")
                        st.rerun()

                with col_btn_cancel:
                    if st.button("❌ Cancelar Edição", key="cancel_edit_caixa"):
                        st.rerun()

            else:
                st.info("ℹ️ Nenhum caixa encontrado para esta funcionária")

    st.divider()

    st.subheader("📦 Controle de Estoque")

    col5, col6 = st.columns(2)

    with col5:
        produto = st.text_input("📦 Nome do produto", key="produto_nome")
        quantidade = st.number_input(
            "🔢 Quantidade", 0, step=1, key="produto_qtd")

        if st.button("➕ Adicionar ao Estoque", key="add_estoque"):
            if produto and quantidade > 0:
                data_hoje = datetime.now().date().isoformat()
                c.execute("INSERT INTO estoque (data, produto, quantidade, responsavel) VALUES (?, ?, ?, ?)",
                          (data_hoje, produto, quantidade, nome_func if 'nome_func' in locals() else nome_func_editar))
                conn.commit()
                st.success(
                    f"✅ {quantidade} unidades de {produto} adicionadas ao estoque!")
                st.rerun()
            else:
                st.error("❌ Preencha todos os campos")

    with col6:
        st.info("📊 Estoque Atual")
        c.execute("SELECT produto, SUM(quantidade) FROM estoque GROUP BY produto")
        estoque_atual = c.fetchall()

        if estoque_atual:
            for produto, qtd in estoque_atual:
                st.write(f"**{produto}:** {qtd} unidades")
        else:
            st.info("ℹ️ Nenhum produto em estoque")

    st.divider()
    st.subheader("✏️ Editar Estoque")

    nome_resp_estoque = st.text_input(
        "👤 Seu nome para buscar itens do estoque", key="nome_estoque_edit")

    if nome_resp_estoque:
        c.execute("""
            SELECT id, data, produto, quantidade 
            FROM estoque 
            WHERE responsavel = ? 
            ORDER BY data DESC
        """, (nome_resp_estoque,))

        itens_estoque = c.fetchall()

        if itens_estoque:
            for item in itens_estoque:
                with st.expander(f"{item[1]} - {item[2]} - {item[3]} unidades"):
                    col_item1, col_item2 = st.columns([3, 1])

                    with col_item1:
                        nova_qtd = st.number_input(
                            "Nova quantidade", value=item[3], min_value=0, key=f"edit_qtd_{item[0]}")

                    with col_item2:
                        st.write("")
                        st.write("")
                        if st.button("💾 Atualizar", key=f"update_estoque_{item[0]}"):
                            c.execute(
                                "UPDATE estoque SET quantidade = ? WHERE id = ?", (nova_qtd, item[0]))
                            conn.commit()
                            st.success("✅ Quantidade atualizada!")
                            st.rerun()

            if st.button("🗑️ Limpar Todos os Itens", type="secondary", key="clear_all_estoque"):
                c.execute("DELETE FROM estoque WHERE responsavel = ?",
                          (nome_resp_estoque,))
                conn.commit()
                st.success("✅ Todos os itens do estoque foram removidos!")
                st.rerun()
        else:
            st.info("ℹ️ Nenhum item encontrado para esta responsável")

# --- ABA ADMIN ---
with abas[1]:
    st.header("👤 Área Administrativa")

    if not st.session_state.admin_logado:
        st.subheader("🔐 Login Administrativo")

        col_login1, col_login2 = st.columns(2)

        with col_login1:
            usuario = st.text_input("Usuário", key="admin_usuario_input")
            senha = st.text_input("Senha", type="password",
                                  key="admin_senha_input")

            if st.button("Entrar", key="btn_login"):
                if usuario == "admin" and senha == "evento123":
                    st.session_state.admin_logado = True
                    st.session_state.admin_usuario = usuario
                    st.rerun()
                else:
                    st.error("Credenciais inválidas!")

        with col_login2:
            st.info("""
            **Insira suas credenciais administrativas.**
            
            ⚠️ Em caso de esquecimento, contactar o suporte.
            """)

    else:
        st.success(f"👋 Bem-vindo(a), {st.session_state.admin_usuario}!")

        if st.button("🚪 Sair", key="btn_logout"):
            st.session_state.admin_logado = False
            st.session_state.admin_usuario = ""
            st.rerun()

        st.divider()

        st.subheader("📊 Dashboard Financeiro")

        totais = calcular_totais()

        col1, col2, col3, col4, col5 = st.columns(5)

        with col1:
            st.metric("💰 Total em Caixa",
                      formatar_moeda(totais['total_caixa']),
                      help="Soma de todos os caixas fechados (dinheiro + maquineta - retiradas)")

        with col2:
            st.metric("📋 Total de Fornecedores",
                      formatar_moeda(totais['total_fornecedores']),
                      help="Valor total de todos os fornecedores cadastrados")

        with col3:
            st.metric("⏳ A Pagar",
                      formatar_moeda(totais['total_a_pagar']),
                      help="Valor que ainda precisa ser pago aos fornecedores",
                      delta=formatar_moeda(-totais['total_a_pagar']))

        with col4:
            st.metric("🎯 A Devolver",
                      formatar_moeda(totais['total_a_devolver']),
                      help="Valor que precisa ser devolvido aos investidores",
                      delta=formatar_moeda(-totais['total_a_devolver']))

        with col5:
            cor_saldo = "green" if totais['saldo_disponivel'] >= 0 else "red"
            st.metric("💵 Saldo Disponível",
                      formatar_moeda(totais['saldo_disponivel']),
                      help="Total em caixa menos contas a pagar e investimentos a devolver",
                      delta=formatar_moeda(totais['saldo_disponivel']))

        st.divider()

        # 🎯 CONTROLE DE INVESTIMENTOS
        st.subheader("🎯 Controle de Investimentos")

        col_inv1, col_inv2 = st.columns(2)

        with col_inv1:
            st.write("### 👥 Investidores")

            # Buscar totais por investidor
            c.execute("""
                SELECT nome, SUM(valor_investido) as total_investido, 
                       SUM(valor_devolvido) as total_devolvido
                FROM investidores 
                GROUP BY nome 
                ORDER BY nome
            """)
            totais_investidores = c.fetchall()

            c.execute("SELECT * FROM investidores ORDER BY nome, id")
            investidores = c.fetchall()

            if investidores:
                # Mostrar totais por investidor
                st.write("**📊 Totais por Investidor:**")
                for total in totais_investidores:
                    nome, total_investido, total_devolvido = total
                    restante = total_investido - total_devolvido

                    col_total1, col_total2, col_total3 = st.columns(3)
                    with col_total1:
                        st.metric(f"💰 {nome}", formatar_moeda(total_investido))
                    with col_total2:
                        st.metric("💵 Devolvido",
                                  formatar_moeda(total_devolvido))
                    with col_total3:
                        st.metric("⏳ Restante", formatar_moeda(restante))

                st.divider()

                # Mostrar investimentos individuais
                st.write("**📋 Investimentos Individuais:**")
                for inv in investidores:
                    with st.expander(f"{inv[1]} - {formatar_moeda(inv[2])} - {formatar_moeda(inv[3])} devolvido"):
                        st.write(f"**Investido:** {formatar_moeda(inv[2])}")
                        st.write(f"**Devolvido:** {formatar_moeda(inv[3])}")
                        st.write(
                            f"**Restante:** {formatar_moeda(inv[2] - inv[3])}")
                        st.write(
                            f"**Status:** {'✅ Devolvido' if inv[4] else '⏳ Pendente'}")

                        if inv[5]:
                            st.write(f"**Data de devolução:** {inv[5]}")

                        if not inv[4]:
                            valor_restante = inv[2] - inv[3]
                            valor_devolucao = st.number_input(
                                "Valor a devolver",
                                min_value=0.0,
                                max_value=float(valor_restante),
                                value=float(valor_restante),
                                format="%.2f",
                                key=f"devolucao_{inv[0]}"
                            )

                            if st.button("💵 Registrar Devolução", key=f"devolver_{inv[0]}"):
                                novo_valor_devolvido = inv[3] + valor_devolucao
                                devolvido_completo = novo_valor_devolvido >= inv[2]

                                c.execute("""
                                    UPDATE investidores 
                                    SET valor_devolvido = ?, devolvido = ?, data_devolucao = ?
                                    WHERE id = ?
                                """, (novo_valor_devolvido, devolvido_completo, datetime.now().date().isoformat(), inv[0]))
                                conn.commit()

                                st.success(
                                    f"✅ Devolução de {formatar_moeda(valor_devolucao)} registrada!")
                                st.rerun()
            else:
                st.info("ℹ️ Nenhum investidor cadastrado")

        with col_inv2:
            st.write("### ➕ Novo Investidor")

            nome_investidor = st.text_input(
                "Nome do Investidor",
                key="novo_investidor_nome",
                placeholder="Ex: João Silva"
            )

            valor_investido = st.number_input(
                "Valor Investido",
                min_value=0.0,
                step=0.01,
                format="%.2f",
                key="novo_investidor_valor",
                value=0.0,
                placeholder="0,00"
            )

            if st.button("💾 Adicionar Investidor", type="primary", key="adicionar_investidor"):
                if nome_investidor.strip() and valor_investido > 0:
                    c.execute("INSERT INTO investidores (nome, valor_investido) VALUES (?, ?)",
                              (nome_investidor.strip(), valor_investido))
                    conn.commit()
                    st.success(
                        f"✅ {nome_investidor} adicionado com investimento de {formatar_moeda(valor_investido)}!")
                    st.rerun()
                else:
                    st.error("❌ Preencha todos os campos corretamente")

        st.divider()

        st.subheader("📋 Contas a Pagar")

        c.execute("""
            SELECT id, nome, valor, valor_pago, pago, data_pagamento, observacoes 
            FROM fornecedor 
            ORDER BY pago, nome
        """)
        fornecedores = c.fetchall()

        if fornecedores:
            fornecedores_pagos = [f for f in fornecedores if f[4]]
            fornecedores_pendentes = [f for f in fornecedores if not f[4]]

            if fornecedores_pendentes:
                st.write("### ⏳ Pendentes de Pagamento")
                for forn in fornecedores_pendentes:
                    with st.expander(f"{forn[1]} - {formatar_moeda(forn[2])}", expanded=True):
                        col_f1, col_f2, col_f3 = st.columns([2, 2, 1])

                        with col_f1:
                            valor_restante = forn[2] - forn[3]
                            st.write(
                                f"**Valor total:** {formatar_moeda(forn[2])}")
                            st.write(f"**Já pago:** {formatar_moeda(forn[3])}")
                            st.write(
                                f"**Restante:** {formatar_moeda(valor_restante)}")

                        with col_f2:
                            valor_pagamento = st.number_input(
                                "Valor a pagar agora",
                                min_value=0.0,
                                max_value=float(valor_restante),
                                value=float(valor_restante),
                                format="%.2f",
                                key=f"pagamento_{forn[0]}"
                            )

                            if forn[5]:
                                st.write(f"Último pagamento: {forn[5]}")

                        with col_f3:
                            st.write("")
                            st.write("")
                            if st.button("💵 Registrar Pagamento", key=f"pagar_{forn[0]}"):
                                novo_valor_pago = forn[3] + valor_pagamento
                                pago_completo = novo_valor_pago >= forn[2]

                                c.execute("""
                                    UPDATE fornecedor 
                                    SET valor_pago = ?, pago = ?, data_pagamento = ?
                                    WHERE id = ?
                                """, (novo_valor_pago, pago_completo, datetime.now().date().isoformat(), forn[0]))
                                conn.commit()

                                st.success(
                                    f"✅ Pagamento de {formatar_moeda(valor_pagamento)} registrado!")
                                st.rerun()

                        if forn[6]:
                            st.write(f"*Observações:* {forn[6]}")

            if fornecedores_pagos:
                st.write("### ✅ Pagas")
                for forn in fornecedores_pagos:
                    st.write(
                        f"**{forn[1]}** - {formatar_moeda(forn[2])} - 💰 Pago em {forn[5]}")
                    if forn[3] > forn[2]:
                        st.write(
                            f"*Valor extra pago: {formatar_moeda(forn[3] - forn[2])}*")

        else:
            st.info("ℹ️ Nenhum fornecedor cadastrado")

        st.divider()

        st.subheader("➕ Novo Fornecedor")

        col_novo1, col_novo2 = st.columns(2)

        with col_novo1:
            nome_novo_fornecedor = st.text_input(
                "Nome do Fornecedor", key="novo_fornecedor_nome")
            valor_novo_fornecedor = st.number_input(
                "Valor Total", 0.0, step=0.01, format="%.2f", key="novo_fornecedor_valor")
            observacoes_novo_fornecedor = st.text_area(
                "Observações", key="novo_fornecedor_obs")

        with col_novo2:
            st.write("")
            if st.button("💾 Salvar Novo Fornecedor", key="salvar_novo_fornecedor"):
                if nome_novo_fornecedor and valor_novo_fornecedor > 0:
                    c.execute("""
                        INSERT INTO fornecedor (nome, valor, observacoes) 
                        VALUES (?, ?, ?)
                    """, (nome_novo_fornecedor, valor_novo_fornecedor, observacoes_novo_fornecedor))
                    conn.commit()
                    st.success("✅ Fornecedor cadastrado!")
                    st.rerun()
                else:
                    st.error("❌ Preencha os campos obrigatórios")

        st.divider()

        st.subheader("📊 Relatórios Detalhados")

        tab_caixa, tab_fornecedores, tab_investimentos, tab_fluxo, tab_estoque = st.tabs(
            ["Caixa", "Fornecedores", "Investimentos", "Fluxo de Caixa", "📦 Estoque"])

        with tab_caixa:
            c.execute(
                "SELECT * FROM caixa WHERE hora_fechamento IS NOT NULL ORDER BY data DESC")
            caixas = c.fetchall()

            if caixas:
                df_caixa = pd.DataFrame(caixas, columns=[
                                        "ID", "Data", "Abertura", "Fechamento", "Funcionária", "Dinheiro", "Maquineta", "Retiradas", "Observações"])

                df_caixa["Dinheiro"] = pd.to_numeric(
                    df_caixa["Dinheiro"], errors='coerce').fillna(0)
                df_caixa["Maquineta"] = pd.to_numeric(
                    df_caixa["Maquineta"], errors='coerce').fillna(0)
                df_caixa["Retiradas"] = pd.to_numeric(
                    df_caixa["Retiradas"], errors='coerce').fillna(0)

                df_caixa["Total"] = df_caixa["Dinheiro"] + \
                    df_caixa["Maquineta"] - df_caixa["Retiradas"]

                st.dataframe(df_caixa, use_container_width=True)

                df_caixa["Data"] = pd.to_datetime(df_caixa["Data"])
                df_diario = df_caixa.groupby(
                    "Data")["Total"].sum().reset_index()

                st.line_chart(df_diario, x="Data", y="Total")

            else:
                st.info("ℹ️ Nenhum caixa fechado encontrado")

        with tab_fornecedores:
            if fornecedores:
                df_fornecedores = pd.DataFrame(fornecedores, columns=[
                                               "ID", "Nome", "Valor", "Valor Pago", "Pago", "Data Pagamento", "Observações"])
                df_fornecedores["Restante"] = df_fornecedores["Valor"] - \
                    df_fornecedores["Valor Pago"]

                st.dataframe(df_fornecedores, use_container_width=True)

                status_count = df_fornecedores["Pago"].value_counts()
                st.bar_chart(status_count)

            else:
                st.info("ℹ️ Nenhum fornecedor cadastrado")

        with tab_investimentos:
            st.write("### 📊 Relatório de Investimentos")

            if investidores:
                df_investidores = pd.DataFrame(investidores, columns=[
                    "ID", "Nome", "Valor Investido", "Valor Devolvido", "Devolvido", "Data Devolução"])

                df_investidores["Restante"] = df_investidores["Valor Investido"] - \
                    df_investidores["Valor Devolvido"]
                df_investidores["% Devolvido"] = (
                    df_investidores["Valor Devolvido"] / df_investidores["Valor Investido"]) * 100

                st.dataframe(df_investidores, use_container_width=True)

                # Gráfico de barras para status de devolução (sem matplotlib)
                status_devolucao = df_investidores["Devolvido"].value_counts()
                if not status_devolucao.empty:
                    status_devolucao.index = status_devolucao.index.map(
                        {True: 'Devolvido', False: 'Pendente'})
                    st.bar_chart(status_devolucao)

                    # Mostrar estatísticas simples
                    col_stat1, col_stat2 = st.columns(2)
                    with col_stat1:
                        st.metric("✅ Devolvidos",
                                  status_devolucao.get('Devolvido', 0))
                    with col_stat2:
                        st.metric("⏳ Pendentes",
                                  status_devolucao.get('Pendente', 0))
            else:
                st.info("ℹ️ Nenhum investidor cadastrado")

        with tab_fluxo:
            st.write("### 📈 Fluxo de Caixa")

            col_res1, col_res2, col_res3, col_res4 = st.columns(4)

            with col_res1:
                st.metric("Entradas", formatar_moeda(totais['total_caixa']))

            with col_res2:
                st.metric("Saídas", formatar_moeda(
                    totais['total_pago'] + totais['total_devolvido']))

            with col_res3:
                st.metric("Obrigações Pendentes",
                          formatar_moeda(totais['total_a_pagar'] + totais['total_a_devolver']))

            with col_res4:
                st.metric("Saldo", formatar_moeda(totais['saldo_disponivel']))

            st.write("### 🔮 Projeção")
            st.info(f"""
            **Situação atual:**
            - 💰 Disponível: {formatar_moeda(totais['saldo_disponivel'])}
            - ⏳ A pagar (fornecedores): {formatar_moeda(totais['total_a_pagar'])}
            - 🎯 A devolver (investidores): {formatar_moeda(totais['total_a_devolver'])}
            - 📊 Saldo final projetado: {formatar_moeda(totais['saldo_disponivel'] - totais['total_a_pagar'] - totais['total_a_devolver'])}
            """)

        with tab_estoque:
            st.subheader("📦 Histórico Completo de Estoque")

            c.execute("SELECT DISTINCT data FROM estoque ORDER BY data DESC")
            datas_estoque = [d[0] for d in c.fetchall()]

            if datas_estoque:
                data_selecionada = st.selectbox(
                    "📅 Selecione a data para visualizar o estoque:",
                    datas_estoque,
                    key="select_data_estoque"
                )

                c.execute("""
                    SELECT produto, quantidade, responsavel 
                    FROM estoque 
                    WHERE data = ? 
                    ORDER BY produto
                """, (data_selecionada,))

                itens_data = c.fetchall()

                if itens_data:
                    st.write(f"### 📋 Estoque em {data_selecionada}")

                    df_estoque = pd.DataFrame(
                        itens_data, columns=["Produto", "Quantidade", "Responsável"])

                    df_agrupado = df_estoque.groupby(
                        "Produto")["Quantidade"].sum().reset_index()
                    df_agrupado["Responsável"] = "Vários"

                    col_est1, col_est2 = st.columns(2)

                    with col_est1:
                        st.write("**📊 Resumo por Produto:**")
                        st.dataframe(df_agrupado, use_container_width=True)

                    with col_est2:
                        st.write("**📝 Detalhes por Responsável:**")
                        st.dataframe(df_estoque, use_container_width=True)

                    total_itens = df_estoque["Quantidade"].sum()
                    total_produtos = len(df_agrupado)
                    total_responsaveis = df_estoque["Responsável"].nunique()

                    col_stat1, col_stat2, col_stat3 = st.columns(3)
                    with col_stat1:
                        st.metric("📦 Total de Itens", total_itens)
                    with col_stat2:
                        st.metric("🏷️ Tipos de Produtos", total_produtos)
                    with col_stat3:
                        st.metric("👥 Responsáveis", total_responsaveis)

                else:
                    st.info(
                        f"ℹ️ Nenhum item em estoque para a data {data_selecionada}")

                st.divider()
                st.subheader("📈 Evolução do Estoque")

                c.execute("""
                    SELECT data, produto, SUM(quantidade) as total
                    FROM estoque 
                    GROUP BY data, produto
                    ORDER BY data
                """)

                evolucao_estoque = c.fetchall()

                if evolucao_estoque:
                    df_evolucao = pd.DataFrame(evolucao_estoque, columns=[
                                               "Data", "Produto", "Quantidade"])

                    df_pivot = df_evolucao.pivot_table(
                        index="Data",
                        columns="Produto",
                        values="Quantidade",
                        fill_value=0
                    ).reset_index()

                    st.line_chart(df_pivot.set_index("Data"))

            else:
                st.info("ℹ️ Nenhum registro de estoque encontrado")

# --- ABA SUPORTE ---
with abas[2]:
    st.header("🆘 Suporte e Ajuda")

    col_sup1, col_sup2 = st.columns(2)

    with col_sup1:
        st.subheader("📞 Contato de Suporte")
        st.info("""
        **Thalita Amorim**  
        📧 thalita.muniz.amorim@gmail.com  
        📞 (98) 98110-4216  
        🕐 Horário: 9h às 17h (Segunda a Sexta)
        """)

        st.subheader("🚨 Suporte Emergencial")
        st.warning("""
        Para problemas urgentes durante o evento:
        - 📞 Ligação prioritária
        - 📱 WhatsApp com resposta rápida
        - 🆘 Plantão para emergências
        """)

    with col_sup2:
        st.subheader("📖 Como Usar o Sistema")

        with st.expander("📋 Caixa - Como funciona"):
            st.write("""
            1. **Abrir Caixa**: Digite seu nome and clique em 'Abrir Caixa'
            2. **Fechar Caixa**: Preencha os valores ao final do dia
            3. **Editar Caixa**: Use o modo 'Editar Caixa Existente' para corrigir erros
            4. **Estoque**: Registre os produtos vendidos/consumidos
            """)

        with st.expander("✏️ Como Editar Erros"):
            st.write("""
            **Para corrigir valores do caixa:**
            1. Selecione 'Editar Caixa Existente'
            2. Digite seu nome
            3. Selecione o caixa que deseja editar
            4. Ajuste os valores and clique em 'Salvar Alterações'
            
            **Para corrigir estoque:**
            1. Digite seu nome no campo 'Editar Estoque'
            2. Ajuste as quantidades de cada item
            3. Clique em 'Atualizar' para cada correção
            """)

        with st.expander("❓ Perguntas Frequentes"):
            st.write("""
            **Q: Digitei um valor errado no caixa, e agora?**  
            R: Use a opção 'Editar Caixa Existente' para corrigir.
            
            **Q: Registrei a quantidade errada no estoque?**  
            R: Use a seção 'Editar Estoque' para ajustar.
            
            **Q: Posso editar caixas de outros dias?**  
            R: Sim, basta selecionar a data desejada.
            """)

    st.divider()

    st.subheader("🐛 Reportar Problema")

    problema = st.text_area("Descreva o problema encontrado:",
                            placeholder="Ex: Ao tentar editar o caixa, o sistema apresentou erro...")
    contato = st.text_input("Seu e-mail para retorno:")

    if st.button("📨 Enviar Relatório", key="report_bug"):
        if problema:
            st.success("✅ Relatório enviado! Entraremos em contato em breve.")
        else:
            st.error("❌ Por favor, descreva o problema.")

# --- Rodapé ---
st.divider()
st.caption("Sistema EventoCaixa - Desenvolvido para gerenciamento de eventos • Suporte: thalita.muniz.amorim@gmail.com • (98) 98110-4216")

# Fechar conexão ao final
conn.close()
