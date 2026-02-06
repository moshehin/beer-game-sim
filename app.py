import streamlit as st
import pandas as pd
import time
from supabase import create_client

# 1. DATABASE CONNECTION
URL = st.secrets["SUPABASE_URL"]
KEY = st.secrets["SUPABASE_KEY"]
supabase = create_client(URL, KEY)

# 2. THE MATH ENGINE (Calculates the Flow of Goods)
def process_team_advance(team_name, week, forced=False):
    res = supabase.table("beer_game").select("*").eq("team", team_name).eq("week", week).execute()
    players = {p['role']: p for p in res.data}
    submitted = [p for p in res.data if p['order_placed'] is not None]
    
    # Only advance if all 4 roles submitted OR admin forced it
    if not forced and len(submitted) < 4:
        return 

    settings = supabase.table("game_settings").select("current_demand").eq("id", 1).single().execute()
    cust_demand = settings.data['current_demand']
    
    # Role Order: Retailer -> Wholesaler -> Distributor -> Manufacturer
    roles = ['Retailer', 'Wholesaler', 'Distributor', 'Manufacturer']
    
    for i, role in enumerate(roles):
        p = players[role]
        
        # Inbound Demand Logic
        if i == 0:
            demand_val = cust_demand
        else:
            prev_role = roles[i-1]
            # Demand comes from what the person below you ordered
            demand_val = players[prev_role]['order_placed'] if players[prev_role]['order_placed'] is not None else 0
            
        total_needed = demand_val + p['backlog']
        shipped = min(p['inventory'], total_needed)
        new_backlog = total_needed - shipped
        
        # Simulating Lead Time: Incoming stock arrives from upstream
        # For simplicity in this version, we assume a constant inflow of 4 or 
        # the order placed 2 weeks ago (if you have that data)
        incoming_stock = 4 
        
        new_inv = (p['inventory'] - shipped) + incoming_stock
        weekly_cost = (new_inv * 0.5) + (new_backlog * 1.0)
        
        supabase.table("beer_game").insert({
            "team": team_name, "role": role, "week": week + 1,
            "inventory": new_inv, "backlog": new_backlog,
            "total_cost": p['total_cost'] + weekly_cost,
            "order_placed": None
        }).execute()

# 3. INTERFACE CONFIGURATION
st.set_page_config(page_title="Beer Game Sim", layout="wide")

# Fetch Game State (Start/Stop)
try:
    settings_res = supabase.table("game_settings").select("*").eq("id", 1).single().execute()
    game_active = settings_res.data['game_active']
    market_demand = settings_res.data['current_demand']
except:
    game_active = False
    market_demand = 4

view_mode = st.sidebar.radio("Navigation", ["Student Portal", "Instructor Dashboard"])

# --- STUDENT PORTAL ---
if view_mode == "Student Portal":
    if 'joined' not in st.session_state:
        st.session_state.joined = False

    # MODAL UI: Joining the Game
    if not st.session_state.joined:
        st.markdown("<br><br>", unsafe_allow_html=True)
        _, col_mid, _ = st.columns([1, 2, 1])
        with col_mid:
            with st.container(border=True):
                st.subheader("Select your role")
                st.write("Select any available role to join the game")
                t_choice = st.selectbox("Team", ["A", "B", "C"])
                r_choice = st.selectbox("Role", ["Retailer", "Wholesaler", "Distributor", "Manufacturer"])
                name = st.text_input("Type in your name or alias")
                
                if not game_active:
                    st.warning("Waiting for Instructor to start the game...")
                
                c1, c2 = st.columns(2)
                with c2:
                    if st.button("LET'S GO!", type="primary", use_container_width=True, disabled=not (name and game_active)):
                        st.session_state.update({"team": t_choice, "role": r_choice, "name": name, "joined": True})
                        st.rerun()
                with c1:
                    if st.button("CANCEL", use_container_width=True): st.toast("Cancelled")

    # PLAYER DASHBOARD UI
    else:
        st.header(f"📦 {st.session_state.role} | {st.session_state.name} (Team {st.session_state.team})")
        
        # Fetch current week data
        res = supabase.table("beer_game").select("*").eq("team", st.session_state.team).eq("role", st.session_state.role).order("week", desc=True).limit(1).execute()
        
        if res.data:
            data = res.data[0]
            
            # Row 1: Orders and Transport
            r1c1, r1c2 = st.columns(2)
            with r1c1:
                with st.container(border=True):
                    st.write("📥 **Incoming Order**")
                    st.title(f"{market_demand if st.session_state.role == 'Retailer' else '?'}")
                    st.caption("From downstream partner")

            with r1c2:
                with st.container(border=True):
                    st.write("🚚 **Outgoing Transport**")
                    st.write("*Leaving next week*")
                    st.title("4") 
                    st.caption("Confirmed shipment")

            # Row 2: Progress and Inventory
            r2c1, r2c2 = st.columns(2)
            with r2c1:
                with st.container(border=True):
                    st.write(f"📅 **Week: {data['week']}**")
                    m1, m2 = st.columns(2)
                    m1.metric("Current Costs", f"${int(data['inventory']*0.5)}")
                    m2.metric("Total Costs", f"${int(data['total_cost'])}")

            with r2c2:
                with st.container(border=True):
                    st.write("🏭 **Stock Inventory**")
                    st.title(int(data['inventory']))
                    if data['backlog'] > 0:
                        st.error(f"Backlog: {int(data['backlog'])}")

            # Row 3: Action and Production
            r3c1, r3c2 = st.columns(2)
            with r3c1:
                with st.container(border=True):
                    st.write("📝 **Place New Order**")
                    if data['order_placed'] is None:
                        val = st.number_input("Amount", min_value=0, step=1, label_visibility="collapsed")
                        if st.button("➕ PLACE ORDER", type="primary", use_container_width=True):
                            supabase.table("beer_game").update({"order_placed": val}).eq("id", data['id']).execute()
                            process_team_advance(st.session_state.team, data['week'])
                            st.rerun()
                    else:
                        st.success("Order locked in. Waiting for others...")
                        if st.button("Check for Week Progress"): st.rerun()

            with r3c2:
                with st.container(border=True):
                    st.write("⏳ **Lead Time Steps**")
                    st.write("Arriving in 1 week: **4**")
                    st.write("Arriving in 2 weeks: **4**")

# --- INSTRUCTOR DASHBOARD ---
else:
    st.title("📊 Instructor Control Panel")
    
    # Toggle Game
    if not game_active:
        if st.button("🚀 ACTIVATE GAME", type="primary"):
            supabase.table("game_settings").update({"game_active": True}).eq("id", 1).execute()
            st.rerun()
    else:
        if st.button("🛑 STOP GAME"):
            supabase.table("game_settings").update({"game_active": False}).eq("id", 1).execute()
            st.rerun()

    # Demand Slider
    new_d = st.slider("Market Demand", 0, 20, int(market_demand))
    if st.button("Update Demand"):
        supabase.table("game_settings").update({"current_demand": new_d}).eq("id", 1).execute()
        st.success("Demand Updated")

    st.divider()
    
    # Force Progress
    st.subheader("Team Management")
    for t in ["A", "B", "C"]:
        if st.button(f"Force Team {t} to Next Week"):
            latest = supabase.table("beer_game").select("week").eq("team", t).order("
