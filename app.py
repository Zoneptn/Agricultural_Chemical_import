import streamlit as st

st.set_page_config(page_title="Chemical Import Dashboard", layout="wide")

overview_page = st.Page("views/overview.py", title="Chemical Overview", icon="🧪", default=True)
comparison_page = st.Page("views/comparison_page.py", title="Chemical Comparison", icon="🔬")
search_page = st.Page("views/registration_search.py", title="Registration Search", icon="🔎")
market_page = st.Page("views/market_summary.py", title="Market Summary", icon="📊")
supplier_page = st.Page("views/supplier_profile.py", title="Supplier Profile", icon="🏢")
cumulative_page = st.Page("views/cumulative_analysis.py", title="Cumulative Analysis", icon="📈")

nav = st.navigation([overview_page, comparison_page, search_page, market_page, supplier_page, cumulative_page])
nav.run()
