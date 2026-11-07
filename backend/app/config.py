from datetime import date
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Événement
    event_name: str = "Loto de la Société de tir de Tartegnin"
    event_date: date = date(2026, 12, 6)
    payment_deadline: date = date(2026, 12, 1)   # dernier jour de paiement QR inclus
    price_chf: int = 50
    sessions: str = "14h,16h"
    capacity_per_session: int = 0                # 0 = illimité

    # Créancier (facture QR)
    creditor_name: str = "SOCIETE DE TIR DE TARTEGNIN"
    creditor_street: str = "Chemin des Clos"
    creditor_house_num: str = "111"
    creditor_pcode: str = "1170"
    creditor_city: str = "Aubonne"
    creditor_iban: str = "CH2380808009356413662"
    reference_prefix: str = "LOTO2026"           # base de la référence RF (SCOR)

    # Base & sécurité
    database_url: str = "sqlite:///./loto.db"
    public_base_url: str = "https://loto.tir-tartegnin.ch"

    # Login admin OIDC (Authentik, provider OAuth2/OpenID « loto »)
    session_secret: str                          # obligatoire : signe les cookies de session
    oidc_issuer: str = "https://auth.snave.ch/application/o/loto/"
    oidc_client_id: str = ""
    oidc_client_secret: str = ""
    admin_users: str = "aquiblier,asoaresfernandes,kevin,lmunier,revans"   # même liste que challenges, sans admin

    # E-mail (Mailcow, STARTTLS)
    smtp_host: str = "mail.snave.ch"
    smtp_port: int = 587
    smtp_user: str = "loto@tir-tartegnin.ch"
    smtp_password: str = ""
    mail_from: str = "Loto Tir Tartegnin <loto@tir-tartegnin.ch>"
    mail_contact: str = "loto@tir-tartegnin.ch"
    mail_enabled: bool = True

    @property
    def session_list(self) -> list[str]:
        return [s.strip() for s in self.sessions.split(",") if s.strip()]

    @property
    def admin_user_list(self) -> set[str]:
        return {u.strip() for u in self.admin_users.split(",") if u.strip()}


settings = Settings()
