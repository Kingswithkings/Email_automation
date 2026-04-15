import httpx

from app.config import MAILBOX_EMAIL, ZOHO_MAIL_BASE


def _auth_headers(access_token: str) -> dict:
    return {"Authorization": f"Zoho-oauthtoken {access_token}"}


def _extract_accounts(data: dict) -> list[dict]:
    accounts = data.get("data", [])
    return accounts if isinstance(accounts, list) else []


def _select_account(accounts: list[dict], mailbox_email: str = "") -> dict | None:
    preferred_email = (mailbox_email or MAILBOX_EMAIL).lower()

    if preferred_email:
        for account in accounts:
            primary = str(account.get("primaryEmailAddress", "")).lower()
            mailbox = str(account.get("mailboxAddress", "")).lower()
            if preferred_email in {primary, mailbox}:
                return account

    for account in accounts:
        if account.get("status") or account.get("enabled"):
            return account

    return accounts[0] if accounts else None


async def _get_accounts(access_token: str) -> dict:
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            f"{ZOHO_MAIL_BASE}/api/accounts",
            headers=_auth_headers(access_token),
        )

    try:
        data = response.json()
    except Exception:
        data = {"raw_response": response.text}

    return {
        "status_code": response.status_code,
        "data": data,
    }


async def _get_folders(access_token: str, account_id: str) -> dict:
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            f"{ZOHO_MAIL_BASE}/api/accounts/{account_id}/folders",
            headers=_auth_headers(access_token),
        )

    try:
        data = response.json()
    except Exception:
        data = {"raw_response": response.text}

    return {
        "status_code": response.status_code,
        "data": data,
    }


def _extract_folders(data: dict) -> list[dict]:
    folders = data.get("data", [])
    return folders if isinstance(folders, list) else []


def _select_inbox_folder(folders: list[dict]) -> dict | None:
    for folder in folders:
        folder_type = str(folder.get("folderType", "")).lower()
        folder_name = str(folder.get("folderName", "")).lower()
        if folder_type == "inbox" or folder_name == "inbox":
            return folder
    return folders[0] if folders else None


async def _get_account_context(access_token: str, mailbox_email: str = "") -> dict:
    result = await _get_accounts(access_token)
    if result["status_code"] != 200:
        return result

    accounts = _extract_accounts(result["data"])
    selected = _select_account(accounts, mailbox_email)
    if not selected:
        return {
            "status_code": 404,
            "data": {
                "message": "No Zoho mailbox accounts were returned for this user.",
            },
        }

    send_details = selected.get("sendMailDetails", [])
    from_address = selected.get("primaryEmailAddress") or selected.get("mailboxAddress")
    if isinstance(send_details, list):
        for detail in send_details:
            if detail.get("status") and detail.get("fromAddress"):
                from_address = detail["fromAddress"]
                break

    return {
        "status_code": 200,
        "data": {
            "accounts": accounts,
            "account": selected,
            "account_id": selected.get("accountId"),
            "mailbox_email": selected.get("primaryEmailAddress") or selected.get("mailboxAddress"),
            "from_address": from_address,
        },
    }


async def get_me(access_token: str, mailbox_email: str = "") -> dict:
    result = await _get_account_context(access_token, mailbox_email)
    if result["status_code"] != 200:
        return result

    account = result["data"]["account"]
    profile = {
        "id": account.get("accountId"),
        "displayName": account.get("displayName") or account.get("accountDisplayName"),
        "mail": account.get("primaryEmailAddress") or account.get("mailboxAddress"),
        "userPrincipalName": account.get("primaryEmailAddress") or account.get("mailboxAddress"),
        "provider": "zoho",
    }
    return {
        "status_code": 200,
        "data": profile,
    }


async def list_messages(access_token: str, top: int = 10, mailbox_email: str = "") -> dict:
    context = await _get_account_context(access_token, mailbox_email)
    if context["status_code"] != 200:
        return context

    account_id = context["data"]["account_id"]
    folders_result = await _get_folders(access_token, account_id)
    if folders_result["status_code"] != 200:
        return folders_result

    folders = _extract_folders(folders_result["data"])
    inbox_folder = _select_inbox_folder(folders)
    if not inbox_folder:
        return {
            "status_code": 404,
            "data": {
                "message": "Zoho mailbox folders were returned, but no inbox folder was found.",
                "folders": folders,
            },
        }

    params = {
        "limit": top,
        "folderId": inbox_folder.get("folderId"),
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            f"{ZOHO_MAIL_BASE}/api/accounts/{account_id}/messages/view",
            headers=_auth_headers(access_token),
            params=params,
        )

    try:
        raw_data = response.json()
    except Exception:
        raw_data = {"raw_response": response.text}

    raw_messages = raw_data.get("data", [])
    messages = []
    if isinstance(raw_messages, list):
        for item in raw_messages:
            sender = item.get("fromAddress") or item.get("sender")
            messages.append(
                {
                    "id": item.get("messageId") or item.get("msgId"),
                    "subject": item.get("subject", ""),
                    "bodyPreview": item.get("summary", "") or item.get("content", ""),
                    "receivedDateTime": item.get("receivedTime") or item.get("receivedDate"),
                    "from": {
                        "emailAddress": {
                            "address": sender or "unknown",
                        }
                    },
                    "provider": "zoho",
                    "raw": item,
                }
            )

    return {
        "status_code": response.status_code,
        "data": messages,
        "raw_data": raw_data,
    }


async def send_mail(
    access_token: str,
    to_email: str,
    subject: str,
    body: str,
    mailbox_email: str = "",
) -> dict:
    context = await _get_account_context(access_token, mailbox_email)
    if context["status_code"] != 200:
        return context

    account_id = context["data"]["account_id"]
    from_address = context["data"]["from_address"]
    payload = {
        "fromAddress": from_address,
        "toAddress": to_email,
        "subject": subject,
        "content": body,
        "mailFormat": "plaintext",
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{ZOHO_MAIL_BASE}/api/accounts/{account_id}/messages",
            headers=_auth_headers(access_token),
            json=payload,
        )

    try:
        data = response.json()
    except Exception:
        data = {"raw_response": response.text}

    return {
        "status_code": response.status_code,
        "data": data,
    }
