# Real Exchange Rate Explorer

A Python 3.12 / Streamlit application for comparing monthly real and nominal exchange rates using IMF SDMX 3.0 CPI and exchange-rate series, from January 1976 where available.

## Live app

https://lreal-exchange-rate-app-atwko5snzdv3xifgqyaty3laylasalah.streamlit.app/

## Data and formulas

Choose Country 1 and Country 2 (including the euro area). The application retrieves monthly CPI and exchange rates quoted as units of local currency per US dollar from IMF CPI and ER dataflows. The nominal bilateral exchange rate is:

`S(t) = (Country 2 currency per USD) / (Country 1 currency per USD)`

Thus **S(t) is Country 2 currency per one unit of Country 1 currency**. For UK vs US, S is USD/GBP.

The real exchange rate and normalized real index are:

`RER(t) = S(t) * CPI_1(t) / CPI_2(t)`

`RER* = arithmetic mean of RER(t) within the selected sample`

`Real Index(t) = 100 * RER(t) / RER*`

The index averages 100 over the selected sample by construction. Selecting another date range recalculates the mean and index. The app offers Real, Nominal, and Both charts (two y-axes for Both), an inspectable table, and CSV download.

## Data quality

IMF monthly labels such as `1976-M01` are parsed explicitly into January 1976, not as generic timestamps. Invalid periods and duplicate months cause errors instead of silently producing incorrect charts. Only overlapping, positive, numeric monthly CPI and FX observations on or after January 1976 are included. Actual coverage varies by country and IMF data availability.

## Run locally

```bash
python -m pip install -r requirements.txt
streamlit run app.py
```

Deploy using Python 3.12 and `app.py` as the Streamlit entry point.

## Suggested verification

1. Select **United Kingdom** (Country 1) and **United States** (Country 2). Confirm the nominal rate is USD per GBP.
2. Check that the earliest month is January 1976 or later and each exported month is unique.
3. Change the sample slider and confirm the real index recalculates to a sample mean of 100.
4. Toggle Real, Nominal and Both charts.
5. Download the CSV and independently verify one row's `S`, `RER`, and `Real_Index` against the displayed CPI and FX values.

**Verification status:** Code-level checks are possible offline; live IMF response and Streamlit deployment must be checked after uploading. This README does not claim those tests have been completed.

## Academic disclosure

Created with AI assistance (OpenAI GPT-6, October 26, 2026). Include the actual prompts/chat record and manual verification in the assignment submission as required by the instructor.
