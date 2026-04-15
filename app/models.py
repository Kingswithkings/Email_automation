from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text

from app.db import Base


class EmailRecord(Base):
    __tablename__ = "emails"

    id = Column(Integer, primary_key=True, index=True)
    sender = Column(String, nullable=False)
    subject = Column(String, nullable=False)
    body = Column(Text, nullable=False)
    category = Column(String, default="unclassified")
    priority = Column(String, default="normal")
    extracted_order_id = Column(String, nullable=True)
    extracted_sku = Column(String, nullable=True)
    extracted_qty = Column(String, nullable=True)
    routed_to = Column(String, nullable=True)
    status = Column(String, default="new")
    created_at = Column(DateTime, default=datetime.utcnow)


class ProcessedMailboxMessage(Base):
    __tablename__ = "processed_mailbox_messages"

    id = Column(Integer, primary_key=True, index=True)
    provider = Column(String, nullable=False, index=True)
    mailbox_email = Column(String, nullable=False, index=True)
    message_id = Column(String, nullable=False, unique=True, index=True)
    subject = Column(String, nullable=True)
    sender = Column(String, nullable=True)
    routed_to = Column(String, nullable=True)
    processed_at = Column(DateTime, default=datetime.utcnow, nullable=False)
