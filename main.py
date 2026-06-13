from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from twilio.rest import Client as TwilioClient
import os
from datetime import datetime

app = FastAPI()

twilio_client = TwilioClient(
    os.environ.get("TWILIO_SID"),
    os.environ.get("TWILIO_TOKEN")
)
TWILIO_FROM = os.environ.get("TWILIO_FROM")
PIZZAIOLO_TEL = os.environ.get("PIZZAIOLO_TEL", "+33788705435")

# Planning du jour
commandes_du_jour = []

# Capacite du four
MAX_PIZZAS_PAR_CRENEAU = 2
DUREE_CRENEAU = 15  # minutes

TEMPS_PREP = {
    "margherita": 12, "reine": 13, "regina": 13, "4 fromage": 14,
    "napolitaine": 12, "parmigiano": 15, "rucola": 14, "thon": 14,
    "palerme": 13, "rucolini": 14, "corleoni": 14, "vegetarienne": 13,
    "flammenkuche": 14, "saumon": 15, "chevre miel": 14, "savoyarde": 15,
    "carnivore": 16, "roquefort": 14, "cremosa": 13, "buffalo": 16,
    "kebab": 14, "biggy burger": 14, "calzone": 18, "calzone kebab": 18,
    "vittoria": 15, "diavolita": 16, "primavera": 15, "calabrese": 15,
    "alpin": 14, "marco": 16, "magretto": 15, "nonna": 16,
    "pollo pesto": 15, "bergere": 14, "default": 13
}


def get_temps(pizza: str) -> int:
    pizza = str(pizza).lower()
    for key in TEMPS_PREP:
        if key in pizza:
            return TEMPS_PREP[key]
    return TEMPS_PREP["default"]


def str_to_min(h: str) -> int:
    h = str(h).strip().replace("H", ":").replace("h", ":")
    if ":" in h:
        p = h.split(":")
        return int(p[0]) * 60 + (int(p[1]) if len(p) > 1 and p[1] else 0)
    return int(h) * 60


def min_to_str(m: int) -> str:
    m = int(m)
    return str(m // 60).zfill(2) + "h" + str(m % 60).zfill(2)


def pizzas_dans_creneau(heure_str: str, exclure_id: int = None) -> int:
    retrait = str_to_min(heure_str)
    total = 0
    for cmd in commandes_du_jour:
        if exclure_id is not None and cmd.get("id") == exclure_id:
            continue
        if cmd.get("annulee"):
            continue
        cmd_retrait = str_to_min(cmd["heure"])
        if abs(cmd_retrait - retrait) < DUREE_CRENEAU:
            total += cmd.get("nb", 1)
    return total


def prochain_creneau_libre(heure_str: str, nb_pizzas: int):
    retrait = str_to_min(heure_str)
    for i in range(0, 120, DUREE_CRENEAU):
        heure_test = min_to_str(retrait + i)
        if pizzas_dans_creneau(heure_test) + nb_pizzas <= MAX_PIZZAS_PAR_CRENEAU:
            return heure_test, True
    return None, False


def calcul_lancement(heure_str: str, pizza: str, nb: int) -> str:
    base = get_temps(pizza)
    total = base + (nb - 1) * 5 + 3
    retrait = str_to_min(heure_str)
    return min_to_str(retrait - total)


def generer_planning() -> str:
    date = datetime.now().strftime("%d/%m/%Y")
    actives = [c for c in commandes_du_jour if not c.get("annulee")]
    lignes = "PLANNING " + date + "\n"
    lignes += str(len(actives)) + " commande(s) active(s)\n\n"
    for cmd in sorted(actives, key=lambda x: x["lancement"]):
        extras = " (" + cmd["extras"] + ")" if cmd.get("extras") else ""
        lignes += "LANCER " + cmd["lancement"] + "\n"
        lignes += str(cmd["nb"]) + "x " + cmd["pizza"] + extras + "\n"
        lignes += "Pour : " + cmd["prenom"] + "\n"
        lignes += "Retrait : " + cmd["heure"] + "\n\n"
    lignes += "Bonne soiree ! Pizza"
    return lignes


def send_whatsapp(message: str) -> bool:
    try:
        twilio_client.messages.create(
            body=message,
            from_="whatsapp:" + str(TWILIO_FROM),
            to="whatsapp:" + str(PIZZAIOLO_TEL)
        )
        print("WhatsApp envoye !")
        return True
    except Exception as e:
        print("Erreur WhatsApp : " + str(e))
        return False


# ──────────────────────────────────────────────
# ROUTES
# ──────────────────────────────────────────────

@app.get("/")
def home():
    actives = [c for c in commandes_du_jour if not c.get("annulee")]
    return {
        "statut": "Nova Pizzeria API",
        "commandes_actives": len(actives),
        "capacite": str(MAX_PIZZAS_PAR_CRENEAU) + " pizzas par " + str(DUREE_CRENEAU) + "min"
    }


@app.get("/health")
def health():
    return {"status": "ok", "agent": "Nova Pizzeria"}


@app.post("/commande")
async def passer_commande(request: Request):
    try:
        data = await request.json()
        print("Commande recue : " + str(data))

        prenom = data.get("prenom", "?")
        pizzas = data.get("pizzas", "?")
        heure = data.get("heure", "19h00")
        extras = data.get("extras", "")

        try:
            nb = int(data.get("nb", 1))
        except (ValueError, TypeError):
            nb = 1

        # Verifier la capacite du creneau
        pizzas_prises = pizzas_dans_creneau(heure)
        if pizzas_prises + nb > MAX_PIZZAS_PAR_CRENEAU:
            nouveau_creneau, trouve = prochain_creneau_libre(heure, nb)
            if trouve:
                return JSONResponse({
                    "statut": "creneau_plein",
                    "message": "Creneau " + heure + " plein (" + str(pizzas_prises) + "/" + str(MAX_PIZZAS_PAR_CRENEAU) + " pizzas). Prochain dispo : " + str(nouveau_creneau),
                    "prochain_creneau": nouveau_creneau
                })
            else:
                return JSONResponse({
                    "statut": "erreur",
                    "message": "Aucun creneau disponible ce soir"
                })

        # Creneau OK - enregistrer la commande
        commande_id = len(commandes_du_jour) + 1
        pizza_principale = pizzas.split(",")[0].strip()
        lancement = calcul_lancement(heure, pizza_principale, nb)

        commandes_du_jour.append({
            "id": commande_id,
            "prenom": prenom,
            "pizza": pizzas,
            "nb": nb,
            "heure": heure,
            "lancement": lancement,
            "extras": extras,
            "annulee": False,
            "created_at": datetime.now().isoformat()
        })

        # WhatsApp immediat au pizzaiolo
        msg = "NOUVELLE COMMANDE #" + str(commande_id) + "\n"
        msg += "Client : " + str(prenom) + "\n"
        msg += "Commande : " + str(nb) + "x " + str(pizzas)
        msg += " (" + str(extras) + ")\n" if extras else "\n"
        msg += "Retrait : " + str(heure) + "\n"
        msg += "Lancer a : " + str(lancement)
        send_whatsapp(msg)

        return JSONResponse({
            "statut": "ok",
            "commande_id": commande_id,
            "message": "Commande de " + str(prenom) + " enregistree pour " + str(heure),
            "lancement": lancement,
            "pizzas_dans_creneau": pizzas_dans_creneau(heure)
        })

    except Exception as e:
        print("Erreur : " + str(e))
        return JSONResponse({"statut": "erreur", "message": str(e)}, status_code=500)


@app.delete("/commande/{commande_id}")
async def annuler_commande(commande_id: int, request: Request):
    try:
        data = {}
        try:
            data = await request.json()
        except Exception:
            pass

        raison = data.get("raison", "Non precisee")

        # Chercher la commande
        commande = next(
            (c for c in commandes_du_jour if c["id"] == commande_id),
            None
        )

        if not commande:
            return JSONResponse(
                {"statut": "erreur", "message": "Commande #" + str(commande_id) + " introuvable"},
                status_code=404
            )

        if commande.get("annulee"):
            return JSONResponse(
                {"statut": "erreur", "message": "Commande #" + str(commande_id) + " deja annulee"},
                status_code=400
            )

        # Marquer comme annulee
        commande["annulee"] = True
        commande["annulee_at"] = datetime.now().isoformat()
        commande["raison_annulation"] = raison

        # WhatsApp au pizzaiolo
        extras_txt = ""
        if commande.get("extras"):
            extras_txt = " (" + str(commande["extras"]) + ")"

        msg = "ANNULATION COMMANDE #" + str(commande_id) + "\n"
        msg += "Client : " + str(commande["prenom"]) + "\n"
        msg += "Commande : " + str(commande["nb"]) + "x " + str(commande["pizza"]) + extras_txt + "\n"
        msg += "Retrait prevu : " + str(commande["heure"]) + "\n"
        msg += "Lancement prevu : " + str(commande["lancement"]) + "\n"
        msg += "Raison : " + str(raison)
        send_whatsapp(msg)

        return JSONResponse({
            "statut": "ok",
            "message": "Commande #" + str(commande_id) + " de " + str(commande["prenom"]) + " annulee",
            "commande": commande
        })

    except Exception as e:
        print("Erreur annulation : " + str(e))
        return JSONResponse({"statut": "erreur", "message": str(e)}, status_code=500)


@app.get("/creneaux")
def voir_creneaux():
    creneaux = {}
    for h in range(18 * 60, 22 * 60, DUREE_CRENEAU):
        heure_str = min_to_str(h)
        prises = pizzas_dans_creneau(heure_str)
        creneaux[heure_str] = {
            "pizzas_prises": prises,
            "disponible": prises < MAX_PIZZAS_PAR_CRENEAU,
            "places_restantes": MAX_PIZZAS_PAR_CRENEAU - prises
        }
    return creneaux


@app.get("/planning")
def voir_planning():
    actives = [c for c in commandes_du_jour if not c.get("annulee")]
    annulees = [c for c in commandes_du_jour if c.get("annulee")]
    return {
        "date": datetime.now().strftime("%d/%m/%Y"),
        "commandes_actives": actives,
        "commandes_annulees": annulees,
        "planning": generer_planning()
    }


@app.post("/send/planning")
async def send_planning_complet():
    actives = [c for c in commandes_du_jour if not c.get("annulee")]
    if not actives:
        return {"statut": "aucune commande active"}
    planning = generer_planning()
    send_whatsapp(planning)
    return {"statut": "ok", "planning": planning}


@app.delete("/reset")
async def reset_planning():
    commandes_du_jour.clear()
    return {"statut": "planning remis a zero"}
    return {"statut": "planning remis a zero"}
