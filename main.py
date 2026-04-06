import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import db_utils

# 1. SETUP DE PÁGINA Y CSS
st.set_page_config(page_title="Balleneros--Torneo semanal 1", layout="wide")

bloomberg_css = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Fira+Code:wght@400;600&display=swap');
html, body, [class*="css"] { font-family: 'Fira Code', 'Courier New', monospace !important; }
h1, h2, h3 { color: #FF9900 !important; text-transform: uppercase; }
[data-testid="stMetricValue"] { color: #00FF00 !important; }
[data-testid="stMetricLabel"] { color: #FF9900 !important; }
.stButton>button { border: 1px solid #FF9900; color: #FF9900; background-color: transparent; }
.stButton>button:hover { background-color: #FF9900; color: #000000; }
</style>
"""
st.markdown(bloomberg_css, unsafe_allow_html=True)

if "user" not in st.session_state:
    st.session_state.user = None

# 2. MOTOR DE PRECIOS Y AUTO-LIQUIDACIÓN
@st.cache_data(ttl=60) # Caché de 60 segundos para no saturar la API
def fetch_market_prices(tickers):
    if not tickers:
        return {}
    if len(tickers) == 1:
        data = yf.Ticker(tickers[0]).history(period="1d")
        return {tickers[0]: data['Close'].iloc[-1]} if not data.empty else {}
    
    # Batch download
    data = yf.download(tickers, period="1d", group_by="ticker", threads=True)
    prices = {}
    for t in tickers:
        try:
            # yfinance returns different structures depending on ticker count
            prices[t] = float(data[t]['Close'].iloc[-1]) if isinstance(data.columns, pd.MultiIndex) else float(data['Close'].iloc[-1])
        except:
            pass
    return prices

def check_auto_liquidations(user_id):
    """Revisa si el precio de mercado ha tocado algún TP o SL y cierra la orden"""
    open_trades = db_utils.get_open_transactions(user_id)
    if not open_trades: return
    
    tickers = list(set([t['ticker'] for t in open_trades]))
    prices = fetch_market_prices(tickers)
    
    for t in open_trades:
        current_price = prices.get(t['ticker'])
        if current_price:
            tp = float(t['take_profit']) if t['take_profit'] else None
            sl = float(t['stop_loss']) if t['stop_loss'] else None
            
            trigger_price = None
            if tp and current_price >= tp: trigger_price = current_price
            elif sl and current_price <= sl: trigger_price = current_price
            
            if trigger_price:
                db_utils.close_trade(t['id'], user_id, t['quantity'], trigger_price)
                st.toast(f"🚨 LIQUIDACIÓN AUTOMÁTICA: {t['ticker']} cerrado a ${trigger_price:,.2f}")

# 3. NAVEGACIÓN Y RUTEO
def main():
    st.title("BALLENEROS--TORNEO SEMANAL 1")

    if st.session_state.user is None:
        show_login()
    else:
        # Forzar chequeo de TP/SL en segundo plano cada vez que navega
        check_auto_liquidations(st.session_state.user["id"])
        
        menu = st.sidebar.radio("NAVEGACIÓN", ["Trading", "Mi Portafolio", "Historial (Blotter)", "Leaderboard"])
        st.sidebar.write("---")
        if st.sidebar.button("Cerrar Sesión"):
            st.session_state.user = None
            st.rerun()

        if menu == "Trading": show_trading()
        elif menu == "Mi Portafolio": show_portfolio()
        elif menu == "Historial (Blotter)": show_history()
        elif menu == "Leaderboard": show_leaderboard()

# 4. MÓDULOS DE INTERFAZ
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
            if db_utils.register_user(reg_user, reg_pass): st.success("CUENTA CREADA.")
            else: st.error("EL USUARIO YA EXISTE.")

def show_trading():
    st.subheader("TERMINAL DE EJECUCIÓN")
    user_id = st.session_state.user["id"]
    current_balance = float(db_utils.get_user_balance(user_id))
    st.metric("PODER DE COMPRA (CASH)", f"${current_balance:,.2f}")
    
    with st.form(key="trading_form"):
        col1, col2 = st.columns(2)
        with col1:
            ticker_input = st.text_input("TICKER (Ej: AAPL, SQM-B.SN)").upper()
            capital = st.number_input("CAPITAL A INVERTIR ($)", min_value=1.0, step=100.0, max_value=float(current_balance) if current_balance > 0 else 1.0)
        with col2:
            tp = st.number_input("TAKE PROFIT ($) (0 = N/A)", min_value=0.0, step=1.0)
            sl = st.number_input("STOP LOSS ($) (0 = N/A)", min_value=0.0, step=1.0)
            
        submit_trade = st.form_submit_button("EJECUTAR ORDEN MKT")
        
    if submit_trade and ticker_input:
        st.info("PROCESANDO ORDEN...")
        try:
            stock = yf.Ticker(ticker_input)
            hist = stock.history(period="1d")
            
            if hist.empty:
                st.error("ACTIVO NO ENCONTRADO O SIN VOLUMEN.")
            else:
                current_price = hist['Close'].iloc[-1]
                
                if capital > current_balance:
                    st.error("SALDO INSUFICIENTE PARA CUBRIR LA ORDEN.")
                else:
                    db_utils.execute_trade(user_id, ticker_input, capital, current_price, tp, sl)
                    st.success(f"ORDEN COMPLETADA: {capital/current_price:.4f} UNIDADES DE {ticker_input} @ ${current_price:,.2f}")
                    st.session_state.user["cash_balance"] = current_balance - capital
                    st.rerun()
        except Exception:
            st.error("ERROR DE CONEXIÓN CON EL PROVEEDOR DE DATOS.")

def show_portfolio():
    st.subheader("POSICIONES ABIERTAS (UNREALIZED)")
    user_id = st.session_state.user["id"]
    transactions = db_utils.get_open_transactions(user_id)
    
    if not transactions:
        st.info("NO HAY POSICIONES ACTIVAS.")
        return
        
    tickers = list(set([t['ticker'] for t in transactions]))
    market_prices = fetch_market_prices(tickers)
    
    portfolio_data = []
    total_equity = 0
    
    for t in transactions:
        current_price = market_prices.get(t['ticker'], t['price_at_execution']) # Fallback al precio de compra si falla la red
        current_value = float(t['quantity']) * float(current_price)
        pnl_pct = ((float(current_price) - float(t['price_at_execution'])) / float(t['price_at_execution'])) * 100
        total_equity += current_value
        
        portfolio_data.append({
            "ID": t['id'],
            "TICKER": t['ticker'],
            "INVERSIÓN": f"${t['capital_invested']:,.2f}",
            "P.COMPRA": f"${t['price_at_execution']:,.2f}",
            "P.ACTUAL": f"${current_price:,.2f}",
            "RETORNO %": f"{pnl_pct:.2f}%",
            "VALOR ACTUAL": f"${current_value:,.2f}",
            "TP": float(t['take_profit']) if t['take_profit'] else 0.0,
            "SL": float(t['stop_loss']) if t['stop_loss'] else 0.0,
            "qty": t['quantity']
        })

    df = pd.DataFrame(portfolio_data)
    st.dataframe(df.drop(columns=['ID', 'qty']), use_container_width=True)
    st.metric("VALOR NETO ACCIONES (NAV)", f"${total_equity:,.2f}")
    
    st.write("---")
    st.subheader("GESTIÓN DE RIESGO / CIERRE")
    opciones = {f"{row['TICKER']} (COMPRA @ {row['P.COMPRA']})": row for row in portfolio_data}
    seleccion = st.selectbox("SELECCIONE POSICIÓN", list(opciones.keys()))
    
    if seleccion:
        pos = opciones[seleccion]
        col1, col2 = st.columns(2)
        with col1:
            with st.form("mod_form"):
                new_tp = st.number_input("NUEVO TAKE PROFIT", value=pos['TP'])
                new_sl = st.number_input("NUEVO STOP LOSS", value=pos['SL'])
                if st.form_submit_button("ACTUALIZAR LÍMITES"):
                    db_utils.update_tp_sl(pos['ID'], new_tp, new_sl)
                    st.success("PARÁMETROS ACTUALIZADOS.")
                    st.rerun()
        with col2:
            if st.button("VENDER A MERCADO (MKT)"):
                current_market_price = market_prices.get(pos['TICKER'])
                db_utils.close_trade(pos['ID'], user_id, pos['qty'], current_market_price)
                st.success(f"POSICIÓN LIQUIDADA @ ${current_market_price:,.2f}")
                st.rerun()

def show_history():
    st.subheader("HISTORIAL DE OPERACIONES (REALIZED P&L)")
    user_id = st.session_state.user["id"]
    closed_trades = db_utils.get_closed_transactions(user_id)
    
    if not closed_trades:
        st.info("AÚN NO HAS CERRADO NINGUNA OPERACIÓN.")
        return
        
    history_data = []
    total_realized = 0
    
    for t in closed_trades:
        compra = float(t['price_at_execution'])
        venta = float(t['close_price'])
        qty = float(t['quantity'])
        
        pnl_usd = (venta - compra) * qty
        pnl_pct = ((venta - compra) / compra) * 100
        total_realized += pnl_usd
        
        history_data.append({
            "FECHA APERTURA": t['timestamp'][:10],
            "TICKER": t['ticker'],
            "P.COMPRA": f"${compra:,.2f}",
            "P.VENTA": f"${venta:,.2f}",
            "P&L ($)": pnl_usd,
            "P&L (%)": f"{pnl_pct:.2f}%"
        })
        
    df = pd.DataFrame(history_data)
    # Formateo condicional para el P&L en la tabla
    df["P&L ($)"] = df["P&L ($)"].apply(lambda x: f"${x:,.2f}")
    
    st.dataframe(df, use_container_width=True)
    st.metric("REALIZED P&L TOTAL", f"${total_realized:,.2f}", delta=f"${total_realized:,.2f}")

def show_leaderboard():
    st.subheader("CLASIFICACIÓN GLOBAL")
    st.write("PROCESANDO BATCH DOWNLOAD...")
    
    users = db_utils.get_all_users()
    all_open_trades = db_utils.get_open_transactions()
    
    # Batch download de todos los activos vivos en el torneo
    all_tickers = list(set([t['ticker'] for t in all_open_trades]))
    market_prices = fetch_market_prices(all_tickers)
    
    leaderboard_data = []
    trade_performance = []
    
    for u in users:
        u_id = u["id"]
        cash = float(u["cash_balance"])
        user_trades = [t for t in all_open_trades if t['user_id'] == u_id]
        
        equity = 0
        for t in user_trades:
            price = market_prices.get(t['ticker'], t['price_at_execution'])
            equity += (float(t['quantity']) * float(price))
            
            pnl_pct = ((float(price) - float(t['price_at_execution'])) / float(t['price_at_execution'])) * 100
            trade_performance.append({
                "OPERADOR": t['profiles']['username'],
                "ACTIVO": t['ticker'],
                "RETORNO": pnl_pct,
                "INVERSIÓN": t['capital_invested']
            })
                
        total_capital = cash + equity
        rentabilidad_pct = ((total_capital - 1000000) / 1000000) * 100
        
        leaderboard_data.append({
            "OPERADOR": u["username"], 
            "MARGEN LIBRE": f"${cash:,.2f}", 
            "MARGEN EN MERCADO": f"${equity:,.2f}", 
            "CAPITAL TOTAL": total_capital,
            "RENTABILIDAD": f"{rentabilidad_pct:,.2f}%"
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