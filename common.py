"""Shared data loading and helpers for the Chemical Import Dashboard (multipage app)."""
import datetime

import pandas as pd
import streamlit as st

DATA_PATH = "chemical_import_database.xlsx"


@st.cache_data
def load_master_import():
    df = pd.read_excel(DATA_PATH, sheet_name="master_import")
    # fillna BEFORE astype(str): pyarrow-backed string columns keep NaN as
    # float, not the string "nan", so fillna has to happen first
    df["formulation_type"] = df["formulation_type"].fillna("Unspecified")
    for col in ["common_name", "concentration", "formulation_type", "origin"]:
        df[col] = df[col].astype(str).str.strip()
    return df


@st.cache_data
def load_reg_no():
    df = pd.read_excel(DATA_PATH, sheet_name="reg_no")
    df["formulation_type"] = df["formulation_type"].fillna("Unspecified")
    for col in ["common_name", "concentration", "formulation_type", "trade_name", "source", "register", "distributor", "status"]:
        df[col] = df[col].astype(str).str.strip()
    return df


@st.cache_data
def load_classifications():
    """IRAC (insecticides), HRAC (herbicides), FRAC (fungicides) mode-of-action
    tables, keyed by a normalized common_name for lookup."""
    tables = {}
    for system in ["irac", "hrac", "frac"]:
        sub = pd.read_excel(DATA_PATH, sheet_name=system)
        sub["_norm_name"] = sub["common_name"].astype(str).str.strip().str.lower()
        tables[system.upper()] = sub
    return tables


def classify_chemical(common_name, tables):
    """Look up a common_name (splitting on '+' for mixtures) against all three
    mode-of-action systems. Returns a list of dict rows, one per component/system hit."""
    rows = []
    for component in str(common_name).split("+"):
        comp_norm = component.strip().lower()
        if not comp_norm:
            continue
        for system, tbl in tables.items():
            hits = tbl[tbl["_norm_name"] == comp_norm]
            for _, hit in hits.iterrows():
                row = {
                    "Component": component.strip(),
                    "System": system,
                    "Physiological category": hit.get("physiological_category", ""),
                    "Mode of action": hit.get("mode_of_action", ""),
                    "Chemical class/group": hit.get("chemical_class", hit.get("chemical_group", "")),
                    "Code": str(hit.get("code", "")),
                }
                rows.append(row)
    return rows


def not_expired(reg_df):
    """Registrations with no expiry date on record are kept (treated as
    still active); everything else needs expire >= today."""
    today = pd.Timestamp(datetime.date.today())
    return reg_df[reg_df["expire"].isna() | (reg_df["expire"] >= today)]


def reload_all():
    load_master_import.clear()
    load_reg_no.clear()
    load_classifications.clear()


def cross_filter_options(df, col, filter_cols, filter_keys, extra_mask=None):
    """Options for `col`, narrowed by every OTHER filter's current session_state
    selection, so any filter can narrow any other regardless of pick order."""
    sub = df if extra_mask is None else df[extra_mask]
    for other in filter_cols:
        if other == col:
            continue
        other_sel = st.session_state.get(filter_keys[other], [])
        if other_sel:
            sub = sub[sub[other].isin(other_sel)]
    return sorted(sub[col].unique())


def render_cross_filters(df, filter_cols, filter_labels, filter_keys, slots, extra_mask=None):
    """Renders one multiselect per column in `slots` (a dict col -> st column),
    cross-narrowing options against every other filter's current selection.
    Returns a dict col -> selected values."""
    sel = {}
    for col in filter_cols:
        with slots[col]:
            opts = cross_filter_options(df, col, filter_cols, filter_keys, extra_mask)
            key = filter_keys[col]
            if key in st.session_state:
                valid = [v for v in st.session_state[key] if v in opts]
                if valid != st.session_state[key]:
                    st.session_state[key] = valid
            sel[col] = st.multiselect(filter_labels[col], opts, key=key)
            if len(opts) == 1:
                st.caption(f"Only one {filter_labels[col].lower()} matches the other filters.")
    return sel
