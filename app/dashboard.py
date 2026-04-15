import requests
import pandas as pd
import streamlit as st

API_URL = "http://127.0.0.1:8000"


def show_table(rows, preferred_columns, empty_message):
    if isinstance(rows, list) and len(rows) > 0:
        df = pd.DataFrame(rows)
        available_columns = [col for col in preferred_columns if col in df.columns]
        if available_columns:
            df = df[available_columns]
        st.dataframe(df, use_container_width=True)
    else:
        st.info(empty_message)


st.set_page_config(page_title="Warehouse Dashboard", layout="wide")
st.title("📦 Warehouse Department Email Routing Dashboard")

st.subheader("Submit Test Email")

with st.form("email_form"):
    sender = st.text_input("Sender", "supplier@example.com")
    subject = st.text_input("Subject", "Urgent dispatch for ORD1001")
    body = st.text_area("Body", "Please dispatch 20 units of SKU-123 today.")
    submitted = st.form_submit_button("Process Email")

    if submitted:
        try:
            res = requests.post(
                f"{API_URL}/process-email",
                json={
                    "sender": sender,
                    "subject": subject,
                    "body": body,
                },
                timeout=30,
            )
            payload = res.json()

            if payload.get("ok"):
                st.success("Email processed successfully")
                st.json(payload)
            else:
                st.warning("Processing failed")
                st.json(payload)
        except Exception as e:
            st.error(f"Failed to process email: {e}")

st.subheader("Run Mailbox Automation")

if st.button("Auto Route Inbox Emails"):
    try:
        res = requests.post(f"{API_URL}/auto-route-emails", timeout=60)
        payload = res.json()

        if payload.get("ok"):
            st.success(f"Automation completed. Processed {payload.get('processed_count', 0)} emails.")
            st.json(payload)
        else:
            st.warning(payload.get("message", "Automation failed"))
            st.json(payload)
    except Exception as e:
        st.error(f"Failed to run automation: {e}")

st.subheader("Processed Test Emails")

try:
    res = requests.get(f"{API_URL}/processed-emails", timeout=30)
    payload = res.json()

    if not payload.get("ok"):
        st.warning(payload.get("message", "Could not fetch processed emails"))
    else:
        show_table(
            payload.get("data", []),
            [
                "sender",
                "subject",
                "department",
                "category",
                "confidence",
                "method",
                "reason",
                "priority",
                "urgency",
                "priority_reason",
                "priority_method",
                "routed_to",
                "matched_keywords",
                "message",
                "body",
            ],
            "No processed test emails yet.",
        )
except Exception as e:
    st.error(f"Could not load processed emails: {e}")

st.subheader("Mailbox Inbox Emails")

try:
    res = requests.get(f"{API_URL}/emails", timeout=30)
    payload = res.json()

    if not payload.get("ok"):
        st.warning(payload.get("message", "Could not fetch mailbox emails"))
    else:
        show_table(
            payload.get("data", []),
            [],
            "No mailbox emails found.",
        )
except Exception as e:
    st.error(f"Could not load mailbox emails: {e}")

st.subheader("Automation Logs")

try:
    res = requests.get(f"{API_URL}/automation-logs", timeout=30)
    payload = res.json()

    if not payload.get("ok"):
        st.warning(payload.get("message", "Could not fetch automation logs"))
    else:
        show_table(
            payload.get("data", []),
            [
                "sender",
                "subject",
                "department",
                "category",
                "confidence",
                "method",
                "reason",
                "priority",
                "urgency",
                "priority_reason",
                "priority_method",
                "redirected_to",
                "matched_keywords",
                "send_status_code",
                "redirected",
                "body_preview",
            ],
            "No automation logs yet.",
        )
except Exception as e:
    st.error(f"Could not load automation logs: {e}")
