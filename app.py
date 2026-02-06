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
    
    # Automation: Fill missing orders with current market demand
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

# 3. UI CONFIGURATION (Mobile Optimization)
st.set_page_config(page_title="Beer Game", layout="centered", initial_sidebar_state="collapsed")
st.markdown("""
    <style>
    [data-testid="stSidebar"] {display: none;}
    .stMetric { background-color: #f0f2f6; padding: 10px; border-radius: 10px; }
    </style>
    """, unsafe_allow_html=True)

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

# --- WINDOW 1: SELECTION ---
if st.session_state.page == "landing":
    st.title("🍺 Beer Game Sim")
    st.write("Choose your access level:")
    if st.button("STUDENT ENTRANCE", use_container_width=True, type="primary"):
        st.session_state.page = "student_join"
        st.rerun()
    if st.button("INSTRUCTOR LOGIN", use_container_width=True):
        st.session_state.page = "instructor_dashboard"
        st.rerun()

# --- WINDOW 2: STUDENT JOIN ---
elif st.session_state.page == "student_join" and not st.session_state.joined:
    with st.container(border=True):
        st.subheader("Join a Team")
        t_choice = st.selectbox("Team", ["A", "B", "C"])
        r_choice = st.selectbox("Role", ["Retailer", "Wholesaler", "Distributor", "Manufacturer"])
        name = st.text_input("Your Alias")
        
        if not game_active:
            st.warning("Waiting for instructor to start...")
        
        if st.button("JOIN GAME", type="primary", use_container_width=True, disabled=not (name and game_active)):
            st.session_state.update({"team": t_choice, "role": r_choice, "name": name, "joined": True})
            st.rerun()
        if st.button("BACK"):
            st.session_state.page = "landing"
            st.rerun()

# --- WINDOW 3A: STUDENT DASHBOARD (MOBILE FRIENDLY) ---
elif st.session_state.page == "student_join" and st.session_state.joined:
    res = supabase.table("beer_game").select("*").eq("team", st.session_state.team).eq("role", st.session_state.role).order("week", desc=True).limit(1).execute()
    
    if res.data:
        data = res.data[0]
        st.subheader(f"{st.session_state.role} | Week {data['week']}")
        
        # COST GAUGES (Visual indicators)
        col_g1, col_g2 = st.columns(2)
        with col_g1:
            cost_ratio = min(data['total_cost'] / 500, 1.0) # Scaling for gauge
            st.write("💸 Cost Health")
            st.progress(cost_ratio)
            st.metric("Total", f"${int(data['total_cost'])}")
        with col_g2:
            inv_ratio = min(data['inventory'] / 50, 1.0)
            st.write("📦 Stock Health")
            st.progress(inv_ratio)
            st.metric("Inventory", int(data['inventory']))

        # INCOMING INFO
        st.info(f"📥 Incoming Order: {market_demand if st.session_state.role == 'Retailer' else '?'}")
        
        # ACTION CARD
        with st.container(border=True):
            if data['order_placed'] is None:
                st.write("📝 **Place New Order**")
                val = st.number_input("Quantity", min_value=0, step=1, label_visibility="collapsed")
                if st.button("CONFIRM ORDER", type="primary", use_container_width=True):
                    supabase.table("beer_game").update({"order_placed": val}).eq("id", data['id']).execute()
                    process_team_advance(st.session_state.team, data['week'])
                    st.rerun()
            else:
                st.success("Order Sent. Waiting...")
                if st.button("Refresh status", use_container_width=True): st.rerun()

    if st.button("Exit"):
        st.session_state.joined = False
        st.session_state.page = "landing"
        st.rerun()

# --- WINDOW 3B: INSTRUCTOR DASHBOARD ---
elif st.session_state.page == "instructor_dashboard":
    st.title("📊 Control Panel")
    
    # 1. RESET BUTTON (DANGER ZONE)
    if st.button("⚠️ RESET ALL TEAMS TO WEEK 1", type="secondary", use_container_width=True):
        supabase.table("beer_game").delete().neq("week", -1).execute() # Clear all
        for t in ["A", "B", "C"]:
            for r in ["Retailer", "Wholesaler", "Distributor", "Manufacturer"]:
                supabase.table("beer_game").insert({"team": t, "role": r, "week": 1, "inventory": 12, "backlog": 0, "total_cost": 0}).execute()
        st.success("Database Reset!")

    st.divider()
    
    # 2. GAME TOGGLE
    if st.button("START GAME" if not game_active else "STOP GAME", type="primary", use_container_width=True):
        supabase.table("game_settings").update({"game_active": not game_active}).eq("id", 1).execute()
        st.rerun()

    # 3. DEMAND CONTROL
    new_d = st.slider("Market Demand", 0, 20, int(market_demand))
    if st.button("Update Market"):
        supabase.table("game_settings").update({"current_demand": new_d}).eq("id", 1).execute()
        st.rerun()

    st.divider()
    
    # 4. TEAM AUTOMATION
    st.write("Automate missing players:")
    for t in ["A", "B", "C"]:
        latest = supabase.table("beer_game").select("week").eq("team", t).order("week", desc=True).limit(1).execute()
        if latest.data:
            if st.button(f"Advance Team {t} (Week {latest.data[0]['week']})", use_container_width=True):
                process_team_advance(t, latest.data[0]['week'], forced=True)
                st.rerun()

    if st.button("BACK TO HOME"):
        st.session_state.page = "landing"
        st.rerun()
