"""
One-time helper: lists every file in your Dropbox (or Team space) so you can
see the EXACT paths to put in secrets.toml - no guessing needed.

Usage:
    pip install dropbox
    python list_dropbox_files.py
It will ask for your app_key / app_secret / refresh_token (the same three
values you already put in secrets.toml) and print out every file path it
can see.
"""
import sys
import dropbox

def main():
    print("Paste your Dropbox App key: ", end="", file=sys.stderr, flush=True)
    app_key = input().strip()
    print("Paste your Dropbox App secret: ", end="", file=sys.stderr, flush=True)
    app_secret = input().strip()
    print("Paste your refresh_token: ", end="", file=sys.stderr, flush=True)
    refresh_token = input().strip()

    dbx = dropbox.Dropbox(
        oauth2_refresh_token=refresh_token,
        app_key=app_key,
        app_secret=app_secret,
    )

    account = dbx.users_get_current_account()
    root_ns = account.root_info.root_namespace_id
    home_ns = account.root_info.home_namespace_id
    if root_ns != home_ns:
        print(f"(Detected a Team space - using namespace root {root_ns})", file=sys.stderr)
        dbx = dbx.with_path_root(dropbox.common.PathRoot.namespace_id(root_ns))

    print("\nBrowsing your Dropbox. At each step, type a [FOLDER] path shown", file=sys.stderr)
    print("to go deeper, or type 'q' to quit.\n", file=sys.stderr)

    current = ""
    while True:
        result = dbx.files_list_folder(current, recursive=False)
        entries = []
        while True:
            entries.extend(result.entries)
            if not result.has_more:
                break
            result = dbx.files_list_folder_continue(result.cursor)

        label = current if current else "(top level)"
        print(f"\n--- Contents of {label} ---", file=sys.stderr)
        for entry in entries:
            if isinstance(entry, dropbox.files.FolderMetadata):
                print(f"[FOLDER] {entry.path_display}")
            elif isinstance(entry, dropbox.files.FileMetadata):
                print(f"[FILE]   {entry.path_display}")

        choice = input(
            "\nPaste a [FOLDER] path above to go deeper, or 'q' to quit: "
        ).strip()
        if choice.lower() == "q" or choice == "":
            print("Done. Copy the [FILE] path(s) you need into secrets.toml", file=sys.stderr)
            print("as gps_path / firstbeat_path.", file=sys.stderr)
            break
        current = choice

if __name__ == "__main__":
    main()
