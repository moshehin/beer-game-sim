import streamlit as st
import pandas as pd
import time
from supabase import create_client

# 1. DATABASE CONNECTION
URL = st.secrets["SUPABASE_URL"]
KEY = st.secrets["SUPABASE_KEY"]
supabase = create_client(URL, KEY)

# 2. THE MATH ENGINE (1-Week Lead Time + Ghost Players)
def process_team_advance(team_name, week, forced=False):
    res = supabase.table("beer_game").select("*").eq("team", team_name).eq("week", week).execute()
    players = {p['role']: p for p in res.data}
    submitted_roles = [p['role'] for p in res.data if p['order_placed'] is not None]
    
    if not forced and len(submitted_roles) < 4:
        return 

    settings = supabase.table("game_settings").select("current_demand").eq("id", 1).single().execute()
    cust_demand = settings.data['current_demand']
    roles = ['Retailer', 'Wholesaler', 'Distributor', 'Manufacturer']
    
    current_orders = {r: (players[r]['order_placed'] if players[r]['order_placed'] is not None else cust_demand) for r in roles}

    for i, role in enumerate(roles):
        p = players[role]
        demand_val = cust_demand if i == 0 else current_orders[roles[i-1]]
        total_needed = demand_val + p['backlog']
        shipped = min(p['inventory'], total_needed)
        new_backlog = total_needed - shipped
        incoming_stock = current_orders[role] # 1-week lead time
        new_inv = (p['inventory'] - shipped) + incoming_stock
        
        supabase.table("beer_game").insert({
            "team": team_name, "role": role, "week": week + 1,
            "inventory": new_inv, "backlog": new_backlog,
            "total_cost": p['total_cost'] + (new_inv * 0.5) + (new_backlog * 1.0),
            "order_placed": None
        }).execute()

# 3. UI CONFIGURATION
st.set_page_config(page_title="Beer Game", layout="centered", initial_sidebar_state="collapsed")
st.markdown("""
    <style>
    [data-testid="stSidebar"] {display: none;}
    .stMetric { background-color: #f8f9fa; padding: 15px; border-radius: 12px; border: 1px solid #dee2e6; }
    .stProgress > div > div > div > div { background-color: #2e7d32; }
    </style>
    """, unsafe_allow_html=True)

# Session State Management
if 'page' not in st.session_state: st.session_state.page = "landing"
if 'joined' not in st.session_state: st.session_state.joined = False

# Fetch Game State
try:
    settings_res = supabase.table("game_settings").select("*").eq("id", 1).single().execute()
    game_active = settings_res.data['game_active']
    market_demand = settings_res.data['current_demand']
except:
    game_active = False
    market_demand = 4

# --- WINDOW 1: IDENTITY SELECTION ---
if st.session_state.page == "landing":
    st.title("🍻 Beer Game Simulator")
    st.write("Welcome! Please select your entrance:")
    if st.button("STUDENT PORTAL", use_container_width=True, type="primary"):
        st.session_state.page = "student_join"
        st.rerun()
    if st.button("INSTRUCTOR LOGIN", use_container_width=True):
        st.session_state.page = "instructor_dashboard"
        st.rerun()

# --- WINDOW 2: STUDENT JOIN ---
elif st.session_state.page == "student_join" and not st.session_state.joined:
    with st.container(border=True):
        st.subheader("Join your Team")
        t_choice = st.selectbox("Team", ["A", "B", "C"])
        r_choice = st.selectbox("Role", ["Retailer", "Wholesaler", "Distributor", "Manufacturer"])
        name = st.text_input("Your Alias")
        
        if st.button("READY TO PLAY", type="primary", use_container_width=True, disabled=not name):
            st.session_state.update({"team": t_choice, "role": r_choice, "name": name, "joined": True})
            st.rerun()
        if st.button("BACK"):
            st.session_state.page = "landing"
            st.rerun()

# --- WINDOW 3: THE LOBBY (WAITING ROOM) ---
elif st.session_state.page == "student_join" and st.session_state.joined and not game_active:
    st.title("⏳ In the Lobby")
    st.info(f"Hi {st.session_state.name}, you have joined **Team {st.session_state.team}** as the **{st.session_state.role}**.")
    st.write("Please wait for the instructor to start the game. Your dashboard will load automatically.")
    
    # Auto-refresh to check if instructor started
    time.sleep(3)
    st.rerun()

# --- WINDOW 4: STUDENT DASHBOARD (MOBILE) ---
elif st.session_state.page == "student_join" and st.session_state.joined and game_active:
    res = supabase.table("beer_game").select("*").eq("team", st.session_state.team).eq("role", st.session_state.role).order("week", desc=True).limit(1).execute()
    
    if res.data:
        data = res.data[0]
        st.subheader(f"📊 {st.session_state.role} | Week {data['week']}")
        
        # COST GAUGES
        c1, c2 = st.columns(2)
        with c1:
            st.write("💰 Total Cost")
            # 500 is the "danger" threshold for the progress bar
            st.progress(min(data['total_cost'] / 500, 1.0))
            st.metric("Spent", f"${int(data['total_cost'])}")
        with c2:
            st.write("📦 Stock Level")
            st.progress(min(data['inventory'] / 40, 1.0))
            st.metric("Inventory", int(data['inventory']))

        # DASHBOARD INFO
        st.markdown(f"**Incoming Order:** `{market_demand if st.session_state.role == 'Retailer' else '?'}`")
        
        with st.container(border=True):
            if data['order_placed'] is None:
                st.write("📝 **Submit Order**")
                val = st.number_input("Amount to order", min_value=0, step=1, label_visibility="collapsed")
                if st.button("PLACE ORDER", type="primary", use_container_width=True):
                    supabase.table("beer_game").update({"order_placed": val}).eq("id", data['id']).execute()
                    process_team_advance(st.session_state.team, data['week'])
                    st.rerun()
            else:
                st.success("Order locked. Waiting for other roles...")
                time.sleep(5)
                st.rerun()

    if st.button("Leave Game"):
        st.session_state.joined = False
        st.session_state.page = "landing"
        st.rerun()

# --- WINDOW 5: INSTRUCTOR DASHBOARD ---
elif st.session_state.page == "instructor_dashboard":
    st.title("🎮 Game Master Controls")
    
    # Security Check
    pw = st.text_input("Instructor Password", type="password")
    if pw == "beer123": # Change this to your preferred password
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🚀 START GAME", type="primary", use_container_width=True, disabled=game_active):
                supabase.table("game_settings").update({"game_active": True}).eq("id", 1).execute()
                st.rerun()
        with col2:
            if st.button("🛑 STOP GAME", use_container_width=True, disabled=not game_active):
                supabase.table("game_settings").update({"game_active": False}).eq("id", 1).execute()
                st.rerun()

        st.divider()
        
        # RESET BUTTON
        if st.button("⚠️ FULL RESET (Restart Game)", use_container_width=True):
            supabase.table("beer_game").delete().neq("week", -1).execute()
            for t in ["A", "B", "C"]:
                for r in ["Retailer", "Wholesaler", "Distributor", "Manufacturer"]:
                    supabase.table("beer_game").insert({"team": t, "role": r, "week": 1, "inventory": 12, "backlog": 0, "total_cost": 0}).execute()
            supabase.table("game_settings").update({"game_active": False, "current_demand": 4}).eq("id", 1).execute()
            st.success("System Reset to Week 1!")

        st.divider()
        new_d = st.slider("Market Demand", 0, 20, int(market_demand))
        if st.button("Update Demand"):
            supabase.table("game_settings").update({"current_demand": new_d}).eq("id", 1).execute()
            st.rerun()

        st.divider()
        st.write("Force team progress (fills ghost roles):")
        for t in ["A", "B", "C"]:
            latest = supabase.table("beer_game").select("week").eq("team", t).order("week", desc=True).limit(1).execute()
            if latest.data and st.button(f"Advance Team {t} (Week {latest.data[0]['week']})", use_container_width=True):
                process_team_advance(t, latest.data[0]['week'], forced=True)
                st.rerun()
    
    if st.button("BACK TO HOME"):
        st.session_state.page = "landing"
        st.rerun()
