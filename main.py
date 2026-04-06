import streamlit as st
import yfinance as yf
import pandas as pd
import db_utils

# Configuración de página y estética
st.set_page_config(page_title="Balleneros--Torneo semanal 1", layout="wide")

# Inyección de CSS estilo Terminal Bloomberg
bloomberg_css = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Fira+Code:wght@400;600&display=swap');

html, body, [class*="css"] {
    font-family: 'Fira Code', 'Courier New', monospace !important;
}

h1, h2, h3 {
    color: #FF9900 !important;
    text-transform: uppercase;
}

[data-testid="stMetricValue"] {
    color: #00FF00 !important;
}

[data-testid="stMetricLabel"] {
    color: #FF9900 !important;
}

.stButton>button {
    border: 1px solid #FF9900;
    color: #FF9900;
    background-color: transparent;
    font-family: 'Fira Code', monospace;
}

.stButton>button:hover {
    background-color: #FF9900;
    color: #000000;
}
</style>
"""
st.markdown(bloomberg_css, unsafe_allow_html=True)

if "user" not in st.session_state:
    st.session_state.user = None

def main():
    st.title("BALLENEROS--TORNEO SEMANAL 1")

    if st.session_state.user is None:
        show_login()
    else:
        menu = st.sidebar.radio("NAVEGACIÓN", ["Trading", "Mi Portafolio", "Leaderboard"])
        st.sidebar.write("---")
        if st.sidebar.button("Cerrar Sesión"):
            st.session_state.user = None
            st.rerun()

        if menu == "Trading":
            show_trading()
        elif menu == "Mi Portafolio":
            show_portfolio()
        elif menu == "Leaderboard":
            show_leaderboard()

def show_login():
    st.subheader("SISTEMA DE ACCESO")
    tab1, tab2 = st.tabs(["INICIAR SESIÓN", "CREAR CUENTA"])
    
    with tab1:
        log_user = st.text_input("USUARIO", key="log_user")
        log_pass = st.text_input("CONTRASEÑA", type="password", key="log_pass")
        if st.button("ENTRAR"):
            user_data = db_utils.login_user(log_user, log_pass)
            if user_data:
                st.session_state.user = user_data
                st.rerun()
            else:
                st.error("CREDENCIALES INCORRECTAS.")
                
    with tab2:
        reg_user = st.text_input("NUEVO USUARIO", key="reg_user")
        reg_pass = st.text_input("NUEVA CONTRASEÑA", type="password", key="reg_pass")
        if st.button("REGISTRAR"):
            new_user = db_utils.register_user(reg_user, reg_pass)
            if new_user:
                st.success("CUENTA CREADA. AHORA PUEDES INICIAR SESIÓN.")
            else:
                st.error("EL USUARIO YA EXISTE.")

def show_trading():
    st.subheader("TERMINAL DE EJECUCIÓN")
    
    user_id = st.session_state.user["id"]
    current_balance = float(db_utils.get_user_balance(user_id))
    st.metric("PODER DE COMPRA (CASH)", f"${current_balance:,.2f}")
    
    with st.form(key="trading_form"):
        col1, col2 = st.columns(2)
        with col1:
            ticker = st.text_input("TICKER (Ej: AAPL, SQM-B.SN, etc)").upper()
            capital = st.number_input("CAPITAL A INVERTIR ($)", min_value=1.0, step=100.0)
        with col2:
            tp = st.number_input("TAKE PROFIT ($) (0 = N/A)", min_value=0.0, step=1.0)
            sl = st.number_input("STOP LOSS ($) (0 = N/A)", min_value=0.0, step=1.0)
            
        submit = st.form_submit_button("EJECUTAR ORDEN")
        
        if submit and ticker:
            try:
                stock = yf.Ticker(ticker)
                todays_data = stock.history(period='1d')
                if todays_data.empty:
                    st.error("TICKER NO ENCONTRADO EN YFINANCE.")
                else:
                    current_price = todays_data['Close'].iloc[0]
                    
                    if capital > current_balance:
                        st.error("SALDO INSUFICIENTE PARA CUBRIR LA ORDEN.")
                    else:
                        db_utils.execute_trade(user_id, ticker, capital, current_price, tp, sl)
                        st.success(f"ORDEN COMPLETADA: {capital/current_price:.4f} UNIDADES DE {ticker} @ ${current_price:,.2f}")
                        st.session_state.user["cash_balance"] = current_balance - capital
                        st.rerun()
            except Exception:
                st.error("ERROR DE CONEXIÓN CON EL PROVEEDOR DE DATOS.")

def show_portfolio():
    st.subheader("POSICIONES ABIERTAS")
    user_id = st.session_state.user["id"]
    transactions = db_utils.get_open_transactions(user_id)
    
    if not transactions:
        st.info("NO HAY POSICIONES ACTIVAS.")
        return
        
    portfolio_data = []
    total_equity = 0
    
    for t in transactions:
        try:
            current_price = yf.Ticker(t['ticker']).history(period='1d')['Close'].iloc[0]
            current_value = t['quantity'] * current_price
            pnl_pct = ((current_price - t['price_at_execution']) / t['price_at_execution']) * 100
            total_equity += current_value
            
            portfolio_data.append({
                "ID": t['id'],
                "TICKER": t['ticker'],
                "INVERSIÓN": f"${t['capital_invested']:,.2f}",
                "P.COMPRA": f"${t['price_at_execution']:,.2f}",
                "P.ACTUAL": f"${current_price:,.2f}",
                "RETORNO": f"{pnl_pct:.2f}%",
                "VALOR ACTUAL": f"${current_value:,.2f}",
                "TP": t['take_profit'],
                "SL": t['stop_loss'],
                "qty": t['quantity']
            })
        except:
            pass

    df = pd.DataFrame(portfolio_data)
    if not df.empty:
        st.dataframe(df.drop(columns=['ID', 'qty']), use_container_width=True)
    st.metric("VALOR NETO ACCIONES (NAV)", f"${total_equity:,.2f}")
    
    st.write("---")
    st.subheader("GESTIÓN DE RIESGO / CIERRE")
    
    opciones = {f"{row['TICKER']} (COMPRA @ ${row['P.COMPRA'].replace('$', '')})": row for row in portfolio_data}
    seleccion = st.selectbox("SELECCIONE POSICIÓN", list(opciones.keys()))
    
    if seleccion:
        pos = opciones[seleccion]
        col1, col2 = st.columns(2)
        
        with col1:
            st.write("### MODIFICAR PARÁMETROS")
            with st.form("mod_form"):
                new_tp = st.number_input("NUEVO TAKE PROFIT", value=float(pos['TP']) if pos['TP'] else 0.0)
                new_sl = st.number_input("NUEVO STOP LOSS", value=float(pos['SL']) if pos['SL'] else 0.0)
                if st.form_submit_button("ACTUALIZAR ÓRDENES"):
                    db_utils.update_tp_sl(pos['ID'], new_tp, new_sl)
                    st.success("PARÁMETROS ACTUALIZADOS.")
                    st.rerun()
                    
        with col2:
            st.write("### LIQUIDAR POSICIÓN")
            if st.button("VENDER A MERCADO (MKT)"):
                current_market_price = float(pos['P.ACTUAL'].replace('$', '').replace(',', ''))
                db_utils.close_trade(pos['ID'], user_id, pos['qty'], current_market_price)
                st.success(f"POSICIÓN LIQUIDADA @ ${current_market_price:,.2f}")
                st.rerun()

def show_leaderboard():
    st.subheader("CLASIFICACIÓN GLOBAL")
    st.write("PROCESANDO MARK-TO-MARKET...")
    
    users = db_utils.get_all_users()
    all_open_trades = db_utils.get_open_transactions()
    
    leaderboard_data = []
    trade_performance = []
    
    for u in users:
        u_id = u["id"]
        cash = float(u["cash_balance"])
        user_trades = [t for t in all_open_trades if t['user_id'] == u_id]
        
        equity = 0
        for t in user_trades:
            try:
                price = yf.Ticker(t['ticker']).history(period='1d')['Close'].iloc[0]
                equity += (t['quantity'] * price)
                
                pnl_pct = ((price - t['price_at_execution']) / t['price_at_execution']) * 100
                trade_performance.append({
                    "OPERADOR": t['profiles']['username'],
                    "ACTIVO": t['ticker'],
                    "RETORNO": pnl_pct,
                    "INVERSIÓN": t['capital_invested']
                })
            except:
                pass
                
        leaderboard_data.append({
            "OPERADOR": u["username"], 
            "LIQUIDEZ": f"${cash:,.2f}", 
            "RENTA VARIABLE": f"${equity:,.2f}", 
            "CAPITAL TOTAL": cash + equity
        })
        
    lb_df = pd.DataFrame(leaderboard_data).sort_values(by="CAPITAL TOTAL", ascending=False).reset_index(drop=True)
    lb_df["CAPITAL TOTAL"] = lb_df["CAPITAL TOTAL"].apply(lambda x: f"${x:,.2f}")
    st.dataframe(lb_df, use_container_width=True)
    
    st.write("---")
    
    if trade_performance:
        perf_df = pd.DataFrame(trade_performance)
        
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("TOP 10 GANANCIAS (UNREALIZED)")
            mejores = perf_df.nlargest(10, 'RETORNO').copy()
            mejores['RETORNO'] = mejores['RETORNO'].apply(lambda x: f"{x:.2f}%")
            mejores['INVERSIÓN'] = mejores['INVERSIÓN'].apply(lambda x: f"${x:,.2f}")
            st.dataframe(mejores.reset_index(drop=True), use_container_width=True)
            
        with col2:
            st.subheader("TOP 10 PÉRDIDAS (UNREALIZED)")
            peores = perf_df.nsmallest(10, 'RETORNO').copy()
            peores['RETORNO'] = peores['RETORNO'].apply(lambda x: f"{x:.2f}%")
            peores['INVERSIÓN'] = peores['INVERSIÓN'].apply(lambda x: f"${x:,.2f}")
            st.dataframe(peores.reset_index(drop=True), use_container_width=True)

if __name__ == "__main__":
    main()