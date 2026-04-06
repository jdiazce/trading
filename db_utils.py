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

def execute_trade(user_id, ticker, quantity, price):
    total_cost = quantity * price
    
    supabase.table("transactions").insert({
        "user_id": user_id,
        "ticker": ticker,
        "quantity": quantity,
        "price_at_execution": price
    }).execute()
    
    current_balance = get_user_balance(user_id)
    new_balance = float(current_balance) - float(total_cost)
    supabase.table("profiles").update({"cash_balance": new_balance}).eq("id", user_id).execute()
    return new_balance

def get_all_users():
    response = supabase.table("profiles").select("id, username, cash_balance").execute()
    return response.data

def get_user_transactions(user_id):
    response = supabase.table("transactions").select("*").eq("user_id", user_id).execute()
    return response.data