import requests
from fastapi import HTTPException

GRAPH_BASE = "https://graph.microsoft.com/v1.0"


def get_me(access_token: str) -> dict:
    if not access_token:
        raise HTTPException(status_code=401, detail="Access token is empty.")

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    try:
        resp = requests.get(f"{GRAPH_BASE}/me", headers=headers, timeout=30)
    except requests.RequestException as e:
        raise HTTPException(
            status_code=500,
            detail=f"Graph /me request failed: {str(e)}",
        )

    print("ME STATUS:", resp.status_code)
    print("ME TEXT:", resp.text)

    if resp.status_code != 200:
        try:
            detail = resp.json()
        except Exception:
            detail = {
                "status_code": resp.status_code,
                "raw_response": resp.text or "empty response from Microsoft Graph",
            }
        raise HTTPException(status_code=resp.status_code, detail=detail)

    try:
        return resp.json()
    except Exception:
        raise HTTPException(
            status_code=500,
            detail={
                "status_code": resp.status_code,
                "raw_response": resp.text or "Graph returned non-JSON success response for /me",
            },
        )


def get_unread_emails(access_token: str, top: int = 10) -> list[dict]:
    if not access_token:
        raise HTTPException(status_code=401, detail="Access token is empty.")

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    params = {
        "$top": top,
        "$select": "id,subject,bodyPreview,body,from,isRead,receivedDateTime",
        "$orderby": "receivedDateTime desc",
        "$filter": "isRead eq false",
    }

    try:
        resp = requests.get(
            f"{GRAPH_BASE}/me/messages",
            headers=headers,
            params=params,
            timeout=30,
        )
    except requests.RequestException as e:
        raise HTTPException(
            status_code=500,
            detail=f"Graph request failed: {str(e)}",
        )

    print("GRAPH STATUS:", resp.status_code)
    print("GRAPH TEXT:", resp.text)

    if resp.status_code != 200:
        try:
            detail = resp.json()
        except Exception:
            detail = {
                "status_code": resp.status_code,
                "raw_response": resp.text or "empty response from Microsoft Graph",
            }
        raise HTTPException(status_code=resp.status_code, detail=detail)

    try:
        data = resp.json()
    except Exception:
        raise HTTPException(
            status_code=500,
            detail={
                "status_code": resp.status_code,
                "raw_response": resp.text or "Graph returned non-JSON success response",
            },
        )

    return data.get("value", [])


def mark_email_as_read(access_token: str, message_id: str) -> bool:
    if not access_token:
        raise HTTPException(status_code=401, detail="Access token is empty.")

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    payload = {"isRead": True}

    try:
        resp = requests.patch(
            f"{GRAPH_BASE}/me/messages/{message_id}",
            headers=headers,
            json=payload,
            timeout=30,
        )
    except requests.RequestException as e:
        print("MARK READ REQUEST ERROR:", str(e))
        return False

    print("MARK READ STATUS:", resp.status_code)
    print("MARK READ TEXT:", resp.text)

    return resp.status_code in (200, 204)