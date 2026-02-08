# --- WINDOW 4: INSTRUCTOR DASHBOARD ---
elif st.session_state.page == "instructor_dashboard":
    st.title("🎮 Instructor Control Room")
    if st.text_input("Password", type="password") == "beer123":
        
        # --- TOP CONTROLS ---
        c1, c2 = st.columns(2)
        with c1:
            if st.button("START / STOP GAME", type="primary", use_container_width=True):
                supabase.table("game_settings").update({"game_active": not game_active}).eq("id", 1).execute(); st.rerun()
        with c2:
            if st.button("♻️ FULL RESET", use_container_width=True):
                supabase.table("beer_game").delete().neq("week", -1).execute()
                for t in ["A", "B", "C"]:
                    for r in ["Retailer", "Wholesaler", "Distributor", "Manufacturer"]:
                        supabase.table("beer_game").insert({"team":t,"role":r,"week":1,"inventory":12,"backlog":0,"total_cost":0,"player_name":None}).execute()
                supabase.table("game_settings").update({"game_active": False, "current_demand": 4}).eq("id", 1).execute()
                st.rerun()

        # --- LIVE ANALYTICS GRAPHS ---
        st.divider()
        st.subheader("📈 Live Supply Chain Analytics")
        
        # Fetch all game data for graphing
        graph_res = supabase.table("beer_game").select("team", "role", "week", "inventory", "order_placed", "incoming_delivery", "total_cost").order("week").execute()
        
        if graph_res.data:
            df_graph = pd.DataFrame(graph_res.data)
            
            # Allow instructor to filter by Team and Role for specific analysis
            view_team = st.selectbox("View Team Data", ["A", "B", "C"])
            team_df = df_graph[df_graph['team'] == view_team]

            tab1, tab2, tab3, tab4 = st.tabs(["Stock Levels", "Orders Placed", "Deliveries", "Accumulated Cost"])
            
            with tab1:
                st.line_chart(team_df.pivot(index='week', columns='role', values='inventory'))
            with tab2:
                st.line_chart(team_df.pivot(index='week', columns='role', values='order_placed'))
            with tab3:
                st.line_chart(team_df.pivot(index='week', columns='role', values='incoming_delivery'))
            with tab4:
                st.line_chart(team_df.pivot(index='week', columns='role', values='total_cost'))

        # --- DEMAND & TEAM MANAGEMENT ---
        st.divider()
        st.subheader("Market Demand Control")
        if market_demand == 8:
            st.warning("⚡ AUTO-SHOCK ACTIVE: Demand is locked at 8 (Week 5+ reached).")
        
        new_demand = st.slider("Manual Adjustment", 0, 20, int(market_demand))
        if st.button("Update Demand"):
            supabase.table("game_settings").update({"current_demand": new_demand}).eq("id", 1).execute(); st.rerun()

        st.divider()
        st.subheader("Team Progress")
        for t in ["A", "B", "C"]:
            latest = supabase.table("beer_game").select("week").eq("team", t).order("week", desc=True).limit(1).execute()
            current_w = latest.data[0]['week'] if latest.data else 1
            if st.button(f"Advance Team {t} (Currently Week {current_w})", use_container_width=True):
                process_team_advance(t, current_w, forced=True); st.rerun()
