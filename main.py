import streamlit as st
import yfinance as yf
import pandas as pd
import datetime
import pytz
import db_utils

st.set_page_config(page_title="Balleneros, torneos internos", layout="wide")

if "user" not in st.session_state:
    st.session_state.user = None

def is_market_open():
    ny_tz = pytz.timezone('US/Eastern')
    ny_time = datetime.datetime.now(ny_tz)
    
    # 0 = Lunes, 4 = Viernes
    if ny_time.weekday() > 4:
        return False
        
    market_open = ny_time.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = ny_time.replace(hour=16, minute=0, second=0, microsecond=0)
    
    return market_open <= ny_time <= market_close

def main():
    st.title("Balleneros, torneos internos")

    if st.session_state.user is None:
        show_login()
    else:
        menu = st.sidebar.radio("Navegación", ["Trading", "Mi Portafolio", "Leaderboard"])
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
    st.subheader("Acceso al Torneo")
    tab1, tab2 = st.tabs(["Iniciar Sesión", "Crear Cuenta"])
    
    with tab1:
        log_user = st.text_input("Usuario", key="log_user")
        log_pass = st.text_input("Contraseña", type="password", key="log_pass")
        if st.button("Entrar"):
            user_data = db_utils.login_user(log_user, log_pass)
            if user_data:
                st.session_state.user = user_data
                st.rerun()
            else:
                st.error("Credenciales incorrectas.")
                
    with tab2:
        reg_user = st.text_input("Nuevo Usuario", key="reg_user")
        reg_pass = st.text_input("Nueva Contraseña", type="password", key="reg_pass")
        if st.button("Registrar"):
            new_user = db_utils.register_user(reg_user, reg_pass)
            if new_user:
                st.success("Cuenta creada. Ahora puedes iniciar sesión.")
            else:
                st.error("El usuario ya existe.")

def show_trading():
    st.subheader("Panel de Ejecución")
    
    if not is_market_open():
        st.warning("⚠️ El mercado está cerrado. Las operaciones solo se permiten de Lunes a Viernes entre 09:30 y 16:00 (Hora de Nueva York).")
        return

    user_id = st.session_state.user["id"]
    current_balance = float(db_utils.get_user_balance(user_id))
    st.metric("Poder de Compra (Cash)", f"${current_balance:,.2f}")
    
    with st.form(key="trading_form"):
        col1, col2 = st.columns(2)
        with col1:
            ticker = st.text_input("Ticker de la acción").upper()
            capital = st.number_input("Capital a Invertir ($)", min_value=1.0, step=100.0)
        with col2:
            tp = st.number_input("Take Profit (Precio Objetivo $)", min_value=0.0, step=1.0, help="Deja en 0 si no deseas Take Profit")
            sl = st.number_input("Stop Loss (Precio de Salida $)", min_value=0.0, step=1.0, help="Deja en 0 si no deseas Stop Loss")
            
        submit = st.form_submit_button("Lanzar Orden")
        
        if submit and ticker:
            try:
                stock = yf.Ticker(ticker)
                todays_data = stock.history(period='1d')
                if todays_data.empty:
                    st.error("Ticker no encontrado.")
                else:
                    current_price = todays_data['Close'].iloc[0]
                    
                    if capital > current_balance:
                        st.error("Saldo insuficiente.")
                    else:
                        db_utils.execute_trade(user_id, ticker, capital, current_price, tp, sl)
                        st.success(f"Orden ejecutada. {capital/current_price:.4f} acciones de {ticker} a ${current_price:,.2f}.")
                        st.session_state.user["cash_balance"] = current_balance - capital
                        st.rerun()
            except Exception:
                st.error("Error al obtener datos del mercado.")

def show_portfolio():
    st.subheader("Mis Posiciones Abiertas")
    user_id = st.session_state.user["id"]
    transactions = db_utils.get_open_transactions(user_id)
    
    if not transactions:
        st.info("No tienes posiciones abiertas.")
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
                "Ticker": t['ticker'],
                "Inversión": f"${t['capital_invested']:,.2f}",
                "P. Compra": f"${t['price_at_execution']:,.2f}",
                "P. Actual": f"${current_price:,.2f}",
                "Retorno %": f"{pnl_pct:.2f}%",
                "Valor Actual": f"${current_value:,.2f}",
                "TP": t['take_profit'],
                "SL": t['stop_loss'],
                "qty": t['quantity']
            })
        except:
            pass

    df = pd.DataFrame(portfolio_data)
    st.dataframe(df.drop(columns=['ID', 'qty']))
    st.metric("Valor del Portafolio en Acciones", f"${total_equity:,.2f}")
    
    st.write("---")
    st.subheader("Gestionar Posiciones")
    
    opciones = {f"{row['Ticker']} (Comprado a ${row['P. Compra'].replace('$', '')})": row for row in portfolio_data}
    seleccion = st.selectbox("Selecciona una posición para modificar o cerrar", list(opciones.keys()))
    
    if seleccion:
        pos = opciones[seleccion]
        col1, col2 = st.columns(2)
        
        with col1:
            st.write("### Modificar TP / SL")
            with st.form("mod_form"):
                new_tp = st.number_input("Nuevo Take Profit", value=float(pos['TP']) if pos['TP'] else 0.0)
                new_sl = st.number_input("Nuevo Stop Loss", value=float(pos['SL']) if pos['SL'] else 0.0)
                if st.form_submit_button("Actualizar Límites"):
                    db_utils.update_tp_sl(pos['ID'], new_tp, new_sl)
                    st.success("Límites actualizados.")
                    st.rerun()
                    
        with col2:
            st.write("### Cerrar Posición")
            if not is_market_open():
                st.warning("Mercado cerrado. No puedes cerrar posiciones ahora.")
            else:
                if st.button("Vender a Mercado"):
                    current_market_price = float(pos['P. Actual'].replace('$', '').replace(',', ''))
                    db_utils.close_trade(pos['ID'], user_id, pos['qty'], current_market_price)
                    st.success(f"Posición cerrada a ${current_market_price:,.2f}")
                    st.rerun()

def show_leaderboard():
    st.subheader("Clasificación General")
    st.write("Calculando posiciones en tiempo real...")
    
    users = db_utils.get_all_users()
    all_open_trades = db_utils.get_open_transactions()
    
    # 1. Calcular el Leaderboard General
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
                    "Usuario": t['profiles']['username'],
                    "Ticker": t['ticker'],
                    "Retorno %": pnl_pct,
                    "Inversión": t['capital_invested']
                })
            except:
                pass
                
        leaderboard_data.append({
            "Usuario": u["username"], 
            "Efectivo": f"${cash:,.2f}", 
            "Acciones": f"${equity:,.2f}", 
            "Capital Total": cash + equity
        })
        
    lb_df = pd.DataFrame(leaderboard_data).sort_values(by="Capital Total", ascending=False).reset_index(drop=True)
    lb_df["Capital Total"] = lb_df["Capital Total"].apply(lambda x: f"${x:,.2f}")
    st.dataframe(lb_df)
    
    st.write("---")
    
    # 2. Rankings Top 10 (Mejores y Peores)
    if trade_performance:
        perf_df = pd.DataFrame(trade_performance)
        
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("🚀 Top 10 Mejores Operaciones")
            mejores = perf_df.nlargest(10, 'Retorno %').copy()
            mejores['Retorno %'] = mejores['Retorno %'].apply(lambda x: f"{x:.2f}%")
            mejores['Inversión'] = mejores['Inversión'].apply(lambda x: f"${x:,.2f}")
            st.dataframe(mejores.reset_index(drop=True))
            
        with col2:
            st.subheader("🩸 Top 10 Peores Operaciones")
            peores = perf_df.nsmallest(10, 'Retorno %').copy()
            peores['Retorno %'] = peores['Retorno %'].apply(lambda x: f"{x:.2f}%")
            peores['Inversión'] = peores['Inversión'].apply(lambda x: f"${x:,.2f}")
            st.dataframe(peores.reset_index(drop=True))

if __name__ == "__main__":
    main()