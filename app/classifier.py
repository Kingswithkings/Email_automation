import re

def detect_priority(text: str) -> str:
    text = text.lower()
    urgent_words = ["urgent", "asap", "immediately", "today", "now"]
    if any(word in text for word in urgent_words):
        return "high"
    return "normal"

def extract_order_id(text: str):
    match = re.search(r"(ORD\d+|PO\d+|INV\d+)", text, re.IGNORECASE)
    return match.group(1) if match else None

def extract_qty(text: str):
    match = re.search(r"(\d+)\s*(units|pcs|pieces|boxes|cartons)?", text, re.IGNORECASE)
    return match.group(1) if match else None

def extract_sku(text: str):
    match = re.search(r"(SKU[-\s]?\d+)", text, re.IGNORECASE)
    return match.group(1) if match else None

def classify_email(subject: str, body: str):
    text = f"{subject} {body}".lower()

    if any(k in text for k in ["damaged", "broken", "faulty", "defective"]):
        return "claims"
    elif any(k in text for k in ["dispatch", "ship today", "urgent delivery", "pick order"]):
        return "warehouse_ops"
    elif any(k in text for k in ["invoice", "payment", "purchase order", "po "]):
        return "finance"
    elif any(k in text for k in ["stock", "inventory", "out of stock", "replenishment"]):
        return "inventory"
    elif any(k in text for k in ["delivery delayed", "missing pallet", "courier", "transport"]):
        return "logistics"
    else:
        return "general"

def extract_fields(subject: str, body: str):
    text = f"{subject} {body}"
    return {
        "priority": detect_priority(text),
        "order_id": extract_order_id(text),
        "sku": extract_sku(text),
        "qty": extract_qty(text),
    }