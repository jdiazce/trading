import streamlit as st
import yfinance as yf
import pandas as pd
import db_utils

st.set_page_config(page_title="Balleneros, torneos internos", layout="wide")

if "user" not in st.session_state:
    st.session_state.user = None

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
                st.success("Cuenta creada. Ahora puedes iniciar sesión en la pestaña contigua.")
            else:
                st.error("El usuario ya existe.")

def show_trading():
    st.subheader("Panel de Ejecución")
    user_id = st.session_state.user["id"]
    current_balance = float(db_utils.get_user_balance(user_id))
    
    st.metric("Poder de Compra (Cash)", f"${current_balance:,.2f}")
    
    ticker = st.text_input("Ticker de la acción (ej. AAPL, MSFT, SPY)").upper()
    if ticker:
        try:
            stock = yf.Ticker(ticker)
            todays_data = stock.history(period='1d')
            if todays_data.empty:
                st.error("Ticker no encontrado o sin datos recientes.")
            else:
                current_price = todays_data['Close'].iloc[0]
                st.info(f"Precio actual de mercado para {ticker}: ${current_price:,.2f}")
                
                qty = st.number_input("Cantidad de acciones a comprar", min_value=1, step=1)
                total_cost = current_price * qty
                
                st.write(f"**Costo Total de la Orden:** ${total_cost:,.2f}")
                
                if st.button("Ejecutar Orden"):
                    if total_cost > current_balance:
                        st.error("Saldo insuficiente para esta operación.")
                    else:
                        db_utils.execute_trade(user_id, ticker, qty, current_price)
                        st.success(f"Orden completada: {qty} acciones de {ticker}.")
                        st.session_state.user["cash_balance"] = current_balance - total_cost
                        st.rerun()
        except Exception:
            st.error("Error de conexión al buscar el ticker.")

def show_portfolio():
    st.subheader("Mis Posiciones")
    user_id = st.session_state.user["id"]
    transactions = db_utils.get_user_transactions(user_id)
    
    if not transactions:
        st.write("No tienes posiciones abiertas.")
        return
        
    df = pd.DataFrame(transactions)
    holdings = df.groupby('ticker')['quantity'].sum().reset_index()
    
    portfolio_data = []
    total_equity = 0
    
    for _, row in holdings.iterrows():
        t = row['ticker']
        q = row['quantity']
        try:
            current_price = yf.Ticker(t).history(period='1d')['Close'].iloc[0]
            value = q * current_price
            total_equity += value
            portfolio_data.append({"Ticker": t, "Cantidad": q, "Precio Actual": current_price, "Valor de Posición": value})
        except:
            pass
            
    if portfolio_data:
        st.dataframe(pd.DataFrame(portfolio_data).set_index("Ticker"))
        st.metric("Valor del Portafolio (Solo Acciones)", f"${total_equity:,.2f}")

def show_leaderboard():
    st.subheader("Clasificación General")
    st.write("Calculando posiciones de mercado (Mark-to-Market)...")
    
    users = db_utils.get_all_users()
    leaderboard_data = []
    
    for u in users:
        u_id = u["id"]
        cash = float(u["cash_balance"])
        transactions = db_utils.get_user_transactions(u_id)
        
        equity = 0
        if transactions:
            df = pd.DataFrame(transactions)
            holdings = df.groupby('ticker')['quantity'].sum().reset_index()
            for _, row in holdings.iterrows():
                t = row['ticker']
                q = row['quantity']
                try:
                    price = yf.Ticker(t).history(period='1d')['Close'].iloc[0]
                    equity += (q * price)
                except:
                    pass
                    
        total_nav = cash + equity
        leaderboard_data.append({
            "Usuario": u["username"], 
            "Efectivo Disponible": f"${cash:,.2f}", 
            "Valor Acciones": f"${equity:,.2f}", 
            "Capital Total": total_nav
        })
        
    lb_df = pd.DataFrame(leaderboard_data).sort_values(by="Capital Total", ascending=False).reset_index(drop=True)
    
    # Dar formato al capital total antes de mostrar la tabla
    lb_df["Capital Total"] = lb_df["Capital Total"].apply(lambda x: f"${x:,.2f}")
    st.dataframe(lb_df)

if __name__ == "__main__":
    main()