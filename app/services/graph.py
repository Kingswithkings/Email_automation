import httpx


async def get_me(access_token: str):
    headers = {"Authorization": f"Bearer {access_token}"}

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            "https://graph.microsoft.com/v1.0/me",
            headers=headers,
        )

    try:
        data = response.json()
    except Exception:
        data = {"raw_response": response.text}

    return {
        "status_code": response.status_code,
        "data": data,
    }


async def list_messages(access_token: str, top: int = 10):
    headers = {"Authorization": f"Bearer {access_token}"}
    url = f"https://graph.microsoft.com/v1.0/me/messages?$top={top}"

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(url, headers=headers)

    try:
        data = response.json()
    except Exception:
        data = {"raw_response": response.text}

    messages = data.get("value", []) if isinstance(data, dict) else []

    return {
        "status_code": response.status_code,
        "data": messages,
        "raw_data": data,
    }


async def send_mail(access_token: str, to_email: str, subject: str, body: str):
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    payload = {
        "message": {
            "subject": subject,
            "body": {
                "contentType": "Text",
                "content": body,
            },
            "toRecipients": [
                {
                    "emailAddress": {
                        "address": to_email,
                    }
                }
            ],
        },
        "saveToSentItems": True,
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            "https://graph.microsoft.com/v1.0/me/sendMail",
            headers=headers,
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
