"""Data loading and cross-page lookups for the Chemical Import Dashboard.

Everything here is pure data — no widgets, no chart rendering. UI-specific
logic lives in filters.py, charts.py, registrations.py, and comparison.py.
"""
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
    df["source_country"] = df["source_country"].fillna("")
    for col in [
        "reg_no", "common_name", "common_name_original", "concentration", "formulation_type",
        "trade_name", "source", "source_country", "register", "importer", "distributor", "status", "category",
    ]:
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


def classify_by_component(common_name, tables):
    """Splits a common_name on '+' (mixtures list multiple active ingredients
    this way) and looks up each component against all three mode-of-action
    systems. Returns one entry per component, in order, even when a component
    has no match — so a 3-way mixture never silently drops a component:
        [{"component": "tebuconazole", "matches": [{"system": "FRAC", ...}]},
         {"component": "azoxystrobin", "matches": [{"system": "FRAC", ...}]}]
    """
    breakdown = []
    for component in str(common_name).split("+"):
        comp_stripped = component.strip()
        comp_norm = comp_stripped.lower()
        if not comp_norm:
            continue
        matches = []
        for system, tbl in tables.items():
            hits = tbl[tbl["_norm_name"] == comp_norm]
            for _, hit in hits.iterrows():
                matches.append({
                    "system": system,
                    "physiological_category": hit.get("physiological_category", ""),
                    "mode_of_action": hit.get("mode_of_action", ""),
                    "chemical_class_group": hit.get("chemical_class", hit.get("chemical_group", "")),
                    "code": str(hit.get("code", "")),
                })
        breakdown.append({"component": comp_stripped, "matches": matches})
    return breakdown


def not_expired(reg_df):
    """Registrations with no expiry date on record are kept (treated as
    still active); everything else needs expire >= today."""
    today = pd.Timestamp(datetime.date.today())
    return reg_df[reg_df["expire"].isna() | (reg_df["expire"] >= today)]


def reload_all():
    load_master_import.clear()
    load_reg_no.clear()
    load_classifications.clear()
