"""
One-time helper: run this locally to get your Dropbox refresh token.
It does the whole exchange in one go, so there's no risk of the
authorization code timing out between copy and paste.

Usage:
    pip install requests
    python get_refresh_token.py
Then follow the prompts.
"""
import requests
import webbrowser

def main():
    app_key = input("Paste your Dropbox App key: ").strip()
    app_secret = input("Paste your Dropbox App secret: ").strip()

    print(f"\nApp key you entered   : '{app_key}'  (length {len(app_key)})")
    print(f"App secret you entered: '{app_secret}'  (length {len(app_secret)})")
    if app_key == app_secret:
        print("\n!! WARNING: your App key and App secret are IDENTICAL.")
        print("!! You've almost certainly pasted the same value into both prompts.")
        print("!! Go back to the Dropbox App Console Settings tab and copy each")
        print("!! one separately - they should look different from each other.")
        return
    if " " in app_key or " " in app_secret:
        print("\n!! WARNING: there's a space in one of these values - that")
        print("!! usually means extra text got copied along with it.")
        return
    confirm = input("\nDo these look correct? (y/n): ").strip().lower()
    if confirm != "y":
        print("Stopping - re-copy the values from Dropbox Settings and try again.")
        return

    auth_url = (
        f"https://www.dropbox.com/oauth2/authorize?client_id={app_key}"
        f"&token_access_type=offline&response_type=code"
    )
    print("\nOpening your browser to the Dropbox authorization page...")
    print("If it doesn't open automatically, go to this URL yourself:")
    print(auth_url)
    webbrowser.open(auth_url)

    print("\nClick 'Allow' in the browser, then immediately copy the code shown.")
    code = input("Paste the authorization code here now: ").strip()

    print("\nExchanging code for a refresh token...")
    resp = requests.post(
        "https://api.dropbox.com/oauth2/token",
        data={
            "code": code,
            "grant_type": "authorization_code",
            "client_id": app_key,
            "client_secret": app_secret,
        },
    )

    if resp.status_code != 200:
        print("\n--- FAILED ---")
        print(resp.status_code, resp.text)
        print("\nMost likely cause: the code expired or was already used.")
        print("Just run this script again and go a bit faster this time -")
        print("everything after clicking 'Allow' should take under 15 seconds.")
        return

    data = resp.json()
    print("\n--- SUCCESS ---")
    print("Add this to your secrets.toml:\n")
    print(f'app_key = "{app_key}"')
    print(f'app_secret = "{app_secret}"')
    print(f'refresh_token = "{data["refresh_token"]}"')
    print("\n(Remove any 'access_token' line if you still have one - use these three instead.)")

if __name__ == "__main__":
    main()
