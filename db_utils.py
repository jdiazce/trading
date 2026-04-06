import streamlit as st
from supabase import create_client, Client

@st.cache_resource
def init_connection():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase: Client = init_connection()

def login_user(username, password):
    response = supabase.table("profiles").select("*").eq("username", username).eq("password", password).execute()
    if len(response.data) > 0:
        return response.data[0]
    return None

def register_user(username, password):
    existing = supabase.table("profiles").select("*").eq("username", username).execute()
    if len(existing.data) > 0:
        return False
    response = supabase.table("profiles").insert({"username": username, "password": password}).execute()
    return response.data[0]

def get_user_balance(user_id):
    response = supabase.table("profiles").select("cash_balance").eq("id", user_id).execute()
    return response.data[0]["cash_balance"]

def execute_trade(user_id, ticker, capital, price, tp, sl):
    qty = capital / price
    
    supabase.table("transactions").insert({
        "user_id": user_id,
        "ticker": ticker,
        "quantity": qty,
        "price_at_execution": price,
        "capital_invested": capital,
        "take_profit": tp if tp > 0 else None,
        "stop_loss": sl if sl > 0 else None,
        "status": "Abierta"
    }).execute()
    
    current_balance = get_user_balance(user_id)
    new_balance = float(current_balance) - float(capital)
    supabase.table("profiles").update({"cash_balance": new_balance}).eq("id", user_id).execute()
    return new_balance

def close_trade(transaction_id, user_id, qty, close_price):
    capital_returned = qty * close_price
    
    # Marcar como cerrada
    supabase.table("transactions").update({
        "status": "Cerrada",
        "close_price": close_price
    }).eq("id", transaction_id).execute()
    
    # Devolver capital al balance
    current_balance = get_user_balance(user_id)
    new_balance = float(current_balance) + float(capital_returned)
    supabase.table("profiles").update({"cash_balance": new_balance}).eq("id", user_id).execute()

def update_tp_sl(transaction_id, tp, sl):
    supabase.table("transactions").update({
        "take_profit": tp if tp > 0 else None,
        "stop_loss": sl if sl > 0 else None
    }).eq("id", transaction_id).execute()

def get_all_users():
    response = supabase.table("profiles").select("id, username, cash_balance").execute()
    return response.data

def get_open_transactions(user_id=None):
    if user_id:
        response = supabase.table("transactions").select("*").eq("user_id", user_id).eq("status", "Abierta").execute()
    else:
        response = supabase.table("transactions").select("*, profiles(username)").eq("status", "Abierta").execute()
    return response.data