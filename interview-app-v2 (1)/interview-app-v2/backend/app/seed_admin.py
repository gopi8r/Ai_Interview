"""
Run this once after setting up the database:
    python -m app.seed_admin
Creates the admin account (credentials from .env: ADMIN_NAME/EMAIL/PASSWORD)
and the default admin_settings row (question_limit). Safe to re-run.
"""
from app.database import SessionLocal, Base, engine
from app import models, auth
from app.config import settings


def seed():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        # --- Admin account ---
        existing_admin = db.query(models.User).filter(models.User.email == settings.ADMIN_EMAIL).first()
        if existing_admin:
            print(f"Admin account already exists ({settings.ADMIN_EMAIL}). Skipping.")
        else:
            admin = models.User(
                name=settings.ADMIN_NAME,
                email=settings.ADMIN_EMAIL,
                hashed_password=auth.hash_password(settings.ADMIN_PASSWORD),
                role=models.UserRole.admin,
            )
            db.add(admin)
            print(f"Created admin account: {settings.ADMIN_EMAIL}")

        # --- Default settings row ---
        settings_row = db.query(models.AdminSettings).filter(models.AdminSettings.id == 1).first()
        if not settings_row:
            db.add(models.AdminSettings(id=1, question_limit=settings.DEFAULT_QUESTION_LIMIT))
            print(f"Created default settings (question_limit={settings.DEFAULT_QUESTION_LIMIT})")
        else:
            print("Settings row already exists. Skipping.")

        db.commit()
        print("Seeding complete.")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
