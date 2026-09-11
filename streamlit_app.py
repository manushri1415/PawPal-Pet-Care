import streamlit as st

pg = st.navigation(
    [
        st.Page("app.py", title="Dashboard", icon="🐾", default=True),
        st.Page("pages/1_Health_Records.py", title="Health Records", icon="🩺"),
    ],
    position="top",
)
pg.run()
