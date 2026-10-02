import streamlit as st

from common import load_reg_no, reload_all
from supplier import (
    ROLE_COLUMNS,
    manufacturer_options,
    manufacturing_country_options,
    company_portfolio,
    render_supplier_profile,
    render_new_entrants,
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

role = st.radio("View by", list(ROLE_COLUMNS.keys()), horizontal=True, key="supplier_role")

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

valid_choices = [PLACEHOLDER] + options
if st.session_state.get("supplier_company") not in valid_choices:
    # clear a company left over from a previous role — e.g. an origin
    # country picked under "Manufacturing country" isn't a valid choice
    # after switching to "Importer", and Streamlit errors on a selectbox
    # whose stored value isn't in its current options list
    st.session_state["supplier_company"] = PLACEHOLDER
company = st.selectbox(f"Choose a {role.lower()}", valid_choices, key="supplier_company")
active_only = st.checkbox("Show only active (non-expired) registrations", value=True, key="supplier_active_only")

st.divider()

if company == PLACEHOLDER:
    st.info(f"Pick a {role.lower()} above to see their registration portfolio.")
else:
    portfolio = company_portfolio(reg_df, role, company, active_only)
    render_supplier_profile(portfolio, role, company)

st.divider()

st.subheader(f"New entrants by year — {role.lower()}s")
st.caption(
    f"Which {role.lower()}s first show up in reg_no each year (by their earliest issued registration), "
    "and how much they've filed since — independent of the company picked above."
)
render_new_entrants(reg_df, role)
