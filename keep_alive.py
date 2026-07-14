name: Keep Streamlit app awake

on:
  schedule:
    # Best practical free-tier mitigation: check every 5 minutes. This
    # can't GUARANTEE the app is never asleep (Streamlit controls sleep
    # behaviour server-side and it's not reliably documented/consistent),
    # but it shrinks the risk window to something small enough that real
    # usage patterns are very unlikely to ever hit it.
    - cron: "*/5 * * * *"
  workflow_dispatch:  # lets you also trigger it manually from the Actions tab

jobs:
  wake-app:
    runs-on: ubuntu-latest
    steps:
      - name: Install Playwright
        run: |
          pip install playwright
          playwright install --with-deps chromium

      - name: Checkout repo
        uses: actions/checkout@v4

      - name: Visit the app to keep it awake
        env:
          STREAMLIT_URL: https://YOUR-APP-NAME.streamlit.app
        run: python keep_alive.py