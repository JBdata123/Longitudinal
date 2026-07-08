# LCFC Longitudinal Report — Streamlit App

Replaces the Power BI longitudinal report with a Streamlit app, reading GPS +
Firstbeat data live from Dropbox.

## What's in here
- `app.py` — the page itself (player dropdown, 5 charts, refresh button)
- `charts.py` — builds the 5 plotly charts
- `theme.py` — LCFC colours + shared helpers
- `data_loader.py` — pulls the two Excel files from Dropbox, cached 30s
- `requirements.txt`
- `.streamlit/secrets.toml.example` — copy to `secrets.toml` and fill in

## 1. Set up Dropbox access
Go to the [Dropbox App Console](https://www.dropbox.com/developers/apps),
create an app (Scoped access, "Full Dropbox" or a specific folder), and
enable the `files.content.read` permission.

- **Quickest for testing:** generate an access token in the App Console and
  paste it into `secrets.toml` as `access_token`. It expires in a few hours.
- **For the real SharePoint-embedded app:** use the refresh-token flow so it
  never expires — `app_key` + `app_secret` + `refresh_token` (Dropbox's docs
  under "OAuth guide" walk through getting a refresh token once; after that
  the app renews itself automatically). This is what's wired up in
  `data_loader.py`.

Set `gps_path` / `firstbeat_path` to the exact paths of your two files in
Dropbox, e.g. `/GPS Dummy Data.xlsx` and `/firstbeat_data.xlsx`.

## 2. Run locally
```bash
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml   # then edit it
streamlit run app.py
```

## 3. Data refresh
- The data cache has a 30 second TTL (`CACHE_TTL_SECONDS` in
  `data_loader.py`), and `st_autorefresh` reruns the app every 30s, so it
  behaves like a live feed of whatever you last saved in Dropbox.
- There's also a manual **"🔄 Refresh data now"** button that forces an
  immediate reload regardless of the 30s timer.

## 4. Deploying so it can sit inside SharePoint
1. Deploy the app somewhere reachable (Streamlit Community Cloud is the
   easiest free option; internally you could also use Azure App Service /
   a VM behind your firewall — talk to IT about what's already approved).
2. Add the Dropbox secrets in that platform's secrets manager (same keys as
   `secrets.toml`).
3. In SharePoint, add an **Embed** web part on the page and point it at your
   app's URL. Two things to check with your IT/security team up front:
   - The hosting platform must allow being loaded in an iframe (set
     `X-Frame-Options` / CSP `frame-ancestors` to allow your SharePoint
     domain — Streamlit Cloud allows embedding by default, self-hosted
     needs this configured).
   - If your SharePoint is behind SSO/VPN, the Streamlit host needs to be
     reachable from wherever people are opening the SharePoint page.

## Notes / assumptions made when building this
- **Sprint Distance**: your file doesn't have a "Velocity Band 6 Total
  Distance" column, only `Velocity Band 6 Total Effort Count`. I used the
  `SD` column (Sprint Distance) for the top segment of the HSR/SD stacked
  bar instead — let me know if that's wrong and it's a one-line fix.
- **Daily totals**: each bar uses the player's whole-session row per day —
  GPS `Period Number == 0` (row named "Session") and Firstbeat
  `Analysis period == "Measurement"` — rather than summing every drill.
- **x-axis label**: `DD/MM - DayType` straight from the GPS `Day` column
  (e.g. `13/01 - Reactivation`).
- **ACWR line**: exponentially weighted, acute = 7-day span, chronic =
  21-day span, computed over the player's full history (missing training
  days counted as 0) so the rolling windows are accurate, then only the
  visible dates are plotted. HSR/SD chart uses combined HSR+SD load;
  the two accel/decel charts each use their own combined accel+decel load.
- **HR chart's floating value**: shows whichever is higher, Aerobic TE or
  Anaerobic TE, per day — rendered as text only (no visible line/marker),
  per your "invisible line" request.
