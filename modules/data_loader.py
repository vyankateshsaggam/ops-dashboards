"""
data_loader.py
---------------
Handles all data ingestion: reading the Excel source, normalising column
names, converting to a JSON cache (for fast reload / portability), and
computing derived KPI columns used across every dashboard view.

Optimised for large files (100k+ rows):
 - uses openpyxl in read-only/optimised mode via pandas engine
 - caches the parsed DataFrame with st.cache_data keyed on file hash + mtime
 - vectorised pandas operations only (no row-wise python loops)
"""
import os
import re
import json
import hashlib
import pandas as pd
import numpy as np
import streamlit as st


def _norm(s: str) -> str:
    """Collapse a header to a bare lowercase alphanumeric string so that
    'Plan - TOTAL M.P.', 'Plan TOTAL MP' and 'plan total mp' all compare
    equal. This absorbs punctuation/spacing differences between source
    files automatically, without needing an alias for every variant."""
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


# Fallback aliases for logical columns whose real-world header *wording*
# (not just punctuation) can differ between source files, e.g. some
# exports use 'TL NAME' where others use 'TL.1' for the same field.
# Add more entries here as new file variants show up.
COLUMN_ALIASES = {
    "team_leader": ["TL NAME", "Team Leader Name", "TL.1"],
    "supervisor":  ["SV NAME", "Supervisor Name", "SV.1"],
}

# Logical keys that the rest of the app cannot function without.
# If, even after alias matching, one of these is missing from the
# uploaded file, we raise a clear error instead of crashing later
# with a cryptic KeyError deep inside a chart function.
REQUIRED_KEYS = [
    "date", "activity", "location", "category", "team_leader", "supervisor",
    "planned_qty", "achieved_qty", "planned_total_mp", "achieved_total_mp",
    "planned_time", "achieved_time",
]


def resolve_columns(df: pd.DataFrame, cols: dict) -> pd.DataFrame:
    """Map a dataframe's actual headers onto the canonical names defined in
    config.json -> columns, so every downstream lookup like
    df[cols["team_leader"]] keeps working no matter the source (uploaded
    Excel file, or a live Google Sheet pull).

    Two layers of tolerance:
    1. Punctuation/spacing differences (e.g. 'Plan - TOTAL M.P.' vs
       'Plan TOTAL MP') are absorbed automatically via `_norm`.
    2. Genuinely different wording (e.g. 'TL NAME' vs 'TL.1') is
       resolved via the COLUMN_ALIASES lookup table.
    """
    actual_by_norm = {}
    for col in df.columns:
        actual_by_norm.setdefault(_norm(col), col)

    rename_map = {}
    missing = []
    for key, configured_name in cols.items():
        if configured_name in df.columns:
            continue  # already an exact match, nothing to do

        candidates = [configured_name] + COLUMN_ALIASES.get(key, [])
        found = None
        for cand in candidates:
            actual = actual_by_norm.get(_norm(cand))
            if actual:
                found = actual
                break

        if found:
            rename_map[found] = configured_name
        elif key in REQUIRED_KEYS:
            missing.append(configured_name)

    if rename_map:
        df = df.rename(columns=rename_map)

    if missing:
        raise ValueError(
            "The file is missing required column(s): "
            + ", ".join(f"'{m}'" for m in missing)
            + ". Please check the headers (or add an alias in "
              "modules/data_loader.py -> COLUMN_ALIASES) and try again."
        )
    return df


class DataLoader:
    def __init__(self, config: dict):
        self.cfg = config
        self.cols = config["columns"]
        self.data_path = config["data_file"]
        self.json_path = config["json_cache"]

    # ---------- helpers ----------
    @staticmethod
    def _file_signature(path: str) -> str:
        """Cheap signature (mtime+size) used as a cache-busting key."""
        if not os.path.exists(path):
            return "missing"
        stat = os.stat(path)
        return hashlib.md5(f"{stat.st_mtime}-{stat.st_size}".encode()).hexdigest()

    def save_uploaded_file(self, uploaded_file) -> None:
        """Admin uploads a new Excel file -> overwrite the source file."""
        os.makedirs(os.path.dirname(self.data_path), exist_ok=True)
        with open(self.data_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        # invalidate caches so every page recalculates automatically
        st.cache_data.clear()

    def save_dataframe_as_source(self, df: pd.DataFrame) -> None:
        """Same effect as save_uploaded_file(), but for data pulled live
        from a manager's Google Sheet instead of a file the admin picked
        from disk. Writes df to the same data_file path, using the same
        'Sheet1' sheet name load_raw() expects, then clears the cache —
        so on the next rerun every one of the 14 dashboard tabs
        recalculates from this manager's data automatically, exactly like
        an Excel upload does."""
        os.makedirs(os.path.dirname(self.data_path), exist_ok=True)
        with pd.ExcelWriter(self.data_path, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Sheet1")
        st.cache_data.clear()

    # ---------- active source tracking (for the "which dashboard am I
    # viewing" header label) ----------
    def _active_source_path(self) -> str:
        return os.path.join(os.path.dirname(self.data_path), "active_source.json")

    def set_active_source(self, kind: str, name: str) -> None:
        """Records which data source is currently loaded — an uploaded
        file, or a specific manager's Google Sheet — so the header can
        show whoever is viewing the dashboard exactly which dataset is
        active. Persisted to disk (not just session state) so it still
        shows correctly after a page reload or for a different session."""
        os.makedirs(os.path.dirname(self.data_path), exist_ok=True)
        with open(self._active_source_path(), "w") as f:
            json.dump({"kind": kind, "name": name}, f)

    def get_active_source(self) -> dict | None:
        """Returns {'kind': 'upload'|'manager', 'name': str}, or None if
        no source has been recorded yet (e.g. still on the default
        data/current_data.xlsx that shipped with the app)."""
        try:
            with open(self._active_source_path()) as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return None

    # ---------- core load + transform ----------
    def load_raw(self, sig: str) -> pd.DataFrame:
        """Read the Excel file. `sig` param forces Streamlit to re-run this
        function whenever the underlying file changes (new upload)."""
        df = pd.read_excel(self.data_path, sheet_name="Sheet1", engine="openpyxl")
        df.columns = [str(c).strip() for c in df.columns]
        df = resolve_columns(df, self.cols)
        return df

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        c = self.cols
        df = df.copy()

        # Standardise types
        df[c["date"]] = pd.to_datetime(df[c["date"]], errors="coerce")
        numeric_cols = [
            c["manpower_planned"], c["planned_total_mp"], c["planned_time"],
            c["planned_qty"], c["manpower_achieved"], c["achieved_total_mp"],
            c["achieved_time"], c["achieved_qty"], c["percent"],
        ]
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        # Clean text categoricals (trim, title-case for consistency)
        text_cols = [c["activity"], c["location"], c["category"], c["team_leader"], c["supervisor"], c["uom"]]
        for col in text_cols:
            if col in df.columns:
                df[col] = df[col].astype(str).str.strip()
                df.loc[df[col].isin(["nan", "None", ""]), col] = "Unspecified"

        # Drop fully blank rows (no date)
        df = df.dropna(subset=[c["date"]])

        # ---- Derived calendar fields ----
        df["Year"] = df[c["date"]].dt.year
        df["Month"] = df[c["date"]].dt.month
        df["MonthName"] = df[c["date"]].dt.strftime("%b %Y")
        df["Week"] = df[c["date"]].dt.isocalendar().week
        df["Weekday"] = df[c["date"]].dt.day_name()
        df["DateOnly"] = df[c["date"]].dt.date

        # ---- Derived KPI fields (vectorised) ----
        # Achievement % (recompute robustly rather than trusting raw Percent col)
        planned_qty = df[c["planned_qty"]].replace(0, np.nan)
        df["Achievement_%"] = (df[c["achieved_qty"]] / planned_qty * 100).clip(upper=200)
        df["Achievement_%"] = df["Achievement_%"].fillna(df[c["percent"]] * 100)

        # Manpower efficiency = achieved MP vs planned MP
        planned_mp = df[c["planned_total_mp"]].replace(0, np.nan)
        df["MP_Efficiency_%"] = (df[c["achieved_total_mp"]] / planned_mp * 100).clip(upper=300)

        # Time efficiency = planned time / achieved time (>100% = faster than plan)
        achieved_time = df[c["achieved_time"]].replace(0, np.nan)
        df["Time_Efficiency_%"] = (df[c["planned_time"]] / achieved_time * 100).clip(upper=300)

        # PPPM (Pieces per person per minute) — use provided cols if present & numeric
        for col in [c["planned_pppm"], c["achieved_pppm"]]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        # Variance / gap
        df["Qty_Gap"] = df[c["achieved_qty"]] - df[c["planned_qty"]]
        df["MP_Gap"] = df[c["achieved_total_mp"]] - df[c["planned_total_mp"]]

        # Status flag
        df["Status"] = np.select(
            [df["Achievement_%"] >= 100, df["Achievement_%"] >= 80],
            ["On Target", "Near Target"],
            default="Below Target",
        )
        return df

    def to_json_cache(self, df: pd.DataFrame) -> None:
        """Persist a JSON snapshot of the cleaned data (portable cache)."""
        os.makedirs(os.path.dirname(self.json_path), exist_ok=True)
        payload = df.copy()
        for col in payload.columns:
            if pd.api.types.is_datetime64_any_dtype(payload[col]):
                payload[col] = payload[col].astype(str)
            elif str(payload[col].dtype) not in ("int64", "float64", "bool"):
                payload[col] = payload[col].astype(str)
        payload.to_json(self.json_path, orient="records")

    def load(self) -> pd.DataFrame:
        sig = self._file_signature(self.data_path)
        return _cached_load(self, sig)



@st.cache_data(show_spinner="Loading & processing dataset...")
def _cached_load(_loader: "DataLoader", sig: str) -> pd.DataFrame:
    """Module-level cached function. Leading underscore on `_loader` tells
    Streamlit to skip hashing that argument; `sig` (file mtime+size hash)
    is the real cache key, so the cache auto-invalidates on new uploads."""
    raw = _loader.load_raw(sig)
    clean = _loader.transform(raw)
    _loader.to_json_cache(clean)
    return clean
