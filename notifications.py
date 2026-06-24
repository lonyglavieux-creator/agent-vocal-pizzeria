import os
import httpx
import json
from datetime import datetime, timedelta

SUPABASE_URL  = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY  = os.environ.get("SUPABASE_KEY", "")
TWILIO_SID    = os.environ.get("TWILIO_SID", "")
TWILIO_TOKEN  = os.environ.get("TWILIO_TOKEN", "")
TWILIO_FROM   = os.environ.get("TWILIO_FROM", "")
TWILIO_PHONE  = os.environ.get("TWILIO_PHONE", "")
SENDGRID_KEY  = os.environ.get("SENDGRID_API_KEY", "")

def get_headers_sb():
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": "Bearer " + SUPABASE_KEY,
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }

# ──────────────────────────────────────────────
# ENVOI WHATSAPP
# ──────────────────────────────────────────────

def send_whatsapp(tel: str, message: str) -> bool:
    try:
        from twilio.rest import Client
        client = Client(TWILIO_SID, TWILIO_TOKEN)
        client.messages.create(
            body=message,
            from_="whatsapp:" + TWILIO_FROM,
            to="whatsapp:" + tel
        )
        print("WhatsApp envoye a " + tel)
        return True
    except Exception as e:
        print("Erreur WhatsApp : " + str(e))
        return False

# ──────────────────────────────────────────────
# ENVOI SMS
# ──────────────────────────────────────────────

def send_sms(tel: str, message: str) -> bool:
    try:
        from twilio.rest import Client
        client = Client(TWILIO_SID, TWILIO_TOKEN)
        client.messages.create(
            body=message,
            from_=TWILIO_PHONE,
            to=tel
        )
        print("SMS envoye a " + tel)
        return True
    except Exception as e:
        print("Erreur SMS : " + str(e))
        return False

# ──────────────────────────────────────────────
# ENVOI EMAIL (SendGrid)
# ──────────────────────────────────────────────

def send_email(to_email: str, subject: str, body_html: str) -> bool:
    if not SENDGRID_KEY:
        print("SendGrid non configure")
        return False
    try:
        r = httpx.post(
            "https://api.sendgrid.com/v3/mail/send",
            headers={
                "Authorization": "Bearer " + SENDGRID_KEY,
                "Content-Type": "application/json"
            },
            json={
                "personalizations": [{"to": [{"email": to_email}]}],
                "from": {"email": "nova@nova-ai.fr", "name": "Nova.AI"},
                "subject": subject,
                "content": [{"type": "text/html", "value": body_html}]
            },
            timeout=10
        )
        print("Email envoye a " + to_email + " status: " + str(r.status_code))
        return r.status_code in [200, 202]
    except Exception as e:
        print("Erreur email : " + str(e))
        return False

# ──────────────────────────────────────────────
# MESSAGES
# ──────────────────────────────────────────────

def msg_j1_whatsapp(nom: str, pizzeria: str, lien: str) -> str:
    return (
        "Bonjour " + nom + " !\n\n"
        "Votre abonnement Nova.AI pour " + pizzeria + " expire demain.\n\n"
        "Pour continuer a recevoir vos commandes vocalement, renouvelez maintenant :\n"
        + lien + "\n\n"
        "Sans renouvellement, Nova sera desactivee demain a minuit.\n\n"
        "Nova.AI"
    )

def msg_j1_sms(nom: str, pizzeria: str, lien: str) -> str:
    return (
        "Nova.AI : Bonjour " + nom + ", votre abonnement " + pizzeria +
        " expire demain. Renouvelez : " + lien
    )

def msg_j1_email(nom: str, pizzeria: str, lien: str) -> str:
    return """
    <div style="font-family:system-ui,sans-serif;max-width:600px;margin:0 auto;padding:32px;">
      <div style="text-align:center;margin-bottom:32px;">
        <h1 style="color:#1A6EF5;font-size:28px;margin:0">Nova.AI</h1>
        <p style="color:#5A677E;margin:8px 0 0">L'IA pour votre metier</p>
      </div>
      <div style="background:#FEF3C7;border-radius:12px;padding:20px;margin-bottom:24px;text-align:center;">
        <p style="font-size:32px;margin:0">⚠️</p>
        <h2 style="color:#92400E;margin:8px 0">Votre abonnement expire demain</h2>
      </div>
      <p style="color:#0D1524;font-size:16px;">Bonjour <strong>""" + nom + """</strong>,</p>
      <p style="color:#5A677E;line-height:1.6;">
        Votre abonnement Nova.AI pour <strong>""" + pizzeria + """</strong> arrive a expiration demain.
        Sans renouvellement, Nova sera desactivee automatiquement et ne pourra plus prendre de commandes.
      </p>
      <div style="text-align:center;margin:32px 0;">
        <a href='""" + lien + """' style="background:#1A6EF5;color:white;padding:14px 32px;border-radius:10px;text-decoration:none;font-weight:600;font-size:16px;">
          Renouveler mon abonnement
        </a>
      </div>
      <p style="color:#9BA5B7;font-size:13px;text-align:center;">
        59€/mois — Sans engagement — Annulable a tout moment
      </p>
      <hr style="border:none;border-top:1px solid #E2E7F0;margin:24px 0">
      <p style="color:#9BA5B7;font-size:12px;text-align:center;">
        Nova.AI — L'IA pour les professionnels
      </p>
    </div>
    """

def msg_expiration_whatsapp(nom: str, pizzeria: str, lien: str) -> str:
    return (
        "Bonjour " + nom + " !\n\n"
        "Votre abonnement Nova.AI pour " + pizzeria + " a expire.\n\n"
        "Nova est maintenant desactivee. Vos clients ne peuvent plus passer de commandes vocalement.\n\n"
        "Pour reactiver Nova : " + lien + "\n\n"
        "Nova.AI"
    )

# ──────────────────────────────────────────────
# GESTION STATUT NOVA (actif/inactif)
# ──────────────────────────────────────────────

def get_clients_supabase() -> list:
    if not (SUPABASE_URL and SUPABASE_KEY):
        return []
    try:
        r = httpx.get(
            SUPABASE_URL + "/rest/v1/clients_nova?select=*&order=created_at.desc",
            headers=get_headers_sb(),
            timeout=10
        )
        return r.json() if r.status_code == 200 else []
    except Exception as e:
        print("Erreur get_clients : " + str(e))
        return []

def mettre_a_jour_statut_client(client_id: int, statut: str):
    if not (SUPABASE_URL and SUPABASE_KEY):
        return
    try:
        httpx.patch(
            SUPABASE_URL + "/rest/v1/clients_nova?id=eq." + str(client_id),
            headers=get_headers_sb(),
            json={"statut": statut, "updated_at": datetime.now().isoformat()},
            timeout=10
        )
        print("Client " + str(client_id) + " statut -> " + statut)
    except Exception as e:
        print("Erreur update statut : " + str(e))

# ──────────────────────────────────────────────
# VERIFICATION ABONNEMENTS STRIPE
# ──────────────────────────────────────────────

def verifier_abonnements_stripe() -> dict:
    from stripe_handler import get_abonnement, statut_abonnement, prochaine_facturation
    clients = get_clients_supabase()
    resultats = {"expires_demain": [], "expires": [], "actifs": [], "erreurs": []}

    for client in clients:
        if not client.get("stripe_subscription_id"):
            continue
        try:
            sub = get_abonnement(client["stripe_subscription_id"])
            if not sub:
                continue

            statut = sub.get("status", "")
            period_end = sub.get("current_period_end", 0)
            now = datetime.now().timestamp()
            demain = now + 86400  # 24h

            if statut == "active":
                if period_end <= demain:
                    resultats["expires_demain"].append(client)
                else:
                    resultats["actifs"].append(client)
            elif statut in ["canceled", "unpaid", "past_due"]:
                resultats["expires"].append(client)
        except Exception as e:
            resultats["erreurs"].append({"client": client.get("nom"), "erreur": str(e)})

    return resultats

# ──────────────────────────────────────────────
# TACHE PRINCIPALE : verifier et notifier
# ──────────────────────────────────────────────

def run_notifications_j1():
    print("Lancement verification abonnements J-1...")
    from stripe_handler import creer_lien_paiement
    PRICE_ID = os.environ.get("STRIPE_PRICE_ID", "")

    resultats = verifier_abonnements_stripe()
    nb_notifies = 0
    nb_desactives = 0

    # Notifications J-1
    for client in resultats["expires_demain"]:
        nom      = client.get("nom", "Client")
        pizzeria = client.get("pizzeria", "votre pizzeria")
        email    = client.get("email", "")
        tel      = client.get("telephone", "")

        lien = creer_lien_paiement(PRICE_ID, pizzeria, email) or "https://nova-ai.fr"

        if tel:
            send_whatsapp(tel, msg_j1_whatsapp(nom, pizzeria, lien))
            send_sms(tel, msg_j1_sms(nom, pizzeria, lien))
        if email:
            send_email(email, "Votre abonnement Nova.AI expire demain", msg_j1_email(nom, pizzeria, lien))

        print("Notifie J-1 : " + nom + " (" + pizzeria + ")")
        nb_notifies += 1

    # Desactivation abonnements expires
    for client in resultats["expires"]:
        nom      = client.get("nom", "Client")
        pizzeria = client.get("pizzeria", "votre pizzeria")
        email    = client.get("email", "")
        tel      = client.get("telephone", "")

        if client.get("statut") == "actif":
            lien = creer_lien_paiement(PRICE_ID, pizzeria, email) or "https://nova-ai.fr"
            if tel:
                send_whatsapp(tel, msg_expiration_whatsapp(nom, pizzeria, lien))
            if email:
                send_email(email, "Votre abonnement Nova.AI a expire - Nova desactivee",
                    msg_j1_email(nom, pizzeria, lien).replace("expire demain", "a expire"))
            mettre_a_jour_statut_client(client["id"], "expire")
            nb_desactives += 1
            print("Desactive : " + nom + " (" + pizzeria + ")")

    print("Notifications J-1 : " + str(nb_notifies) + " envoyes, " + str(nb_desactives) + " desactives")
    return {"notifies": nb_notifies, "desactives": nb_desactives}
