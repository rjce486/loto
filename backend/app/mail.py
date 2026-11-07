import logging
import smtplib
from email.message import EmailMessage
from email.utils import formatdate

from .config import settings
from .models import Reservation

log = logging.getLogger("loto.mail")


def send_confirmation(r: Reservation, pdf: bytes | None) -> None:
    if not settings.mail_enabled:
        return
    msg = EmailMessage()
    msg["Subject"] = f"Réservation n° {r.number} – {settings.event_name}"
    msg["From"] = settings.mail_from
    msg["To"] = r.email
    msg["Reply-To"] = settings.mail_contact
    msg["Date"] = formatdate(localtime=True)

    lines = [
        f"Bonjour {r.first_name} {r.last_name},",
        "",
        f"Nous avons bien enregistré votre réservation n° {r.number} pour le loto du "
        f"{settings.event_date:%d.%m.%Y} :",
    ]
    if r.qty_14h:
        lines.append(f"  • Session de 14h : {r.qty_14h} abonnement(s), {r.players_14h} joueur(s)")
    if r.qty_16h:
        lines.append(f"  • Session de 16h : {r.qty_16h} abonnement(s), {r.players_16h} joueur(s)")
    lines += ["", f"Total : CHF {r.amount}.-", ""]
    if r.status == "onsite":
        lines += ["Le paiement en ligne n'est plus possible : le montant est à régler sur place, "
                  "à l'entrée du loto, lors du retrait de vos abonnements."]
    else:
        lines += ["Merci de régler ce montant au moyen de la facture QR en pièce jointe.",
                  "Votre réservation est effective dès réception du paiement.",
                  f"Vous pouvez la retrouver ici : {settings.public_base_url}/r/{r.token}"]
    lines += ["", "Les abonnements vous seront remis à l'entrée, sur présentation de cet e-mail et d'une pièce d'identité.",
              "", "Avec nos meilleures salutations,", "Société de tir de Tartegnin", settings.mail_contact]
    msg.set_content("\n".join(lines))
    if pdf:
        msg.add_attachment(pdf, maintype="application", subtype="pdf",
                           filename=f"facture-qr-loto-{r.number}.pdf")
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as s:
            s.starttls()
            if settings.smtp_password:
                s.login(settings.smtp_user, settings.smtp_password)
            s.send_message(msg)
    except Exception:  # l'échec d'envoi ne doit pas bloquer la réservation
        log.exception("Envoi e-mail impossible pour la réservation %s", r.number)
