import os
import secrets


class Settings:
    """Everything configurable comes from environment variables, read once at startup."""

    def __init__(self) -> None:
        self.database_url = os.getenv("DATABASE_URL", "sqlite:///./slotbook.db")
        # The random fallback means tokens stop working on restart: the safe failure for a dev default.
        self.secret_key = os.getenv("SECRET_KEY") or secrets.token_urlsafe(32)
        self.static_dir = os.getenv("STATIC_DIR", "")
        # Base for links in emails. Empty means "use the URL the request came in on".
        self.public_url = os.getenv("PUBLIC_URL", "").rstrip("/")
        self.cors_origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")]
        # Create the read-only demo business on startup.
        self.seed_demo = os.getenv("SEED_DEMO", "1") == "1"

        # Email: "console" prints messages (local dev), "smtp" sends them, "memory" keeps them (tests).
        self.email_backend = os.getenv("EMAIL_BACKEND", "console")
        self.email_from = os.getenv("EMAIL_FROM", "SlotBook <no-reply@slotbook.local>")
        self.smtp_host = os.getenv("SMTP_HOST", "")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_user = os.getenv("SMTP_USER", "")
        self.smtp_password = os.getenv("SMTP_PASSWORD", "")


settings = Settings()
