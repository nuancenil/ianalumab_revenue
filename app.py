
import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime
from zoneinfo import ZoneInfo

# Optional: Google Sheets logging
try:
    from google.oauth2.service_account import Credentials
    import gspread
    SHEETS_AVAILABLE = True
except Exception:
    SHEETS_AVAILABLE = False

st.set_page_config(page_title="Ianalumab Revenue Model", layout="centered")

# --- UTM tracking (robust, compatible with different Streamlit versions) ---
def _get_query_params():
    try:
        p = st.query_params  # new versions: Mapping[str, str]
        return {k: p.get(k, "") for k in ("utm_source","utm_medium","utm_campaign","app")}
    except Exception:
        p = st.experimental_get_query_params()  # old: Dict[str, List[str]]
        def getv(k): 
            v = p.get(k, [""])
            return v[0] if isinstance(v, list) and v else (v or "")
        return {k: getv(k) for k in ("utm_source","utm_medium","utm_campaign","app")}

qp = _get_query_params()
utm_new = {k: qp.get(k, "") for k in ("utm_source", "utm_medium", "utm_campaign")}
if any(utm_new.values()):
    st.session_state["utm"] = utm_new
else:
    st.session_state.setdefault("utm", utm_new)
utm = st.session_state["utm"]

if any(utm.values()):
    st.caption(f"Traffic Source: {utm.get('utm_source','')} / {utm.get('utm_medium','')} / {utm.get('utm_campaign','')}")

st.title("Ianalumab Revenue & Investment Model")

# Sidebar - parameters
st.sidebar.header("Parameters")
launch_year = st.sidebar.number_input("Launch Year", 2025, 2035, 2027)
ramp_years  = st.sidebar.slider("Ramp Years to Peak", 3, 8, 5)
peak_sales_bil = st.sidebar.number_input("Peak Sales (B$)", 0.1, 5.0, 0.638, step=0.01, format="%.3f")
pos = st.sidebar.slider("Probability of Success (PoS)", 0.3, 1.0, 0.80, step=0.05)
ramp_shape = st.sidebar.selectbox("Ramp Shape", ["linear", "fast", "slow"])

cogs_pct = st.sidebar.slider("COGS % of Revenue", 0.05, 0.40, 0.15, step=0.01)
sga_pct  = st.sidebar.slider("SG&A % of Gross Profit", 0.10, 0.50, 0.25, step=0.01)

prelaunch_years = st.sidebar.slider("Pre-launch Investment Years", 0, 3, 2)
postlaunch_years = st.sidebar.slider("Post-launch Investment Years", 0, 3, 1)
total_invest_m = st.sidebar.number_input("Total Investment (USD $M)", 100, 2000, 670, step=10)

# Optional: who is using (for identification)
st.sidebar.markdown("---")
name = st.sidebar.text_input("Your name (optional)")
linkedin_url = st.sidebar.text_input("LinkedIn URL (optional)")
consent = st.sidebar.checkbox("I consent to save this run to Google Sheet (optional)")

# Ramp function
def ramp_factors(n, kind="linear"):
    if kind == "fast":
        base = [0.2, 0.5, 0.8, 0.95, 1.0]
    elif kind == "slow":
        base = [0.05, 0.2, 0.4, 0.7, 1.0]
    else:  # linear
        base = np.linspace(0.1, 1.0, 5).tolist()
    if n == 5:
        return base
    x = np.linspace(1, 5, num=5)
    xi = np.linspace(1, 5, num=n)
    return np.interp(xi, x, base).tolist()

factors = ramp_factors(ramp_years, ramp_shape)
years = list(range(launch_year, launch_year + ramp_years))

# Investment allocation
invest_years = list(range(launch_year - prelaunch_years, launch_year + postlaunch_years))
invest_per_year_bil = (total_invest_m / 1000.0) / max(1, len(invest_years))

rows = []
cum_profit = 0.0
break_even_year = None

for y in years:
    revenue_b = peak_sales_bil * factors[y - launch_year] * pos
    gross_profit_b = revenue_b * (1 - cogs_pct)
    op_profit_b = gross_profit_b * (1 - sga_pct)
    invest_b = invest_per_year_bil if y in invest_years else 0.0
    cum_profit += (op_profit_b - invest_b)
    if break_even_year is None and cum_profit >= 0:
        break_even_year = y
    rows.append({
        "Year": y,
        "Revenue (B$)": round(revenue_b, 3),
        "Gross Profit (B$)": round(gross_profit_b, 3),
        "Operating Profit (B$)": round(op_profit_b, 3),
        "Investment (B$)": round(invest_b, 3),
        "Cumulative Profit (B$)": round(cum_profit, 3)
    })

df = pd.DataFrame(rows)
st.subheader("Forecast Table")
st.dataframe(df, use_container_width=True)

# Chart
st.subheader("Revenue & Cumulative Profit")
fig, ax = plt.subplots(figsize=(8, 4.5))
ax.plot(df["Year"], df["Revenue (B$)"], marker="o", label="Revenue (B$)")
ax.plot(df["Year"], df["Cumulative Profit (B$)"], marker="o", label="Cumulative Profit (B$)")
ax.set_xlabel("Year"); ax.set_ylabel("Billion USD"); ax.grid(True); ax.legend()
st.pyplot(fig)

st.markdown("---")
st.write(f"**Approx. Break-even Year:** {break_even_year if break_even_year else 'Not reached'}")
st.caption("Change PoS, Ramp Shape, or Investment to see how break-even shifts.")

# Ensure UTM columns exist and write to df
for k in ("utm_source", "utm_medium", "utm_campaign"):
    df[k] = utm.get(k, "")

# Download CSV
csv = df.to_csv(index=False).encode("utf-8")
st.download_button("Download CSV", csv, "ianalumab_model.csv", "text/csv")

# --- Google Sheets logging (optional) ---
def sheets_enabled():
    return SHEETS_AVAILABLE and "gcp_service_account" in st.secrets and "sheets" in st.secrets

@st.cache_resource(show_spinner=False)
def _open_worksheet():
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ],
    )
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(st.secrets["sheets"]["sheet_key"])
    # worksheet name: from secrets or query param ?app=, fallback to 'runs'
    ws_name = st.secrets["sheets"].get("worksheet", qp.get("app") or "runs")
    try:
        ws = sh.worksheet(ws_name)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=ws_name, rows=2000, cols=40)
        ws.append_row([
            "timestamp_taipei","app_id","name","linkedin_url",
            "utm_source","utm_medium","utm_campaign",
            "launch_year","ramp_years","ramp_shape",
            "peak_sales_bil","pos","cogs_pct","sga_pct",
            "prelaunch_years","postlaunch_years","total_invest_m",
            "break_even_year"
        ])
    return ws

def log_run():
    ws = _open_worksheet()
    tz = ZoneInfo("Asia/Taipei")
    ts = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")
    app_id = qp.get("app") or st.secrets["sheets"].get("worksheet","runs")
    ws.append_row([
        ts, app_id, name, linkedin_url,
        utm.get("utm_source",""), utm.get("utm_medium",""), utm.get("utm_campaign",""),
        launch_year, ramp_years, ramp_shape,
        float(peak_sales_bil), float(pos), float(cogs_pct), float(sga_pct),
        prelaunch_years, postlaunch_years, total_invest_m,
        break_even_year or ""
    ], value_input_option="USER_ENTERED")

# UI for saving to Google Sheet
if sheets_enabled():
    if st.button("Save this run to Google Sheet"):
        if consent:
            try:
                log_run()
                st.success("Saved to Google Sheet ✅")
            except Exception as e:
                st.error(f"Failed to save: {e}")
        else:
            st.warning("Please check consent box to save this run.")
else:
    st.caption("Tip: Add Google Sheets credentials in Secrets to enable logging (optional).")
