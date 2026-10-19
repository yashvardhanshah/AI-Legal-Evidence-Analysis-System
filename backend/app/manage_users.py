"""Local operator command; no default administrator or password is created."""
import argparse
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.auth import audit, now
from app.database import get_engine
from app.models import AuthSession, User


def main():
    parser = argparse.ArgumentParser(description="Promote an existing registered account using local database operator access")
    parser.add_argument("email")
    parser.add_argument("--bootstrap-administrator", action="store_true", required=True)
    args = parser.parse_args()
    with Session(get_engine()) as db:
        # Serialize administrator bootstrap; normal role administration uses the API.
        from sqlalchemy import text
        db.execute(text("SELECT pg_advisory_xact_lock(703031)"))
        if db.scalar(select(User.id).where(User.role == "administrator", User.is_active.is_(True))):
            parser.error("An administrator already exists; use authenticated role administration")
        user = db.scalar(select(User).where(User.email == args.email.strip().lower(), User.is_active.is_(True)))
        if not user:
            parser.error("Register the intended account first")
        user.role = "administrator"
        for session in db.scalars(select(AuthSession).where(AuthSession.user_id == user.id)):
            session.revoked_at = now()
        audit(db, user, "user.bootstrap_administrator", "user", user.id, operator="local CLI")
        db.commit()
        print("Administrator assigned; existing sessions revoked. Log in again.")


if __name__ == "__main__":
    main()
