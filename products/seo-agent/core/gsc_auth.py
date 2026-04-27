"""Bootstrap GSC OAuth token. Run once locally:

    python -m core.gsc_auth

Opens a browser, performs OAuth, writes token to GSC_TOKEN_PATH.
After bootstrap, copy the token JSON to the VPS credentials/ volume.
"""

from core.gsc_client import load_credentials


def main() -> None:
    creds = load_credentials()
    print("OAuth complete.")
    print(f"Token written. valid={creds.valid}, has_refresh={bool(creds.refresh_token)}")


if __name__ == "__main__":
    main()
