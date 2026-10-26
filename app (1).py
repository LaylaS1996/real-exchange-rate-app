"""IMF real exchange rate explorer (Python 3.12 / Streamlit)."""
from __future__ import annotations

from datetime import date
import re
import io
import requests
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

BASE = "https://api.imf.org/external/sdmx/3.0"
START = "1976-01"
# Common IMF ISO3 codes. IMF euro area is G163.
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

st.set_page_config(page_title="Real Exchange Rate Explorer", layout="wide")
st.title("Real Exchange Rate Explorer")
st.caption("Monthly IMF CPI and exchange-rate data · Available observations from January 1976 onward")


def _parse_months(raw: pd.Series) -> pd.Series:
    """Parse explicit IMF monthly period labels; never interpret numbers as Unix timestamps."""
    labels = raw.astype("string").str.strip()
    # IMF SDMX monthly periods may be YYYY-M01, YYYY-MM, YYYY-MM-DD, or YYYYMM.
    labels = labels.str.replace(r"^(\d{4})-M(0[1-9]|1[0-2])$", r"\1-\2", regex=True)
    labels = labels.str.replace(r"^(\d{4})(\d{2})$", r"\1-\2", regex=True)
    valid = labels.str.fullmatch(r"\d{4}-(0[1-9]|1[0-2])(?:-01)?")
    if not valid.fillna(False).all():
        examples = labels[~valid.fillna(False)].dropna().head(4).tolist()
        raise ValueError(
            "IMF returned period labels that are not recognizable calendar months: "
            f"{examples}. Stopping instead of assigning incorrect dates."
        )
    months = pd.to_datetime(labels.str.slice(0, 7) + "-01", format="%Y-%m-%d", errors="raise")
    return months


def _read_sdmx_csv(content: bytes) -> pd.DataFrame:
    """Read IMF SDMX CSV and strictly normalize monthly time/value columns."""
    df = pd.read_csv(io.BytesIO(content), low_memory=False, dtype={"TIME_PERIOD": "string", "TIME_PERIOD_ID": "string", "TIME": "string"})
    df.columns = [str(c).strip() for c in df.columns]
    time_col = next((c for c in ("TIME_PERIOD", "TIME_PERIOD_ID", "TIME") if c in df), None)
    value_col = next((c for c in ("OBS_VALUE", "OBS_VALUE_NUMERIC", "VALUE") if c in df), None)
    if time_col is None or value_col is None:
        raise ValueError(f"Unexpected IMF response columns: {', '.join(df.columns[:18])}")
    result = pd.DataFrame({"month": _parse_months(df[time_col]),
                           "value": pd.to_numeric(df[value_col], errors="coerce")})
    result = result.dropna(subset=["value"])
    if result["month"].duplicated().any():
        raise ValueError("IMF returned multiple observations for the same month; check the series key.")
    result = result.set_index("month").sort_index()
    return result


@st.cache_data(ttl=3600, show_spinner=False)
def get_series(country: str, indicator: str) -> pd.Series:
    # IMF SDMX 3.0 compact data query: database, dataflow, version, key.
    # Dataflow is IMF CPI or exchange rate database; the indicator key comes from the assignment.
    if indicator == "cpi":
        flow, key = "CPI", f"{country}.CPI._T.IX.M"
    else:
        flow, key = "ER", f"{country}.XDC_USD.PA_RT.M"
    # Dataflow agency/version can vary; try the canonical IMF flow first.
    url = f"{BASE}/data/dataflow/IMF.STA/{flow}/+/{key}"
    params = {"startPeriod": START, "format": "csvfile"}
    headers = {"Accept": "text/csv, application/vnd.sdmx.csv;version=2, */*",
               "User-Agent": "MBA-real-exchange-rate-study-app/1.0"}
    try:
        response = requests.get(url, params=params, headers=headers, timeout=45)
        response.raise_for_status()
        result = _read_sdmx_csv(response.content)["value"]
        if result.empty:
            raise ValueError("IMF returned no valid monthly observations")
        return result.rename(indicator)
    except (requests.RequestException, ValueError, pd.errors.ParserError) as exc:
        raise RuntimeError(f"Unable to retrieve {indicator.upper()} for {country} from IMF. "
                           f"Request: {response.url if 'response' in locals() else url}. "
                           f"Details: {exc}") from exc


st.markdown("**Quote convention:** S = units of Country 2 currency per 1 unit of Country 1 currency.")
c1, c2 = st.columns(2)
labels = list(COUNTRIES)
with c1:
    first = st.selectbox("Country 1 (base currency)", labels, index=labels.index("United Kingdom"))
with c2:
    second = st.selectbox("Country 2 (quote currency)", labels, index=labels.index("United States"))
if first == second:
    st.warning("Choose two different countries.")
    st.stop()

with st.spinner("Retrieving IMF observations…"):
    try:
        p1 = get_series(COUNTRIES[first], "cpi")
        p2 = get_series(COUNTRIES[second], "cpi")
        e1 = get_series(COUNTRIES[first], "fx")
        e2 = get_series(COUNTRIES[second], "fx")
    except RuntimeError as error:
        st.error(str(error))
        st.info("Some IMF series have gaps or limited coverage. Try another country pair or retry later.")
        st.stop()

# IMF rates are local-currency units per USD. Divide country-2 rate by country-1 rate.
df = pd.concat([p1.rename("CPI_1"), p2.rename("CPI_2"),
                e1.rename("Local_1_per_USD"), e2.rename("Local_2_per_USD")], axis=1)
df = df.dropna().sort_index()
df = df[(df > 0).all(axis=1)]
df = df.loc[df.index >= pd.Timestamp("1976-01-01")]
if not df.empty and (df.index.day != 1).any():
    st.error("Monthly dates could not be verified. No calculations were produced.")
    st.stop()
df["S_country2_per_country1"] = df["Local_2_per_USD"] / df["Local_1_per_USD"]
df["RER"] = df["S_country2_per_country1"] * df["CPI_1"] / df["CPI_2"]
if df.empty:
    st.error("No overlapping positive CPI and FX observations from January 1976 onward for these countries.")
    st.stop()

first_date, last_date = df.index.min().date(), df.index.max().date()
st.caption(f"Overlapping monthly observations: {first_date:%b %Y} – {last_date:%b %Y} ({len(df)} months)")
start, end = st.slider("Sample period", min_value=first_date, max_value=last_date,
                       value=(first_date, last_date), format="MMM YYYY")
selection = df.loc[(df.index.date >= start) & (df.index.date <= end)].copy()
if selection.empty:
    st.warning("No valid monthly observations within the chosen sample period.")
    st.stop()
mean_rer = selection["RER"].mean()
selection["Real_Index"] = 100 * selection["RER"] / mean_rer
mode = st.radio("Chart", ["Real", "Nominal", "Both"], horizontal=True)

col_a, col_b, col_c = st.columns(3)
col_a.metric("Valid months", f"{len(selection):,}")
col_b.metric("Sample mean RER (RER*)", f"{mean_rer:,.4f}")
col_c.metric("Mean real index", f"{selection['Real_Index'].mean():.2f}")

if mode == "Both":
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Scatter(x=selection.index, y=selection["Real_Index"],
                             name="Real index (mean = 100)", mode="lines"), secondary_y=False)
    fig.add_trace(go.Scatter(x=selection.index, y=selection["S_country2_per_country1"],
                             name="Nominal S (currency 2 / currency 1)", mode="lines"), secondary_y=True)
    fig.update_yaxes(title_text="Real index (sample mean = 100)", secondary_y=False)
    fig.update_yaxes(title_text=f"{second} currency / {first} currency", secondary_y=True)
else:
    col = "Real_Index" if mode == "Real" else "S_country2_per_country1"
    fig = go.Figure(go.Scatter(x=selection.index, y=selection[col], mode="lines", name=mode))
    fig.update_yaxes(title_text="Real index (sample mean = 100)" if mode == "Real"
                     else f"{second} currency / {first} currency")
fig.update_layout(title=f"{first} vs {second}: {mode} exchange rate", xaxis_title="Month",
                  hovermode="x unified", legend=dict(orientation="h"))
st.plotly_chart(fig, use_container_width=True)

export = selection.reset_index().rename(columns={"month": "Month", "index": "Month"})
export["Month"] = pd.to_datetime(export["Month"]).dt.strftime("%Y-%m")
export["Country_1"] = first
export["Country_2"] = second
export["Sample_mean_RER"] = mean_rer
st.download_button("Download sample data and calculations (CSV)",
                   data=export.to_csv(index=False).encode("utf-8"),
                   file_name="real_exchange_rate_calculations.csv", mime="text/csv")
with st.expander("Inspect calculations and data"):
    st.latex(r"S_t = \frac{\text{Country 2 local currency per USD}}{\text{Country 1 local currency per USD}}")
    st.latex(r"RER_t = S_t\frac{P_{1,t}}{P_{2,t}}")
    st.latex(r"RER^* = \operatorname{mean}_{t\in sample}(RER_t),\quad RealIndex_t=100\frac{RER_t}{RER^*}")
    st.dataframe(export, use_container_width=True)
st.caption("Source: IMF SDMX API. The data are subject to IMF availability and revisions. "
           "For euro area observations, historical coverage may be limited.")
