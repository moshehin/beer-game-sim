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
    game_active = False; market_demand = 4

# --- WINDOW 1: LANDING ---
if st.session_state.page == "landing":
    st.title("🏭 Beer Game: Supply Chain Simulator")
    st.subheader("Operations Club Session")
    st.write("Optimize inventory and master the bullwhip effect in this 20-week logistics simulation.")
    
    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("📦 STUDENT ENTRANCE", use_container_width=True, type="primary"):
            st.session_state.page = "student_join"; st.rerun()
    with col_b:
        if st.button("🛡️ COMMAND CENTER", use_container_width=True):
            st.session_state.page = "instructor_dashboard"; st.rerun()

# --- WINDOW 2: STUDENT JOIN ---
elif st.session_state.page == "student_join" and not st.session_state.joined:
    with st.container(border=True):
        st.subheader("Register Unit")
        t_choice = st.selectbox("Assign Team", ["A", "B", "C"])
        r_choice = st.selectbox("Assign Role", ["Retailer", "Wholesaler", "Distributor", "Manufacturer"])
        
        check = supabase.table("beer_game").select("player_name").eq("team", t_choice).eq("role", r_choice).neq("player_name", "null").order("week", desc=True).limit(1).execute()
        is_taken = len(check.data) > 0 and check.data[0]['player_name'] not in [None, "", "null"]
        
        if is_taken:
            st.error(f"⚠️ Unit Taken: {check.data[0]['player_name']}")
            st.button("LOCKED", disabled=True, use_container_width=True)
        else:
            name = st.text_input("Enter Name")
            if st.button("INITIALIZE", type="primary", use_container_width=True, disabled=not name):
                supabase.table("beer_game").update({"player_name": name}).eq("team", t_choice).eq("role", r_choice).execute()
                st.session_state.update({"team": t_choice, "role": r_choice, "name": name, "joined": True})
                st.rerun()

# --- WINDOW 3: STUDENT DASHBOARD ---
elif st.session_state.page == "student_join" and st.session_state.joined:
    if not game_active:
        st.info(f"🏗️ Welcome, {st.session_state.name}. Awaiting distribution network activation..."); time.sleep(4); st.rerun()

    res = supabase.table("beer_game").select("*").eq("team", st.session_state.team).eq("role", st.session_state.role).order("week", desc=True).limit(1).execute()
    
    if res.data:
        curr = res.data[0]
        wk = curr['week']

        if wk > 20:
            st.balloons()
            st.header("🏁 20-Week Audit Complete")
            st.success(f"Simulation ended for Team {st.session_state.team}.")
            f1, f2 = st.columns(2)
            f1.metric("Final Cumulative Cost", f"${curr['total_cost']:.2f}")
            f2.metric("Final Inventory", int(curr['inventory']))
            st.stop()

        st.header(f"🏢 {st.session_state.role} Unit")
        st.markdown(f"**Week:** {wk} / 20 | **Team:** {st.session_state.team}")
        
        c1, c2 = st.columns(2)
        with c1:
            st.metric("📦 Inventory Level", int(curr['inventory']), f"{int(curr['backlog'])} Backlog", delta_color="inverse")
            st.metric("📥 Customer Order", market_demand if st.session_state.role == "Retailer" else curr.get('last_demand', 0))
        with c2:
            st.metric("🏗️ Incoming Cargo", curr.get('incoming_delivery', 4))
            st.metric("🚚 Outgoing Shipment", curr.get('last_shipped', 0))
        
        st.divider()
        weekly_c = (curr['inventory'] * 0.5) + (curr['backlog'] * 1.0)
        cl, cr = st.columns(2)
        with cl:
            cw = "cost-high" if weekly_c > 10 else "cost-normal"
            st.markdown(f"**Period Cost:** <span class='{cw}'>${weekly_c:.2f}</span>", unsafe_allow_html=True)
        with cr:
            ct = "cost-high" if curr['total_cost'] > 100 else "cost-normal"
            st.markdown(f"**Total Cost:** <span class='{ct}'>${curr['total_cost']:.2f}</span>", unsafe_allow_html=True)

        with st.container(border=True):
            if curr['order_placed'] is None:
                val = st.number_input("Procurement Order", min_value=0, step=1, value=4)
                if st.button("AUTHORIZE ORDER", type="primary", use_container_width=True):
                    supabase.table("beer_game").update({"order_placed": val}).eq("id", curr['id']).execute()
                    process_team_advance(st.session_state.team, wk)
                    st.rerun()
            else:
                st.success("🚚 Order Sent. Waiting for sync..."); time.sleep(5); st.rerun()

# --- WINDOW 4: INSTRUCTOR DASHBOARD ---
elif st.session_state.page == "instructor_dashboard":
    st.title("🛡️ COMMAND CENTER")
    pwd = st.text_input("Admin Credentials", type="password")
    
    if pwd == "beer123":
        c1, c2 = st.columns(2)
        with c1:
            btn_txt = "⏹️ HALT GAME" if game_active else "▶️ START GAME"
            if st.button(btn_txt, type="primary", use_container_width=True):
                supabase.table("game_settings").update({"game_active": not game_active}).eq("id", 1).execute(); st.rerun()
        with c2:
            if st.button("♻️ FULL GRID RESET", use_container_width=True):
                supabase.table("beer_game").delete().neq("week", -1).execute()
                for t in ["A", "B", "C"]:
                    for r in ["Retailer", "Wholesaler", "Distributor", "Manufacturer"]:
                        supabase.table("beer_game").insert({"team":t,"role":r,"week":1,"inventory":12,"backlog":0,"total_cost":0,"player_name":None}).execute()
                supabase.table("game_settings").update({"game_active": False, "current_demand": 4}).eq("id", 1).execute(); st.rerun()

        # --- THE DEMAND ADJUSTER ---
        st.divider()
        with st.expander("🎯 MARKET DEMAND CONTROL", expanded=True):
            st.write(f"Current Demand Level: **{market_demand} units**")
            new_demand = st.slider("Set New Demand", 0, 20, int(market_demand))
            if st.button("APPLY DEMAND CHANGE", use_container_width=True):
                supabase.table("game_settings").update({"current_demand": new_demand}).eq("id", 1).execute()
                st.success(f"Market demand updated to {new_demand}!"); time.sleep(1); st.rerun()

        # Roster & Analytics
        st.divider()
        st.subheader("👥 Personnel Roster")
        roster = supabase.table("beer_game").select("team", "role", "player_name").neq("player_name", "null").order("team").execute()
        if roster.data: st.table(pd.DataFrame(roster.data).drop_duplicates())

        st.divider()
        st.subheader("📈 Supply Chain Analytics")
        graph_data = supabase.table("beer_game").select("*").order("week").execute()
        if graph_data.data:
            df = pd.DataFrame(graph_data.data)
            t_sel = st.selectbox("Analyze Team", ["A", "B", "C"])
            tdf = df[df['team'] == t_sel]
            tabs = st.tabs(["Inventory", "Orders", "Costs"])
            with tabs[0]: st.line_chart(tdf.pivot_table(index='week', columns='role', values='inventory', aggfunc='max'))
            with tabs[1]: st.line_chart(tdf.pivot_table(index='week', columns='role', values='order_placed', aggfunc='max'))
            with tabs[2]: st.line_chart(tdf.pivot_table(index='week', columns='role', values='total_cost', aggfunc='max'))

        st.divider()
        for t in ["A", "B", "C"]:
            latest = supabase.table("beer_game").select("week").eq("team", t).order("week", desc=True).limit(1).execute()
            w_num = latest.data[0]['week'] if latest.data else 1
            if st.button(f"Advance Team {t} (W{w_num})", use_container_width=True):
                process_team_advance(t, w_num, forced=True); st.rerun()
