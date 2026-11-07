"""Génération de la facture QR suisse (SVG + PDF)."""
import io
import re
import tempfile
from pathlib import Path

from qrbill import QRBill
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from svglib.svglib import svg2rlg
from reportlab.graphics import renderPDF

from .config import settings
from .models import Reservation

LOGO_PATH = Path(__file__).parent / "assets" / "logo.png"
LOGO_HEIGHT = 64          # points ; en-tête, aligné sur la marge haute du titre


def rf_reference(raw: str) -> str:
    """Référence créancier ISO 11649 (RF + 2 chiffres de contrôle)."""
    body = "".join(c for c in raw.upper() if c.isalnum())
    digits = "".join(str(int(c, 36)) for c in body + "RF00")
    check = 98 - int(digits) % 97
    return f"RF{check:02d}{body}"


def reference_for(r: Reservation) -> str:
    return rf_reference(f"{settings.reference_prefix}{r.number}")


def debtor_country(r: Reservation) -> str:
    """NPA suisse à 4 chiffres, code postal français à 5 : seuls pays admis à la réservation."""
    return "FR" if len(r.pcode) == 5 else "CH"


def build_bill(r: Reservation) -> QRBill:
    return QRBill(
        account=settings.creditor_iban,
        creditor={
            "name": settings.creditor_name,
            "street": settings.creditor_street,
            "house_num": settings.creditor_house_num,
            "pcode": settings.creditor_pcode,
            "city": settings.creditor_city,
            "country": "CH",
        },
        debtor={  # adresse structurée (type S), seule admise depuis le 21.11.2025
            "name": f"{r.first_name} {r.last_name}",
            "street": r.street,
            "house_num": r.house_num,
            "pcode": r.pcode,
            "city": r.city,
            "country": debtor_country(r),
        },
        amount=f"{r.amount:.2f}",
        currency="CHF",
        reference_number=reference_for(r),
        additional_information=f"Loto {settings.event_date:%d.%m.%Y} - reservation {r.number}",
        language="fr",
    )


def bill_svg(r: Reservation) -> bytes:
    buf = io.StringIO()
    build_bill(r).as_svg(buf)
    return buf.getvalue().encode("utf-8")


def qr_code_svg(r: Reservation) -> bytes:
    """Code QR seul (avec croix suisse), pour un affichage lisible sur mobile."""
    img = build_bill(r).qr_image()
    svg = img.to_string().decode("utf-8") if isinstance(img.to_string(), bytes) else img.to_string()
    # croix suisse au centre : carré noir 7 % + croix blanche, exigée par la norme
    m = re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', svg)
    w = float(m.group(1)) if m else 100
    c, sq, arm, th = w / 2, w * 0.07, w * 0.045, w * 0.012
    cross = (f'<rect x="{c-sq/2}" y="{c-sq/2}" width="{sq}" height="{sq}" fill="#000"/>'
             f'<rect x="{c-arm/2}" y="{c-th/2}" width="{arm}" height="{th}" fill="#fff"/>'
             f'<rect x="{c-th/2}" y="{c-arm/2}" width="{th}" height="{arm}" fill="#fff"/>')
    return svg.replace("</svg>", cross + "</svg>").encode("utf-8")


def bill_pdf(r: Reservation) -> bytes:
    """Page A4 : récapitulatif en haut, section paiement QR en bas (norme suisse)."""
    with tempfile.NamedTemporaryFile(suffix=".svg", mode="w", encoding="utf-8", delete=False) as f:
        build_bill(r).as_svg(f)
        svg_path = f.name
    drawing = svg2rlg(svg_path)

    buf = io.BytesIO()
    w, h = A4
    c = canvas.Canvas(buf, pagesize=A4)
    c.setTitle(f"Reservation {r.number} - {settings.event_name}")

    # logo de la société, en haut à droite : n'empiète ni sur le titre ni sur la section paiement
    if LOGO_PATH.exists():
        logo = ImageReader(str(LOGO_PATH))
        lw, lh = logo.getSize()
        lw, lh = LOGO_HEIGHT * lw / lh, LOGO_HEIGHT
        c.drawImage(logo, w - 50 - lw, h - 50 - lh, width=lw, height=lh, mask="auto")

    y = h - 60
    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, y, settings.event_name)
    y -= 22
    c.setFont("Helvetica", 11)
    c.drawString(50, y, f"Dimanche {settings.event_date:%d.%m.%Y} - Réservation n° {r.number}")
    y -= 30
    c.setFont("Helvetica-Bold", 11)
    c.drawString(50, y, "Réservé par")
    c.setFont("Helvetica", 11)
    for line in (f"{r.first_name} {r.last_name}", f"{r.street} {r.house_num}".strip(), f"{r.pcode} {r.city}" + (" (France)" if debtor_country(r) == "FR" else ""), r.email):
        y -= 15
        c.drawString(50, y, line)
    y -= 30
    c.setFont("Helvetica-Bold", 11)
    c.drawString(50, y, "Abonnements")
    c.setFont("Helvetica", 11)
    for label, qty, players in (("Session de 14h", r.qty_14h, r.players_14h), ("Session de 16h", r.qty_16h, r.players_16h)):
        if qty:
            y -= 15
            c.drawString(50, y, f"{label} : {qty} x CHF {settings.price_chf}.- ({players} joueur{'s' if players > 1 else ''})")
    y -= 20
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, y, f"Total : CHF {r.amount}.-")
    y -= 30
    c.setFont("Helvetica", 9)
    for line in (
        "Merci de régler ce montant au moyen de la facture QR ci-dessous.",
        "La réservation est effective dès réception du paiement. Les abonnements sont remis à l'entrée du loto,",
        f"sur présentation de cette confirmation et d'une pièce d'identité. Questions : {settings.mail_contact}",
    ):
        c.drawString(50, y, line)
        y -= 13

    # Section paiement : 210 x 105 mm en bas de page, pleine largeur
    scale = w / drawing.width
    drawing.scale(scale, scale)
    renderPDF.draw(drawing, c, 0, 0)
    c.showPage()
    c.save()
    return buf.getvalue()
