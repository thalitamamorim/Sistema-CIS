import streamlit as st
from supabase import create_client, Client
from datetime import datetime
from zoneinfo import ZoneInfo
import pandas as pd
import re
import time
import io

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

# --- Funções de horário de Brasília ---


def obter_horario_brasilia():
    """Retorna o horário atual no fuso de Brasília"""
    return datetime.now(ZoneInfo("America/Sao_Paulo"))


def formatar_hora_brasilia(dt=None):
    """Formata datetime para string no formato HH:MM:SS"""
    if dt is None:
        dt = obter_horario_brasilia()
    return dt.strftime("%H:%M:%S")

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
        return supabase.table(tabela).select("*").order(ordenar_por, ascending=ascendente).execute()
    except Exception as e:
        st.error(f"Erro ao buscar dados: {e}")
        return None

# --- FUNÇÕES DE RASTREAMENTO DE PAGAMENTOS ---


def registrar_pagamento_fornecedor(fornecedor_id, valor_pago, origem_pagamento, observacao=None):
    """Registra pagamento de fornecedor com origem do dinheiro"""
    try:
        response = supabase.table('fornecedor').select(
            '*').eq('id', fornecedor_id).execute()
        fornecedor = response.data[0] if response.data else None

        if not fornecedor:
            st.error("Fornecedor não encontrado!")
            return False

        novo_valor_pago = (fornecedor['valor_pago'] or 0) + valor_pago
        pago_completo = novo_valor_pago >= fornecedor['valor']

        historico_pagamento = {
            'fornecedor_id': fornecedor_id,
            'valor_pago': valor_pago,
            'origem_pagamento': origem_pagamento,
            'data_pagamento': obter_horario_brasilia().date().isoformat(),
            'observacao': observacao
        }

        supabase.table('historico_pagamentos').insert(
            historico_pagamento).execute()

        supabase.table('fornecedor').update({
            'valor_pago': novo_valor_pago,
            'pago': pago_completo,
            'data_pagamento': obter_horario_brasilia().date().isoformat() if pago_completo else fornecedor['data_pagamento']
        }).eq('id', fornecedor_id).execute()

        return True

    except Exception as e:
        st.error(f"Erro ao registrar pagamento: {e}")
        return False


def obter_historico_pagamentos(fornecedor_id):
    """Obtém histórico de pagamentos de um fornecedor"""
    try:
        response = supabase.table('historico_pagamentos').select(
            '*').eq('fornecedor_id', fornecedor_id).order('data_pagamento', desc=True).execute()
        return response.data
    except Exception as e:
        st.error(f"Erro ao buscar histórico: {e}")
        return []

# --- FUNÇÕES DE ESTOQUE POR CAIXA ---


def buscar_estoque_por_caixa(caixa_id):
    """Busca itens de estoque relacionados a um caixa específico"""
    try:
        response = supabase.table('estoque').select(
            '*').eq('caixa_id', caixa_id).execute()
        return response.data
    except Exception as e:
        st.error(f"Erro ao buscar estoque do caixa: {e}")
        return []


def buscar_caixas_com_estoque():
    """Busca caixas que têm estoque relacionado"""
    try:
        response = supabase.table('caixa').select(
            '*').not_.is_('hora_fechamento', None).order('data', desc=True).execute()
        caixas = response.data

        caixas_com_estoque = []
        for caixa in caixas:
            estoque = buscar_estoque_por_caixa(caixa['id'])
            if estoque:
                caixa['itens_estoque'] = estoque
                caixa['total_itens'] = sum(item['quantidade']
                                           for item in estoque)
                caixas_com_estoque.append(caixa)

        return caixas_com_estoque
    except Exception as e:
        st.error(f"Erro ao buscar caixas com estoque: {e}")
        return []


def obter_caixa_aberto_hoje(funcionaria_nome):
    """Obtém o caixa aberto hoje para uma funcionária"""
    try:
        data_hoje = obter_horario_brasilia().date().isoformat()
        response = supabase.table('caixa').select('id').eq('data', data_hoje).eq(
            'nome_funcionario', funcionaria_nome).is_('hora_fechamento', None).execute()
        return response.data[0] if response.data else None
    except Exception as e:
        st.error(f"Erro ao buscar caixa aberto: {e}")
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
    """Calcula todos os totais financeiros considerando estornos"""
    try:
        response = supabase.table('caixa').select('*').execute()
        caixas = response.data

        total_caixa = 0
        total_conta_bancaria = 0

        for caixa in caixas:
            if caixa['hora_fechamento'] is not None:
                # Buscar estornos para este caixa
                estornos = buscar_estornos_caixa(caixa['id'])

                # Calcular totais considerando estornos
                dinheiro_corrigido = caixa['dinheiro'] or 0
                maquineta_corrigida = caixa['maquineta'] or 0
                retiradas_corrigidas = caixa['retiradas'] or 0

                for estorno in estornos:
                    if estorno['tipo_lancamento'] == 'dinheiro':
                        dinheiro_corrigido -= estorno['valor_estorno']
                    elif estorno['tipo_lancamento'] == 'maquineta':
                        maquineta_corrigida -= estorno['valor_estorno']
                    elif estorno['tipo_lancamento'] == 'retiradas':
                        retiradas_corrigidas -= estorno['valor_estorno']

                # Garantir que valores não fiquem negativos
                dinheiro_corrigido = max(0, dinheiro_corrigido)
                maquineta_corrigida = max(0, maquineta_corrigida)
                retiradas_corrigidas = max(0, retiradas_corrigidas)

                total_caixa += dinheiro_corrigido + maquineta_corrigida - retiradas_corrigidas
                total_conta_bancaria += caixa['conta_bancaria'] or 0

        response = supabase.table('fornecedor').select(
            'valor, valor_pago').execute()
        total_fornecedores = 0
        total_pago = 0
        for item in response.data:
            total_fornecedores += item['valor'] or 0
            total_pago += item['valor_pago'] or 0

        total_a_pagar = total_fornecedores - total_pago
        totais_invest = calcular_totais_investimentos()

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
            'total_caixa': 0, 'total_conta_bancaria': 0, 'total_fornecedores': 0,
            'total_pago': 0, 'total_a_pagar': 0, 'saldo_disponivel': 0,
            'total_investido': 0, 'total_devolvido': 0, 'total_a_devolver': 0
        }

# --- FUNÇÃO PARA EXPORTAR DADOS ---


def exportar_dados(tabela, formato="csv"):
    """Exporta dados para CSV ou Excel"""
    try:
        response = supabase.table(tabela).select('*').execute()
        if not response.data:
            return None

        df = pd.DataFrame(response.data)

        if formato == "csv":
            return df.to_csv(index=False, encoding='utf-8-sig')
        else:
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, index=False)
            return output.getvalue()
    except Exception as e:
        st.error(f"Erro ao exportar dados: {e}")
        return None

# --- FUNÇÕES DE ESTORNO ---


def registrar_estorno_caixa(caixa_id, valor_estorno, motivo_estorno, tipo_lancamento):
    """
    Registra um estorno para corrigir lançamento incorreto no caixa
    tipo_lancamento: 'dinheiro', 'maquineta' ou 'retiradas'
    """
    try:
        # Buscar dados atuais do caixa
        response = supabase.table('caixa').select(
            '*').eq('id', caixa_id).execute()
        caixa = response.data[0] if response.data else None

        if not caixa:
            return False, "Caixa não encontrado"

        # Registrar o estorno
        dados_estorno = {
            'caixa_id': caixa_id,
            'valor_estorno': valor_estorno,
            'tipo_lancamento': tipo_lancamento,
            'motivo': motivo_estorno,
            'data_estorno': obter_horario_brasilia().date().isoformat(),
            'hora_estorno': formatar_hora_brasilia()
        }

        supabase.table('estornos_caixa').insert(dados_estorno).execute()

        # Atualizar o caixa com o valor corrigido
        novo_valor = (caixa[tipo_lancamento] or 0) - valor_estorno
        if novo_valor < 0:
            novo_valor = 0

        supabase.table('caixa').update({
            tipo_lancamento: novo_valor
        }).eq('id', caixa_id).execute()

        return True, "Estorno registrado com sucesso"

    except Exception as e:
        return False, f"Erro ao registrar estorno: {e}"


def buscar_estornos_caixa(caixa_id=None):
    """Busca estornos registrados para um caixa específico ou todos"""
    try:
        query = supabase.table('estornos_caixa').select('*')
        if caixa_id:
            query = query.eq('caixa_id', caixa_id)

        response = query.order('data_estorno', desc=True).order(
            'hora_estorno', desc=True).execute()
        return response.data
    except Exception as e:
        st.error(f"Erro ao buscar estornos: {e}")
        return []


# --- Interface ---
st.title("💰 Sistema EventoCaixa")

# Verificar login para área admin
if "admin_logado" not in st.session_state:
    st.session_state.admin_logado = False
if "admin_usuario" not in st.session_state:
    st.session_state.admin_usuario = ""

# Abas principais: Caixa, Admin e Suporte
abas_principais = st.tabs(["📋 Caixa", "👤 Admin", "🆘 Suporte"])

# --- ABA CAIXA ---
with abas_principais[0]:
    st.header("📋 Controle de Caixa")

    modo_caixa = st.radio("Modo de operação:", [
                          "Abrir Novo Caixa", "Editar Caixa Existente"], horizontal=True, key="modo_caixa")

    if modo_caixa == "Abrir Novo Caixa":
        col1, col2 = st.columns(2)

        with col1:
            nome_func = st.text_input(
                "👤 Nome da Funcionária", key="nome_funcionaria")

            if nome_func:
                data_hoje = obter_horario_brasilia().date().isoformat()
                response = supabase.table('caixa').select('*').eq('data', data_hoje).eq(
                    'nome_funcionario', nome_func).is_('hora_fechamento', None).execute()
                caixa_aberto = response.data

                if not caixa_aberto:
                    if st.button("🟢 Abrir Caixa", type="primary", key="abrir_caixa"):
                        hora_abertura = formatar_hora_brasilia()
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
                    st.info("ℹ️ Você já tem a caixa aberto hoje")
            else:
                st.info("ℹ️ Digite seu nome para verificar caixas abertos")

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

            idx = None
            for caixa in caixas_abertos:
                if f"{caixa['nome_funcionario']} - {caixa['data']}" == caixa_selecionado:
                    idx = caixa['id']
                    break

            if idx is not None:
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
                            st.metric("↗️ Retiradas",
                                      formatar_moeda(retiradas))

                        st.metric("💰 Total Líquido", formatar_moeda(dinheiro + maquineta - retiradas),
                                  delta=formatar_moeda(dinheiro + maquineta - retiradas))
                    else:
                        st.info("ℹ️ Digite os valores para ver o resumo")

                observacoes = st.text_area("📝 Observações", key="obs_caixa")

                if st.button("🔒 Fechar Caixa", type="primary", key="fechar_caixa"):
                    if dinheiro == 0 and maquineta == 0:
                        st.warning(
                            "⚠️ Valores zerados. Confirme se está correto.")
                    else:
                        hora_fechamento = formatar_hora_brasilia()
                        supabase.table('caixa').update({
                            'dinheiro': dinheiro,
                            'maquineta': maquineta,
                            'retiradas': retiradas,
                            'observacoes': observacoes,
                            'hora_fechamento': hora_fechamento
                        }).eq('id', idx).execute()

                        # Vincular estoque ao caixa
                        data_hoje = obter_horario_brasilia().date().isoformat()
                        response_estoque = supabase.table('estoque').select(
                            '*').eq('data', data_hoje).eq('responsavel', nome_func).is_('caixa_id', None).execute()
                        itens_nao_vinculados = response_estoque.data

                        if itens_nao_vinculados:
                            for item in itens_nao_vinculados:
                                supabase.table('estoque').update(
                                    {'caixa_id': idx}).eq('id', item['id']).execute()

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
                    novas_retiradas = st.number_input("↗️ Retiradas do caixa", value=float(
                        caixa_dados['retiradas'] or 0), format="%.2f", key="edit_retiradas_user")

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
                data_hoje = obter_horario_brasilia().date().isoformat()
                responsavel = nome_func if 'nome_func' in locals(
                ) and nome_func else nome_func_editar if 'nome_func_editar' in locals() and nome_func_editar else "Não informado"

                # Buscar caixa aberto para vincular
                caixa_aberto = obter_caixa_aberto_hoje(responsavel)

                dados_estoque = {
                    'data': data_hoje,
                    'produto': produto,
                    'quantidade': quantidade,
                    'responsavel': responsavel
                }

                # Vincular ao caixa se existir
                if caixa_aberto:
                    dados_estoque['caixa_id'] = caixa_aberto['id']
                    mensagem = f"✅ {quantidade} unidades de {produto} adicionadas ao estoque (vinculado ao caixa)!"
                else:
                    mensagem = f"✅ {quantidade} unidades de {produto} adicionadas ao estoque!"

                supabase.table('estoque').insert(dados_estoque).execute()
                st.success(mensagem)
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
                            supabase.table('estoque').update(
                                {'quantidade': nova_qtd}).eq('id', item['id']).execute()
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
with abas_principais[1]:
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

        col_metric1, col_metric2, col_metric3, col_metric4 = st.columns(4)
        with col_metric1:
            st.metric("💰 Caixa", formatar_moeda(totais['total_caixa']))
            st.metric("🏦 Bancária", formatar_moeda(
                totais['total_conta_bancaria']))

        with col_metric2:
            st.metric("📋 Fornecedores", formatar_moeda(
                totais['total_fornecedores']))
            st.metric("⏳ A Pagar", formatar_moeda(
                totais['total_a_pagar']), delta=formatar_moeda(-totais['total_a_pagar']))

        with col_metric3:
            st.metric("🎯 A Devolver", formatar_moeda(
                totais['total_a_devolver']), delta=formatar_moeda(-totais['total_a_devolver']))
            st.metric("💵 Saldo", formatar_moeda(
                totais['saldo_disponivel']), delta=formatar_moeda(totais['saldo_disponivel']))

        with col_metric4:
            st.metric("📊 Total Investido", formatar_moeda(
                totais['total_investido']))
            st.metric("💵 Devolvido", formatar_moeda(totais['total_devolvido']))

        st.divider()
        # Abas para os diferentes módulos administrativos
        abas_admin = st.tabs(
            ["🏦 Bancário", "🎯 Investimentos",
                "📋 Fornecedores", "📊 Relatórios", "🔄 Estornos"]
        )

        # --- ABA BANCÁRIO ---
        with abas_admin[0]:
            st.subheader("🏦 Controle de Conta Bancária")

            data_selecionada = st.date_input(
                "Selecione a data:", datetime.now().date(), key="data_conta_bancaria")

            response = supabase.table('caixa').select(
                '*').eq('data', data_selecionada.isoformat()).execute()
            caixas_do_dia = response.data

            if caixas_do_dia:
                st.write(f"**Caixas encontrados para {data_selecionada}:**")
                total_conta_dia = sum(
                    [caixa.get('conta_bancaria', 0) or 0 for caixa in caixas_do_dia])

                col_bank1, col_bank2 = st.columns(2)

                with col_bank1:
                    st.metric("💰 Total em Conta (Dia)",
                              formatar_moeda(total_conta_dia))
                    valor_conta = entrada_monetaria(
                        "💳 Valor a adicionar à conta bancária", "valor_conta_bancaria", valor_minimo=0.0)

                    if st.button("💾 Adicionar à Conta Bancária", key="add_conta_bancaria"):
                        valor_por_caixa = valor_conta / \
                            len(caixas_do_dia) if caixas_do_dia else 0
                        for caixa in caixas_do_dia:
                            novo_valor = (
                                caixa.get('conta_bancaria', 0) or 0) + valor_por_caixa
                            supabase.table('caixa').update({'conta_bancaria': novo_valor}).eq(
                                'id', caixa['id']).execute()
                        st.success(
                            f"✅ Valor de {formatar_moeda(valor_conta)} adicionado à conta bancária!")
                        time.sleep(1)
                        st.rerun()

                with col_bank2:
                    st.write("**Valores por caixa:**")
                    for caixa in caixas_do_dia:
                        st.write(
                            f"{caixa['nome_funcionario']}: {formatar_moeda(caixa.get('conta_bancaria', 0) or 0)}")
            else:
                st.warning(
                    f"Nenhum caixa encontrado para {data_selecionada}. Abra caixas primeiro para adicionar valores bancários.")

        # --- ABA INVESTIMENTOS ---
        with abas_admin[1]:
            st.subheader("🎯 Controle de Investimentos")
            col_inv1, col_inv2 = st.columns(2)

            with col_inv1:
                st.write("### 👥 Investidores")
                response = supabase.table('investidores').select(
                    'nome, valor_investido, valor_devolvido').execute()
                investidores_data = response.data

                if investidores_data:
                    df_investidores = pd.DataFrame(investidores_data)
                    totais_investidores = df_investidores.groupby('nome').agg(
                        {'valor_investido': 'sum', 'valor_devolvido': 'sum'}).reset_index()

                    st.write("**📊 Totais por Investidor:**")
                    for _, total in totais_investidores.iterrows():
                        nome = total['nome']
                        total_investido = total['valor_investido']
                        total_devolvido = total['valor_devolvido']
                        restante = total_investido - total_devolvido

                        col_total1, col_total2, col_total3 = st.columns(3)
                        with col_total1:
                            st.metric(f"💰 {nome}", formatar_moeda(
                                total_investido))
                        with col_total2:
                            st.metric("💵 Devolvido",
                                      formatar_moeda(total_devolvido))
                        with col_total3:
                            st.metric("⏳ Restante", formatar_moeda(restante))

                    st.divider()
                    response = supabase.table('investidores').select(
                        '*').order('nome').order('id').execute()
                    investidores = response.data

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
                                valor_devolucao = st.number_input("Valor a devolver", min_value=0.0, max_value=float(
                                    valor_restante), value=float(valor_restante), format="%.2f", key=f"devolucao_{inv['id']}")

                                if st.button("💵 Registrar Devolução", key=f"devolver_{inv['id']}"):
                                    novo_valor_devolvido = inv['valor_devolvido'] + \
                                        valor_devolucao
                                    devolvido_completo = novo_valor_devolvido >= inv['valor_investido']
                                    supabase.table('investidores').update({
                                        'valor_devolvido': novo_valor_devolvido,
                                        'devolvido': devolvido_completo,
                                        'data_devolucao': obter_horario_brasilia().date().isoformat() if devolvido_completo else None
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
                    "Nome do Investidor", key="novo_investidor_nome", placeholder="Ex: João Silva")
                valor_investido = entrada_monetaria(
                    "Valor Investido (R$)", "novo_investidor_valor_input", valor_minimo=0.01)

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
        # --- ABA FORNECEDORES ---
        with abas_admin[2]:
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
                                    (forn['valor_pago'] or 0)
                                st.write(
                                    f"**Valor total:** {formatar_moeda(forn['valor'])}")
                                st.write(
                                    f"**Já pago:** {formatar_moeda(forn['valor_pago'] or 0)}")
                                st.write(
                                    f"**Restante:** {formatar_moeda(valor_restante)}")

                                historico = obter_historico_pagamentos(
                                    forn['id'])
                                if historico:
                                    st.write("**📋 Histórico de Pagamentos:**")
                                    for pagamento in historico:
                                        st.write(
                                            f"- {formatar_moeda(pagamento['valor_pago'])} ({pagamento['origem_pagamento']}) - {pagamento['data_pagamento']}")

                            with col_f2:
                                valor_pagamento = st.number_input("Valor a pagar agora", min_value=0.0, max_value=float(
                                    valor_restante), value=float(valor_restante), format="%.2f", key=f"pagamento_{forn['id']}")
                                origem_pagamento = st.selectbox("Origem do pagamento:", [
                                                                "Selecione...", "Dinheiro", "Maquineta", "Conta Bancária", "Transferência", "Outro"], key=f"origem_{forn['id']}")
                                observacao_pagamento = st.text_input(
                                    "Observação:", placeholder="Ex: Pagamento parcial", key=f"obs_{forn['id']}")

                            with col_f3:
                                st.write("")
                                st.write("")
                                if st.button("💵 Registrar Pagamento", key=f"pagar_{forn['id']}"):
                                    if origem_pagamento != "Selecione...":
                                        sucesso = registrar_pagamento_fornecedor(
                                            forn['id'], valor_pagamento, origem_pagamento, observacao_pagamento)
                                        if sucesso:
                                            st.success(
                                                f"✅ Pagamento de {formatar_moeda(valor_pagamento)} registrado via {origem_pagamento}!")
                                            time.sleep(1)
                                            st.rerun()
                                    else:
                                        st.error(
                                            "❌ Selecione a origem do pagamento")

                            if forn['observacoes']:
                                st.write(
                                    f"*Observações:* {forn['observacoes']}")

                if fornecedores_pagos:
                    st.write("### ✅ Pagas")
                    for forn in fornecedores_pagos:
                        with st.expander(f"**{forn['nome']}** - {formatar_moeda(forn['valor'])} - 💰 Pago em {forn['data_pagamento']}"):
                            historico = obter_historico_pagamentos(forn['id'])
                            if historico:
                                st.write("**📊 Detalhes dos Pagamentos:**")
                                total_pago = 0
                                for pagamento in historico:
                                    st.write(
                                        f"- {formatar_moeda(pagamento['valor_pago'])} via {pagamento['origem_pagamento']} em {pagamento['data_pagamento']}")
                                    if pagamento['observacao']:
                                        st.write(
                                            f"  *Observação:* {pagamento['observacao']}")
                                    total_pago += pagamento['valor_pago']

                                if total_pago > forn['valor']:
                                    st.write(
                                        f"*Valor extra pago: {formatar_moeda(total_pago - forn['valor'])}*")
                            else:
                                st.write(
                                    "Sem histórico de pagamentos detalhado.")
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
                pagamento_inicial = st.number_input(
                    "Pagamento Inicial (opcional)", 0.0, step=0.01, format="%.2f", key="pagamento_inicial")
                origem_pagamento_inicial = st.selectbox("Origem do Pagamento Inicial:", [
                                                        "Selecione...", "Dinheiro", "Maquineta", "Conta Bancária", "Transferência", "Outro"], key="origem_pagamento_inicial")
                obs_pagamento_inicial = st.text_input(
                    "Observação do Pagamento:", key="obs_pagamento_inicial")

            if st.button("💾 Salvar Novo Fornecedor", key="salvar_novo_fornecedor"):
                if nome_novo_fornecedor and valor_novo_fornecedor > 0:
                    response = supabase.table('fornecedor').insert({
                        'nome': nome_novo_fornecedor,
                        'valor': valor_novo_fornecedor,
                        'observacoes': observacoes_novo_fornecedor,
                        'valor_pago': pagamento_inicial if pagamento_inicial > 0 else 0,
                        'pago': pagamento_inicial >= valor_novo_fornecedor if pagamento_inicial > 0 else False
                    }).execute()

                    fornecedor_id = response.data[0]['id'] if response.data else None

                    if pagamento_inicial > 0 and origem_pagamento_inicial != "Selecione..." and fornecedor_id:
                        registrar_pagamento_fornecedor(
                            fornecedor_id, pagamento_inicial, origem_pagamento_inicial, obs_pagamento_inicial)

                    st.success("✅ Fornecedor cadastrado!")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("❌ Preencha os campos obrigatórios")
        # --- ABA RELATÓRIOS ---
        with abas_admin[3]:
            st.subheader("📊 Relatórios Detalhados")
            tab_relatorios = st.tabs(
                ["Caixa", "Fornecedores", "Investimentos", "Fluxo de Caixa", "Estoque", "Bancário"])

            # --- RELATÓRIO DE CAIXA ---
            with tab_relatorios[0]:
                st.subheader("📊 Relatório de Caixa")
                col_filtro1, col_filtro2 = st.columns(2)
                with col_filtro1:
                    data_inicio = st.date_input("Data início:", datetime.now(
                    ).date().replace(day=1), key="data_inicio_caixa")
                with col_filtro2:
                    data_fim = st.date_input(
                        "Data fim:", datetime.now().date(), key="data_fim_caixa")

                if st.button("📈 Gerar Relatório de Caixa", key="btn_relatorio_caixa"):
                    response = supabase.table('caixa').select('*').gte('data', data_inicio.isoformat()).lte(
                        'data', data_fim.isoformat()).order('data', desc=True).execute()
                    caixas = response.data

                    if caixas:
                        df_caixa = pd.DataFrame(caixas)
                        df_caixa["Total"] = df_caixa["dinheiro"] + \
                            df_caixa["maquineta"] - df_caixa["retiradas"]
                        df_caixa["Total Geral"] = df_caixa["Total"] + \
                            df_caixa["conta_bancaria"]

                        for col in ['dinheiro', 'maquineta', 'retiradas', 'conta_bancaria', 'Total', 'Total Geral']:
                            df_caixa[col] = df_caixa[col].apply(formatar_moeda)

                        st.dataframe(df_caixa[['data', 'nome_funcionario', 'hora_abertura', 'hora_fechamento', 'dinheiro', 'maquineta',
                                     'retiradas', 'conta_bancaria', 'Total', 'Total Geral']], use_container_width=True, height=400)

                        st.subheader("📈 Estatísticas")
                        col_stat1, col_stat2, col_stat3, col_stat4 = st.columns(
                            4)

                        with col_stat1:
                            total_dinheiro = sum(
                                [float(c['dinheiro'] or 0) for c in caixas])
                            st.metric("💵 Total Dinheiro",
                                      formatar_moeda(total_dinheiro))

                        with col_stat2:
                            total_maquineta = sum(
                                [float(c['maquineta'] or 0) for c in caixas])
                            st.metric("💳 Total Maquineta",
                                      formatar_moeda(total_maquineta))

                        with col_stat3:
                            total_retiradas = sum(
                                [float(c['retiradas'] or 0) for c in caixas])
                            st.metric("↗️ Total Retiradas",
                                      formatar_moeda(total_retiradas))

                        with col_stat4:
                            total_bancario = sum(
                                [float(c['conta_bancaria'] or 0) for c in caixas])
                            st.metric("🏦 Total Bancário",
                                      formatar_moeda(total_bancario))

                        df_caixa["Data"] = pd.to_datetime(df_caixa["data"])
                        df_diario = df_caixa.groupby(
                            "Data")["Total"].sum().reset_index()
                        st.line_chart(df_diario, x="Data",
                                      y="Total", height=300)
                    else:
                        st.info(
                            "ℹ️ Nenhum caixa encontrado para o período selecionado")

            # --- RELATÓRIO DE FORNECEDORES ---
            with tab_relatorios[1]:
                st.subheader("📋 Relatório de Fornecedores")
                response = supabase.table('fornecedor').select('*').execute()
                fornecedores = response.data

                if fornecedores:
                    fornecedores_completo = []
                    for forn in fornecedores:
                        historico = obter_historico_pagamentos(forn['id'])
                        forn['historico_pagamentos'] = historico
                        fornecedores_completo.append(forn)

                    df_fornecedores = pd.DataFrame(fornecedores_completo)
                    df_fornecedores["Restante"] = df_fornecedores["valor"] - \
                        df_fornecedores["valor_pago"]

                    for col in ['valor', 'valor_pago', 'Restante']:
                        df_fornecedores[col] = df_fornecedores[col].apply(
                            formatar_moeda)

                    st.dataframe(df_fornecedores[['nome', 'valor', 'valor_pago', 'Restante',
                                 'pago', 'data_pagamento']], use_container_width=True, height=400)

                    st.subheader("📊 Estatísticas de Pagamentos por Origem")
                    todas_origens = []
                    for forn in fornecedores_completo:
                        for pagamento in forn.get('historico_pagamentos', []):
                            todas_origens.append(pagamento)

                    if todas_origens:
                        df_origens = pd.DataFrame(todas_origens)
                        total_por_origem = df_origens.groupby('origem_pagamento')[
                            'valor_pago'].sum().reset_index()

                        col_orig1, col_orig2 = st.columns(2)

                        with col_orig1:
                            st.write("**💰 Total Pago por Origem:**")
                            for _, origem in total_por_origem.iterrows():
                                st.write(
                                    f"- {origem['origem_pagamento']}: {formatar_moeda(origem['valor_pago'])}")

                        with col_orig2:
                            st.bar_chart(total_por_origem.set_index(
                                'origem_pagamento'))
                    else:
                        st.info("ℹ️ Nenhum pagamento registrado com origem")
                else:
                    st.info("ℹ️ Nenhum fornecedor cadastrado")
            # --- RELATÓRIO DE INVESTIMENTOS ---
            with tab_relatorios[2]:
                st.subheader("📊 Relatório de Investimentos")
                response = supabase.table('investidores').select('*').execute()
                investidores_data = response.data

                if investidores_data:
                    df_investidores = pd.DataFrame(investidores_data)
                    df_investidores["Restante"] = df_investidores["valor_investido"] - \
                        df_investidores["valor_devolvido"]
                    df_investidores["% Devolvido"] = (
                        df_investidores["valor_devolvido"] / df_investidores["valor_investido"]) * 100

                    for col in ['valor_investido', 'valor_devolvido', 'Restante']:
                        df_investidores[col] = df_investidores[col].apply(
                            formatar_moeda)

                    df_investidores["% Devolvido"] = df_investidores["% Devolvido"].round(
                        2).astype(str) + "%"

                    st.dataframe(df_investidores,
                                 use_container_width=True, height=400)

                    st.subheader("📈 Estatísticas de Investimentos")
                    col_istat1, col_istat2, col_istat3, col_istat4 = st.columns(
                        4)

                    with col_istat1:
                        total_investido = sum(
                            [i['valor_investido'] for i in investidores_data])
                        st.metric("💰 Total Investido",
                                  formatar_moeda(total_investido))

                    with col_istat2:
                        total_devolvido = sum(
                            [i['valor_devolvido'] for i in investidores_data])
                        st.metric("💵 Devolvido",
                                  formatar_moeda(total_devolvido))

                    with col_istat3:
                        total_restante = total_investido - total_devolvido
                        st.metric("⏳ A Devolver",
                                  formatar_moeda(total_restante))

                    with col_istat4:
                        percentual = (
                            total_devolvido / total_investido * 100) if total_investido > 0 else 0
                        st.metric("📊 % Devolvido", f"{percentual:.2f}%")

         # Gráfico de barras para status de devolução
                    # Verificar se a coluna existe antes de acessar
                    if "devolvido" in df_investidores.columns:
                        status_devolucao = df_investidores["devolvido"].value_counts(
                        )
                    else:
                        st.error(
                            "Coluna 'devolvido' não encontrada. Colunas disponíveis:")
                        st.write(df_investidores.columns.tolist())
                        status_devolucao = pd.Series()  # série vazia para evitar erro

                    if not status_devolucao.empty:
                        status_devolucao.index = status_devolucao.index.map(
                            {True: 'Devolvido', False: 'Pendente'})
                        st.bar_chart(status_devolucao)
                else:
                    st.info("ℹ️ Nenhum investidor cadastrado")

            # --- RELATÓRIO DE FLUXO DE CAIXA ---
            with tab_relatorios[3]:
                st.subheader("📈 Fluxo de Caixa Consolidado")
                col_periodo1, col_periodo2 = st.columns(2)
                with col_periodo1:
                    data_inicio_fluxo = st.date_input(
                        "Data início:", datetime.now().date().replace(day=1), key="data_inicio_fluxo")
                with col_periodo2:
                    data_fim_fluxo = st.date_input(
                        "Data fim:", datetime.now().date(), key="data_fim_fluxo")

                if st.button("📊 Gerar Fluxo de Caixa", key="btn_fluxo_caixa"):
                    response_caixa = supabase.table('caixa').select(
                        '*').gte('data', data_inicio_fluxo.isoformat()).lte('data', data_fim_fluxo.isoformat()).execute()
                    caixas_periodo = response_caixa.data

                    totais = calcular_totais()

                    st.subheader("💰 Situação Financeira")
                    col_fluxo1, col_fluxo2, col_fluxo3, col_fluxo4 = st.columns(
                        4)

                    with col_fluxo1:
                        st.metric("Entradas Caixa", formatar_moeda(
                            totais['total_caixa']))
                        st.metric("🏦 Conta Bancária", formatar_moeda(
                            totais['total_conta_bancaria']))

                    with col_fluxo2:
                        st.metric("Saídas (Pagas)", formatar_moeda(
                            totais['total_pago'] + totais['total_devolvido']))
                        st.metric("Obrigações Pendentes", formatar_moeda(
                            totais['total_a_pagar'] + totais['total_a_devolver']))

                    with col_fluxo3:
                        st.metric("Saldo Disponível", formatar_moeda(
                            totais['saldo_disponivel']))
                        disponivel_apos_obrigacoes = totais['saldo_disponivel'] - \
                            totais['total_a_pagar'] - \
                            totais['total_a_devolver']
                        st.metric("Saldo Final Projetado", formatar_moeda(
                            disponivel_apos_obrigacoes), delta=formatar_moeda(disponivel_apos_obrigacoes))

                    with col_fluxo4:
                        if caixas_periodo:
                            df_fluxo = pd.DataFrame(caixas_periodo)
                            df_fluxo['data'] = pd.to_datetime(df_fluxo['data'])
                            df_fluxo['total_dia'] = df_fluxo['dinheiro'] + \
                                df_fluxo['maquineta'] - df_fluxo['retiradas']
                            fluxo_medio = df_fluxo['total_dia'].mean()
                            st.metric("📊 Fluxo Médio Diário",
                                      formatar_moeda(fluxo_medio))

                            if fluxo_medio > 0 and (totais['total_a_pagar'] + totais['total_a_devolver']) > 0:
                                dias_zerar = (
                                    totais['total_a_pagar'] + totais['total_a_devolver']) / fluxo_medio
                                st.metric(
                                    "⏳ Dias para Zerar Obrigações", f"{dias_zerar:.1f}")

                    st.subheader("🔮 Projeção Financeira")
                    col_proj1, col_proj2 = st.columns(2)

                    with col_proj1:
                        st.info(f"""
                        **Situação atual:**
                        - 💰 Disponível: {formatar_moeda(totais['saldo_disponivel'])}
                        - ⏳ A pagar (fornecedores): {formatar_moeda(totais['total_a_pagar'])}
                        - 🎯 A devolver (investidores): {formatar_moeda(totais['total_a_devolver'])}
                        - 📊 Saldo final projetado: {formatar_moeda(totais['saldo_disponivel'] - totais['total_a_pagar'] - totais['total_a_devolver'])}
                        """)

                    with col_proj2:
                        st.warning(f"""
                        **Recomendações:**
                        - {'✅ Saldo positivo' if totais['saldo_disponivel'] > 0 else '⚠️ Saldo negativo'}
                        - {'✅ Obrigações cobertas' if totais['saldo_disponivel'] >= (totais['total_a_pagar'] + totais['total_a_devolver']) else '⚠️ Obrigações não cobertas'}
                        - {'✅ Fluxo saudável' if disponivel_apos_obrigacoes > 0 else '⚠️ Atenção ao fluxo'}
                        """)

                    if caixas_periodo:
                        st.subheader("📊 Composição do Fluxo")
                        composicao_data = {
                            'Categoria': ['Dinheiro', 'Maquineta', 'Bancário', 'Retiradas'],
                            'Valor': [
                                sum([c['dinheiro'] or 0 for c in caixas_periodo]),
                                sum([c['maquineta'] or 0 for c in caixas_periodo]),
                                sum([c['conta_bancaria']
                                    or 0 for c in caixas_periodo]),
                                sum([c['retiradas'] or 0 for c in caixas_periodo]) * -1
                            ]
                        }
                        df_composicao = pd.DataFrame(composicao_data)
                        st.bar_chart(df_composicao.set_index('Categoria'))

            # --- RELATÓRIO DE ESTOQUE ---
            with tab_relatorios[4]:
                st.subheader("📦 Relatório de Estoque por Caixa")
                modo_visualizacao = st.radio("Modo de visualização:", [
                                             "Por Caixa", "Por Produto", "Por Data"], horizontal=True, key="modo_estoque")

                if modo_visualizacao == "Por Caixa":
                    st.write("### 📊 Estoque Organizado por Caixa")
                    caixas_com_estoque = buscar_caixas_com_estoque()

                    if caixas_com_estoque:
                        for caixa in caixas_com_estoque:
                            with st.expander(f"📦 Caixa {caixa['data']} - {caixa['nome_funcionario']} - {caixa['total_itens']} itens"):
                                col_caixa1, col_caixa2, col_caixa3 = st.columns([
                                                                                2, 1, 1])

                                with col_caixa1:
                                    st.write(f"**Data:** {caixa['data']}")
                                    st.write(
                                        f"**Funcionária:** {caixa['nome_funcionario']}")
                                    st.write(
                                        f"**Total de itens:** {caixa['total_itens']}")
                                    st.write(
                                        f"**Horário:** {caixa['hora_abertura']} - {caixa['hora_fechamento']}")

                                with col_caixa2:
                                    total_caixa = (
                                        caixa['dinheiro'] or 0) + (caixa['maquineta'] or 0) - (caixa['retiradas'] or 0)
                                    st.metric("💰 Total Caixa",
                                              formatar_moeda(total_caixa))

                                with col_caixa3:
                                    st.metric(
                                        "📦 Itens/Venda", f"R$ {total_caixa/caixa['total_itens']:.2f}" if caixa['total_itens'] > 0 else "N/A")

                                st.write("**📋 Itens do Estoque:**")
                                df_estoque = pd.DataFrame(
                                    caixa['itens_estoque'])
                                st.dataframe(df_estoque[['produto', 'quantidade', 'responsavel']],
                                             use_container_width=True, height=200)

                                if len(caixa['itens_estoque']) > 1:
                                    st.write("**📊 Distribuição de Produtos:**")
                                    df_produtos = pd.DataFrame(
                                        caixa['itens_estoque'])
                                    df_agrupado = df_produtos.groupby(
                                        'produto')['quantidade'].sum().reset_index()
                                    st.bar_chart(
                                        df_agrupado.set_index('produto'))
                    else:
                        st.info("ℹ️ Nenhum caixa com estoque registrado")

                elif modo_visualizacao == "Por Produto":
                    st.write("### 📊 Estoque Agrupado por Produto")
                    response = supabase.table('estoque').select(
                        'produto, quantidade, data, caixa_id').execute()
                    estoque_data = response.data

                    if estoque_data:
                        df_estoque = pd.DataFrame(estoque_data)
                        df_agrupado = df_estoque.groupby('produto').agg(
                            {'quantidade': 'sum', 'data': 'count'}).reset_index()
                        df_agrupado.columns = [
                            'Produto', 'Quantidade Total', 'Nº de Registros']

                        st.dataframe(
                            df_agrupado, use_container_width=True, height=300)
                        st.bar_chart(df_agrupado.set_index(
                            'Produto')['Quantidade Total'])
                    else:
                        st.info("ℹ️ Nenhum produto em estoque")

                else:
                    st.write("### 📊 Estoque por Data")
                    response = supabase.table('estoque').select(
                        'data, produto, quantidade').execute()
                    datas_estoque = response.data

                    if datas_estoque:
                        df_datas = pd.DataFrame(datas_estoque)
                        df_agrupado = df_datas.groupby('data').agg(
                            {'quantidade': 'sum', 'produto': 'count'}).reset_index()
                        df_agrupado.columns = [
                            'Data', 'Total Itens', 'Tipos de Produtos']

                        col_data1, col_data2 = st.columns(2)

                        with col_data1:
                            st.dataframe(
                                df_agrupado, use_container_width=True, height=300)

                        with col_data2:
                            st.line_chart(df_agrupado.set_index(
                                'Data')['Total Itens'])
                    else:
                        st.info("ℹ️ Nenhum registro de estoque por data")

                st.divider()
                st.subheader("📈 Estatísticas Gerais de Estoque")
                response = supabase.table('estoque').select(
                    'quantidade, produto, data, caixa_id').execute()
                estoque_geral = response.data

                if estoque_geral:
                    df_geral = pd.DataFrame(estoque_geral)

                    col_stat1, col_stat2, col_stat3, col_stat4 = st.columns(4)

                    with col_stat1:
                        total_itens = df_geral['quantidade'].sum()
                        st.metric("📦 Total de Itens", total_itens)

                    with col_stat2:
                        tipos_produtos = df_geral['produto'].nunique()
                        st.metric("🏷️ Tipos de Produtos", tipos_produtos)

                    with col_stat3:
                        dias_registrados = df_geral['data'].nunique()
                        st.metric("📅 Dias com Registro", dias_registrados)

                    with col_stat4:
                        caixas_com_estoque = df_geral['caixa_id'].nunique()
                        st.metric("💰 Caixas com Estoque", caixas_com_estoque)

            # --- RELATÓRIO BANCÁRIO ---
            with tab_relatorios[5]:
                st.subheader("📊 Relatório de Conta Bancária")
                col_periodo1, col_periodo2 = st.columns(2)
                with col_periodo1:
                    data_inicio = st.date_input("Data início:", datetime.now(
                    ).date().replace(day=1), key="data_inicio_bancario")
                with col_periodo2:
                    data_fim = st.date_input(
                        "Data fim:", datetime.now().date(), key="data_fim_bancario")

                if st.button("📈 Gerar Relatório Bancário", key="btn_relatorio_bancario"):
                    response = supabase.table('caixa').select(
                        '*').gte('data', data_inicio.isoformat()).lte('data', data_fim.isoformat()).execute()
                    caixas_periodo = response.data

                    if caixas_periodo:
                        df_bancario = pd.DataFrame(caixas_periodo)
                        df_bancario['data'] = pd.to_datetime(
                            df_bancario['data'])
                        df_agrupado = df_bancario.groupby('data').agg({
                            'conta_bancaria': 'sum',
                            'dinheiro': 'sum',
                            'maquineta': 'sum',
                            'retiradas': 'sum'
                        }).reset_index()

                        total_bancario = df_agrupado['conta_bancaria'].sum()
                        total_dinheiro = df_agrupado['dinheiro'].sum()
                        total_maquineta = df_agrupado['maquineta'].sum()
                        total_retiradas = df_agrupado['retiradas'].sum()
                        total_liquido = total_bancario + total_dinheiro + \
                            total_maquineta - total_retiradas

                        st.subheader("📈 Métricas do Período")
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

                        st.subheader("📊 Evolução da Conta Bancária")
                        st.line_chart(df_agrupado.set_index(
                            'data')['conta_bancaria'])

                        st.subheader("📋 Detalhes por Data")
                        for col in ['conta_bancaria', 'dinheiro', 'maquineta', 'retiradas']:
                            df_agrupado[col] = df_agrupado[col].apply(
                                formatar_moeda)

                        st.dataframe(
                            df_agrupado, use_container_width=True, height=300)

                        st.subheader("📈 Análise de Tendência")
                        if len(df_agrupado) > 1:
                            df_agrupado['variação'] = df_agrupado['conta_bancaria'].pct_change(
                            ) * 100
                            col_tend1, col_tend2 = st.columns(2)

                            with col_tend1:
                                media_diaria = df_bancario['conta_bancaria'].mean(
                                )
                                st.metric("📊 Média Diária",
                                          formatar_moeda(media_diaria))

                            with col_tend2:
                                maior_valor = df_bancario['conta_bancaria'].max(
                                )
                                st.metric("🚀 Maior Valor",
                                          formatar_moeda(maior_valor))

                            st.info("""
                            **💡 Recomendações:**
                            - Mantenha registros diários consistentes
                            - Compare com períodos anteriores
                            - Estabeleça metas de crescimento
                            """)
                        else:
                            st.info(
                                "ℹ️ Dados insuficientes para análise de tendência")
                    else:
                        st.info(
                            "Nenhum dado encontrado para o período selecionado.")
        # --- ABA ESTORNOS ---
        with abas_admin[4]:
            st.subheader("🔄 Sistema de Estornos")

            st.warning("""
            **⚠️ USE COM CAUTELA!**
            Esta funcionalidade deve ser utilizada apenas para corrigir lançamentos incorretos.
            Cada estorno fica registrado no histórico para auditoria.
            """)

            # Selecionar caixa para estorno
            response = supabase.table('caixa').select(
                '*').order('data', desc=True).order('hora_abertura', desc=True).execute()
            caixas = response.data

            if caixas:
                opcoes_caixas = [
                    f"{c['data']} - {c['nome_funcionario']} - R$ {(c['dinheiro'] or 0) + (c['maquineta'] or 0):.2f}" for c in caixas]
                caixa_selecionado = st.selectbox(
                    "Selecione o caixa para estorno:",
                    opcoes_caixas,
                    key="select_caixa_estorno"
                )

                idx = None
                for i, caixa in enumerate(caixas):
                    if f"{caixa['data']} - {caixa['nome_funcionario']} - R$ {(caixa['dinheiro'] or 0) + (caixa['maquineta'] or 0):.2f}" == caixa_selecionado:
                        idx = caixa['id']
                        caixa_dados = caixa
                        break

                if idx:
                    st.write("---")
                    st.write("### 📝 Registrar Estorno")

                    col_est1, col_est2 = st.columns(2)

                    with col_est1:
                        tipo_estorno = st.selectbox(
                            "Tipo de lançamento a estornar:",
                            ["dinheiro", "maquineta", "retiradas"],
                            key="tipo_estorno"
                        )

                        valor_atual = caixa_dados[tipo_estorno] or 0
                        st.write(
                            f"**Valor atual em {tipo_estorno}:** {formatar_moeda(valor_atual)}")

                        valor_estorno = st.number_input(
                            "Valor a estornar:",
                            min_value=0.0,
                            max_value=float(valor_atual),
                            value=0.0,
                            format="%.2f",
                            key="valor_estorno"
                        )

                    with col_est2:
                        motivo_estorno = st.text_area(
                            "Motivo do estorno:",
                            placeholder="Ex: Lançamento duplicado, valor digitado incorretamente...",
                            height=100,
                            key="motivo_estorno"
                        )

                        if valor_estorno > 0:
                            novo_valor = valor_atual - valor_estorno
                            st.metric("💰 Valor após estorno",
                                      formatar_moeda(novo_valor))
                            st.metric("📉 Valor estornado",
                                      formatar_moeda(-valor_estorno))

                    if st.button("🔄 Registrar Estorno", type="secondary", key="btn_registrar_estorno"):
                        if valor_estorno > 0 and motivo_estorno.strip():
                            sucesso, mensagem = registrar_estorno_caixa(
                                idx, valor_estorno, motivo_estorno, tipo_estorno
                            )
                            if sucesso:
                                st.success(f"✅ {mensagem}")
                                time.sleep(2)
                                st.rerun()
                            else:
                                st.error(f"❌ {mensagem}")
                        else:
                            st.error("❌ Preencha todos os campos corretamente")

                    st.write("---")
                    st.write("### 📋 Histórico de Estornos")

                    estornos = buscar_estornos_caixa(idx)
                    if estornos:
                        for estorno in estornos:
                            with st.expander(f"{estorno['data_estorno']} - {formatar_moeda(estorno['valor_estorno'])} - {estorno['tipo_lancamento']}"):
                                st.write(f"**Motivo:** {estorno['motivo']}")
                                st.write(
                                    f"**Valor:** {formatar_moeda(estorno['valor_estorno'])}")
                                st.write(
                                    f"**Tipo:** {estorno['tipo_lancamento']}")
                                st.write(
                                    f"**Data/Hora:** {estorno['data_estorno']} {estorno['hora_estorno']}")
                    else:
                        st.info("ℹ️ Nenhum estorno registrado para este caixa")

            else:
                st.info("ℹ️ Nenhum caixa encontrado para realizar estornos")

# --- ABA SUPORTE ---
with abas_principais[2]:
    st.header("🆘 Suporte e Ajuda")
    tab_suporte = st.tabs(
        ["📞 Contatos", "📚 Tutoriais", "❓ FAQ", "🐛 Reportar Bug"])

    with tab_suporte[0]:
        col_contato1, col_contato2 = st.columns(2)

        with col_contato1:
            st.subheader("📞 Contato de Suporte")
            st.info("""
            **Thalita Amorim**  
            📧 thalita.muniz.amorim@gmail.com  
            📞 (98) 98110-4216  
            🕐 Horário: 9h às 17h (Segunda a Sexta)
            """)

            if st.button("📧 Copiar Email", key="btn_email"):
                st.success("Email thalita.muniz.amorim@gmail.com copiado!")

            if st.button("📱 Copiar Telefone", key="btn_ligar"):
                st.success("Número (98) 98110-4216 copiado!")

        with col_contato2:
            st.subheader("🚨 Suporte Emergencial")
            st.warning("""
            **Para problemas urgentes durante o evento:**
            - 📞 Ligação prioritária
            - 📱 WhatsApp com resposta rápida
            - 🆘 Plantão para emergências
            - ⏰ Plantão 24h para críticas
            """)

            st.error("""
            **⛔ Problemas Críticos:**
            - Sistema fora do ar
            - Perda de dados
            - Erros graves de cálculo
            """)

    with tab_suporte[1]:
        st.subheader("📚 Tutoriais e Guias Passo a Passo")
        col_tutorial1, col_tutorial2 = st.columns(2)

        with col_tutorial1:
            with st.expander("📋 Como Abrir e Fechar Caixa", expanded=True):
                st.write("""
                **🔹 ABRIR CAIXA:**
                1. Vá para a aba 'Caixa'
                2. Digite seu nome no campo 'Nome da Funcionária'
                3. Clique em 'Abrir Caixa'
                4. O sistema registra automaticamente data e hora
                
                **🔹 FECHAR CAIXA:**
                1. Preencha os valores ao final do dia:
                   - 💵 Valor em dinheiro
                   - 💳 Valor na maquineta  
                   - ↗️ Retiradas do caixa
                2. Adicione observações se necessário
                3. Clique em 'Fechar Caixa'
                4. Confirme os valores antes de finalizar
                
                **⚠️ IMPORTANTE:** Só é possível fechar caixas abertos no mesmo dia
                """)

            with st.expander("📦 Controle de Estoque"):
                st.write("""
                **🔹 ADICIONAR PRODUTO:**
                1. Digite o nome do produto
                2. Informe la quantidade
                3. Clique em 'Adicionar ao Estoque'
                
                **🔹 EDITAR ESTOQUE:**
                1. Digite seu nome no campo 'Editar Estoque'
                2. Expanda o item desejado
                3. Ajuste a quantidade
                4. Clique em 'Atualizar'
                
                **👀 MONITORAMENTO:**
                - Visualize o estoque atual no painel direito
                - Acompanhe por responsável
                - Verifique histórico por data
                """)

        with col_tutorial2:
            with st.expander("👤 Área Administrativa"):
                st.write("""
                **🔹 ACESSO ADMIN:**
                - Login: admin
                - Senha: evento123
                
                **🔹 RELATÓRIOS COMPLETOS:**
                1. Acesse a aba 'Admin'
                2. Faça login com credenciais
                3. Navegue pelas abas de relatórios:
                   - 🏦 Bancário
                   - 🎯 Investimentos  
                   - 📋 Fornecedores
                   - 📊 Relatórios
                   - 🔄 Estornos
                
                **🔹 EXPORTAR DADOS:**
                - Use o menu lateral para exportar
                - Escolha entre CSV ou Excel
                - Selecione a tabela desejada
                """)

            with st.expander("📊 Como Gerar Relatórios"):
                st.write("""
                **🔹 RELATÓRIOS DETALHADOS:**
                1. Acesse 'Admin' → 'Relatórios'
                2. Selecione o tipo de relatório:
                   - Caixa: Controle diário de entradas/saídas
                   - Fornecedores: Contas a pagar
                   - Investimentos: Devoluções e saldos
                   - Fluxo de Caixa: Visão consolidada
                   - Estoque: Controle de produtos
                   - Bancário: Movimentação financeira
                
                **🔹 FILTROS POR PERÍODO:**
                - Selecione datas inicial e final
                - Aplique filtros específicos
                - Visualize gráficos e estatísticas
                
                **📈 DICAS:**
                - Use períodos mensais para análise
                - Compare com meses anteriores
                - Exporte dados para planilhas
                """)

    with tab_suporte[2]:
        st.subheader("❓ Perguntas Frequentes")
        faq_items = [
            {"pergunta": "Digitei um valor errado no caixa, e agora?",
                "resposta": "Use a opção 'Editar Caixa Existente' para corrigir. Selecione seu nome, escolha o caixa e ajuste os valores."},
            {"pergunta": "Registrei a quantidade errada no estoque?",
                "resposta": "Use a seção 'Editar Estoque', digite seu nome e ajuste as quantidades dos itens."},
            {"pergunta": "Posso editar caixas de outros dias?",
                "resposta": "Sim, basta selecionar a data desejada no modo 'Editar Caixa Existente'."},
            {"pergunta": "Como visualizar relatórios completos?",
                "resposta": "Acesse a área Admin → Relatórios para uma visão detalhada de todos os dados."},
            {"pergunta": "Esqueci minhas credenciais administrativas?",
                "resposta": "Entre em contato com o suporte pelo email thalita.muniz.amorim@gmail.com"},
            {"pergunta": "Como fechar o caixa corretamente?",
                "resposta": "Preencha todos os valores (dinheiro, maquineta, retiradas) e confirme antes de finalizar."},
            {"pergunta": "O que fazer se o sistema travar?",
                "resposta": "Recarregue a página e verifique se os dados foram salvos. Em caso de perda, contate o suporte."}
        ]

        for faq in faq_items:
            with st.expander(f"❔ {faq['pergunta']}"):
                st.write(f"**✅ Resposta:** {faq['resposta']}")

    with tab_suporte[3]:
        st.subheader("🐛 Reportar Problema")
        col_bug1, col_bug2 = st.columns(2)

        with col_bug1:
            st.write("**Descreva o problema detalhadamente:**")
            problema = st.text_area(
                "Descrição:", placeholder="Ex: Ao tentar editar o caixa, o sistema apresentou erro...\n\nPassos para reproduzir:\n1. ...\n2. ...\n3. ...", height=150, key="problema_desc")
            tipo_problema = st.selectbox("Tipo de problema:", [
                                         "Selecione...", "Erro no sistema", "Dúvida funcional", "Melhoria", "Outro"], key="tipo_problema")

        with col_bug2:
            st.write("**Seus dados para contato:**")
            contato_nome = st.text_input("Seu nome:", key="contato_nome")
            contato_email = st.text_input("Seu e-mail:", key="contato_email")
            contato_telefone = st.text_input(
                "Seu telefone:", key="contato_telefone")
            urgencia = st.slider("Nível de urgência:", 1, 5, 3,
                                 help="1 = Pouco urgente, 5 = Muito urgente", key="urgencia")

        if st.button("📨 Enviar Relatório de Problema", type="primary", key="btn_report_bug"):
            if problema and contato_email and tipo_problema != "Selecione...":
                st.success(
                    "✅ Relatório enviado com sucesso! Entraremos em contato em breve.")
                st.info(f"""
                **📋 Resumo do Report:**
                - **Tipo:** {tipo_problema}
                - **Urgência:** {urgencia}/5
                - **Contato:** {contato_nome} | {contato_email} | {contato_telefone}
                - **Descrição:** {problema[:100]}...
                """)
                st.session_state.problema_desc = ""
                st.session_state.contato_nome = ""
                st.session_state.contato_email = ""
                st.session_state.contato_telefone = ""
            else:
                st.error("❌ Preencha todos os campos obrigatórios.")

# --- RODAPÉ ---
st.divider()
footer_col1, footer_col2, footer_col3 = st.columns(3)

with footer_col1:
    st.caption("**Sistema EventoCaixa**")
    st.caption("Desenvolvido para gerenciamento de eventos")

with footer_col2:
    st.caption("**Suporte**")
    st.caption("📧 thalita.muniz.amorim@gmail.com")
    st.caption("📞 (98) 98110-4216")

with footer_col3:
    st.caption("**Versão**")
    st.caption("2.0 - Agosto 2025")
    st.caption("Última atualização: " +
               obter_horario_brasilia().strftime("%d/%m/%Y %H:%M"))

# --- BOTÕES DE AÇÃO RÁPIDA ---
if st.session_state.admin_logado:
    st.sidebar.write("---")
    st.sidebar.subheader("⚡ Ações Rápidas")

    if st.sidebar.button("🔄 Atualizar Dados", key="btn_refresh"):
        st.rerun()

    if st.sidebar.button("📊 Ver Dashboard", key="btn_dashboard"):
        st.success("Navegando para o Dashboard...")

    if st.sidebar.button("📋 Relatório Hoje", key="btn_report_today"):
        data_hoje = obter_horario_brasilia().date().isoformat()
        response = supabase.table('caixa').select(
            '*').eq('data', data_hoje).execute()
        caixas_hoje = response.data

        if caixas_hoje:
            total_hoje = sum([(c.get('dinheiro', 0) or 0) + (c.get('maquineta', 0)
                             or 0) - (c.get('retiradas', 0) or 0) for c in caixas_hoje])
            st.sidebar.success(f"💰 Total hoje: {formatar_moeda(total_hoje)}")
        else:
            st.sidebar.info("ℹ️ Nenhum caixa hoje")

# --- ESTILOS CSS ---
st.markdown("""
<style>
.stDataFrame {font-size: 14px;}
.stButton > button {
    border-radius: 8px; border: 1px solid #ccc; padding: 10px 20px; font-weight: 500;
}
.stButton > button:hover {border-color: #007bff; background-color: #f8f9fa;}
.stTabs [data-baseweb="tab-list"] {gap: 8px;}
.stTabs [data-baseweb="tab"] {
    height: 50px; white-space: pre-wrap; background-color: #f8f9fa;
    border-radius: 8px 8px 0px 0px; gap: 8px; padding: 10px 16px;
}
.stTabs [aria-selected="true"] {background-color: #007bff; color: white;}
[data-testid="stMetric"] {
    background-color: #f8f9fa; padding: 15px; border-radius: 10px; border: 1px solid #e9ecef;
}
[data-testid="stMetricValue"] {font-size: 1.5rem; font-weight: bold;}
[data-testid="stMetricLabel"] {font-size: 1rem; color: #6c757d;}
</style>
""", unsafe_allow_html=True)

# --- BOTÃO VOLTAR AO TOPO ---
if st.button("⬆️ Voltar ao Topo", key="btn_top"):
    st.write("""
    <script>window.scrollTo(0, 0);</script>
    """, unsafe_allow_html=True)

