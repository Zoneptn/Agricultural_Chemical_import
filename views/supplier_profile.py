import streamlit as st

from common import load_reg_no, reload_all
from supplier import (
    ROLE_COLUMNS,
    manufacturer_options,
    manufacturing_country_options,
    company_portfolio,
    render_supplier_profile,
)

reg_df = load_reg_no()

st.title("🏢 Supplier Profile")
st.caption(
    "Registration portfolio for a manufacturer, manufacturing country, importer, or distributor, "
    "built from reg_no. Import quantity and value aren't shown here — master_import records only "
    "the shipment's origin country, not which company or manufacturing country handled it, so "
    "there's no link between the two."
)

st.sidebar.header("Data")
if st.sidebar.button("🔄 Reload data"):
    reload_all()
    st.rerun()

role = st.radio("View by", list(ROLE_COLUMNS.keys()), horizontal=True)

PLACEHOLDER = "— Select —"
if role == "Manufacturer (source)":
    options = manufacturer_options(reg_df)
    st.caption("Manufacturer names come straight from reg_no's source field — near-duplicate spellings may appear as separate entries.")
elif role == "Manufacturing country":
    options = manufacturing_country_options(reg_df)
    st.caption(
        "A registration can list several manufacturers across different countries — it counts toward "
        "every country involved, not just one."
    )
else:
    options = sorted(reg_df[ROLE_COLUMNS[role]].unique())

company = st.selectbox(f"Choose a {role.lower()}", [PLACEHOLDER] + options)
active_only = st.checkbox("Show only active (non-expired) registrations", value=True)

st.divider()

if company == PLACEHOLDER:
    st.info(f"Pick a {role.lower()} above to see their registration portfolio.")
else:
    portfolio = company_portfolio(reg_df, role, company, active_only)
    render_supplier_profile(portfolio, role, company)
