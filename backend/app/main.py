import csv
import io
import logging
import re
from datetime import date, datetime, timezone

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse
from itsdangerous import BadSignature, URLSafeTimedSerializer
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .auth import admin, router as auth_router
from .config import settings
from .mail import send_confirmation
from .models import Reservation, SessionLocal, init_db
from .qr import bill_pdf, bill_svg, qr_code_svg, reference_for

log = logging.getLogger("loto.antispam")

app = FastAPI(title="Loto Tir Tartegnin – prévente", docs_url=None, redoc_url=None)
init_db()
app.include_router(auth_router)

FIELD_LABELS = {
    "last_name": "Nom", "first_name": "Prénom", "street": "Rue", "house_num": "N°",
    "pcode": "NPA", "city": "Localité", "email": "E-mail", "phone": "Téléphone",
    "qty_14h": "Abonnements 14h", "qty_16h": "Abonnements 16h", "players_14h": "Joueurs 14h", "players_16h": "Joueurs 16h",
    "accept_terms": "Conditions générales",
}


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    """Remplace le détail technique de Pydantic par un message lisible."""
    missing, invalid = [], []
    for e in exc.errors():
        label = FIELD_LABELS.get(str(e["loc"][-1]), str(e["loc"][-1]))
        empty = e["type"] == "missing" or (e["type"] == "string_too_short" and not e.get("input"))
        (missing if empty else invalid).append(label)
    parts = []
    if missing:
        parts.append(("Merci de remplir le champ " if len(missing) == 1 else "Merci de remplir les champs ")
                     + ", ".join(dict.fromkeys(missing)) + ".")
    if invalid:
        parts.append(("Le champ suivant est invalide : " if len(invalid) == 1 else "Les champs suivants sont invalides : ")
                     + ", ".join(dict.fromkeys(invalid)) + ".")
    return JSONResponse(status_code=422, content={"detail": " ".join(parts) or "Données invalides."})


def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def qr_open(today: date | None = None) -> bool:
    return (today or date.today()) <= settings.payment_deadline


def sold(s: Session, field) -> int:
    return s.scalar(select(func.coalesce(func.sum(field), 0))
                    .where(Reservation.status != "cancelled")) or 0


# ---------- anti-robots ----------

# jeton signé remis avec /api/info : prouve que le formulaire a été affiché, et depuis quand
_form = URLSafeTimedSerializer(settings.session_secret, salt="loto-form")
FORM_MIN_SECONDS = 3            # un humain met plus longtemps à remplir le formulaire
FORM_MAX_AGE = 7 * 24 * 3600    # au-delà, la page doit être rechargée


def check_human(data: "ReservationIn", request: Request) -> None:
    ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "?")
    if data.website:   # champ piège, invisible pour un humain
        log.warning("Réservation refusée (champ piège rempli) ip=%s email=%s", ip, data.email)
        raise HTTPException(400, "Envoi refusé. Merci de réessayer ou de nous contacter par e-mail.")
    try:
        _, issued = _form.loads(data.form_token, max_age=FORM_MAX_AGE, return_timestamp=True)
    except BadSignature:
        log.warning("Réservation refusée (jeton absent, invalide ou expiré) ip=%s email=%s", ip, data.email)
        raise HTTPException(400, "Le formulaire a expiré. Merci de recharger la page et de recommencer.")
    if (datetime.now(timezone.utc) - issued).total_seconds() < FORM_MIN_SECONDS:
        log.warning("Réservation refusée (envoi trop rapide) ip=%s email=%s", ip, data.email)
        raise HTTPException(400, "Envoi trop rapide. Merci de patienter quelques secondes et de réessayer.")


# ---------- public ----------

@app.get("/api/info")
def info(s: Session = Depends(db)):
    cap = settings.capacity_per_session
    return {
        "event_name": settings.event_name,
        "event_date": settings.event_date.isoformat(),
        "payment_deadline": settings.payment_deadline.isoformat(),
        "price": settings.price_chf,
        "qr_open": qr_open(),
        "contact": settings.mail_contact,
        "form_token": _form.dumps("reservation"),
        "remaining": None if not cap else {
            "14h": max(0, cap - sold(s, Reservation.qty_14h)),
            "16h": max(0, cap - sold(s, Reservation.qty_16h)),
        },
    }


# numéro national (0 + 9 chiffres) ou international +41 / +33, une fois séparateurs et « (0) » ôtés
PHONE = re.compile(r"0\d{9}|(\+|00)(41|33)[1-9]\d{8}")
# champs repris dans l'e-mail et la facture : ni balisage, ni caractère de contrôle, ni lien ou adresse
FORBIDDEN = re.compile(r"[<>{}\\\x00-\x1f\x7f]|://|www\.|@"
                       r"|\b[\w-]+\.(com|net|org|info|biz|io|xyz|top|ru|cn|ch|fr|de|co|me|ly|online|site|link)\b",
                       re.IGNORECASE)


class ReservationIn(BaseModel):
    last_name: str = Field(min_length=1, max_length=80)
    first_name: str = Field(min_length=1, max_length=80)
    street: str = Field(min_length=1, max_length=70)
    house_num: str = Field(default="", max_length=16)
    pcode: str = Field(min_length=4, max_length=5, pattern=r"^\d{4,5}$")  # NPA suisse ou code postal français
    city: str = Field(min_length=1, max_length=80)
    email: EmailStr
    phone: str = Field(default="", max_length=30)
    qty_14h: int = Field(ge=0, le=20)
    qty_16h: int = Field(ge=0, le=20)
    players_14h: int = Field(default=0, ge=0, le=40)
    players_16h: int = Field(default=0, ge=0, le=40)
    accept_terms: bool
    website: str = Field(default="", max_length=200)      # champ piège
    form_token: str = Field(default="", max_length=200)

    @field_validator("phone")
    @classmethod
    def phone_ch_fr(cls, v: str) -> str:
        if v and not PHONE.fullmatch(re.sub(r"\(0\)|[\s.\-/()]", "", v)):
            raise ValueError("numéro suisse ou français attendu")
        return v

    @field_validator("last_name", "first_name", "street", "house_num", "city")
    @classmethod
    def clean_text(cls, v: str) -> str:
        if FORBIDDEN.search(v):
            raise ValueError("caractères ou lien non autorisés")
        return v

    @field_validator("last_name", "first_name")
    @classmethod
    def no_digits(cls, v: str) -> str:
        if any(c.isdigit() for c in v):
            raise ValueError("chiffres non autorisés")
        return v

    @field_validator("last_name", "first_name", "street", "house_num", "pcode", "city", "phone", mode="before")
    @classmethod
    def strip(cls, v):
        return " ".join(v.split()) if isinstance(v, str) else v


def serialize(r: Reservation) -> dict:
    return {
        "number": r.number, "token": r.token, "status": r.status,
        "created_at": r.created_at.isoformat(),
        "last_name": r.last_name, "first_name": r.first_name,
        "street": r.street, "house_num": r.house_num, "pcode": r.pcode, "city": r.city,
        "email": r.email, "phone": r.phone,
        "qty_14h": r.qty_14h, "qty_16h": r.qty_16h, "players_14h": r.players_14h, "players_16h": r.players_16h,
        "amount": r.amount, "reference": reference_for(r),
        "paid_at": r.paid_at.isoformat() if r.paid_at else None,
        "note": r.note,
    }


@app.post("/api/reservations", status_code=201)
def create(data: ReservationIn, request: Request, bg: BackgroundTasks, s: Session = Depends(db)):
    check_human(data, request)
    if not data.accept_terms:
        raise HTTPException(400, "Les conditions générales doivent être acceptées.")
    if data.qty_14h + data.qty_16h == 0:
        raise HTTPException(400, "Choisissez au moins un abonnement.")
    for sess in ("14h", "16h"):   # au moins un joueur par session réservée, aucun sans abonnement
        if getattr(data, f"qty_{sess}") and not getattr(data, f"players_{sess}"):
            raise HTTPException(400, f"Indiquez le nombre de joueurs pour la session de {sess}.")
        if not getattr(data, f"qty_{sess}"):
            setattr(data, f"players_{sess}", 0)
    cap = settings.capacity_per_session
    if cap:
        for field, qty, label in ((Reservation.qty_14h, data.qty_14h, "14h"),
                                  (Reservation.qty_16h, data.qty_16h, "16h")):
            if qty and sold(s, field) + qty > cap:
                raise HTTPException(409, f"Plus assez d'abonnements disponibles pour la session de {label}.")
    r = Reservation(**data.model_dump(exclude={"accept_terms", "website", "form_token"}),
                    status="pending" if qr_open() else "onsite")
    s.add(r)
    s.commit()
    s.refresh(r)
    pdf = bill_pdf(r) if r.status == "pending" else None
    bg.add_task(send_confirmation, r, pdf)
    return serialize(r)


def get_by_token(token: str, s: Session) -> Reservation:
    r = s.scalar(select(Reservation).where(Reservation.token == token))
    if not r:
        raise HTTPException(404, "Réservation introuvable.")
    return r


@app.get("/api/reservations/{token}")
def read(token: str, s: Session = Depends(db)):
    return serialize(get_by_token(token, s))


@app.get("/api/reservations/{token}/qr.svg")
def qr_svg(token: str, s: Session = Depends(db)):
    r = get_by_token(token, s)
    if r.status not in ("pending", "paid"):
        raise HTTPException(404)
    return Response(bill_svg(r), media_type="image/svg+xml")


@app.get("/api/reservations/{token}/code.svg")
def qr_code(token: str, s: Session = Depends(db)):
    r = get_by_token(token, s)
    if r.status not in ("pending", "paid"):
        raise HTTPException(404)
    return Response(qr_code_svg(r), media_type="image/svg+xml")


@app.get("/api/reservations/{token}/facture.pdf")
def qr_pdf(token: str, s: Session = Depends(db)):
    r = get_by_token(token, s)
    if r.status not in ("pending", "paid"):
        raise HTTPException(404)
    return Response(bill_pdf(r), media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="facture-qr-loto-{r.number}.pdf"'})


# ---------- admin (session OIDC, voir auth.py) ----------

@app.get("/api/admin/reservations")
def admin_list(s: Session = Depends(db), _: str = Depends(admin)):
    rows = s.scalars(select(Reservation).order_by(Reservation.id.desc())).all()
    active = [r for r in rows if r.status != "cancelled"]
    return {
        "reservations": [serialize(r) for r in rows],
        "totals": {
            "qty_14h": sum(r.qty_14h for r in active),
            "qty_16h": sum(r.qty_16h for r in active),
            "players_14h": sum(r.players_14h for r in active),
            "players_16h": sum(r.players_16h for r in active),
            "paid_chf": sum(r.amount for r in active if r.status == "paid"),
            "pending_chf": sum(r.amount for r in active if r.status == "pending"),
            "onsite_chf": sum(r.amount for r in active if r.status == "onsite"),
        },
    }


class StatusIn(BaseModel):
    status: str = Field(pattern="^(pending|paid|onsite|cancelled)$")
    note: str | None = None


@app.patch("/api/admin/reservations/{token}")
def admin_update(token: str, data: StatusIn, s: Session = Depends(db), _: str = Depends(admin)):
    r = get_by_token(token, s)
    r.status = data.status
    r.paid_at = datetime.utcnow() if data.status == "paid" else None
    if data.note is not None:
        r.note = data.note
    s.commit()
    return serialize(r)


@app.get("/api/admin/export.csv")
def admin_export(s: Session = Depends(db), _: str = Depends(admin)):
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["N°", "Date", "Statut", "Nom", "Prénom", "Rue", "N°", "NPA", "Localité", "E-mail", "Tél.",
                "14h", "16h", "Joueurs 14h", "Joueurs 16h", "Montant", "Référence", "Payé le", "Note"])
    for r in s.scalars(select(Reservation).order_by(Reservation.id)):
        w.writerow([r.number, r.created_at.strftime("%d.%m.%Y %H:%M"), r.status, r.last_name, r.first_name,
                    r.street, r.house_num, r.pcode, r.city, r.email, r.phone, r.qty_14h, r.qty_16h, r.players_14h, r.players_16h, r.amount,
                    reference_for(r), r.paid_at.strftime("%d.%m.%Y") if r.paid_at else "", r.note])
    return StreamingResponse(iter([("﻿" + buf.getvalue()).encode("utf-8")]), media_type="text/csv",
                             headers={"Content-Disposition": 'attachment; filename="loto-reservations.csv"'})
