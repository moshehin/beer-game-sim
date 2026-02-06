import streamlit as st
import pandas as pd
import time
from supabase import create_client

# 1. DATABASE CONNECTION
# Ensure these match the names you put in Streamlit Secrets!
URL = st.secrets["SUPABASE_URL"]
KEY = st.secrets["SUPABASE_KEY"]
supabase = create_client(URL, KEY)

# 2. MATH ENGINE (Advanced Week Logic)
def process_team_advance(team_name, week):
    res = supabase.table("beer_game").select("*").eq("team", team_name).eq("week", week).execute()
    players = {p['role']: p for p in res.data if p['order_placed'] is not None}
    
    if len(players) < 4:
        return # Wait until all 4 roles submit

    # Fetch demand from Admin settings
    settings = supabase.table("game_settings").select("current_demand").eq("id", 1).single().execute()
    cust_demand = settings.data['current_demand']
    
    demand_flow = {
        'Retailer': cust_demand,
        'Wholesaler': players.get('Retailer', {}).get('order_placed', 0),
        'Distributor': players.get('Wholesaler', {}).get('order_placed', 0),
        'Factory': players.get('Distributor', {}).get('order_placed', 0)
    }

    for role in ['Retailer', 'Wholesaler', 'Distributor', 'Factory']:
        p = players[role]
        demand = demand_flow[role] + p['backlog']
        shipped = min(p['inventory'], demand)
        new_backlog = demand - shipped
        new_inv = (p['inventory'] - shipped) + 4 # Simulating 2-week lead time arrivals
        weekly_cost = (new_inv * 0.5) + (new_backlog * 1.0)
        
        supabase.table("beer_game").insert({
            "team": team_name, "role": role, "week": week + 1,
            "inventory": new_inv, "backlog": new_backlog,
            "total_cost": p['total_cost'] + weekly_cost,
            "order_placed": None
        }).execute()

# 3. USER INTERFACE
st.set_page_config(page_title="Beer Game Simulator", layout="wide")
view_mode = st.sidebar.radio("Navigation", ["Student Portal", "Instructor Dashboard"])

if view_mode == "Student Portal":
    st.title("🍺 Beer Game: Student Portal")
    team = st.sidebar.selectbox("Select Team", ["A", "B", "C"])
    role = st.sidebar.selectbox("Select Role", ["Retailer", "Wholesaler", "Distributor", "Factory"])
    
    # SAFE DATA FETCHING
    res = supabase.table("beer_game").select("*").eq("team", team).eq("role", role).order("week", desc=True).limit(1).execute()
    
    if not res.data:
        st.error(f"⚠️ No data found for Team {team} - {role}. Ensure you seeded the database!")
        st.stop()
    
    data = res.data[0]

    if data['order_placed'] is not None:
        st.info(f"Week {data['week']} submitted. Waiting for teammates...")
        if st.button("Refresh Status"): st.rerun()
    else:
        st.header(f"Week {data['week']} | {role}")
        
        # 20-SECOND TIMER
        if 'start_t' not in st.session_state: st.session_state.start_t = time.time()
        elapsed = time.time() - st.session_state.start_t
        timer = max(0, 20 - int(elapsed))
        
        st.metric("Inventory", int(data['inventory']), f"{int(data['backlog'])} Backlog", delta_color="inverse")
        
        order_input = st.number_input("Order Quantity:", min_value=0, step=1, key="order_box")
        
        if timer <= 0:
            st.error("Time Expired! Submitting 0.")
            supabase.table("beer_game").update({"order_placed": 0}).eq("id", data['id']).execute()
            process_team_advance(team, data['week'])
            if 'start_t' in st.session_state: del st.session_state.start_t
            st.rerun()

        if st.button(f"Submit Order ({timer}s)"):
            supabase.table("beer_game").update({"order_placed": order_input}).eq("id", data['id']).execute()
            process_team_advance(team, data['week'])
            if 'start_t' in st.session_state: del st.session_state.start_t
            st.rerun()
        
        time.sleep(1)
        st.rerun()

else:
    st.title("📊 Instructor Dashboard")
    
    # Market Demand Slider
    st.subheader("Market Controls")
    set_res = supabase.table("game_settings").select("current_demand").eq("id", 1).single().execute()
    current_d = set_res.data['current_demand']
    
    new_d = st.slider("Customer Demand", 0, 20, int(current_d))
    if st.button("Update Market Demand"):
        supabase.table("game_settings").update({"current_demand": new_d}).eq("id", 1).execute()
        st.success(f"Demand updated to {new_d}")

    # Graphs
    all_data = supabase.table("beer_game").select("team, role, week, order_placed, total_cost").execute()
    df = pd.DataFrame(all_data.data)
    
    if not df.empty:
        st.subheader("The Bullwhip Effect")
        sel_team = st.selectbox("View Team Graph", ["A", "B", "C"])
        t_df = df[(df['team'] == sel_team) & (df['order_placed'].notnull())]
        if not t_df.empty:
            chart_data = t_df.pivot(index='week', columns='role', values='order_placed')
            st.line_chart(chart_data)
        
        st.subheader("Total Costs")
        costs = df.groupby("team")["total_cost"].max()
        st.bar_chart(costs)
