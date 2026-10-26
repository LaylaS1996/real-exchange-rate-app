"""Real Exchange Rate Explorer — monthly IMF SDMX data (Python 3.12)."""
from __future__ import annotations

import io
import re

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st
from plotly.subplots import make_subplots

BASE = "https://api.imf.org/external/sdmx/3.0"
START = "1976-01"
COUNTRIES = {
    "Australia": "AUS", "Austria": "AUT", "Belgium": "BEL", "Brazil": "BRA",
    "Canada": "CAN", "China": "CHN", "Denmark": "DNK", "Euro area": "G163",
    "Finland": "FIN", "France": "FRA", "Germany": "DEU", "Greece": "GRC",
    "India": "IND", "Ireland": "IRL", "Israel": "ISR", "Italy": "ITA",
    "Japan": "JPN", "Mexico": "MEX", "Netherlands": "NLD", "New Zealand": "NZL",
    "Norway": "NOR", "Poland": "POL", "Portugal": "PRT", "Singapore": "SGP",
    "South Africa": "ZAF", "South Korea": "KOR", "Spain": "ESP", "Sweden": "SWE",
    "Switzerland": "CHE", "Turkey": "TUR", "United Kingdom": "GBR",
    "United States": "USA",
}


def parse_months(values: pd.Series) -> pd.Series:
    """Accept IMF YYYY-M01, YYYY-MM, YYYYMM and YYYY-MM-01 monthly labels.

    Reject unknown formats rather than silently interpreting numbers as timestamps.
    """
    raw = values.astype("string").str.strip()
    normalized = raw.str.replace(r"^(\d{4})-M(0[1-9]|1[0-2])$", r"\1-\2", regex=True)
    normalized = normalized.str.replace(r"^(\d{4})(0[1-9]|1[0-2])$", r"\1-\2", regex=True)
    valid = normalized.str.fullmatch(r"\d{4}-(0[1-9]|1[0-2])(?:-01)?")
    if not valid.fillna(False).all():
        examples = raw[~valid.fillna(False)].head(5).tolist()
        raise ValueError(f"Unrecognized IMF monthly periods: {examples}")
    return pd.to_datetime(normalized.str.slice(0, 7) + "-01", format="%Y-%m-%d", errors="raise")


def read_imf_csv(content: bytes) -> pd.Series:
    """Return one numeric observation per true calendar month."""
    df = pd.read_csv(io.BytesIO(content), dtype=str, low_memory=False)
    df.columns = df.columns.str.strip()
    time_col = next((c for c in ("TIME_PERIOD", "TIME_PERIOD_ID", "TIME") if c in df.columns), None)
    value_col = next((c for c in ("OBS_VALUE", "OBS_VALUE_NUMERIC", "VALUE") if c in df.columns), None)
    if time_col is None or value_col is None:
        raise ValueError(f"Unexpected IMF CSV columns: {list(df.columns)[:15]}")
    months = parse_months(df[time_col])
    out = pd.DataFrame({"month": months, "value": pd.to_numeric(df[value_col], errors="coerce")})
    out = out.dropna(subset=["month", "value"])
    out = out[out["month"] >= pd.Timestamp("1976-01-01")]
    if out["month"].duplicated().any():
        raise ValueError("IMF returned more than one value for a month. Check the requested series key.")
    return out.set_index("month")["value"].sort_index()


@st.cache_data(ttl=3600, show_spinner=False)
def get_series(country: str, indicator: str) -> pd.Series:
    if indicator == "cpi":
        flow, key = "CPI", f"{country}.CPI._T.IX.M"
    elif indicator == "fx":
        flow, key = "ER", f"{country}.XDC_USD.PA_RT.M"
    else:
        raise ValueError("Unknown indicator")
    url = f"{BASE}/data/dataflow/IMF.STA/{flow}/+/{key}"
    try:
        response = requests.get(
            url,
            params={"startPeriod": START, "format": "csvfile"},
            headers={"Accept": "text/csv, application/vnd.sdmx.csv;version=2, */*",
                     "User-Agent": "MBA-real-exchange-rate-explorer/1.0"},
            timeout=45,
        )
        response.raise_for_status()
        series = read_imf_csv(response.content)
        if series.empty:
            raise ValueError("No monthly observations since January 1976")
        return series
    except (requests.RequestException, ValueError, pd.errors.ParserError) as exc:
        raise RuntimeError(f"Could not retrieve {indicator.upper()} for {country} from IMF: {exc}") from exc


def calculate(p1: pd.Series, p2: pd.Series, fx1: pd.Series, fx2: pd.Series) -> pd.DataFrame:
    data = pd.concat([
        p1.rename("CPI_1"), p2.rename("CPI_2"),
        fx1.rename("Local_1_per_USD"), fx2.rename("Local_2_per_USD"),
    ], axis=1).dropna().sort_index()
    data = data.loc[data.index >= pd.Timestamp("1976-01-01")].copy()
    data = data.loc[(data > 0).all(axis=1)].copy()
    if data.index.has_duplicates:
        raise ValueError("Duplicate monthly dates in merged data")
    data["S_country2_per_country1"] = data["Local_2_per_USD"] / data["Local_1_per_USD"]
    data["RER"] = data["S_country2_per_country1"] * data["CPI_1"] / data["CPI_2"]
    return data


def main() -> None:
    st.set_page_config(page_title="Real Exchange Rate Explorer", layout="wide")
    st.title("Real Exchange Rate Explorer")
    st.caption("Monthly IMF CPI and exchange-rate data · January 1976 onward, where available")
    st.markdown("**Quote convention:** S = units of Country 2 currency per 1 unit of Country 1 currency.")
    left, right = st.columns(2)
    names = list(COUNTRIES)
    with left:
        first = st.selectbox("Country 1 (base currency)", names, index=names.index("United Kingdom"))
    with right:
        second = st.selectbox("Country 2 (quote currency)", names, index=names.index("United States"))
    if first == second:
        st.warning("Choose two different countries.")
        st.stop()

    with st.spinner("Retrieving IMF monthly observations…"):
        try:
            data = calculate(
                get_series(COUNTRIES[first], "cpi"),
                get_series(COUNTRIES[second], "cpi"),
                get_series(COUNTRIES[first], "fx"),
                get_series(COUNTRIES[second], "fx"),
            )
        except (RuntimeError, ValueError) as exc:
            st.error(str(exc))
            st.info("The IMF may not have all four series for this country pair. Try another pair or retry later.")
            st.stop()

    if data.empty:
        st.error("No overlapping positive monthly CPI and FX observations since January 1976.")
        st.stop()
    start_available = data.index.min().date()
    end_available = data.index.max().date()
    st.caption(f"Overlapping monthly observations: {start_available:%b %Y} – {end_available:%b %Y} ({len(data)} months)")
    start, end = st.slider("Sample period", min_value=start_available, max_value=end_available,
                           value=(start_available, end_available), format="MMM YYYY")
    selected = data.loc[(data.index.date >= start) & (data.index.date <= end)].copy()
    if selected.empty:
        st.warning("No observations in the selected period.")
        st.stop()
    mean_rer = selected["RER"].mean()
    selected["Real_Index"] = 100.0 * selected["RER"] / mean_rer
    mode = st.radio("Chart", ["Real", "Nominal", "Both"], horizontal=True)
    a, b, c = st.columns(3)
    a.metric("Valid months", f"{len(selected):,}")
    b.metric("Sample mean RER (RER*)", f"{mean_rer:,.4f}")
    c.metric("Mean real index", f"{selected['Real_Index'].mean():.2f}")

    if mode == "Both":
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        fig.add_trace(go.Scatter(x=selected.index, y=selected["Real_Index"],
                                 name="Real index (mean = 100)", mode="lines"), secondary_y=False)
        fig.add_trace(go.Scatter(x=selected.index, y=selected["S_country2_per_country1"],
                                 name="Nominal S", mode="lines"), secondary_y=True)
        fig.update_yaxes(title_text="Real index (mean = 100)", secondary_y=False)
        fig.update_yaxes(title_text=f"{second} currency per {first} currency", secondary_y=True)
    else:
        column = "Real_Index" if mode == "Real" else "S_country2_per_country1"
        fig = go.Figure(go.Scatter(x=selected.index, y=selected[column], mode="lines", name=mode))
        fig.update_yaxes(title_text="Real index (mean = 100)" if mode == "Real"
                         else f"{second} currency per {first} currency")
    fig.update_layout(title=f"{first} vs {second}: {mode} exchange rate", xaxis_title="Month",
                      hovermode="x unified", legend=dict(orientation="h"))
    st.plotly_chart(fig, use_container_width=True)

    export = selected.reset_index().rename(columns={"month": "Month", "index": "Month"})
    export["Month"] = pd.to_datetime(export["Month"]).dt.strftime("%Y-%m")
    export["Country_1"] = first
    export["Country_2"] = second
    export["Sample_mean_RER"] = mean_rer
    st.download_button("Download sample data and calculations (CSV)",
                       data=export.to_csv(index=False).encode("utf-8"),
                       file_name="real_exchange_rate_calculations.csv", mime="text/csv")
    with st.expander("Inspect calculations and data"):
        st.latex(r"S_t = \frac{\mathrm{Country\ 2\ currency/USD}}{\mathrm{Country\ 1\ currency/USD}}")
        st.latex(r"RER_t = S_t \frac{P_{1,t}}{P_{2,t}}")
        st.latex(r"RER^* = \operatorname{mean}_{t\in\mathrm{sample}}(RER_t),\quad RealIndex_t = 100\frac{RER_t}{RER^*}")
        st.dataframe(export, use_container_width=True)
    st.caption("Source: IMF SDMX 3.0 API. Availability and revisions depend on the IMF; euro area historical coverage may be limited.")


if __name__ == "__main__":
    main()
