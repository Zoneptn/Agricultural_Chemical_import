"""Shared IRAC/HRAC/FRAC classification-detail rendering, used by both the
Overview page (one chemical at a time) and the Comparison page (several)."""
import streamlit as st

from common import classify_by_component


def render_classification_expanders(chem_names, classification_tables):
    """One expander per unique chemical name, each component of a mixture
    shown as its own labeled block so long bilingual mode-of-action text
    never gets crammed into a table cell."""
    unique_chems = list(dict.fromkeys(chem_names))
    if not unique_chems:
        st.info("Pick a chemical above to see its IRAC/HRAC/FRAC classification.")
        return

    for name in unique_chems:
        breakdown = classify_by_component(name, classification_tables)
        with st.expander(name, expanded=(len(unique_chems) == 1)):
            is_mixture = len(breakdown) > 1
            for entry in breakdown:
                if is_mixture:
                    st.markdown(f"**Component: {entry['component']}**")
                if not entry["matches"]:
                    st.caption("No IRAC/HRAC/FRAC match found for this component.")
                else:
                    for m in entry["matches"]:
                        st.markdown(f"**{m['system']}** — Code {m['code']}")
                        st.markdown(f"- Physiological category: {m['physiological_category']}")
                        st.markdown(f"- Mode of action: {m['mode_of_action']}")
                        st.markdown(f"- Chemical class/group: {m['chemical_class_group']}")
                if is_mixture and entry is not breakdown[-1]:
                    st.divider()
