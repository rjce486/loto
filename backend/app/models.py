import secrets
from datetime import datetime

from sqlalchemy import Integer, String, DateTime, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from .config import settings

engine = create_engine(settings.database_url, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False)


class Base(DeclarativeBase):
    pass


class Reservation(Base):
    __tablename__ = "reservations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token: Mapped[str] = mapped_column(String(32), unique=True, index=True,
                                       default=lambda: secrets.token_urlsafe(16))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    last_name: Mapped[str] = mapped_column(String(80))
    first_name: Mapped[str] = mapped_column(String(80))
    street: Mapped[str] = mapped_column(String(70))
    house_num: Mapped[str] = mapped_column(String(16), default="")
    pcode: Mapped[str] = mapped_column(String(10))
    city: Mapped[str] = mapped_column(String(80))
    email: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str] = mapped_column(String(30), default="")

    qty_14h: Mapped[int] = mapped_column(Integer, default=0)
    qty_16h: Mapped[int] = mapped_column(Integer, default=0)
    players_14h: Mapped[int] = mapped_column(Integer, default=0)   # nombre de joueurs attendus par session
    players_16h: Mapped[int] = mapped_column(Integer, default=0)

    # pending = facture QR envoyée ; paid = payé ; onsite = réservé après délai, paiement sur place ; cancelled
    status: Mapped[str] = mapped_column(String(12), default="pending", index=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    note: Mapped[str] = mapped_column(Text, default="")

    @property
    def qty_total(self) -> int:
        return self.qty_14h + self.qty_16h

    @property
    def amount(self) -> int:
        return self.qty_total * settings.price_chf

    @property
    def number(self) -> str:
        return f"{self.id:04d}"


def init_db() -> None:
    Base.metadata.create_all(engine)
