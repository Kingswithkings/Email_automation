import os
import json
import asyncio

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from openai import AsyncOpenAI

from app.config import (
    AUTO_ROUTE_ENABLED,
    AUTO_ROUTE_INTERVAL_SECONDS,
    SESSION_SECRET,
    get_default_provider,
)
from app.db import Base, SessionLocal, engine
from app.models import ProcessedMailboxMessage
from app.routes.auth import (
    TOKEN_STORE,
    ensure_valid_session_token,
    load_token_store,
    router as auth_router,
)
from app.services.mail import get_me, list_messages, send_mail

load_dotenv()

app = FastAPI(title="Warehouse Department Email Routing System")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)

DEPARTMENT_EMAILS = {
    "finance": "finance@1st-kings.com",
    "operations": "operations@1st-kings.com",
    "inventory": "operations@1st-kings.com",
    "logistics": "operations@1st-kings.com",
    "procurement": "operations@1st-kings.com",
    "hr": "management@1st-kings.com",
    "customer_service": "support@1st-kings.com",
    "returns_claims": "support@1st-kings.com",
    "maintenance": "operations@1st-kings.com",
    "it_systems": "management@1st-kings.com",
    "management": "management@1st-kings.com",
    "general": "support@1st-kings.com",
}

DEPARTMENT_KEYWORDS = {
    "finance": [
        "money", "budget", "payment", "salary", "income", "expenses",
        "invoice", "billing", "payroll", "cost", "revenue", "profit",
        "loss", "purchase order", "po", "refund", "bank", "transaction",
        "quotation", "quote", "receipt", "cashflow", "financial"
    ],
    "operations": [
        "dispatch", "shipment", "delivery", "pick", "packing", "warehouse",
        "loading", "unloading", "fulfilment", "fulfillment", "processing",
        "order ready", "ship today", "urgent dispatch",
        "sku", "units", "order", "dispatch order", "pick ticket"
    ],
    "inventory": [
        "stock", "inventory", "out of stock", "replenishment", "sku",
        "cycle count", "stock level", "restock", "available quantity",
        "count", "quantity available"
    ],
    "logistics": [
        "transport", "courier", "route", "truck", "driver", "delay",
        "late delivery", "freight", "shipping", "pallet", "container",
        "vehicle", "haulage"
    ],
    "procurement": [
        "supplier", "vendor", "purchase", "procure", "sourcing",
        "purchase order", "po", "quote", "quotation", "buy", "ordering"
    ],
    "hr": [
        "leave", "staff", "employee", "recruitment", "hiring",
        "absence", "holiday", "disciplinary", "training",
        "resignation", "interview", "promotion"
    ],
    "customer_service": [
        "customer", "support", "help", "complaint", "service",
        "follow up", "request update", "issue", "feedback"
    ],
    "returns_claims": [
        "damaged", "broken", "faulty", "defective", "return",
        "claim", "replacement", "wrong item", "missing item"
    ],
    "maintenance": [
        "repair", "machine", "equipment", "maintenance", "breakdown",
        "fault", "service request", "generator", "forklift"
    ],
    "it_systems": [
        "system", "login", "password", "software", "network",
        "printer", "scanner", "access", "email issue", "vpn",
        "computer", "laptop", "internet"
    ],
    "management": [
        "escalation", "approval", "approve", "manager", "director",
        "urgent review", "board", "decision"
    ],
}

PRIORITY_KEYWORDS = {
    "high": [
        "urgent", "asap", "immediately", "today", "now",
        "critical", "emergency", "blocked", "cannot proceed",
        "delay", "failed", "failure", "escalation"
    ],
    "medium": [
        "soon", "important", "review", "approval", "pending",
        "follow up", "this week", "attention"
    ],
    "low": [
        "whenever", "no rush", "next week", "for review",
        "fyi", "information only"
    ],
}

URGENCY_MAP = {
    "high": "immediate",
    "medium": "soon",
    "low": "routine",
}

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8501",
        "http://127.0.0.1:8501",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    same_site="lax",
    https_only=False,
    max_age=3600,
)

app.include_router(auth_router)

processed_email_store = []
automation_log_store = []
auto_route_task: asyncio.Task | None = None


class EmailInput(BaseModel):
    sender: str
    subject: str
    body: str


def get_token_data_from_session(request: Request):
    session_id = request.session.get("session_id")
    if not session_id:
        return None
    return TOKEN_STORE.get(session_id)


def init_database():
    Base.metadata.create_all(bind=engine)


def get_processed_message_ids() -> set[str]:
    db = SessionLocal()
    try:
        rows = db.query(ProcessedMailboxMessage.message_id).all()
        return {row[0] for row in rows}
    finally:
        db.close()


def save_processed_message(
    provider: str,
    mailbox_email: str,
    message_id: str,
    subject: str,
    sender: str,
    routed_to: str,
):
    db = SessionLocal()
    try:
        exists = db.query(ProcessedMailboxMessage).filter_by(message_id=message_id).first()
        if exists:
            return

        db.add(
            ProcessedMailboxMessage(
                provider=provider or "unknown",
                mailbox_email=mailbox_email or "unknown",
                message_id=message_id,
                subject=subject,
                sender=sender,
                routed_to=routed_to,
            )
        )
        db.commit()
    finally:
        db.close()


def get_active_mail_sessions() -> list[tuple[str, dict]]:
    active_tokens = []
    for session_id, token_data in TOKEN_STORE.items():
        if token_data.get("access_token"):
            active_tokens.append((session_id, token_data))
    return active_tokens


def normalize_text(subject: str, body: str) -> str:
    return f"{subject} {body}".lower().strip()


def apply_department_bias(text: str, scores: dict):
    if any(x in text for x in ["dispatch", "order", "sku", "units"]):
        scores["operations"] = scores.get("operations", 0) + 2

    if any(x in text for x in ["truck", "driver", "route", "freight"]):
        scores["logistics"] = scores.get("logistics", 0) + 2

    return scores


def detect_priority_by_rules(subject: str, body: str):
    text = normalize_text(subject, body)

    high_matches = [kw for kw in PRIORITY_KEYWORDS["high"] if kw in text]
    medium_matches = [kw for kw in PRIORITY_KEYWORDS["medium"] if kw in text]
    low_matches = [kw for kw in PRIORITY_KEYWORDS["low"] if kw in text]

    if high_matches:
        return {
            "priority": "high",
            "urgency": URGENCY_MAP["high"],
            "priority_reason": f"Matched high priority keywords: {', '.join(high_matches)}",
            "priority_method": "rules",
        }

    if medium_matches:
        return {
            "priority": "medium",
            "urgency": URGENCY_MAP["medium"],
            "priority_reason": f"Matched medium priority keywords: {', '.join(medium_matches)}",
            "priority_method": "rules",
        }

    if low_matches:
        return {
            "priority": "low",
            "urgency": URGENCY_MAP["low"],
            "priority_reason": f"Matched low priority keywords: {', '.join(low_matches)}",
            "priority_method": "rules",
        }

    return {
        "priority": "medium",
        "urgency": "soon",
        "priority_reason": "No strong priority keywords found. Defaulted to medium.",
        "priority_method": "rules",
    }


def classify_email_by_rules(subject: str, body: str):
    text = normalize_text(subject, body)
    scores = {}

    for dept, keywords in DEPARTMENT_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in text)
        if score > 0:
            scores[dept] = score

    scores = apply_department_bias(text, scores)

    if not scores:
        return {
            "department": "general",
            "confidence": "low",
            "method": "rules",
            "matched_keywords": [],
            "reason": "No match",
        }

    best = max(scores, key=scores.get)
    score = scores[best]
    matched_keywords = [kw for kw in DEPARTMENT_KEYWORDS[best] if kw in text]

    confidence = "high" if score >= 3 else "medium" if score == 2 else "low"

    return {
        "department": best,
        "confidence": confidence,
        "method": "rules",
        "matched_keywords": matched_keywords,
        "reason": f"Rule match score: {score}",
    }


async def classify_email_ai(subject: str, body: str):
    try:
        prompt = f"""
Classify this email into one department:
finance, operations, inventory, logistics, procurement, hr,
customer_service, returns_claims, maintenance, it_systems,
management, general

Also assign:
- priority: high, medium, or low
- urgency: immediate, soon, or routine

Return valid JSON only in this exact format:
{{
  "department": "...",
  "confidence": "high",
  "reason": "...",
  "priority": "medium",
  "urgency": "soon",
  "priority_reason": "..."
}}

Subject: {subject}
Body: {body}
"""
        res = await ai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )

        data = json.loads(res.choices[0].message.content)

        department = data.get("department", "general")
        if department not in DEPARTMENT_EMAILS:
            department = "general"

        confidence = data.get("confidence", "low")
        if confidence not in ["high", "medium", "low"]:
            confidence = "low"

        priority = data.get("priority", "medium")
        if priority not in ["high", "medium", "low"]:
            priority = "medium"

        urgency = data.get("urgency", "soon")
        if urgency not in ["immediate", "soon", "routine"]:
            urgency = "soon"

        return {
            "department": department,
            "confidence": confidence,
            "method": "ai",
            "matched_keywords": [],
            "reason": data.get("reason", ""),
            "priority": priority,
            "urgency": urgency,
            "priority_reason": data.get("priority_reason", "AI assigned priority."),
            "priority_method": "ai",
        }

    except Exception as e:
        return {
            "department": "general",
            "confidence": "low",
            "method": "ai_failed",
            "matched_keywords": [],
            "reason": str(e),
            "priority": "medium",
            "urgency": "soon",
            "priority_reason": f"AI priority detection failed: {str(e)}",
            "priority_method": "ai_failed",
        }


async def classify_email(subject: str, body: str):
    rule_result = classify_email_by_rules(subject, body)
    rule_priority = detect_priority_by_rules(subject, body)

    if rule_result["confidence"] in ["high", "medium"]:
        return {
            **rule_result,
            **rule_priority,
        }

    ai_result = await classify_email_ai(subject, body)
    return ai_result


def route_department_email(department: str) -> str:
    return DEPARTMENT_EMAILS.get(department, DEPARTMENT_EMAILS["general"])


async def process_mailbox_messages(token_data: dict, trigger: str) -> list[dict]:
    result = await list_messages(token_data)
    if result["status_code"] != 200:
        return []

    processed_ids = get_processed_message_ids()
    routed_rows = []

    for email in result["data"]:
        message_id = email.get("id")
        if not message_id or message_id in processed_ids:
            continue

        subject = email.get("subject", "") or ""
        body_preview = email.get("bodyPreview", "") or ""

        sender_info = email.get("from", {}) or {}
        sender_email = (sender_info.get("emailAddress", {}) or {}).get("address", "unknown")

        classification = await classify_email(subject, body_preview)
        routed_to = route_department_email(classification["department"])

        forward_subject = f"[{classification['department'].upper()} | {classification['priority'].upper()}] {subject}"
        forward_body = (
            f"Email auto-routed by Warehouse Department Routing System.\n\n"
            f"Original sender: {sender_email}\n"
            f"Department: {classification['department']}\n"
            f"Confidence: {classification['confidence']}\n"
            f"Method: {classification['method']}\n"
            f"Reason: {classification['reason']}\n"
            f"Priority: {classification['priority']}\n"
            f"Urgency: {classification['urgency']}\n"
            f"Priority reason: {classification['priority_reason']}\n"
            f"Priority method: {classification['priority_method']}\n"
            f"Matched keywords: {', '.join(classification['matched_keywords']) if classification['matched_keywords'] else 'None'}\n"
            f"Original subject: {subject}\n\n"
            f"Preview:\n{body_preview}"
        )

        send_result = await send_mail(
            token_data=token_data,
            to_email=routed_to,
            subject=forward_subject,
            body=forward_body,
        )

        redirected = send_result["status_code"] in [200, 202]
        if redirected:
            save_processed_message(
                provider=token_data.get("provider", "unknown"),
                mailbox_email=token_data.get("mailbox_email", ""),
                message_id=message_id,
                subject=subject,
                sender=sender_email,
                routed_to=routed_to,
            )
            processed_ids.add(message_id)

        log_record = {
            "message_id": message_id,
            "sender": sender_email,
            "subject": subject,
            "body_preview": body_preview,
            "provider": token_data.get("provider"),
            "department": classification["department"],
            "category": classification["department"],
            "confidence": classification["confidence"],
            "method": classification["method"],
            "reason": classification["reason"],
            "matched_keywords": classification["matched_keywords"],
            "priority": classification["priority"],
            "urgency": classification["urgency"],
            "priority_reason": classification["priority_reason"],
            "priority_method": classification["priority_method"],
            "redirected_to": routed_to,
            "send_status_code": send_result["status_code"],
            "redirected": redirected,
            "trigger": trigger,
        }

        automation_log_store.append(log_record)
        routed_rows.append(log_record)

    return routed_rows


async def auto_route_loop():
    while True:
        try:
            for session_id, _ in get_active_mail_sessions():
                token_data = await ensure_valid_session_token(session_id)
                if not token_data:
                    continue

                await process_mailbox_messages(token_data, trigger="poller")
        except Exception:
            pass

        await asyncio.sleep(max(AUTO_ROUTE_INTERVAL_SECONDS, 15))


@app.on_event("startup")
async def on_startup():
    global auto_route_task
    load_token_store()
    init_database()
    if AUTO_ROUTE_ENABLED and auto_route_task is None:
        auto_route_task = asyncio.create_task(auto_route_loop())


@app.on_event("shutdown")
async def on_shutdown():
    global auto_route_task
    if auto_route_task:
        auto_route_task.cancel()
        auto_route_task = None


@app.get("/")
async def root():
    return {
        "ok": True,
        "message": "Warehouse Department Email Routing System is running",
        "mail_provider": get_default_provider(),
        "auto_route_enabled": AUTO_ROUTE_ENABLED,
        "auto_route_interval_seconds": AUTO_ROUTE_INTERVAL_SECONDS,
    }


@app.get("/debug-session")
async def debug_session(request: Request):
    return {
        "ok": True,
        "session": dict(request.session),
    }


@app.get("/debug-token")
async def debug_token(request: Request):
    session_id = request.session.get("session_id")
    token_data = await ensure_valid_session_token(session_id)
    if not token_data:
        return {"ok": False, "message": "No token stored in server-side token store"}

    return {
        "ok": True,
        "has_access_token": bool(token_data.get("access_token")),
        "has_refresh_token": bool(token_data.get("refresh_token")),
        "provider": token_data.get("provider"),
        "mailbox_email": token_data.get("mailbox_email"),
        "scope": token_data.get("scope"),
        "token_type": token_data.get("token_type"),
        "expires_in": token_data.get("expires_in"),
    }


@app.get("/me")
async def me(request: Request):
    session_id = request.session.get("session_id")
    token_data = await ensure_valid_session_token(session_id)
    if not token_data or not token_data.get("access_token"):
        return {"ok": False, "message": "Not authenticated"}
    result = await get_me(token_data)
    return {
        "ok": result["status_code"] == 200,
        "status_code": result["status_code"],
        "data": result["data"],
    }


@app.get("/emails")
async def emails(request: Request):
    session_id = request.session.get("session_id")
    token_data = await ensure_valid_session_token(session_id)
    if not token_data or not token_data.get("access_token"):
        return {"ok": False, "message": "Not authenticated"}
    result = await list_messages(token_data)
    return {
        "ok": result["status_code"] == 200,
        "status_code": result["status_code"],
        "data": result["data"],
    }


@app.post("/send-test-email")
async def send_test_email(request: Request):
    session_id = request.session.get("session_id")
    token_data = await ensure_valid_session_token(session_id)
    if not token_data or not token_data.get("access_token"):
        return {"ok": False, "message": "Not authenticated"}
    result = await send_mail(
        token_data=token_data,
        to_email="kings@1st-kings.com",
        subject="Warehouse System Test",
        body="This is a test email from the Warehouse Department Email Routing System.",
    )
    return {
        "ok": result["status_code"] in [200, 202],
        "status_code": result["status_code"],
        "data": result["data"],
    }


@app.post("/process-email")
async def process_email(payload: EmailInput):
    result = await classify_email(payload.subject, payload.body)
    routed = route_department_email(result["department"])

    record = {
        "sender": payload.sender,
        "subject": payload.subject,
        "body": payload.body,
        "department": result["department"],
        "category": result["department"],
        "confidence": result["confidence"],
        "method": result["method"],
        "reason": result["reason"],
        "matched_keywords": result["matched_keywords"],
        "priority": result["priority"],
        "urgency": result["urgency"],
        "priority_reason": result["priority_reason"],
        "priority_method": result["priority_method"],
        "routed_to": routed,
        "message": "Email processed successfully",
    }

    processed_email_store.append(record)

    return {
        "ok": True,
        **record,
    }


@app.get("/processed-emails")
async def processed():
    return {
        "ok": True,
        "data": processed_email_store,
    }


@app.post("/auto-route-emails")
async def auto_route_emails(request: Request):
    session_id = request.session.get("session_id")
    token_data = await ensure_valid_session_token(session_id)
    if not token_data or not token_data.get("access_token"):
        return {"ok": False, "message": "Not authenticated"}

    routed_rows = await process_mailbox_messages(token_data, trigger="manual")

    return {
        "ok": True,
        "processed_count": len(routed_rows),
        "data": routed_rows,
    }


@app.get("/automation-logs")
async def automation_logs():
    return {
        "ok": True,
        "count": len(automation_log_store),
        "data": automation_log_store,
    }
