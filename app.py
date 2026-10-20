"""ScholarForge — autonomous opportunity agent for students. Run with: streamlit run app.py"""
import streamlit as st

from core import db
from core.views import audit_page, profile_page, results_page, run_page

st.set_page_config(page_title="ScholarForge", page_icon="🔥", layout="wide")
db.init()

run = st.Page(run_page, title="Run Agent", icon=":material/play_circle:", default=True)
results = st.Page(results_page, title="Results", icon=":material/list:")
profile = st.Page(profile_page, title="Profile", icon=":material/person:")
audit = st.Page(audit_page, title="Audit log", icon=":material/history:")
st.session_state["_results_page"] = results

st.navigation([run, results, profile, audit]).run()
