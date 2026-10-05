"""Data loading and cross-page lookups for the Chemical Import Dashboard.

Everything here is pure data — no widgets, no chart rendering. UI-specific
logic lives in filters.py, charts.py, registrations.py, and comparison.py.
"""
import datetime

import pandas as pd
import streamlit as st

DATA_PATH = "chemical_import_database.xlsx"


def _clean_text_cols(df, cols, blank_defaults=None):
    """Normalizes every column in `cols` to a plain stripped string, with no
    stray NaN surviving as a float.

    fillna has to run BEFORE astype(str), not after: pandas' (pyarrow-backed)
    string dtype keeps a missing cell as an actual float NaN even once the
    column is cast with astype(str) — astype(str) only stringifies values
    that are already there, it doesn't stringify a missing one into "nan".
    A column left this way silently mixes floats and strings, which blows up
    the moment anything tries to sort or compare it (TypeError: '<' not
    supported between instances of 'float' and 'str'). Filling every column
    up front, not just the ones a past bug happened to touch, closes off the
    whole class of bug rather than one column at a time.

    `blank_defaults` can map a column name to what its blanks should read as
    (e.g. "Unspecified") instead of the plain empty string every other
    column gets.
    """
    blank_defaults = blank_defaults or {}
    for col in cols:
        default = blank_defaults.get(col, "")
        df[col] = df[col].fillna(default).astype(str).str.strip()
        df.loc[df[col] == "", col] = default
    return df


@st.cache_data
def load_master_import():
    df = pd.read_excel(DATA_PATH, sheet_name="master_import")
    df = _clean_text_cols(
        df,
        ["common_name", "concentration", "formulation_type", "origin", "category"],
        blank_defaults={"formulation_type": "Unspecified", "category": "other"},
    )
    return df


@st.cache_data
def load_reg_no():
    df = pd.read_excel(DATA_PATH, sheet_name="reg_no")
    df = _clean_text_cols(
        df,
        [
            "reg_no", "common_name", "common_name_original", "concentration", "formulation_type",
            "trade_name", "source", "source_country", "register", "importer", "distributor", "status", "category",
        ],
        blank_defaults={"formulation_type": "Unspecified"},
    )
    return df


@st.cache_data
def load_pesticide_list():
    """Official list of pesticides permitted for registration (one row per
    chemical + concentration + formulation, tagged with the Royal Gazette
    announcement it came from). The sheet carries blank trailing rows and a
    few exact duplicates, which are dropped here."""
    df = pd.read_excel(DATA_PATH, sheet_name="pesticide_list")
    df = df.dropna(subset=["common_name"]).copy()
    # a stray cell (e.g. a "False" left by a formula) can sit in a row with
    # nothing else filled in; real entries always carry a strength
    df = df.dropna(subset=["concentration", "formulation_type", "royal_gazette_volume"], how="all")
    df = _clean_text_cols(
        df,
        ["common_name", "concentration", "formulation_type", "royal_gazette_volume"],
        blank_defaults={"formulation_type": "Unspecified", "royal_gazette_volume": "Not stated"},
    )
    for col in ["common_name", "concentration", "formulation_type"]:
        # a few cells carry stray line breaks / double spaces inside the text
        df[col] = df[col].str.replace(r"\s+", " ", regex=True)
    df = df.drop_duplicates(subset=["common_name", "concentration", "formulation_type", "royal_gazette_volume"])
    return df.reset_index(drop=True)


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


def aggregate_with_price(df, group_cols, qty_col="quantity_kg", value_col="value_bht"):
    """Groups by group_cols, summing quantity from every row (valid across
    all years) and computing average price using only rows where value is
    actually recorded (value > 0). This matters beyond the obvious case: 2024
    and 2025 have $0 recorded for value_bht across every row in this dataset
    despite real shipped quantity. For a group that spans only one of those
    years, including the zero rows would show an obvious price of 0 — easy
    to notice. But for a group spanning MULTIPLE years at once (e.g. total
    price by origin country, or a comparison summary across the whole date
    range), blending a $0 year in with real-value years silently understates
    the average instead of showing anything obviously wrong. Excluding those
    rows from the price computation entirely (not just masking an
    already-summed total) handles both cases correctly with one mechanism."""
    qty_agg = df.groupby(group_cols, as_index=False)[qty_col].sum()
    priced_rows = df[df[value_col] > 0]
    if priced_rows.empty:
        qty_agg["price_thb"] = pd.NA
        return qty_agg
    price_agg = priced_rows.groupby(group_cols, as_index=False)[[qty_col, value_col]].sum()
    price_agg["price_thb"] = price_agg[value_col] / price_agg[qty_col].replace(0, pd.NA)
    return qty_agg.merge(price_agg[list(group_cols) + ["price_thb"]], on=group_cols, how="left")


def reload_all():
    load_master_import.clear()
    load_reg_no.clear()
    load_pesticide_list.clear()
    load_classifications.clear()
