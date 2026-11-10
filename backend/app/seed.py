"""Run with python -m app.seed. Never run demo seeding against production."""
import getpass
import os

from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import engine
from .models import Agent, Ticket, TicketEvent, TicketMessage
from .security import password_hasher


def main():
    with Session(engine) as db:
        email = "agent@example.com"
        if db.scalar(select(Agent).where(Agent.email == email)) is None:
            password = os.environ.get("DEMO_AGENT_PASSWORD") or getpass.getpass("Choose a demo agent password (12+ characters): ")
            if len(password) < 12:
                raise SystemExit("Please use at least 12 characters.")
            db.add(Agent(email=email, name="Badi Support", password_hash=password_hasher.hash(password)))

        # A second demo agent lets you test assignment and reassignment. The
        # setup helpers supply the local demo password; direct seed reruns do
        # not silently reset an existing account's password.
        demo_password = os.environ.get('DEMO_AGENT_PASSWORD')
        if demo_password and db.scalar(select(Agent).where(Agent.email == 'mia@example.com')) is None:
            db.add(Agent(email='mia@example.com', name='Mia Support', password_hash=password_hasher.hash(demo_password)))

        # Check each seed by its identifying values so rerunning doesn't duplicate.
        examples = [
            ("eSIM QR code will not scan", "INSTALLATION", "HIGH"),
            ("Mobile data stopped working after arrival", "CONNECTIVITY", "HIGH"),
            ("Question about remaining data balance", "OTHER", "LOW"),
        ]
        for subject, category, priority in examples:
            exists = db.scalar(select(Ticket.id).where(Ticket.subject == subject, Ticket.customer_email == "demo@example.com"))
            if exists is None:
                ticket = Ticket(customer_email="demo@example.com", subject=subject, category=category,
                                priority=priority, status="OPEN", description="Demo support request for local testing.")
                db.add(ticket)
                db.flush()
                db.add(TicketMessage(ticket_id=ticket.id, sender_role='CUSTOMER', sender_name=ticket.customer_email,
                                     kind='PUBLIC', body=ticket.description))
                db.add(TicketEvent(ticket_id=ticket.id, actor='Demo customer', field='created', new_value='OPEN'))

        db.commit()
    print("Demo agent and tickets are ready. Sign in using agent@example.com and your chosen password.")


if __name__ == "__main__":
    main()
