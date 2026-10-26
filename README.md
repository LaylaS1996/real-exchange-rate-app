# Real Exchange Rate Explorer

Streamlit app for comparing real and nominal exchange rates using monthly IMF CPI and FX observations, built for an International Finance assignment. Compatible with Python 3.12.

## Deploy on Streamlit Community Cloud
1. Create a **public** GitHub repository called `real-exchange-rate-app` with a README.
2. Add `app.py` and `requirements.txt` at the repository root and replace README with this file.
3. Visit https://share.streamlit.io and sign in with GitHub.
4. Choose **Create app** → **Yup, I have an app**; select your repository, branch `main`, and entrypoint `app.py`.
5. In advanced settings choose Python **3.12**, leave Secrets blank, and deploy.

## Economic definitions
- S(t): Country 2 currency units per one Country 1 currency unit.
- IMF local-currency-per-USD rates imply S(t) = FX2(t) / FX1(t).
- RER(t) = S(t) × CPI1(t) / CPI2(t).
- RER* = mean of valid RER observations within the selected sample.
- Real Index(t) = 100 × RER(t) / RER*.
- Nominal S(t) is **not** normalized; the Both chart uses a secondary y-axis.

## Verification checklist
- Select **United Kingdom** for Country 1 and **United States** for Country 2.
- Confirm S is USD per GBP (not GBP per USD).
- Change sample dates and confirm sample mean real index remains approximately 100.
- Download CSV; for one month verify S = Local_2_per_USD / Local_1_per_USD and RER = S × CPI_1 / CPI_2.
- Check Real, Nominal and Both chart modes.
- Record your ChatGPT prompt, model name, date, deployed Streamlit URL, GitHub URL, and verification notes for submission.

## Data availability / limitations
The app requests monthly CPI and FX observations from IMF SDMX 3.0. IMF availability, series naming, and response formats may change; data may have gaps. The app reports failures instead of fabricating observations. IMF rates are local currency per USD and are inverted through the ratio FX2 / FX1 to match the required S direction. If an IMF endpoint returns an error, check its flow identifiers and series key in the IMF API documentation before redeploying.
