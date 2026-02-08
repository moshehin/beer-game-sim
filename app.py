import streamlit as st
import pandas as pd
import time
import random
from supabase import create_client

# 1. DATABASE CONNECTION
URL = st.secrets["SUPABASE_URL"]
KEY = st.secrets["SUPABASE_KEY"]
supabase = create_client(URL, KEY)

# 2. THE MATH ENGINE (MA Systems / MIT Logic)
def process_team_advance(team_name, week, forced=False):
    res = supabase.table("beer_game").select("*").eq("team", team_name).eq("week", week).execute()
    players = {p['role']: p for p in res.data}
    submitted_roles = [p['role'] for p in res.data if p['order_placed'] is not None]
    
    if not forced and len(submitted_roles) < 4:
        return 

    settings = supabase.table("game_settings").select("current_demand").eq("id", 1).single().execute()
    cust_demand = settings.data['current_demand']
    roles = ['Retailer', 'Wholesaler', 'Distributor', 'Manufacturer']
    
    # GHOST LOGIC: Simulate random human-like error if player is missing
    current_orders = {r: (players[r]['order_placed'] if players[r]['order_placed'] is not None else random.randint(3, 7)) for r in roles}

    for i, role in enumerate(roles):
        p = players[role]
        
        # Demand: From customer (Retailer) or downstream partner
        demand_val = cust_demand if i == 0 else current_orders[roles[i-1]]
        total_needed = demand_val + p['backlog']
        
        # Outgoing Transport calculation
        shipped = min(p['inventory'], total_needed)
        new_backlog = total_needed - shipped
        
        # MA Systems Delivery Logic: Fetch order from 2 weeks ago (2-week shipping delay)
        # Note: For week 1 & 2, we use a default startup value of 4
        prev_week = week - 1
        delivery_res = supabase.table("beer_game").select("order_placed").eq("team", team_name).eq("role", role).eq("week", prev_week).execute()
        incoming_delivery = delivery_res.data[0]['order_placed'] if delivery_res.data and delivery_res.data[0]['order_placed'] is not None else 4

        # New Stock = (Current - Shipped) + Incoming
        new_inv = (p['inventory'] - shipped) + incoming_delivery
        weekly_cost = (new_inv * 0.5) + (new_backlog * 1.0)
        
        supabase.table("beer_game").insert({
            "team": team_name, "role": role, "week": week + 1,
            "inventory": new_inv, "backlog": new_backlog,
            "total_cost": p['total_cost'] + weekly_cost,
            "order_placed": None,
            "player_name": p.get('player_name'),
            "last_shipped": shipped, # Outgoing Transport
            "last_demand": demand_val, # Customer Order
            "incoming_delivery": incoming_delivery
        }).execute()

# 3. UI CONFIGURATION
st.set_page_config(page_title="MA Systems Beer Game", layout="centered", initial_sidebar_state="collapsed")
st.markdown("""
    <style>
    [data-testid="stSidebar"] {display: none;}
    .stMetric { background-color: #1e1e1e; padding: 15px; border-radius: 12px; border: 1px solid #333; }
    .stProgress > div > div > div > div { background-color: #2e7d32; }
    </style>
    """, unsafe_allow_html=True)

if 'page' not in st.session_state: st.session_state.page = "landing"
if 'joined' not in st.session_state: st.session_state.joined = False

# Fetch Settings
try:
    s_res = supabase.table("game_settings").select("*").eq("id", 1).single().execute()
    game_active = s_res.data['game_active']
    market_demand = s_res.data['current_demand']
except:
    game_active = False; market_demand = 4

# --- NAVIGATION ---
if st.session_state.page == "landing":
    st.title("🍺 MA Systems Beer Game")
    if st.button("STUDENT PORTAL", use_container_width=True, type="primary"):
        st.session_state.page = "student_join"; st.rerun()
    if st.button("INSTRUCTOR LOGIN", use_container_width=True):
        st.session_state.page = "instructor_dashboard"; st.rerun()

elif st.session_state.page == "student_join" and not st.session_state.joined:
    with st.container(border=True):
        st.subheader("Role Registration")
        t_choice = st.selectbox("Team", ["A", "B", "C"])
        r_choice = st.selectbox("Role", ["Retailer", "Wholesaler", "Distributor", "Manufacturer"])
        name = st.text_input("Name")
        
        check = supabase.table("beer_game").select("player_name").eq("team", t_choice).eq("role", r_choice).order("week", desc=True).limit(1).execute()
        is_taken = any(p.get('player_name') for p in check.data) if check.data else False
        
        if is_taken: st.error("❌ Position already occupied.")
        if st.button("JOIN", type="primary", use_container_width=True, disabled=not name or is_taken):
            supabase.table("beer_game").update({"player_name": name}).eq("team", t_choice).eq("role", r_choice).execute()
            st.session_state.update({"team": t_choice, "role": r_choice, "name": name, "joined": True})
            st.rerun()

# --- THE MA SYSTEMS DASHBOARD ---
elif st.session_state.page == "student_join" and st.session_state.joined:
    if not game_active:
        st.info("🕒 Waiting for instructor to start...")
        time.sleep(3); st.rerun()

    res = supabase.table("beer_game").select("*").eq("team", st.session_state.team).eq("role", st.session_state.role).order("week", desc=True).limit(1).execute()
    
    if res.data:
        curr = res.data[0]
        st.markdown(f"### {st.session_state.role} | Week {curr['week']}")

        # 1. TOP ROW: ORDERS & SHIPMENTS
        col_a, col_b = st.columns(2)
        with col_a:
            # Customer Order (Market demand for Retailer, downstream order for others)
            val = market_demand if st.session_state.role == "Retailer" else curr.get('last_demand', '?')
            st.metric("📥 Customer Order", val)
        with col_b:
            # Outgoing Transport (What you actually shipped)
            st.metric("🚚 Outgoing Transport", curr.get('last_shipped', 0))

        # 2. MIDDLE ROW: STOCK & DELIVERY
        col_c, col_d = st.columns(2)
        with col_c:
            st.metric("📦 Stock (Inventory)", int(curr['inventory']), f"{int(curr['backlog'])} Backlog", delta_color="inverse")
        with col_d:
            # Incoming Delivery (Arriving now from your order placed 2 weeks ago)
            st.metric("🏗️ Incoming Delivery", curr.get('incoming_delivery', 4))

        # 3. BOTTOM ROW: COSTS
        st.markdown("---")
        c1, c2 = st.columns(2)
        with c1:
            st.write("📈 Total Cost")
            st.progress(min(curr['total_cost'] / 1000, 1.0))
            st.metric("Cumulative", f"${int(curr['total_cost'])}")
        with c2:
            st.write("📊 Cost This Week")
            weekly = (curr['inventory'] * 0.5) + (curr['backlog'] * 1.0)
            st.metric("Weekly", f"${weekly}")

        # ACTION AREA
        with st.container(border=True):
            if curr['order_placed'] is None:
                order_amt = st.number_input("Enter New Order Amount", min_value=0, step=1, value=4)
                if st.button("PLACE ORDER", type="primary", use_container_width=True):
                    supabase.table("beer_game").update({"order_placed": order_amt}).eq("id", curr['id']).execute()
                    process_team_advance(st.session_state.team, curr['week'])
                    st.rerun()
            else:
                st.success("Order Recorded. Waiting for partners...")
                time.sleep(5); st.rerun()

# --- INSTRUCTOR CONTROL ---
elif st.session_state.page == "instructor_dashboard":
    st.title("🎮 Instructor Panel")
    if st.text_input("Access Key", type="password") == "beer123":
        if st.button("RESET GAME & CLEAR USERS", use_container_width=True):
            supabase.table("beer_game").delete().neq("week", -1).execute()
            for t in ["A", "B", "C"]:
                for r in ["Retailer", "Wholesaler", "Distributor", "Manufacturer"]:
                    # Seed week 1 with 12 units (MA Systems Start)
                    supabase.table("beer_game").insert({"team":t,"role":r,"week":1,"inventory":12,"backlog":0,"total_cost":0,"player_name":None}).execute()
            supabase.table("game_settings").update({"game_active": False, "current_demand": 4}).eq("id", 1).execute()
            st.success("Reset Complete.")

        if st.button("START / STOP GAME", type="primary", use_container_width=True):
            supabase.table("game_settings").update({"game_active": not game_active}).eq("id", 1).execute(); st.rerun()
        
        st.divider()
        for t in ["A", "B", "C"]:
            if st.button(f"Advance Team {t}", use_container_width=True):
                latest = supabase.table("beer_game").select("week").eq("team", t).order("week", desc=True).limit(1).execute()
                process_team_advance(t, latest.data[0]['week'], forced=True); st.rerun()
