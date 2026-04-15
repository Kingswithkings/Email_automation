from app.services import graph, zoho


def _get_provider(token_data: dict) -> str:
    return (token_data.get("provider") or "microsoft").strip().lower()


def _get_access_token(token_data: dict) -> str:
    return token_data.get("access_token", "")


def _get_mailbox_email(token_data: dict) -> str:
    return token_data.get("mailbox_email", "")


async def get_me(token_data: dict) -> dict:
    provider = _get_provider(token_data)
    access_token = _get_access_token(token_data)
    mailbox_email = _get_mailbox_email(token_data)

    if provider == "zoho":
        return await zoho.get_me(access_token, mailbox_email)

    return await graph.get_me(access_token)


async def list_messages(token_data: dict, top: int = 10) -> dict:
    provider = _get_provider(token_data)
    access_token = _get_access_token(token_data)
    mailbox_email = _get_mailbox_email(token_data)

    if provider == "zoho":
        return await zoho.list_messages(access_token, top=top, mailbox_email=mailbox_email)

    return await graph.list_messages(access_token, top=top)


async def send_mail(token_data: dict, to_email: str, subject: str, body: str) -> dict:
    provider = _get_provider(token_data)
    access_token = _get_access_token(token_data)
    mailbox_email = _get_mailbox_email(token_data)

    if provider == "zoho":
        return await zoho.send_mail(
            access_token,
            to_email=to_email,
            subject=subject,
            body=body,
            mailbox_email=mailbox_email,
        )

    return await graph.send_mail(
        access_token,
        to_email=to_email,
        subject=subject,
        body=body,
    )
