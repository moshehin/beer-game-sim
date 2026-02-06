import streamlit as st
import pandas as pd
import time
from supabase import create_client

# 1. DATABASE CONNECTION
URL = st.secrets["SUPABASE_URL"]
KEY = st.secrets["SUPABASE_KEY"]
supabase = create_client(URL, KEY)

# 2. MATH ENGINE
def process_team_advance(team_name, week):
    # Check if all 4 roles have submitted for this week
    res = supabase.table("beer_game").select("*").eq("team", team_name).eq("week", week).execute()
    players = {p['role']: p for p in res.data if p['order_placed'] is not None}
    
    if len(players) < 4:
        return # Not everyone is ready yet

    # Fetch demand from Admin settings
    settings = supabase.table("game_settings").select("current_demand").eq("id", 1).single().execute()
    cust_demand = settings.data['current_demand']
    
    # Map who orders from whom
    demand_flow = {
        'Retailer': cust_demand,
        'Wholesaler': players['Retailer']['order_placed'],
        'Distributor': players['Wholesaler']['order_placed'],
        'Factory': players['Distributor']['order_placed']
    }

    for role, p in players.items():
        demand = demand_flow[role] + p['backlog']
        shipped = min(p['inventory'], demand)
        new_backlog = demand - shipped
        
        # Simple lead time: incoming is the order from 2 weeks ago (using 4 for stability)
        new_inv = (p['inventory'] - shipped) + 4 
        
        # Costs: $0.50 holding, $1.00 backlog
        weekly_cost = (new_inv * 0.5) + (new_backlog * 1.0)
        
        # Create Week + 1
        supabase.table("beer_game").insert({
            "team": team_name, "role": role, "week": week + 1,
            "inventory": new_inv, "backlog": new_backlog,
            "total_cost": p['total_cost'] + weekly_cost,
            "order_placed": None
        }).execute()

# 3. INTERFACE
st.set_page_config(page_title="Supply Chain Beer Game", layout="wide")
view = st.sidebar.radio("Navigation", ["Student Portal", "Instructor Dashboard"])

if view == "Student Portal":
    team = st.selectbox("Select Team", ["A", "B", "C"])
    role = st.selectbox("Select Role", ["Retailer", "Wholesaler", "Distributor", "Factory"])
    
    # Get latest data
   # 1. Get the response from Supabase
response = supabase.table("beer_game").select("*").eq("team", team).eq("role", role).order("week", desc=True).limit(1).execute()

# 2. Check if the list of data has anything in it before accessing [0]
if len(response.data) > 0:
    data = response.data[0]
else:
    st.error(f"Error: No data found for Team {team} and Role {role}. Check your Supabase table!")
    st.stop() # This stops the app gracefully instead of crashing

    if data['order_placed'] is not None:
        st.info(f"Week {data['week']} submitted. Waiting for your team...")
        if st.button("Refresh"): st.rerun()
    else:
        st.header(f"Week {data['week']} | {role}")
        
        # TIMER LOGIC
        if 'start' not in st.session_state: st.session_state.start = time.time()
        timer = 20 - int(time.time() - st.session_state.start)
        
        st.metric("Inventory", int(data['inventory']), f"{int(data['backlog'])} Backlog", delta_color="inverse")
        
        order = st.number_input("Order Quantity:", min_value=0, step=1)
        
        if timer <= 0:
            supabase.table("beer_game").update({"order_placed": 0}).eq("id", data['id']).execute()
            process_team_advance(team, data['week'])
            del st.session_state.start
            st.rerun()

        if st.button(f"Submit Order ({timer}s)"):
            supabase.table("beer_game").update({"order_placed": order}).eq("id", data['id']).execute()
            process_team_advance(team, data['week'])
            del st.session_state.start
            st.rerun()
        
        time.sleep(1)
        st.rerun()

else:
    st.title("Instructor Dashboard")
    
    # DEMAND CONTROL
    st.subheader("Market Controls")
    current_set = supabase.table("game_settings").select("current_demand").eq("id", 1).single().execute().data['current_demand']
    new_d = st.slider("Customer Demand", 0, 20, int(current_set))
    if st.button("Update Demand"):
        supabase.table("game_settings").update({"current_demand": new_d}).eq("id", 1).execute()
        st.success(f"Demand is now {new_d}!")

    # LIVE GRAPHS
    all_res = supabase.table("beer_game").select("team, role, week, order_placed, total_cost").execute()
    df = pd.DataFrame(all_res.data)
    if not df.empty:
        st.subheader("The Bullwhip (Orders by Week)")
        chart_team = st.selectbox("Select Team to View", ["A", "B", "C"])
        team_df = df[df['team'] == chart_team].pivot(index='week', columns='role', values='order_placed')
        st.line_chart(team_df)
