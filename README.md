# 💰 Sistema CIS - Gestão Completa para Eventos

[![Python](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://www.python.org/)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.28+-red.svg)](https://streamlit.io/)
[![SQLite](https://img.shields.io/badge/SQLite-3.40+-green.svg)](https://sqlite.org/)
[![License](https://img.shields.io/badge/Licença-MIT-yellow.svg)](LICENSE)
[![Status](https://img.shields.io/badge/Status-Production%20Ready-brightgreen.svg)]()
[![Code Style](https://img.shields.io/badge/Code%20Style-PEP8-black.svg)](https://pep8.org/)

Sistema completo de gestão financeira e operacional para eventos, com controle de caixa, estoque, fornecedores e relatórios administrativos em tempo real.

![Dashboard Preview](https://via.placeholder.com/800x400/0088cc/ffffff?text=Sistema+CIS+-+Dashboard+Administrativo)

---

## ✨ Funcionalidades Principais

### 🏦 Gestão Financeira
- **Controle de Caixa Multi-usuário**: Abertura/fechamento com horário registrado  
- **Pagamentos Múltiplos**: Dinheiro, maquineta, PIX e controle de retiradas  
- **Conciliação Bancária**: Registro e acompanhamento de transações  

### 📦 Controle de Estoque
- **Gestão por Produto e Lote**: Controle individualizado com validade  
- **Inventário em Tempo Real**: Movimentações atualizadas instantaneamente  
- **Relatórios de Consumo**: Análise de vendas e perdas  

### 👥 Área Administrativa
- **Dashboard Interativo**: Métricas financeiras em tempo real  
- **Gestão de Fornecedores**: Contas a pagar com histórico de pagamentos  
- **Controle de Acesso**: Multi-níveis de permissão por usuário  

### 📊 Business Intelligence
- **Relatórios Personalizáveis**: Exportação em PDF, Excel e CSV  
- **Análise de Rentabilidade**: Margem de lucro por produto/evento  
- **Projeções Financeiras**: Previsão de fluxo de caixa  

---

## 🛠️ Tecnologias Utilizadas

| Tecnologia | Versão | Finalidade |
|------------|---------|------------|
| **Python** | 3.12+ | Lógica de negócio e backend |
| **Streamlit** | 1.28+ | Interface web responsiva |
| **SQLite** | 3.40+ | Banco de dados embarcado |
| **Pandas** | 2.0+ | Análise e processamento de dados |
| **Plotly** | 5.15+ | Gráficos interativos e dashboards |

---

## 📦 Estrutura do Projeto

```text
Sistema-CIS/
├── src/
│   ├── sistema_caixa.py    # Aplicação principal
│   ├── database/           # Gerenciamento do banco
│   ├── utils/              # Funções utilitárias
│   └── components/         # Componentes da interface
├── docs/
│   ├── images/             # Screenshots e assets
│   ├── manual.md           # Manual do usuário
│   └── api.md              # Documentação da API
├── tests/                  # Testes automatizados
├── requirements.txt        # Dependências do projeto
└── README.md               # Este arquivo
