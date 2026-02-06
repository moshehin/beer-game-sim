import streamlit as st
import pandas as pd
import time
from supabase import create_client

# 1. DATABASE CONNECTION
# Accessing keys from Streamlit Secrets
URL = st.secrets["SUPABASE_URL"]
KEY = st.secrets["SUPABASE_KEY"]
supabase = create_client(URL, KEY)

# 2. THE MATH ENGINE (1-Week Lead Time Logic)
def process_team_advance(team_name, week, forced=False):
    # Fetch all players for the current team and week
    res = supabase.table("beer_game").select("*").eq("team", team_name).eq("week", week).execute()
    players = {p['role']: p for p in res.data}
    submitted = [p for p in res.data if p['order_placed'] is not None]
    
    # Check if all 4 roles have submitted (unless forced by Admin)
    if not forced and len(submitted) < 4:
        return 

    # Fetch current market demand from settings
    settings = supabase.table("game_settings").select("current_demand").eq("id", 1).single().execute()
    cust_demand = settings.data['current_demand']
    
    # Supply Chain Flow: Retailer -> Wholesaler -> Distributor -> Manufacturer
    roles = ['Retailer', 'Wholesaler', 'Distributor', 'Manufacturer']
    
    for i, role in enumerate(roles):
        p = players.get(role)
        if not p: continue
        
        # Determine Demand: From external customer or downstream partner
        if i == 0:
            demand_val = cust_demand
        else:
            prev_role = roles[i-1]
            # Demand is the order placed by the player below in the chain
            demand_val = players[prev_role]['order_placed'] if players[prev_role]['order_placed'] is not None else 0
            
        total_needed = demand_val + p['backlog']
        shipped = min(p['inventory'], total_needed)
        new_backlog = total_needed - shipped
        
        # --- 1-WEEK LEAD TIME LOGIC ---
        # The 'incoming_stock' is exactly what THIS player ordered in the week just finished.
        incoming_stock = p['order_placed'] if p['order_placed'] is not None else 0
        
        new_inv = (p['inventory'] - shipped) + incoming_stock
        weekly_cost = (new_inv * 0.5) + (new_backlog * 1.0)
        
        # Insert the state for the next week
        supabase.table("beer_game").insert({
            "team": team_name, 
            "role": role, 
            "week": week + 1,
            "inventory": new_inv, 
            "backlog": new_backlog,
            "total_cost": p['total_cost'] + weekly_cost,
            "order_placed": None
        }).execute()

# 3. INTERFACE CONFIGURATION
st.set_page_config(page_title="Beer Game Simulator", layout="wide")

# Fetch Global Game State from Supabase
try:
    settings_res = supabase.table("game_settings").select("*").eq("id", 1).single().execute()
    game_active = settings_res.data['game_active']
    market_demand = settings_res.data['current_demand']
except Exception:
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
                name_alias = st.text_input("Type in your name or alias")
                
                if not game_active:
                    st.warning("The game hasn't started yet. Please wait for your instructor.")
                
                c1, c2 = st.columns(2)
                with c2:
                    btn_label = "LET'S GO!"
                    if st.button(btn_label, type="primary", use_container_width=True, disabled=not (name_alias and game_active)):
                        st.session_state.update({"team": t_choice, "role": r_choice, "name": name_alias, "joined": True})
                        st.rerun()
                with c1:
                    if st.button("CANCEL", use_container_width=True):
                        st.toast("Selection reset.")

  # PLAYER DASHBOARD UI (Matches your reference image)
    else:
        st.markdown(f"### 🍺 {st.session_state.role.upper()} | {st.session_state.name.upper()} (Team {st.session_state.team})")
        
        # Fetch latest data for this player
        res = supabase.table("beer_game").select("*").eq("team", st.session_state.team).eq("role", st.session_state.role).order("week", desc=True).limit(1).execute()
        
        if res.data:
            data = res.data[0]
            
            # Layout Grid
            r1c1, r1c2 = st.columns(2)
            r2c1, r2c2 = st.columns(2)
            r3c1, r3c2 = st.columns(2)

            with r1c1:
                with st.container(border=True):
                    st.write("📥 **Customer Order**")
                    # Simplified logic: Retailer sees market demand, others see '?' or hidden value
                    display_demand = market_demand if st.session_state.role == "Retailer" else "?"
                    st.title(display_demand)
                    st.caption("→ 0% change")

            with r1c2:
                with st.container(border=True):
                    st.write("🚚 **Outgoing transport**")
                    st.write("*Leaving next week*")
                    st.title("4") 
                    st.caption("→ 0% change")

            with r2c1:
                with st.container(border=True):
                    st.write(f"📅 **Week: {data['week']}**")
                    m1, m2 = st.columns(2)
                    # Simulated Gauges using metrics
                    m1.metric("Current week costs", f"${int(data['inventory']*0.5 + data['backlog']*1)}")
                    m2.metric("Total costs", f"${int(data['total_cost'])}")

            with r2c2:
                with st.container(border=True):
                    st.write("📦 **Stock**")
                    st.title(int(data['inventory']))
                    if data['backlog'] > 0:
                        st.error(f"Backlog: {int(data['backlog'])}")
                    st.caption("→ 0% change")

            with r3c1:
                with st.container(border=True):
                    st.write("📝 **New order**")
                    if data['order_placed'] is None:
                        val = st.number_input("Enter amount", min_value=0, step=1, label_visibility="collapsed")
                        if st.button("➕ PLACE ORDER", type="primary", use_container_width=True):
                            supabase.table("beer_game").update({"order_placed": val}).eq("id", data['id']).execute()
                            process_team_advance(st.session_state.team, data['week'])
                            st.rerun()
                    else:
                        st.success("Order placed! Waiting for teammates...")
                        if st.button("Refresh Week"): st.rerun()

            with r3c2:
                with st.container(border=True):
                    st.write("🏗️ **Lead time status**")
                    st.write(f"Arriving next week: **{data['order_placed'] if data['order_placed'] is not None else '---'}**")
                    st.caption("1-Week Lead Time Active")

# --- INSTRUCTOR DASHBOARD ---
else:
    st.title("📊 Instructor Control Panel")
    
    # Global Controls
    col_a, col_b = st.columns(2)
    with col_a:
        if not game_active:
            if st.button("🚀 ACTIVATE GAME", type="primary", use_container_width=True):
                supabase.table("game_settings").update({"game_active": True}).eq("id", 1).execute()
                st.rerun()
        else:
            if st.button("🛑 STOP GAME", use_container_width=True):
                supabase.table("game_settings").update({"game_active": False}).eq("id", 1).execute()
                st.rerun()
    
    with col_b:
        new_d = st.slider("Set Market Demand", 0, 20, int(market_demand))
        if st.button("Update Demand"):
            supabase.table("game_settings").update({"current_demand": new_d}).eq("id", 1).execute()
            st.success(f"Market demand set to {new_d}")

    st.divider()
    
    # Manual Progression
    st.subheader("Force Team Progress")
    cols = st.columns(3)
    for i, t in enumerate(["A", "B", "C"]):
        with cols[i]:
            latest = supabase.table("beer_game").select("week").eq("team", t).order("week", desc=True).limit(1).execute()
            if latest.data:
                curr_w = latest.data[0]['week']
                if st.button(f"Advance Team {t} (Week {curr_w})"):
                    process_team_advance(t, curr_w, forced=True)
                    st.success(f"Team {t} pushed to Week {curr_w + 1}")
