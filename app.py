import streamlit as st
import pandas as pd
import time
import random
from supabase import create_client

# 1. DATABASE CONNECTION
URL = st.secrets["SUPABASE_URL"]
KEY = st.secrets["SUPABASE_KEY"]
supabase = create_client(URL, KEY)

# 2. THE MATH ENGINE (2-Week Lead Time + Ghost Automation)
def process_team_advance(team_name, week, forced=False):
    res = supabase.table("beer_game").select("*").eq("team", team_name).eq("week", week).execute()
    players = {p['role']: p for p in res.data}
    submitted_roles = [p['role'] for p in res.data if p['order_placed'] is not None]
    
    # Wait for all 4 roles unless forced by Instructor
    if not forced and len(submitted_roles) < 4:
        return 

    # Fetch current demand set by Instructor
    settings = supabase.table("game_settings").select("current_demand").eq("id", 1).single().execute()
    cust_demand = settings.data['current_demand']
    roles = ['Retailer', 'Wholesaler', 'Distributor', 'Manufacturer']
    
    # Identify orders (Human or Random Ghost)
    current_orders = {r: (players[r]['order_placed'] if players[r]['order_placed'] is not None else random.randint(2, 8)) for r in roles}

    for i, role in enumerate(roles):
        p = players[role]
        
        # Demand Logic
        demand_val = cust_demand if i == 0 else current_orders[roles[i-1]]
        total_needed = demand_val + p['backlog']
        shipped = min(p['inventory'], total_needed)
        new_backlog = total_needed - shipped
        
        # --- 2-WEEK LEAD TIME LOGIC ---
        # Arrival today is the order placed 2 weeks ago (from week - 1 record)
        arrival_res = supabase.table("beer_game").select("order_placed").eq("team", team_name).eq("role", role).eq("week", week - 1).execute()
        incoming_delivery = arrival_res.data[0]['order_placed'] if arrival_res.data and arrival_res.data[0]['order_placed'] is not None else 4
        
        new_inv = (p['inventory'] - shipped) + incoming_delivery
        weekly_cost = (new_inv * 0.5) + (new_backlog * 1.0)
        
        supabase.table("beer_game").insert({
            "team": team_name, "role": role, "week": week + 1,
            "inventory": new_inv, "backlog": new_backlog,
            "total_cost": p['total_cost'] + weekly_cost,
            "order_placed": None,
            "player_name": p.get('player_name'),
            "last_shipped": shipped,
            "last_demand": demand_val,
            "incoming_delivery": incoming_delivery
        }).execute()

# 3. UI THEME
st.set_page_config(page_title="Beer Game Sim", layout="centered", initial_sidebar_state="collapsed")
st.markdown("<style>[data-testid='stSidebar'] {display: none;} .stMetric {background-color: #1e1e1e; border-radius: 10px; padding: 10px;}</style>", unsafe_allow_html=True)

if 'page' not in st.session_state: st.session_state.page = "landing"
if 'joined' not in st.session_state: st.session_state.joined = False

# Global State Fetch
try:
    s_res = supabase.table("game_settings").select("*").eq("id", 1).single().execute()
    game_active = s_res.data['game_active']
    market_demand = s_res.data['current_demand']
except:
    game_active = False; market_demand = 4

# --- WINDOW 1: LANDING ---
if st.session_state.page == "landing":
    st.title("🍺 Beer Game Simulator")
    if st.button("STUDENT PORTAL", use_container_width=True, type="primary"):
        st.session_state.page = "student_join"; st.rerun()
    if st.button("INSTRUCTOR LOGIN", use_container_width=True):
        st.session_state.page = "instructor_dashboard"; st.rerun()

# --- WINDOW 2: STUDENT JOIN ---
elif st.session_state.page == "student_join" and not st.session_state.joined:
    with st.container(border=True):
        st.subheader("Join a Team")
        t_choice = st.selectbox("Team", ["A", "B", "C"])
        r_choice = st.selectbox("Role", ["Retailer", "Wholesaler", "Distributor", "Manufacturer"])
        name = st.text_input("Name")
        
        # Duplicate Prevention
        check = supabase.table("beer_game").select("player_name").eq("team", t_choice).eq("role", r_choice).order("week", desc=True).limit(1).execute()
        is_taken = any(p.get('player_name') for p in check.data) if (check.data and check.data[0]['player_name']) else False
        
        if is_taken: st.error("❌ Position already occupied.")
        if st.button("JOIN GAME", type="primary", use_container_width=True, disabled=not name or is_taken):
            supabase.table("beer_game").update({"player_name": name}).eq("team", t_choice).eq("role", r_choice).execute()
            st.session_state.update({"team": t_choice, "role": r_choice, "name": name, "joined": True})
            st.rerun()

# --- WINDOW 3: STUDENT DASHBOARD ---
elif st.session_state.page == "student_join" and st.session_state.joined:
    if not game_active:
        st.info("🕒 Waiting for instructor to start...")
        time.sleep(3); st.rerun()

    res = supabase.table("beer_game").select("*").eq("team", st.session_state.team).eq("role", st.session_state.role).order("week", desc=True).limit(1).execute()
    
    if res.data:
        curr = res.data[0]
        st.subheader(f"📊 {st.session_state.role} | Week {curr['week']}")

        # Display Stats
        c1, c2 = st.columns(2)
        with c1:
            st.metric("Total Cost", f"${int(curr['total_cost'])}")
            st.progress(min(curr['total_cost'] / 500, 1.0))
        with c2:
            st.metric("Stock", int(curr['inventory']), f"{int(curr['backlog'])} Backlog", delta_color="inverse")
            st.progress(min(curr['inventory'] / 40, 1.0))

        st.markdown(f"**Customer Order:** `{market_demand if st.session_state.role == 'Retailer' else curr.get('last_demand', '?')}`")
        st.markdown(f"**Incoming Delivery:** `{curr.get('incoming_delivery', 4)}`")

        with st.container(border=True):
            if curr['order_placed'] is None:
                val = st.number_input("Order Quantity", min_value=0, step=1, value=4)
                if st.button("PLACE ORDER", type="primary", use_container_width=True):
                    supabase.table("beer_game").update({"order_placed": val}).eq("id", curr['id']).execute()
                    process_team_advance(st.session_state.team, curr['week'])
                    st.rerun()
            else:
                st.success("Order locked. Waiting...")
                time.sleep(5); st.rerun()

# --- WINDOW 4: INSTRUCTOR DASHBOARD ---
elif st.session_state.page == "instructor_dashboard":
    st.title("🎮 Instructor Panel")
    if st.text_input("Password", type="password") == "beer123":
        
        # Start/Stop
        if st.button("START / STOP GAME", type="primary", use_container_width=True):
            supabase.table("game_settings").update({"game_active": not game_active}).eq("id", 1).execute(); st.rerun()
        
        # RESET
        if st.button("♻️ FULL RESET (Clear Names & Data)", use_container_width=True):
            supabase.table("beer_game").delete().neq("week", -1).execute()
            for t in ["A", "B", "C"]:
                for r in ["Retailer", "Wholesaler", "Distributor", "Manufacturer"]:
                    supabase.table("beer_game").insert({"team":t,"role":r,"week":1,"inventory":12,"backlog":0,"total_cost":0,"player_name":None}).execute()
            supabase.table("game_settings").update({"game_active": False, "current_demand": 4}).eq("id", 1).execute()
            st.rerun()

        st.divider()
        # DEMAND CONTROL
        st.subheader("Market Demand Control")
        new_demand = st.slider("Set Current Demand", 0, 20, int(market_demand))
        if st.button("Apply New Demand"):
            supabase.table("game_settings").update({"current_demand": new_demand}).eq("id", 1).execute()
            st.success(f"Market demand updated to {new_demand}")

        st.divider()
        # MANUAL ADVANCE
        for t in ["A", "B", "C"]:
            if st.button(f"Advance Team {t}", use_container_width=True):
                latest = supabase.table("beer_game").select("week").eq("team", t).order("week", desc=True).limit(1).execute()
                process_team_advance(t, latest.data[0]['week'], forced=True); st.rerun()
