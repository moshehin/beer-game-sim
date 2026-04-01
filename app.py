import streamlit as st
import pandas as pd
import time
import random
from supabase import create_client

# 1. DATABASE CONNECTION
URL = st.secrets["SUPABASE_URL"]
KEY = st.secrets["SUPABASE_KEY"]
supabase = create_client(URL, KEY)

# 2. THE MATH ENGINE (2-Week Lead Time + Auto-Demand Shock)
def process_team_advance(team_name, week, forced=False):
    res = supabase.table("beer_game").select("*").eq("team", team_name).eq("week", week).execute()
    players = {p['role']: p for p in res.data}
    submitted_roles = [p['role'] for p in res.data if p['order_placed'] is not None]
    
    if not forced and len(submitted_roles) < 4:
        return 

    # Demand Logic: Week 5 Shock or Manual Setting
    if week >= 5:
        cust_demand = 8
        supabase.table("game_settings").update({"current_demand": 8}).eq("id", 1).execute()
    else:
        settings = supabase.table("game_settings").select("current_demand").eq("id", 1).single().execute()
        cust_demand = settings.data['current_demand']

    roles = ['Retailer', 'Wholesaler', 'Distributor', 'Manufacturer']
    current_orders = {r: (players[r]['order_placed'] if players[r]['order_placed'] is not None else 4) for r in roles}

    for i, role in enumerate(roles):
        p = players[role]
        demand_val = cust_demand if i == 0 else current_orders[roles[i-1]]
        total_needed = demand_val + p['backlog']
        shipped = min(p['inventory'], total_needed)
        new_backlog = total_needed - shipped
        
        # 2-WEEK LEAD TIME
        prev_res = supabase.table("beer_game").select("order_placed").eq("team", team_name).eq("role", role).eq("week", week - 1).execute()
        incoming = prev_res.data[0]['order_placed'] if prev_res.data and prev_res.data[0]['order_placed'] is not None else 4
        
        new_inv = (p['inventory'] - shipped) + incoming
        weekly_cost = (new_inv * 0.5) + (new_backlog * 1.0)
        
        supabase.table("beer_game").insert({
            "team": team_name, "role": role, "week": week + 1,
            "inventory": new_inv, "backlog": new_backlog,
            "total_cost": p['total_cost'] + weekly_cost,
            "order_placed": None,
            "player_name": p.get('player_name'),
            "last_shipped": shipped,
            "last_demand": demand_val,
            "incoming_delivery": incoming
        }).execute()

# 3. UI THEME & LIGHT MODE CSS
st.set_page_config(page_title="Operations Club: Beer Game", layout="centered", initial_sidebar_state="collapsed")
st.markdown("""
    <style>
    .stApp { background-color: #fcfcfc; color: #333; }
    [data-testid='stSidebar'] {display: none;} 
    .stMetric {
        background-color: #ffffff; 
        border-radius: 12px; 
        padding: 20px; 
        border-left: 6px solid #0056b3;
        box-shadow: 0 4px 6px rgba(0,0,0,0.05);
    }
    .cost-normal { color: #2ecc71; font-weight: bold; font-size: 1.1rem; }
    .cost-high { color: #e74c3c; font-weight: bold; font-size: 1.1rem; }
    h1, h2, h3 { color: #2c3e50 !important; }
    </style>
    """, unsafe_allow_html=True)

if 'page' not in st.session_state: st.session_state.page = "landing"
if 'joined' not in st.session_state: st.session_state.joined = False

try:
    s_res = supabase.table("game_settings").select("*").eq("id", 1).single().execute()
    game_active = s_res.data['game_active']
    market_demand = s_res.data['current_demand']
except:
