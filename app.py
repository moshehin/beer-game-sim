import streamlit as st
import pandas as pd
import time
from supabase import create_client

# 1. DATABASE CONNECTION
URL = st.secrets["SUPABASE_URL"]
KEY = st.secrets["SUPABASE_KEY"]
supabase = create_client(URL, KEY)

# 2. THE MATH ENGINE (1-Week Lead Time + Automation)
def process_team_advance(team_name, week, forced=False):
    res = supabase.table("beer_game").select("*").eq("team", team_name).eq("week", week).execute()
    players = {p['role']: p for p in res.data}
    submitted_roles = [p['role'] for p in res.data if p['order_placed'] is not None]
    
    # Check if all roles are ready or if admin forced it
    if not forced and len(submitted_roles) < 4:
        return 

    settings = supabase.table("game_settings").select("current_demand").eq("id", 1).single().execute()
    cust_demand = settings.data['current_demand']
    roles = ['Retailer', 'Wholesaler', 'Distributor', 'Manufacturer']
    
    # Use 4 (steady state) for automated roles
    current_orders = {r: (players[r]['order_placed'] if players[r]['order_placed'] is not None else 4) for r in roles}

    for i, role in enumerate(roles):
        p = players[role]
        demand_val = cust_demand if i == 0 else current_orders[roles[i-1]]
        total_needed = demand_val + p['backlog']
        shipped = min(p['inventory'], total_needed)
        new_backlog = total_needed - shipped
        incoming_stock = current_orders[role] # 1-week lead time
        
        supabase.table("beer_game").insert({
            "team": team_name, "role": role, "week": week + 1,
            "inventory": (p['inventory'] - shipped) + incoming_stock,
            "backlog": new_backlog,
            "total_cost": p['total_cost'] + ((p['inventory'] - shipped + incoming_stock) * 0.5) + (new_backlog * 1.0),
            "order_placed": None,
            "player_name": p.get('player_name') # Carry name to next week
        }).execute()

# 3. UI THEME & CONFIG
st.set_page_config(page_title="Beer Game", layout="centered", initial_sidebar_state="collapsed")
st.markdown("""
    <style>
    [data-testid="stSidebar"] {display: none;}
    .stMetric { background-color: #1e1e1e; padding: 15px; border-radius: 10px; border: 1px solid #333; }
    .stProgress > div > div > div > div { background-color: #4CAF50; }
    </style>
    """, unsafe_allow_html=True)

if 'page' not in st.session_state: st.session_state.page = "landing"
if 'joined' not in st.session_state: st.session_state.joined = False

# Fetch Global Settings
try:
    settings_res = supabase.table("game_settings").select("*").eq("id", 1).single().execute()
    game_active = settings_res.data['game_active']
    market_demand = settings_res.data['current_demand']
except:
    game_active = False; market_demand = 4

# --- WINDOW 1: IDENTITY ---
if st.session_state.page == "landing":
    st.title("🍺 Beer Game Simulator")
    if st.button("STUDENT PORTAL", use_container_width=True, type="primary"):
        st.session_state.page = "student_join"; st.rerun()
    if st.button("INSTRUCTOR DASHBOARD", use_container_width=True):
        st.session_state.page = "instructor_dashboard"; st.rerun()

# --- WINDOW 2: JOIN (WITH DUPLICATE PREVENTION) ---
elif st.session_state.page == "student_join" and not st.session_state.joined:
    st.subheader("Select your role")
    with st.container(border=True):
        t_choice = st.selectbox("Team", ["A", "B", "C"])
        r_choice = st.selectbox("Role", ["Retailer", "Wholesaler", "Distributor", "Manufacturer"])
        name = st.text_input("Type in your name or alias")
        
        # Check if role is taken
        check = supabase.table("beer_game").select("player_name").eq("team", t_choice).eq("role", r_choice).execute()
        is_taken = any(p.get('player_name') for p in check.data) if check.data else False
        
        if is_taken:
            st.error(f"❌ This role in Team {t_choice} is already occupied.")
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("LET'S GO!", type="primary", use_container_width=True, disabled=not name or is_taken):
                supabase.table("beer_game").update({"player_name": name}).eq("team", t_choice).eq("role", r_choice).execute()
                st.session_state.update({"team": t_choice, "role": r_choice, "name": name, "joined": True})
                st.rerun()
        with col2:
            if st.button("CANCEL", use_container_width=True):
                st.session_state.page = "landing"; st.rerun()

# --- WINDOW 3: LOBBY ---
elif st.session_state.page == "student_join" and st.session_state.joined and not game_active:
    st.info(f"Welcome {st.session_state.name}! Waiting for instructor to start the game...")
    time.sleep(3); st.rerun()

# --- WINDOW 4: STUDENT DASHBOARD (FIXED UI) ---
elif st.session_state.page == "student_join" and st.session_state.joined and game_active:
    res = supabase.table("beer_game").select("*").eq("team", st.session_state.team).eq("role", st.session_state.role).order("week", desc=True).limit(1).execute()
    
    if res.data:
        data = res.data[0]
        st.subheader(f"📊 {st.session_state.role} | Week {data['week']}")
        
        # Visual Gauges
        c1, c2 = st.columns(2)
        with c1:
            st.write("💰 Total Cost")
            st.progress(min(data['total_cost'] / 1000, 1.0))
            st.metric("Spent", f"${int(data['total_cost'])}")
        with c2:
            st.write("📦 Stock Level")
            st.progress(min(data['inventory'] / 50, 1.0))
            st.metric("Inventory", int(data['inventory']))

        st.markdown(f"**Incoming Order:** `{market_demand if st.session_state.role == 'Retailer' else '?'}`")
        
        with st.container(border=True):
            if data['order_placed'] is None:
                val = st.number_input("Order Amount", min_value=0, step=1)
                if st.button("PLACE ORDER", type="primary", use_container_width=True):
                    supabase.table("beer_game").update({"order_placed": val}).eq("id", data['id']).execute()
                    process_team_advance(st.session_state.team, data['week'])
                    st.rerun()
            else:
                st.success("Order locked. Waiting for others...")
                time.sleep(5); st.rerun()
    
    if st.button("Leave Game"):
        st.session_state.joined = False; st.session_state.page = "landing"; st.rerun()

# --- WINDOW 5: INSTRUCTOR DASHBOARD (RESET ADDED) ---
elif st.session_state.page == "instructor_dashboard":
    st.title("🎮 Instructor Panel")
    pw = st.text_input("Password", type="password")
    if pw == "beer123":
        if st.button("RESET GAME & CLEAR PLAYERS", type="secondary", use_container_width=True):
            supabase.table("beer_game").delete().neq("week", -1).execute()
            for t in ["A", "B", "C"]:
                for r in ["Retailer", "Wholesaler", "Distributor", "Manufacturer"]:
                    supabase.table("beer_game").insert({"team": t, "role": r, "week": 1, "inventory": 12, "backlog": 0, "total_cost": 0, "player_name": None}).execute()
            supabase.table("game_settings").update({"game_active": False}).eq("id", 1).execute()
            st.success("Database Purged. All roles are now free.")

        if st.button("START GAME" if not game_active else "STOP GAME", type="primary", use_container_width=True):
            supabase.table("game_settings").update({"game_active": not game_active}).eq("id", 1).execute()
            st.rerun()
        
        st.divider()
        new_d = st.slider("Demand", 0, 20, int(market_demand))
        if st.button("Apply Demand"):
            supabase.table("game_settings").update({"current_demand": new_d}).eq("id", 1).execute(); st.rerun()
