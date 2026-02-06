import streamlit as st
import pandas as pd
import time
from supabase import create_client

# 1. DATABASE CONNECTION
URL = st.secrets["SUPABASE_URL"]
KEY = st.secrets["SUPABASE_KEY"]
supabase = create_client(URL, KEY)

# 2. THE MATH ENGINE (Modified to allow partial teams)
def process_team_advance(team_name, week, forced=False):
    res = supabase.table("beer_game").select("*").eq("team", team_name).eq("week", week).execute()
    players = {p['role']: p for p in res.data}
    
    # If not forced, check if everyone who IS playing has submitted
    # If forced, we fill missing orders with 0
    submitted = [p for p in res.data if p['order_placed'] is not None]
    
    if not forced and len(submitted) < 4:
        return 

    settings = supabase.table("game_settings").select("current_demand").eq("id", 1).single().execute()
    cust_demand = settings.data['current_demand']
    
    # Roles in order: Retailer -> Wholesaler -> Distributor -> Factory
    roles = ['Retailer', 'Wholesaler', 'Distributor', 'Factory']
    
    for i, role in enumerate(roles):
        p = players[role]
        # Demand comes from downstream or external customer
        if i == 0:
            demand_val = cust_demand
        else:
            prev_role = roles[i-1]
            # Use 0 if the downstream person didn't order
            demand_val = players[prev_role]['order_placed'] if players[prev_role]['order_placed'] is not None else 0
            
        demand = demand_val + p['backlog']
        shipped = min(p['inventory'], demand)
        new_backlog = demand - shipped
        new_inv = (p['inventory'] - shipped) + 4 
        weekly_cost = (new_inv * 0.5) + (new_backlog * 1.0)
        
        supabase.table("beer_game").insert({
            "team": team_name, "role": role, "week": week + 1,
            "inventory": new_inv, "backlog": new_backlog,
            "total_cost": p['total_cost'] + weekly_cost,
            "order_placed": None
        }).execute()

# 3. INTERFACE
st.set_page_config(page_title="Beer Game 2026", layout="wide")
view_mode = st.sidebar.radio("Navigation", ["Student Portal", "Instructor Dashboard"])

# Fetch Global Game State
game_status = supabase.table("game_settings").select("game_active").eq("id", 1).single().execute().data['game_active']

if view_mode == "Student Portal":
    if not game_status:
        st.title("⏳ Waiting Room")
        st.info("The game has not started yet. Please wait for the instructor to initialize the session.")
        if st.button("Refresh"): st.rerun()
    else:
        # --- (Existing Student Logic: Team/Role Selection and Order Input) ---
        team = st.sidebar.selectbox("Team", ["A", "B", "C"])
        role = st.sidebar.selectbox("Role", ["Retailer", "Wholesaler", "Distributor", "Factory"])
        res = supabase.table("beer_game").select("*").eq("team", team).eq("role", role).order("week", desc=True).limit(1).execute()
        
        if res.data:
            data = res.data[0]
            if data['order_placed'] is not None:
                st.success(f"Week {data['week']} Submitted! Waiting for next week...")
                time.sleep(5)
                st.rerun()
            else:
                st.header(f"Team {team} - {role} (Week {data['week']})")
                order = st.number_input("Order Quantity", min_value=0, step=1)
                if st.button("Submit Order"):
                    supabase.table("beer_game").update({"order_placed": order}).eq("id", data['id']).execute()
                    process_team_advance(team, data['week'])
                    st.rerun()

else:
    st.title("📊 Instructor Control Panel")
    
    # START/STOP TOGGLE
    if not game_status:
        if st.button("🚀 START GAME (Open Waiting Room)", type="primary"):
            supabase.table("game_settings").update({"game_active": True}).eq("id", 1).execute()
            st.rerun()
    else:
        if st.button("🛑 STOP GAME (Close Access)", type="secondary"):
            supabase.table("game_settings").update({"game_active": False}).eq("id", 1).execute()
            st.rerun()

    st.divider()
    
    # FORCE PROGRESSION (If players are missing)
    st.subheader("Manual Progression")
    col1, col2, col3 = st.columns(3)
    for i, t in enumerate(["A", "B", "C"]):
        with [col1, col2, col3][i]:
            # Get current week for the team
            curr = supabase.table("beer_game").select("week").eq("team", t).order("week", desc=True).limit(1).execute().data[0]['week']
            if st.button(f"Force Team {t} to Week {curr + 1}"):
                process_team_advance(t, curr, forced=True)
                st.success(f"Team {t} advanced!")

    # ... (Include your existing Demand Sliders and Graphs here) ...
