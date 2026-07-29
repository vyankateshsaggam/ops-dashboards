# 📦 Warehouse Operations Intelligence Dashboard

A production-ready, role-based, interactive operations dashboard built with
**Streamlit + Plotly + Pandas + OpenPyXL**, designed to visualize warehouse
planned-vs-achieved performance data from an Excel source file.

---

## 1. Folder Structure

```
ops_dashboard/
├── app.py                     # Main entry point (login, filters, all dashboards)
├── config.json                # App config: theme, column mapping, users
├── requirements.txt           # Python dependencies
├── .streamlit/
│   └── config.toml            # Streamlit theme + server settings
├── data/
│   ├── current_data.xlsx      # Active data source (replaced on Admin upload)
│   └── current_data.json      # Auto-generated JSON cache of cleaned data
└── modules/
    ├── auth.py                # Login screen + role-based session management
    ├── data_loader.py         # Excel → DataFrame → JSON, cached, derived KPIs
    ├── filters.py              # Sidebar global filters (Date, TL, Activity, etc.)
    ├── charts.py               # Reusable Plotly chart factory + KPI cards
    └── export.py                # CSV / Excel / PNG export helpers
```

## 2. Local Setup (Windows / VS Code)

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

App opens at `http://localhost:8501`.

**Demo logins:**
| Username | Password    | Role   |
|----------|-------------|--------|
| admin    | admin@123   | Admin  |
| viewer   | viewer@123  | Viewer |
| ceo      | ceo@123     | Viewer |

> ⚠️ For real deployment, replace the plaintext credentials in `config.json`
> with hashed passwords or connect `modules/auth.py` to your SSO/LDAP/Azure AD.

## 3. How the "no-code-change" data refresh works

1. Admin logs in → opens **Admin Panel** → uploads a new `.xlsx` file.
2. `DataLoader.save_uploaded_file()` overwrites `data/current_data.xlsx` and
   clears Streamlit's cache (`st.cache_data.clear()`).
3. On the next render, `DataLoader.load()` recomputes a file signature
   (mtime + size), which busts the `@st.cache_data` key on `_cached_load`,
   forcing a fresh read → clean → derive-KPIs → JSON-cache cycle.
4. Every chart on every tab reads from this single refreshed DataFrame, so
   **all 14 dashboard tabs update immediately with zero code changes**.

This design also scales to 100k+ row files because:
- Excel is read once per file-change (cached by signature, not on every rerun).
- All transformations use vectorised pandas/numpy operations, not row loops.
- Aggregations (`groupby`) used by charts are computed once per filter change
  and reused across multiple chart calls in the same tab.

## 4. Deployment Guide — Windows Server + IIS

Streamlit is a Python web app server; IIS does not run Python natively, so the
standard production pattern is: **IIS as a reverse proxy → Streamlit running
as a Windows Service on localhost**.

### Step 1 — Install prerequisites on the server
```powershell
# Install Python 3.11+ (from python.org), then:
python -m venv C:\apps\ops_dashboard\venv
C:\apps\ops_dashboard\venv\Scripts\activate
pip install -r requirements.txt
```

### Step 2 — Run Streamlit as a background service
Use **NSSM** (Non-Sucking Service Manager) to wrap Streamlit as a Windows
Service so it survives reboots:
```powershell
nssm install OpsDashboard "C:\apps\ops_dashboard\venv\Scripts\streamlit.exe" ^
  "run C:\apps\ops_dashboard\app.py --server.port 8501 --server.address 127.0.0.1 --server.headless true"
nssm start OpsDashboard
```

### Step 3 — Configure IIS as a reverse proxy
1. Install **IIS** with the **Application Request Routing (ARR)** and
   **URL Rewrite** modules.
2. Enable ARR proxy: IIS Manager → Server node → Application Request Routing
   Cache → Server Proxy Settings → check **Enable proxy**.
3. Create a new IIS site (e.g. `ops-dashboard.yourcompany.com`) bound to
   port 80/443.
4. Add a `web.config` to the site root with a reverse-proxy rule to
   `http://127.0.0.1:8501`:

```xml
<configuration>
  <system.webServer>
    <rewrite>
      <rules>
        <rule name="StreamlitProxy" stopProcessing="true">
          <match url="(.*)" />
          <action type="Rewrite" url="http://127.0.0.1:8501/{R:1}" />
        </rule>
      </rules>
    </rewrite>
    <webSocket enabled="true" />
  </system.webServer>
</configuration>
```
(WebSockets must stay enabled — Streamlit relies on them for live updates.)

### Step 4 — TLS / HTTPS
Bind an SSL certificate to the IIS site (via IIS Manager → Bindings) so the
dashboard is served over HTTPS to the CEO and other stakeholders.

### Step 5 — Verify
Browse to `https://ops-dashboard.yourcompany.com` — IIS proxies all traffic
(including WebSocket) to the Streamlit service running on `127.0.0.1:8501`.

---

## 5. Customization without touching code
- **Branding / colors** → edit `config.json → theme` and `.streamlit/config.toml`.
- **Column mapping** → if your Excel headers change, update `config.json → columns`
  (no code edits needed, as long as the same logical fields exist).
- **Users / roles** → edit `config.json → users`.
