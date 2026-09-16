import streamlit as st

st.set_page_config(page_title="Chemical Import Dashboard", layout="wide")

overview_page = st.Page("views/overview.py", title="Chemical Overview", icon="🧪", default=True)
comparison_page = st.Page("views/comparison_page.py", title="Chemical Comparison", icon="🔬")

nav = st.navigation([overview_page, comparison_page])
nav.run()
