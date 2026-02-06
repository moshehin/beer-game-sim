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

# 3. UI CONFIGURATION (Hide Sidebar)
st.set_page_config(page_title="Beer Game Sim", layout="wide", initial_sidebar_state="collapsed")
st.markdown("<style>#MainMenu {visibility: hidden;} footer {visibility: hidden;} [data-testid='stSidebar'] {display: none;}</style>", unsafe_allow_html=True)

# Initialize Session States
if 'page' not in st.session_state: st.session_state.page = "landing"
if 'joined' not in st.session_state: st.session_state.joined = False

# Fetch Game State
settings_res = supabase.table("game_settings").select("*").eq("id", 1).single().execute()
game_active = settings_res.data['game_active']
market_demand = settings_res.data['current_demand']

# --- WINDOW 1: IDENTITY SELECTION ---
if st.session_state.page == "landing":
    st.markdown("<br><br><h1 style='text-align: center;'>Welcome to the Beer Game</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center;'>Please select your role to continue</p>", unsafe_allow_html=True)
    
    _, col1, col2, _ = st.columns([1, 2, 2, 1])
    with col1:
        if st.button("👨‍🎓 STUDENT", use_container_width=True, type="primary"):
            st.session_state.page = "student_join"
            st.rerun()
    with col2:
        if st.button("👨‍🏫 INSTRUCTOR", use_container_width=True):
            st.session_state.page = "instructor_dashboard"
            st.rerun()

# --- WINDOW 2: STUDENT JOIN MODAL ---
elif st.session_state.page == "student_join" and not st.session_state.joined:
    _, col_mid, _ = st.columns([1, 2, 1])
    with col_mid:
        with st.container(border=True):
            st.subheader("Select your role")
            t_choice = st.selectbox("Team", ["A", "B", "C"])
            r_choice = st.selectbox("Role", ["Retailer", "Wholesaler", "Distributor", "Manufacturer"])
            name = st.text_input("Enter your name")
            
            if not game_active:
                st.warning("Game is not active. Wait for instructor.")
            
            c1, c2 = st.columns(2)
            with c2:
                if st.button("LET'S GO!", type="primary", use_container_width=True, disabled=not (name and game_active)):
                    st.session_state.update({"team": t_choice, "role": r_choice, "name": name, "joined": True})
                    st.rerun()
            with c1:
                if st.button("BACK", use_container_width=True):
                    st.session_state.page = "landing"
                    st.rerun()

# --- WINDOW 3A: STUDENT DASHBOARD ---
elif st.session_state.page == "student_join" and st.session_state.joined:
    st.header(f"📦 {st.session_state.role} | {st.session_state.name} (Team {st.session_state.team})")
    res = supabase.table("beer_game").select("*").eq("team", st.session_state.team).eq("role", st.session_state.role).order("week", desc=True).limit(1).execute()
    
    if res.data:
        data = res.data[0]
        r1c1, r1c2 = st.columns(2)
        with r1c1:
            with st.container(border=True):
                st.write("📥 **Incoming Order**")
                st.title(market_demand if st.session_state.role == "Retailer" else "?")
        with r1c2:
            with st.container(border=True):
                st.write("🚚 **Stock**")
                st.title(int(data['inventory']))
        
        with st.container(border=True):
            st.write("📝 **Place Order**")
            if data['order_placed'] is None:
                val = st.number_input("Amount", min_value=0, step=1, label_visibility="collapsed")
                if st.button("➕ SUBMIT ORDER", type="primary", use_container_width=True):
                    supabase.table("beer_game").update({"order_placed": val}).eq("id", data['id']).execute()
                    process_team_advance(st.session_state.team, data['week'])
                    st.rerun()
            else:
                st.success("Wait for teammates...")
                if st.button("Refresh"): st.rerun()
    
    if st.button("Exit Game"):
        st.session_state.joined = False
        st.session_state.page = "landing"
        st.rerun()

# --- WINDOW 3B: INSTRUCTOR DASHBOARD ---
elif st.session_state.page == "instructor_dashboard":
    st.title("📊 Instructor Control Panel")
    if st.button("Toggle Game Status"):
        supabase.table("game_settings").update({"game_active": not game_active}).eq("id", 1).execute()
        st.rerun()
    
    new_d = st.slider("Market Demand", 0, 20, int(market_demand))
    if st.button("Set Demand"):
        supabase.table("game_settings").update({"current_demand": new_d}).eq("id", 1).execute()
        st.rerun()

    st.divider()
    for t in ["A", "B", "C"]:
        latest = supabase.table("beer_game").select("week").eq("team", t).order("week", desc=True).limit(1).execute()
        if latest.data and st.button(f"Automate/Advance Team {t} (Week {latest.data[0]['week']})"):
            process_team_advance(t, latest.data[0]['week'], forced=True)
            st.success(f"Team {t} advanced!")

    if st.button("BACK TO HOME"):
        st.session_state.page = "landing"
        st.rerun()
