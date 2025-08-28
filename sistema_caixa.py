import streamlit as st
from supabase import create_client, Client
from datetime import datetime
import pandas as pd
import re
import time

# --- Configuração da página ---
st.set_page_config(
    page_title="Sistema EventoCaixa",
    page_icon="💰",
    layout="wide"
)

# --- Conexão com Supabase ---


@st.cache_resource
def init_supabase():
    supabase: Client = create_client(
        st.secrets["supabase"]["url"],
        st.secrets["supabase"]["key"]
    )
    return supabase


supabase = init_supabase()

# --- Funções auxiliares ---


def formatar_moeda(valor):
    if valor == 0:
        return "R$ 0,00"
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


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

# --- Funções de acesso ao Supabase ---


def executar_query(tabela, operacao="select", filtros={}, dados=None, id=None):
    try:
        if operacao == "select":
            query = supabase.table(tabela).select("*")
            for key, value in filtros.items():
                query = query.eq(key, value)
            return query.execute()

        elif operacao == "insert":
            return supabase.table(tabela).insert(dados).execute()

        elif operacao == "update":
            return supabase.table(tabela).update(dados).eq('id', id).execute()

        elif operacao == "delete":
            return supabase.table(tabela).delete().eq('id', id).execute()

    except Exception as e:
        st.error(f"Erro no banco de dados: {e}")
        return None


def buscar_todos(tabela, ordenar_por="id", ascendente=True):
    try:
        order = {"column": ordenar_por, "ascending": ascendente}
        return supabase.table(tabela).select("*").order(ordenar_por, ascending=ascendente).execute()
    except Exception as e:
        st.error(f"Erro ao buscar dados: {e}")
        return None


def calcular_totais_investimentos():
    """Calcula totais relacionados aos investimentos"""
    try:
        response = supabase.table('investidores').select(
            'valor_investido, valor_devolvido, devolvido').execute()
        total_investido = 0
        total_devolvido = 0
        total_a_devolver = 0

        for item in response.data:
            total_investido += item['valor_investido'] or 0
            total_devolvido += item['valor_devolvido'] or 0
            if not item['devolvido']:
                total_a_devolver += (item['valor_investido']
                                     or 0) - (item['valor_devolvido'] or 0)

        return {
            'total_investido': total_investido,
            'total_devolvido': total_devolvido,
            'total_a_devolver': total_a_devolver
        }
    except Exception as e:
        st.error(f"Erro ao calcular investimentos: {e}")
        return {'total_investido': 0, 'total_devolvido': 0, 'total_a_devolver': 0}


def calcular_totais():
    """Calcula todos os totais financeiros"""
    try:
        # Total de caixa (dinheiro + maquineta + conta_bancaria - retiradas)
        response = supabase.table('caixa').select(
            'dinheiro, maquineta, conta_bancaria, retiradas, hora_fechamento').execute()
        total_caixa = 0
        total_conta_bancaria = 0

        for item in response.data:
            if item['hora_fechamento'] is not None:
                total_caixa += (item['dinheiro'] or 0) + \
                    (item['maquineta'] or 0) - (item['retiradas'] or 0)
                total_conta_bancaria += item['conta_bancaria'] or 0

        # Total de fornecedores
        response = supabase.table('fornecedor').select(
            'valor, valor_pago').execute()
        total_fornecedores = 0
        total_pago = 0
        for item in response.data:
            total_fornecedores += item['valor'] or 0
            total_pago += item['valor_pago'] or 0

        total_a_pagar = total_fornecedores - total_pago

        # Calcular totais de investimentos
        totais_invest = calcular_totais_investimentos()

        # Saldo disponível (caixa + conta_bancaria - total a pagar - total a devolver)
        saldo_disponivel = total_caixa + total_conta_bancaria - \
            total_a_pagar - totais_invest['total_a_devolver']

        return {
            'total_caixa': total_caixa,
            'total_conta_bancaria': total_conta_bancaria,
            'total_fornecedores': total_fornecedores,
            'total_pago': total_pago,
            'total_a_pagar': total_a_pagar,
            'saldo_disponivel': saldo_disponivel,
            'total_investido': totais_invest['total_investido'],
            'total_devolvido': totais_invest['total_devolvido'],
            'total_a_devolver': totais_invest['total_a_devolver']
        }

    except Exception as e:
        st.error(f"Erro ao calcular totais: {e}")
        return {
            'total_caixa': 0,
            'total_conta_bancaria': 0,
            'total_fornecedores': 0,
            'total_pago': 0,
            'total_a_pagar': 0,
            'saldo_disponivel': 0,
            'total_investido': 0,
            'total_devolvido': 0,
            'total_a_devolver': 0
        }


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
            response = supabase.table('caixa').select('*').eq('data', data_hoje).eq(
                'nome_funcionario', nome_func).is_('hora_fechamento', None).execute()
            caixa_aberto = response.data

            if not caixa_aberto:
                if st.button("🟢 Abrir Caixa", type="primary", key="abrir_caixa"):
                    if nome_func:
                        hora_abertura = datetime.now().time().strftime("%H:%M:%S")
                        supabase.table('caixa').insert({
                            'data': data_hoje,
                            'hora_abertura': hora_abertura,
                            'nome_funcionario': nome_func,
                            'dinheiro': 0.0,
                            'maquineta': 0.0,
                            'conta_bancaria': 0.0,
                            'retiradas': 0.0
                        }).execute()
                        st.success(f"✅ Caixa aberto às {hora_abertura}!")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error("❌ Digite o nome da funcionária")
            else:
                st.info("ℹ️ Você já tem um caixa aberto hoje")

        with col2:
            response = supabase.table('caixa').select(
                '*').is_('hora_fechamento', None).execute()
            caixas_abertos = response.data

            if caixas_abertos:
                st.subheader("Caixas Abertos")
                for caixa in caixas_abertos:
                    st.write(
                        f"{caixa['nome_funcionario']} - {caixa['data']} ({caixa['hora_abertura']})")
            else:
                st.info("ℹ️ Nenhum caixa aberto no momento")

        st.divider()

        if caixas_abertos:
            st.subheader("🔒 Fechamento de Caixa")

            caixa_selecionado = st.selectbox("Selecione o caixa para fechar",
                                             [f"{x['nome_funcionario']} - {x['data']}" for x in caixas_abertos],
                                             key="select_caixa")
            idx = caixas_abertos[[
                f"{x['nome_funcionario']} - {x['data']}" for x in caixas_abertos].index(caixa_selecionado)]['id']

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
                    supabase.table('caixa').update({
                        'dinheiro': dinheiro,
                        'maquineta': maquineta,
                        'retiradas': retiradas,
                        'observacoes': observacoes,
                        'hora_fechamento': hora_fechamento
                    }).eq('id', idx).execute()

                    for key in ["dinheiro_input", "maquineta_input", "retiradas_input"]:
                        if key in st.session_state:
                            st.session_state[key] = ""

                    st.success(f"✅ Caixa fechado às {hora_fechamento}!")
                    time.sleep(1)
                    st.rerun()

    else:  # Modo Editar Caixa Existente
        st.subheader("✏️ Editar Caixa Existente")

        nome_func_editar = st.text_input(
            "👤 Seu nome para buscar caixas", key="nome_editar")

        if nome_func_editar:
            response = supabase.table('caixa').select('*').eq('nome_funcionario', nome_func_editar).order(
                'data', desc=True).order('hora_abertura', desc=True).execute()
            caixas_funcionaria = response.data

            if caixas_funcionaria:
                opcoes_caixas = [
                    f"{c['data']} - {c['hora_abertura']} - R$ {c['dinheiro'] + c['maquineta']:.2f} {'(Fechado)' if c['hora_fechamento'] else '(Aberto)'}" for c in caixas_funcionaria]
                caixa_editar = st.selectbox(
                    "Selecione o caixa para editar", opcoes_caixas, key="select_editar_caixa_user")

                idx = caixas_funcionaria[opcoes_caixas.index(
                    caixa_editar)]['id']
                caixa_dados = caixas_funcionaria[opcoes_caixas.index(
                    caixa_editar)]

                st.write("---")
                st.write("### 📝 Editar Valores do Caixa")

                col_edit1, col_edit2 = st.columns(2)

                with col_edit1:
                    novo_dinheiro = st.number_input("💵 Valor em dinheiro", value=float(
                        caixa_dados['dinheiro']), format="%.2f", key="edit_dinheiro_user")
                    novo_maquineta = st.number_input("💳 Valor na maquineta", value=float(
                        caixa_dados['maquineta']), format="%.2f", key="edit_maquineta_user")
                    novas_retiradas = st.number_input(
                        "↗️ Retiradas do caixa", value=float(caixa_dados['retiradas'] or 0), format="%.2f", key="edit_retiradas_user")

                with col_edit2:
                    st.metric("💰 Total Atual", formatar_moeda(
                        caixa_dados['dinheiro'] + caixa_dados['maquineta'] - (caixa_dados['retiradas'] or 0)))
                    st.metric("💰 Total Novo", formatar_moeda(
                        novo_dinheiro + novo_maquineta - novas_retiradas))
                    st.metric("📆 Data", caixa_dados['data'])
                    st.metric("⏰ Hora Abertura", caixa_dados['hora_abertura'])
                    if caixa_dados['hora_fechamento']:
                        st.metric("🔒 Hora Fechamento",
                                  caixa_dados['hora_fechamento'])

                nova_observacao = st.text_area(
                    "📝 Observações", value=caixa_dados['observacoes'] or "", key="edit_observacao_user")

                col_btn_edit, col_btn_cancel = st.columns(2)
                with col_btn_edit:
                    if st.button("💾 Salvar Alterações", type="primary", key="save_edit_caixa"):
                        supabase.table('caixa').update({
                            'dinheiro': novo_dinheiro,
                            'maquineta': novo_maquineta,
                            'retiradas': novas_retiradas,
                            'observacoes': nova_observacao
                        }).eq('id', idx).execute()
                        st.success("✅ Caixa atualizado com sucesso!")
                        time.sleep(1)
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
                responsavel = nome_func if 'nome_func' in locals() else nome_func_editar
                supabase.table('estoque').insert({
                    'data': data_hoje,
                    'produto': produto,
                    'quantidade': quantidade,
                    'responsavel': responsavel
                }).execute()
                st.success(
                    f"✅ {quantidade} unidades de {produto} adicionadas ao estoque!")
                time.sleep(1)
                st.rerun()
            else:
                st.error("❌ Preencha todos os campos")

    with col6:
        st.info("📊 Estoque Atual")
        response = supabase.table('estoque').select(
            'produto, quantidade').execute()
        estoque_atual = response.data

        if estoque_atual:
            # Agrupar por produto
            df_estoque = pd.DataFrame(estoque_atual)
            df_agrupado = df_estoque.groupby(
                'produto')['quantidade'].sum().reset_index()

            for _, row in df_agrupado.iterrows():
                st.write(f"**{row['produto']}:** {row['quantidade']} unidades")
        else:
            st.info("ℹ️ Nenhum produto em estoque")

    st.divider()
    st.subheader("✏️ Editar Estoque")

    nome_resp_estoque = st.text_input(
        "👤 Seu nome para buscar itens do estoque", key="nome_estoque_edit")

    if nome_resp_estoque:
        response = supabase.table('estoque').select(
            '*').eq('responsavel', nome_resp_estoque).order('data', desc=True).execute()
        itens_estoque = response.data

        if itens_estoque:
            for item in itens_estoque:
                with st.expander(f"{item['data']} - {item['produto']} - {item['quantidade']} unidades"):
                    col_item1, col_item2 = st.columns([3, 1])

                    with col_item1:
                        nova_qtd = st.number_input(
                            "Nova quantidade", value=item['quantidade'], min_value=0, key=f"edit_qtd_{item['id']}")

                    with col_item2:
                        st.write("")
                        st.write("")
                        if st.button("💾 Atualizar", key=f"update_estoque_{item['id']}"):
                            supabase.table('estoque').update({
                                'quantidade': nova_qtd
                            }).eq('id', item['id']).execute()
                            st.success("✅ Quantidade atualizada!")
                            time.sleep(1)
                            st.rerun()

            if st.button("🗑️ Limpar Todos os Itens", type="secondary", key="clear_all_estoque"):
                for item in itens_estoque:
                    supabase.table('estoque').delete().eq(
                        'id', item['id']).execute()
                st.success("✅ Todos os itens do estoque foram removidos!")
                time.sleep(1)
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

        col1, col2, col3, col4, col5, col6 = st.columns(6)

        with col1:
            st.metric("💰 Total em Caixa",
                      formatar_moeda(totais['total_caixa']),
                      help="Soma de todos os caixas fechados (dinheiro + maquineta - retiradas)")

        with col2:
            st.metric("🏦 Conta Bancária",
                      formatar_moeda(totais['total_conta_bancaria']),
                      help="Valores depositados em conta bancária")

        with col3:
            st.metric("📋 Total de Fornecedores",
                      formatar_moeda(totais['total_fornecedores']),
                      help="Valor total de todos os fornecedores cadastrados")

        with col4:
            st.metric("⏳ A Pagar",
                      formatar_moeda(totais['total_a_pagar']),
                      help="Valor que ainda precisa ser pago aos fornecedores",
                      delta=formatar_moeda(-totais['total_a_pagar']))

        with col5:
            st.metric("🎯 A Devolver",
                      formatar_moeda(totais['total_a_devolver']),
                      help="Valor que precisa ser devolvido aos investidores",
                      delta=formatar_moeda(-totais['total_a_devolver']))

        with col6:
            cor_saldo = "green" if totais['saldo_disponivel'] >= 0 else "red"
            st.metric("💵 Saldo Disponível",
                      formatar_moeda(totais['saldo_disponivel']),
                      help="Total em caixa menos contas a pagar e investimentos a devolver",
                      delta=formatar_moeda(totais['saldo_disponivel']))

        st.divider()

        # --- CONTROLE DE CONTA BANCÁRIA ---
        st.subheader("🏦 Controle de Conta Bancária")

        # Seletor de data para adicionar valor bancário
        data_selecionada = st.date_input(
            "Selecione a data:",
            datetime.now().date(),
            key="data_conta_bancaria"
        )

        # Buscar caixas da data selecionada
        response = supabase.table('caixa').select(
            '*').eq('data', data_selecionada.isoformat()).execute()
        caixas_do_dia = response.data

        if caixas_do_dia:
            st.write(f"**Caixas encontrados para {data_selecionada}:**")

            # Calcular total atual da conta bancária para o dia
            total_conta_dia = sum(
                [caixa.get('conta_bancaria', 0) or 0 for caixa in caixas_do_dia])

            col_bank1, col_bank2 = st.columns(2)

            with col_bank1:
                st.metric("💰 Total em Conta (Dia)",
                          formatar_moeda(total_conta_dia))

                # Entrada para adicionar valor à conta bancária
                valor_conta = entrada_monetaria(
                    "💳 Valor a adicionar à conta bancária",
                    "valor_conta_bancaria",
                    valor_minimo=0.0
                )

                if st.button("💾 Adicionar à Conta Bancária", key="add_conta_bancaria"):
                    # Distribuir o valor igualmente entre os caixas do dia
                    valor_por_caixa = valor_conta / \
                        len(caixas_do_dia) if caixas_do_dia else 0

                    for caixa in caixas_do_dia:
                        novo_valor = (caixa.get('conta_bancaria', 0)
                                      or 0) + valor_por_caixa
                        supabase.table('caixa').update({
                            'conta_bancaria': novo_valor
                        }).eq('id', caixa['id']).execute()

                    st.success(
                        f"✅ Valor de {formatar_moeda(valor_conta)} adicionado à conta bancária!")
                    time.sleep(1)
                    st.rerun()

            with col_bank2:
                # Listar caixas do dia com seus valores bancários
                st.write("**Valores por caixa:**")
                for caixa in caixas_do_dia:
                    st.write(
                        f"{caixa['nome_funcionario']}: "
                        f"{formatar_moeda(caixa.get('conta_bancaria', 0) or 0)}"
                    )

        else:
            st.warning(f"Nenhum caixa encontrado para {data_selecionada}. "
                       f"Abra caixas primeiro para adicionar valores bancários.")

        st.divider()

        # 🎯 CONTROLE DE INVESTIMENTOS
        st.subheader("🎯 Controle de Investimentos")

        col_inv1, col_inv2 = st.columns(2)

        with col_inv1:
            st.write("### 👥 Investidores")

            # Buscar totais por investidor
            response = supabase.table('investidores').select(
                'nome, valor_investido, valor_devolvido').execute()
            investidores_data = response.data

            if investidores_data:
                # Agrupar por investidor
                df_investidores = pd.DataFrame(investidores_data)
                totais_investidores = df_investidores.groupby('nome').agg({
                    'valor_investido': 'sum',
                    'valor_devolvido': 'sum'
                }).reset_index()

                # Mostrar totais por investidor
                st.write("**📊 Totais por Investidor:**")
                for _, total in totais_investidores.iterrows():
                    nome = total['nome']
                    total_investido = total['valor_investido']
                    total_devolvido = total['valor_devolvido']
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

                # Buscar todos os investimentos
                response = supabase.table('investidores').select(
                    '*').order('nome').order('id').execute()
                investidores = response.data

                # Mostrar investimentos individuais
                st.write("**📋 Investimentos Individuais:**")
                for inv in investidores:
                    with st.expander(f"{inv['nome']} - {formatar_moeda(inv['valor_investido'])} - {formatar_moeda(inv['valor_devolvido'])} devolvido"):
                        st.write(
                            f"**Investido:** {formatar_moeda(inv['valor_investido'])}")
                        st.write(
                            f"**Devolvido:** {formatar_moeda(inv['valor_devolvido'])}")
                        st.write(
                            f"**Restante:** {formatar_moeda(inv['valor_investido'] - inv['valor_devolvido'])}")
                        st.write(
                            f"**Status:** {'✅ Devolvido' if inv['devolvido'] else '⏳ Pendente'}")

                        if inv['data_devolucao']:
                            st.write(
                                f"**Data de devolução:** {inv['data_devolucao']}")

                        if not inv['devolvido']:
                            valor_restante = inv['valor_investido'] - \
                                inv['valor_devolvido']
                            valor_devolucao = st.number_input(
                                "Valor a devolver",
                                min_value=0.0,
                                max_value=float(valor_restante),
                                value=float(valor_restante),
                                format="%.2f",
                                key=f"devolucao_{inv['id']}"
                            )

                            if st.button("💵 Registrar Devolução", key=f"devolver_{inv['id']}"):
                                novo_valor_devolvido = inv['valor_devolvido'] + \
                                    valor_devolucao
                                devolvido_completo = novo_valor_devolvido >= inv['valor_investido']

                                supabase.table('investidores').update({
                                    'valor_devolvido': novo_valor_devolvido,
                                    'devolvido': devolvido_completo,
                                    'data_devolucao': datetime.now().date().isoformat() if devolvido_completo else None
                                }).eq('id', inv['id']).execute()

                                st.success(
                                    f"✅ Devolução de {formatar_moeda(valor_devolucao)} registrada!")
                                time.sleep(1)
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

            valor_investido = entrada_monetaria(
                "Valor Investido (R$)",
                "novo_investidor_valor_input",
                valor_minimo=0.01
            )

            if st.button("💾 Adicionar Investidor", type="primary", key="adicionar_investidor"):
                if nome_investidor.strip() and valor_investido >= 0.01:
                    supabase.table('investidores').insert({
                        'nome': nome_investidor.strip(),
                        'valor_investido': valor_investido,
                        'valor_devolvido': 0,
                        'devolvido': False
                    }).execute()
                    st.success(
                        f"✅ {nome_investidor} adicionado com investimento de {formatar_moeda(valor_investido)}!")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("❌ Preencha todos os campos corretamente")

            st.divider()

            st.subheader("📋 Contas a Pagar")

            response = supabase.table('fornecedor').select(
                '*').order('pago').order('nome').execute()
            fornecedores = response.data

            if fornecedores:
                fornecedores_pagos = [f for f in fornecedores if f['pago']]
                fornecedores_pendentes = [
                    f for f in fornecedores if not f['pago']]

                if fornecedores_pendentes:
                    st.write("### ⏳ Pendentes de Pagamento")
                    for forn in fornecedores_pendentes:
                        with st.expander(f"{forn['nome']} - {formatar_moeda(forn['valor'])}", expanded=True):
                            col_f1, col_f2, col_f3 = st.columns([2, 2, 1])

                            with col_f1:
                                valor_restante = forn['valor'] - \
                                    forn['valor_pago']
                                st.write(
                                    f"**Valor total:** {formatar_moeda(forn['valor'])}")
                                st.write(
                                    f"**Já pago:** {formatar_moeda(forn['valor_pago'])}")
                                st.write(
                                    f"**Restante:** {formatar_moeda(valor_restante)}")

                            with col_f2:
                                valor_pagamento = st.number_input(
                                    "Valor a pagar agora",
                                    min_value=0.0,
                                    max_value=float(valor_restante),
                                    value=float(valor_restante),
                                    format="%.2f",
                                    key=f"pagamento_{forn['id']}"
                                )

                                if forn['data_pagamento']:
                                    st.write(
                                        f"Último pagamento: {forn['data_pagamento']}")

                            with col_f3:
                                st.write("")
                                st.write("")
                                if st.button("💵 Registrar Pagamento", key=f"pagar_{forn['id']}"):
                                    novo_valor_pago = forn['valor_pago'] + \
                                        valor_pagamento
                                    pago_completo = novo_valor_pago >= forn['valor']

                                    supabase.table('fornecedor').update({
                                        'valor_pago': novo_valor_pago,
                                        'pago': pago_completo,
                                        'data_pagamento': datetime.now().date().isoformat()
                                    }).eq('id', forn['id']).execute()

                                    st.success(
                                        f"✅ Pagamento de {formatar_moeda(valor_pagamento)} registrado!")
                                    time.sleep(1)
                                    st.rerun()

                        if forn['observacoes']:
                            st.write(f"*Observações:* {forn['observacoes']}")

                if fornecedores_pagos:
                    st.write("### ✅ Pagas")
                    for forn in fornecedores_pagos:
                        st.write(
                            f"**{forn['nome']}** - {formatar_moeda(forn['valor'])} - 💰 Pago em {forn['data_pagamento']}")
                        if forn['valor_pago'] > forn['valor']:
                            st.write(
                                f"*Valor extra pago: {formatar_moeda(forn['valor_pago'] - forn['valor'])}*")

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
                        supabase.table('fornecedor').insert({
                            'nome': nome_novo_fornecedor,
                            'valor': valor_novo_fornecedor,
                            'observacoes': observacoes_novo_fornecedor,
                            'valor_pago': 0,
                            'pago': False
                        }).execute()
                        st.success("✅ Fornecedor cadastrado!")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error("❌ Preencha os campos obrigatórios")

            st.divider()

            st.subheader("📊 Relatórios Detalhados")

            tab_caixa, tab_fornecedores, tab_investimentos, tab_fluxo, tab_estoque, tab_bancario = st.tabs(
                ["Caixa", "Fornecedores", "Investimentos", "Fluxo de Caixa", "📦 Estoque", "🏦 Bancário"])

            with tab_caixa:
                response = supabase.table('caixa').select(
                    '*').not_.is_('hora_fechamento', None).order('data', desc=True).execute()
                caixas = response.data

                if caixas:
                    df_caixa = pd.DataFrame(caixas)
                    df_caixa["Total"] = df_caixa["dinheiro"] + df_caixa["maquineta"] + \
                        df_caixa["conta_bancaria"] - df_caixa["retiradas"]

                    st.dataframe(df_caixa, use_container_width=True)

                    df_caixa["Data"] = pd.to_datetime(df_caixa["data"])
                    df_diario = df_caixa.groupby(
                        "Data")["Total"].sum().reset_index()

                    st.line_chart(df_diario, x="Data", y="Total")

                else:
                    st.info("ℹ️ Nenhum caixa fechado encontrado")

            with tab_fornecedores:
                if fornecedores:
                    df_fornecedores = pd.DataFrame(fornecedores)
                    df_fornecedores["Restante"] = df_fornecedores["valor"] - \
                        df_fornecedores["valor_pago"]

                    st.dataframe(df_fornecedores, use_container_width=True)

                    status_count = df_fornecedores["pago"].value_counts()
                    st.bar_chart(status_count)

                else:
                    st.info("ℹ️ Nenhum fornecedor cadastrado")

            with tab_investimentos:
                st.write("### 📊 Relatório de Investimentos")

                if investidores_data:
                    df_investidores = pd.DataFrame(investidores_data)
                    df_investidores["Restante"] = df_investidores["valor_investido"] - \
                        df_investidores["valor_devolvido"]
                    df_investidores["% Devolvido"] = (
                        df_investidores["valor_devolvido"] / df_investidores["valor_investido"]) * 100

                    st.dataframe(df_investidores, use_container_width=True)

                    # Gráfico de barras para status de devolução
                    status_devolucao = df_investidores["devolvido"].value_counts(
                    )
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

                col_res1, col_res2, col_res3, col_res4, col_res5 = st.columns(
                    5)

                with col_res1:
                    st.metric("Entradas Caixa", formatar_moeda(
                        totais['total_caixa']))

                with col_res2:
                    st.metric("🏦 Conta Bancária", formatar_moeda(
                        totais['total_conta_bancaria']))

                with col_res3:
                    st.metric("Saídas", formatar_moeda(
                        totais['total_pago'] + totais['total_devolvido']))

                with col_res4:
                    st.metric("Obrigações Pendentes",
                              formatar_moeda(totais['total_a_pagar'] + totais['total_a_devolver']))

                with col_res5:
                    st.metric("Saldo Total", formatar_moeda(
                        totais['saldo_disponivel']))

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

                response = supabase.table('estoque').select('data').execute()
                datas_estoque = list(set([d['data'] for d in response.data]))
                datas_estoque.sort(reverse=True)

                if datas_estoque:
                    data_selecionada = st.selectbox(
                        "📅 Selecione a data para visualizar o estoque:",
                        datas_estoque,
                        key="select_data_estoque"
                    )

                    response = supabase.table('estoque').select(
                        '*').eq('data', data_selecionada).execute()
                    itens_data = response.data

                    if itens_data:
                        st.write(f"### 📋 Estoque em {data_selecionada}")

                        df_estoque = pd.DataFrame(itens_data)

                        df_agrupado = df_estoque.groupby(
                            "produto")["quantidade"].sum().reset_index()
                        df_agrupado["responsavel"] = "Vários"

                        col_est1, col_est2 = st.columns(2)

                        with col_est1:
                            st.write("**📊 Resumo por Produto:**")
                            st.dataframe(df_agrupado, use_container_width=True)

                        with col_est2:
                            st.write("**📝 Detalhes por Responsável:**")
                            st.dataframe(
                                df_estoque[['produto', 'quantidade', 'responsavel']], use_container_width=True)

                        total_itens = df_estoque["quantidade"].sum()
                        total_produtos = len(df_agrupado)
                        total_responsaveis = df_estoque["responsavel"].nunique(
                        )

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

                    response = supabase.table('estoque').select(
                        'data, produto, quantidade').execute()
                    evolucao_estoque = response.data

                    if evolucao_estoque:
                        df_evolucao = pd.DataFrame(evolucao_estoque)

                        df_pivot = df_evolucao.pivot_table(
                            index="data",
                            columns="produto",
                            values="quantidade",
                            fill_value=0
                        ).reset_index()

                        st.line_chart(df_pivot.set_index("data"))

                    else:
                        st.info("ℹ️ Nenhum registro de estoque encontrado")

            with tab_bancario:
                st.subheader("📊 Relatório de Conta Bancária")

                # Seletor de período para relatório
                col_periodo1, col_periodo2 = st.columns(2)
                with col_periodo1:
                    data_inicio = st.date_input("Data início:", datetime.now(
                    ).date().replace(day=1), key="data_inicio_bancario")
                with col_periodo2:
                    data_fim = st.date_input(
                        "Data fim:", datetime.now().date(), key="data_fim_bancario")

                if st.button("📈 Gerar Relatório Bancário", key="btn_relatorio_bancario"):
                    # Buscar dados do período
                    response = supabase.table('caixa').select(
                        '*').gte('data', data_inicio.isoformat()).lte('data', data_fim.isoformat()).execute()
                    caixas_periodo = response.data

                    if caixas_periodo:
                        # Processar dados para o relatório
                        df_bancario = pd.DataFrame(caixas_periodo)
                        df_bancario['data'] = pd.to_datetime(
                            df_bancario['data'])

                        # Agrupar por data
                        df_agrupado = df_bancario.groupby('data').agg({
                            'conta_bancaria': 'sum',
                            'dinheiro': 'sum',
                            'maquineta': 'sum',
                            'retiradas': 'sum'
                        }).reset_index()

                        # Calcular totais
                        total_bancario = df_agrupado['conta_bancaria'].sum()
                        total_dinheiro = df_agrupado['dinheiro'].sum()
                        total_maquineta = df_agrupado['maquineta'].sum()
                        total_retiradas = df_agrupado['retiradas'].sum()
                        total_liquido = total_bancario + total_dinheiro + \
                            total_maquineta - total_retiradas

                        # Exibir métricas
                        col_metric1, col_metric2, col_metric3, col_metric4 = st.columns(
                            4)
                        with col_metric1:
                            st.metric("🏦 Total Bancário",
                                      formatar_moeda(total_bancario))
                        with col_metric2:
                            st.metric("💵 Total Dinheiro",
                                      formatar_moeda(total_dinheiro))
                        with col_metric3:
                            st.metric("💳 Total Maquineta",
                                      formatar_moeda(total_maquineta))
                        with col_metric4:
                            st.metric("💰 Total Líquido",
                                      formatar_moeda(total_liquido))

                        # Gráfico de evolução
                        st.line_chart(df_agrupado.set_index(
                            'data')['conta_bancaria'])

                        # Tabela detalhada
                        st.dataframe(df_agrupado)
                    else:
                        st.info(
                            "Nenhum dado encontrado para o período selecionado.")

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
