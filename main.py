from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from twilio.rest import Client as TwilioClient
import os
from datetime import datetime

app = FastAPI()

twilio_client = TwilioClient(
    os.environ.get("TWILIO_SID"),
    os.environ.get("TWILIO_TOKEN")
)
TWILIO_FROM   = os.environ.get("TWILIO_FROM")
PIZZAIOLO_TEL = os.environ.get("PIZZAIOLO_TEL", "+33788705435")

# Planning du jour
commandes_du_jour = []

# Capacite du four
MAX_PIZZAS_PAR_CRENEAU = 2
DUREE_CRENEAU = 15  # minutes

TEMPS_PREP = {
    "margherita":12,"reine":13,"regina":13,"4 fromage":14,
    "napolitaine":12,"parmigiano":15,"rucola":14,"thon":14,
    "palermo":13,"rucolini":14,"corleoni":14,"vegetarienne":13,
    "flammenkush":14,"salmone":15,"chevre miel":14,"savoyarde":15,
    "carnivore":16,"roquefort":14,"cremosa":13,"buffalo":16,
    "kebab":14,"biggy burger":14,"calzone":18,"calzone kebab":18,
    "vittoria":15,"diavolita":16,"primavera":15,"calabrese":15,
    "alpine":14,"marco":16,"magretto":15,"nonna":16,
    "pollo pesto":15,"bergere":14,"default":13
}

def get_temps(pizza):
    pizza = str(pizza).lower()
    for key in TEMPS_PREP:
        if key in pizza:
            return TEMPS_PREP[key]
    return TEMPS_PREP["default"]

def str_to_min(h):
    h = str(h).strip().replace("h",":").replace("H",":")
    if ":" in h:
        p = h.split(":")
        return int(p[0])*60 + (int(p[1]) if len(p)>1 and p[1] else 0)
    return int(h)*60

def min_to_str(m):
    m = int(m)
    return f"{m//60:02d}h{m%60:02d}"

def pizzas_dans_creneau(heure_str):
    """Compte le nombre de pizzas dans un créneau de 15 min"""
    retrait = str_to_min(heure_str)
    total = 0
    for cmd in commandes_du_jour:
        cmd_retrait = str_to_min(cmd['heure'])
        if abs(cmd_retrait - retrait) < DUREE_CRENEAU:
            total += cmd.get('nb', 1)
    return total

def prochain_creneau_libre(heure_str, nb_pizzas):
    """Trouve le prochain créneau disponible"""
    retrait = str_to_min(heure_str)
    # Essaie jusqu'à 2h plus tard
    for i in range(0, 120, DUREE_CRENEAU):
        heure_test = min_to_str(retrait + i)
        if pizzas_dans_creneau(heure_test) + nb_pizzas <= MAX_PIZZAS_PAR_CRENEAU:
            return heure_test, True
    return None, False

def calcule_lancement(heure_str, pizza, nb):
    base = get_temps(pizza)
    total = base + (nb-1)*5 + 3
    retrait = str_to_min(heure_str)
    return min_to_str(retrait - total)

def generer_planning():
    date = datetime.now().strftime("%d/%m/%Y")
    lignes = f"PLANNING {date}\n"
    lignes += f"{len(commandes_du_jour)} commande(s)\n\n"
    for cmd in sorted(commandes_du_jour, key=lambda x: x['lancement']):
        extras = f" ({cmd['extras']})" if cmd.get('extras') else ""
        lignes += f"LANCER {cmd['lancement']}\n"
        lignes += f"  {cmd['nb']}x {cmd['pizza']}{extras}\n"
        lignes += f"  Pour : {cmd['prenom']}\n"
        lignes += f"  Retrait : {cmd['heure']}\n\n"
    lignes += "Bonne soiree !"
    return lignes

def envoyer_whatsapp(message):
    try:
        twilio_client.messages.create(
            body=message,
            from_=f"whatsapp:{TWILIO_FROM}",
            to=f"whatsapp:{PIZZAIOLO_TEL}"
        )
        print(f"WhatsApp envoye !")
        return True
    except Exception as e:
        print(f"Erreur WhatsApp : {e}")
        return False

@app.get("/")
def home():
    return {
        "status": "Nova Pizzeria API",
        "commandes": len(commandes_du_jour),
        "capacite": f"{MAX_PIZZAS_PAR_CRENEAU} pizzas par {DUREE_CRENEAU}min"
    }

@app.get("/health")
def health():
    return {"status": "ok", "agent": "Nova Pizzeria"}

@app.post("/commande")
async def recevoir_commande(request: Request):
    try:
        data = await request.json()
        print(f"Commande recue : {data}")

        prenom = data.get("prenom", "?")
        pizzas = data.get("pizzas", "?")
        heure  = data.get("heure", "19h00")
        extras = data.get("extras", "")

        # Compte le nombre de pizzas
        nb = data.get("nb", 1)
        try:
            nb = int(nb)
        except:
            nb = 1

        # Verifie la capacite du creneau
        pizzas_prises = pizzas_dans_creneau(heure)
        if pizzas_prises + nb > MAX_PIZZAS_PAR_CRENEAU:
            # Trouve le prochain creneau libre
            nouveau_creneau, trouve = prochain_creneau_libre(heure, nb)
            if trouve:
                message_erreur = f"Creneau {heure} plein ({pizzas_prises}/{MAX_PIZZAS_PAR_CRENEAU} pizzas). Prochain dispo : {nouveau_creneau}"
                return JSONResponse({
                    "status": "creneau_plein",
                    "message": message_erreur,
                    "prochain_creneau": nouveau_creneau
                })
            else:
                return JSONResponse({
                    "status": "error",
                    "message": "Aucun creneau disponible ce soir"
                })

        # Creneau OK - enregistre la commande
        pizza_principale = pizzas.split(",")[0].strip()
        lancement = calcule_lancement(heure, pizza_principale, nb)

        commandes_du_jour.append({
            "prenom": prenom,
            "pizza": pizzas,
            "nb": nb,
            "heure": heure,
            "lancement": lancement,
            "extras": extras
        })

        # WhatsApp immediat au pizzaiolo
        msg  = f"NOUVELLE COMMANDE\n"
        msg += f"Client : {prenom}\n"
        msg += f"Commande : {nb}x {pizzas}"
        msg += f" ({extras})\n" if extras else "\n"
        msg += f"Retrait : {heure}\n"
        msg += f"Lancer a : {lancement}"
        envoyer_whatsapp(msg)

        return JSONResponse({
            "status": "ok",
            "message": f"Commande de {prenom} enregistree pour {heure}",
            "lancement": lancement,
            "pizzas_dans_creneau": pizzas_dans_creneau(heure)
        })

    except Exception as e:
        print(f"Erreur : {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)

@app.get("/creneaux")
def voir_creneaux():
    """Voir les créneaux disponibles"""
    creneaux = {}
    for h in range(18*60, 22*60, DUREE_CRENEAU):
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
    return {
        "date": datetime.now().strftime("%d/%m/%Y"),
        "commandes": commandes_du_jour,
        "planning": generer_planning()
    }

@app.post("/envoyer-planning")
async def envoyer_planning_complet():
    if not commandes_du_jour:
        return {"status": "aucune commande"}
    planning = generer_planning()
    envoyer_whatsapp(planning)
    return {"status": "ok", "planning": planning}

@app.delete("/reset")
async def reset_planning():
    commandes_du_jour.clear()
    return {"status": "planning remis a zero"}
