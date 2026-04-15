import os

from dotenv import load_dotenv

load_dotenv()

SESSION_SECRET = os.getenv("SESSION_SECRET", "dev-secret").strip()
MAIL_PROVIDER = os.getenv("MAIL_PROVIDER", "auto").strip().lower()
MAILBOX_EMAIL = os.getenv("MAILBOX_EMAIL", "").strip().lower()
AUTO_ROUTE_ENABLED = os.getenv("AUTO_ROUTE_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}
AUTO_ROUTE_INTERVAL_SECONDS = int(os.getenv("AUTO_ROUTE_INTERVAL_SECONDS", "60").strip())

AZURE_TENANT_ID = os.getenv("AZURE_TENANT_ID", "").strip()
AZURE_CLIENT_ID = os.getenv("AZURE_CLIENT_ID", "").strip()
AZURE_CLIENT_SECRET = os.getenv("AZURE_CLIENT_SECRET", "").strip()
AZURE_REDIRECT_URI = os.getenv("AZURE_REDIRECT_URI", "").strip()

ZOHO_CLIENT_ID = os.getenv("ZOHO_CLIENT_ID", "").strip()
ZOHO_CLIENT_SECRET = os.getenv("ZOHO_CLIENT_SECRET", "").strip()
ZOHO_REDIRECT_URI = os.getenv("ZOHO_REDIRECT_URI", "").strip()
ZOHO_ACCOUNTS_BASE = os.getenv("ZOHO_ACCOUNTS_BASE", "https://accounts.zoho.com").strip().rstrip("/")
ZOHO_MAIL_BASE = os.getenv("ZOHO_MAIL_BASE", "https://mail.zoho.com").strip().rstrip("/")

MICROSOFT_SCOPES = [
    "openid",
    "profile",
    "email",
    "offline_access",
    "User.Read",
    "Mail.Read",
    "Mail.Send",
]

ZOHO_SCOPES = [
    "ZohoMail.accounts.READ",
    "ZohoMail.folders.READ",
    "ZohoMail.messages.ALL",
]


def _is_complete(*values: str) -> bool:
    return all(bool(value) for value in values)


def get_default_provider() -> str:
    if MAIL_PROVIDER in {"microsoft", "zoho"}:
        return MAIL_PROVIDER

    if _is_complete(ZOHO_CLIENT_ID, ZOHO_CLIENT_SECRET, ZOHO_REDIRECT_URI):
        return "zoho"

    return "microsoft"


def get_provider_config(provider: str | None = None) -> dict:
    resolved = (provider or get_default_provider()).strip().lower()

    if resolved == "zoho":
        missing = [
            name
            for name, value in [
                ("ZOHO_CLIENT_ID", ZOHO_CLIENT_ID),
                ("ZOHO_CLIENT_SECRET", ZOHO_CLIENT_SECRET),
                ("ZOHO_REDIRECT_URI", ZOHO_REDIRECT_URI),
            ]
            if not value
        ]
        if missing:
            raise ValueError(f"Zoho mail is selected, but these .env values are missing: {', '.join(missing)}")

        return {
            "provider": "zoho",
            "label": "Zoho",
            "client_id": ZOHO_CLIENT_ID,
            "client_secret": ZOHO_CLIENT_SECRET,
            "redirect_uri": ZOHO_REDIRECT_URI,
            "authorize_url": f"{ZOHO_ACCOUNTS_BASE}/oauth/v2/auth",
            "token_url": f"{ZOHO_ACCOUNTS_BASE}/oauth/v2/token",
            "scopes": ZOHO_SCOPES,
            "scope_delimiter": ",",
            "auth_params": {
                "access_type": "offline",
                "prompt": "consent",
            },
            "mailbox_email": MAILBOX_EMAIL,
        }

    missing = [
        name
        for name, value in [
            ("AZURE_TENANT_ID", AZURE_TENANT_ID),
            ("AZURE_CLIENT_ID", AZURE_CLIENT_ID),
            ("AZURE_CLIENT_SECRET", AZURE_CLIENT_SECRET),
            ("AZURE_REDIRECT_URI", AZURE_REDIRECT_URI),
        ]
        if not value
    ]
    if missing:
        raise ValueError(f"Microsoft mail is selected, but these .env values are missing: {', '.join(missing)}")

    authority = f"https://login.microsoftonline.com/{AZURE_TENANT_ID}"
    return {
        "provider": "microsoft",
        "label": "Microsoft",
        "client_id": AZURE_CLIENT_ID,
        "client_secret": AZURE_CLIENT_SECRET,
        "redirect_uri": AZURE_REDIRECT_URI,
        "authorize_url": f"{authority}/oauth2/v2.0/authorize",
        "token_url": f"{authority}/oauth2/v2.0/token",
        "scopes": MICROSOFT_SCOPES,
        "scope_delimiter": " ",
        "auth_params": {
            "response_mode": "query",
        },
        "mailbox_email": MAILBOX_EMAIL,
    }
