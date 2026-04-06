import yfinance as yf
import pandas as pd
from supabase import create_client
import os

# Configuración de credenciales de Supabase
# El script prioriza las variables de entorno de GitHub para mayor seguridad
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://pvirgxiixummtjzltneo.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "sb_publishable_j9Od8AiUfqPlDBHGVyheYg_Gx9CmPB_")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def fetch_market_prices(tickers):
    """Descarga precios en lote para optimizar tiempo y evitar bloqueos de API"""
    if not tickers:
        return {}
    try:
        # Descarga de datos del último minuto para precisión máxima
        data = yf.download(tickers, period="1d", interval="1m", group_by="ticker", threads=True, progress=False)
        prices = {}
        for t in tickers:
            try:
                if len(tickers) == 1:
                    prices[t] = float(data['Close'].iloc[-1])
                else:
                    prices[t] = float(data[t]['Close'].iloc[-1])
            except:
                pass
        return prices
    except Exception as e:
        print(f"Error al descargar precios: {e}")
        return {}

def run_liquidation_engine():
    print("Iniciando motor de liquidación...")
    
    # Obtener todas las transacciones abiertas de todos los usuarios del torneo
    response = supabase.table("transactions").select("*").eq("status", "Abierta").execute()
    open_trades = response.data
    
    if not open_trades:
        print("No hay posiciones abiertas para procesar.")
        return

    # Obtener lista de tickers únicos para una sola llamada a la API
    tickers = list(set([t['ticker'] for t in open_trades]))
    market_prices = fetch_market_prices(tickers)
    
    for t in open_trades:
        current_price = market_prices.get(t['ticker'])
        if current_price is None:
            continue
        
        tp = float(t['take_profit']) if t['take_profit'] else None
        sl = float(t['stop_loss']) if t['stop_loss'] else None
        
        trigger_price = None
        
        # Lógica de ejecución de Take Profit
        if tp and current_price >= tp:
            trigger_price = tp
            print(f"TP HIT: {t['ticker']} @ {current_price} (Target: {tp})")
            
        # Lógica de ejecución de Stop Loss
        elif sl and current_price <= sl:
            trigger_price = sl
            print(f"SL HIT: {t['ticker']} @ {current_price} (Target: {sl})")
            
        if trigger_price:
            # 1. Marcar la transacción como cerrada en la base de datos
            supabase.table("transactions").update({
                "status": "Cerrada",
                "close_price": trigger_price
            }).eq("id", t['id']).execute()
            
            # 2. Calcular capital a devolver y actualizar el saldo del usuario
            profile_res = supabase.table("profiles").select("cash_balance").eq("id", t['user_id']).execute()
            if profile_res.data:
                current_cash = float(profile_res.data[0]['cash_balance'])
                capital_returned = float(t['quantity']) * trigger_price
                new_cash = current_cash + capital_returned
                
                supabase.table("profiles").update({"cash_balance": new_cash}).eq("id", t['user_id']).execute()
                print(f"Liquidación completada para usuario {t['user_id']}. Capital devuelto: ${capital_returned:,.2f}")

if __name__ == "__main__":
    run_liquidation_engine()