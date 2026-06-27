import os
import httpx
from datetime import datetime

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")

MINUTES_INCLUSES = 1000
PRIX_100_MIN = 2.50
STRIPE_API = "https://api.stripe.com/v1"

def get_headers_sb():
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": "Bearer " + SUPABASE_KEY,
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }

def stripe_headers():
    return {
        "Authorization": "Bearer " + STRIPE_SECRET_KEY,
        "Content-Type": "application/x-www-form-urlencoded"
    }

# ──────────────────────────────────────────────
# ENREGISTRER LES MINUTES D UN APPEL
# ──────────────────────────────────────────────

def enregistrer_minutes(pizzeria_id: int, duree_secondes: float):
    duree_min = round(duree_secondes / 60, 2)
    mois = datetime.now().strftime("%Y-%m")
    try:
        # Chercher si un compteur existe pour ce mois
        r = httpx.get(
            SUPABASE_URL + "/rest/v1/minutes_usage?pizzeria_id=eq." + str(pizzeria_id) + "&mois=eq." + mois,
            headers=get_headers_sb(),
            timeout=10
        )
        if r.status_code == 200 and r.json():
            # Mettre a jour le compteur existant
            existing = r.json()[0]
            new_total = round(existing["minutes_utilisees"] + duree_min, 2)
            httpx.patch(
                SUPABASE_URL + "/rest/v1/minutes_usage?pizzeria_id=eq." + str(pizzeria_id) + "&mois=eq." + mois,
                headers=get_headers_sb(),
                json={"minutes_utilisees": new_total, "updated_at": datetime.now().isoformat()},
                timeout=10
            )
        else:
            # Creer un nouveau compteur
            httpx.post(
                SUPABASE_URL + "/rest/v1/minutes_usage",
                headers=get_headers_sb(),
                json={
                    "pizzeria_id": pizzeria_id,
                    "mois": mois,
                    "minutes_utilisees": duree_min,
                    "minutes_facturees": 0,
                    "depassement_facture": False
                },
                timeout=10
            )
        print("Minutes enregistrees : " + str(duree_min) + " min pour pizzeria " + str(pizzeria_id))
    except Exception as e:
        print("Erreur enregistrer_minutes : " + str(e))


def get_minutes_mois(pizzeria_id: int, mois: str = None) -> dict:
    if not mois:
        mois = datetime.now().strftime("%Y-%m")
    try:
        r = httpx.get(
            SUPABASE_URL + "/rest/v1/minutes_usage?pizzeria_id=eq." + str(pizzeria_id) + "&mois=eq." + mois,
            headers=get_headers_sb(),
            timeout=10
        )
        if r.status_code == 200 and r.json():
            data = r.json()[0]
            utilisees = data["minutes_utilisees"]
            depassement = max(0, utilisees - MINUTES_INCLUSES)
            tranches = int(depassement / 100)
            montant_depassement = round(tranches * PRIX_100_MIN, 2)
            return {
                "pizzeria_id": pizzeria_id,
                "mois": mois,
                "minutes_utilisees": utilisees,
                "minutes_incluses": MINUTES_INCLUSES,
                "depassement_minutes": round(depassement, 2),
                "tranches_100min": tranches,
                "montant_depassement": montant_depassement,
                "depassement_facture": data.get("depassement_facture", False)
            }
        return {
            "pizzeria_id": pizzeria_id,
            "mois": mois,
            "minutes_utilisees": 0,
            "minutes_incluses": MINUTES_INCLUSES,
            "depassement_minutes": 0,
            "tranches_100min": 0,
            "montant_depassement": 0,
            "depassement_facture": False
        }
    except Exception as e:
        print("Erreur get_minutes_mois : " + str(e))
        return {}


# ──────────────────────────────────────────────
# FACTURATION DEPASSEMENT STRIPE
# ──────────────────────────────────────────────

def facturer_depassement(pizzeria_id: int, stripe_customer_id: str, mois: str = None) -> dict:
    if not mois:
        mois = datetime.now().strftime("%Y-%m")

    usage = get_minutes_mois(pizzeria_id, mois)

    if not usage:
        return {"statut": "erreur", "message": "Pas de donnees d usage"}

    if usage["depassement_facture"]:
        return {"statut": "deja_facture", "message": "Depassement deja facture pour " + mois}

    if usage["montant_depassement"] <= 0:
        return {"statut": "ok", "message": "Aucun depassement ce mois", "montant": 0}

    montant_centimes = int(usage["montant_depassement"] * 100)

    try:
        # Creer une facture Stripe pour le depassement
        r = httpx.post(
            STRIPE_API + "/invoiceitems",
            headers=stripe_headers(),
            data={
                "customer": stripe_customer_id,
                "amount": str(montant_centimes),
                "currency": "eur",
                "description": "Depassement minutes Nova.AI - " + mois +
                    " (" + str(usage["tranches_100min"]) + " tranches x 100min a 2.50EUR)"
            },
            timeout=10
        )

        if r.status_code != 200:
            return {"statut": "erreur", "message": "Erreur Stripe : " + r.text}

        # Creer et envoyer la facture
        r2 = httpx.post(
            STRIPE_API + "/invoices",
            headers=stripe_headers(),
            data={
                "customer": stripe_customer_id,
                "auto_advance": "true",
                "collection_method": "charge_automatically"
            },
            timeout=10
        )

        if r2.status_code == 200:
            invoice_id = r2.json().get("id", "")
            # Finaliser la facture
            httpx.post(
                STRIPE_API + "/invoices/" + invoice_id + "/finalize",
                headers=stripe_headers(),
                timeout=10
            )

            # Marquer comme facture dans Supabase
            httpx.patch(
                SUPABASE_URL + "/rest/v1/minutes_usage?pizzeria_id=eq." + str(pizzeria_id) + "&mois=eq." + mois,
                headers=get_headers_sb(),
                json={
                    "depassement_facture": True,
                    "montant_facture": usage["montant_depassement"],
                    "invoice_id": invoice_id,
                    "facture_at": datetime.now().isoformat()
                },
                timeout=10
            )

            print("Depassement facture : " + str(usage["montant_depassement"]) + "EUR pour pizzeria " + str(pizzeria_id))
            return {
                "statut": "ok",
                "montant": usage["montant_depassement"],
                "tranches": usage["tranches_100min"],
                "minutes_depassement": usage["depassement_minutes"],
                "invoice_id": invoice_id
            }

        return {"statut": "erreur", "message": "Erreur creation facture"}

    except Exception as e:
        print("Erreur facturer_depassement : " + str(e))
        return {"statut": "erreur", "message": str(e)}


def run_facturation_mensuelle():
    mois = datetime.now().strftime("%Y-%m")
    print("Facturation mensuelle " + mois + "...")
    if not (SUPABASE_URL and SUPABASE_KEY):
        return {"erreur": "Supabase non configure"}
    try:
        r = httpx.get(
            SUPABASE_URL + "/rest/v1/minutes_usage?mois=eq." + mois + "&depassement_facture=eq.false",
            headers=get_headers_sb(),
            timeout=10
        )
        usages = r.json() if r.status_code == 200 else []
        resultats = []
        for usage in usages:
            pizzeria_id = usage["pizzeria_id"]
            mins = usage["minutes_utilisees"]
            if mins <= MINUTES_INCLUSES:
                continue
            # Recuperer stripe_customer_id de la pizzeria
            rp = httpx.get(
                SUPABASE_URL + "/rest/v1/pizzerias?id=eq." + str(pizzeria_id),
                headers=get_headers_sb(),
                timeout=10
            )
            if rp.status_code == 200 and rp.json():
                pizzeria = rp.json()[0]
                customer_id = pizzeria.get("stripe_customer_id", "")
                if customer_id:
                    result = facturer_depassement(pizzeria_id, customer_id, mois)
                    resultats.append({"pizzeria": pizzeria.get("nom"), "result": result})

        print("Facturation terminee : " + str(len(resultats)) + " pizzerias traitees")
        return {"statut": "ok", "mois": mois, "traites": resultats}
    except Exception as e:
        print("Erreur run_facturation_mensuelle : " + str(e))
        return {"statut": "erreur", "message": str(e)}
