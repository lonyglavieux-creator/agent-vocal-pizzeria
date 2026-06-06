from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from groq import Groq
from twilio.rest import Client as TwilioClient
import os
from datetime import datetime

app = FastAPI()

groq_client   = Groq(api_key=os.environ.get("GROQ_API_KEY"))
twilio_client = TwilioClient(
    os.environ.get("TWILIO_SID"),
    os.environ.get("TWILIO_TOKEN")
)
TWILIO_FROM   = os.environ.get("TWILIO_FROM")
PIZZAIOLO_TEL = os.environ.get("PIZZAIOLO_TEL", "+33788705435")

# Planning du jour
commandes_du_jour = []

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
    pizza = pizza.lower()
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
    return f"{int(m)//60:02d}h{int(m)%60:02d}"

def calcule_lancement(heure_str, pizza, nb):
    base   = get_temps(pizza)
    total  = base + (nb-1)*5 + 3
    retrait = str_to_min(heure_str)
    return min_to_str(retrait - total)

def generer_planning():
    date   = datetime.now().strftime("%d/%m/%Y")
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

def envoyer_sms(message, dest=None):
    if not dest:
        dest = PIZZAIOLO_TEL
    try:
        twilio_client.messages.create(
            body=message,
            from_=TWILIO_FROM,
            to=dest
        )
        print(f"SMS envoye a {dest}")
        return True
    except Exception as e:
        print(f"Erreur SMS : {e}")
        return False

@app.get("/")
def home():
    return {"status": "Nova Pizzeria API", "commandes": len(commandes_du_jour)}

@app.get("/health")
def health():
    return {"status": "ok", "agent": "Nova Pizzeria"}

@app.post("/commande")
async def recevoir_commande(request: Request):
    """Reçoit les commandes depuis ElevenLabs webhook"""
    try:
        data = await request.json()
        print(f"Commande recue : {data}")

        prenom = data.get("prenom", "?")
        pizzas = data.get("pizzas", "?")
        heure  = data.get("heure", "19h00")
        extras = data.get("extras", "")

        # Calcule le temps de prep
        pizza_principale = pizzas.split(",")[0].strip()
        nb = pizzas.lower().count("pizza") or 1
        lancement = calcule_lancement(heure, pizza_principale, nb)

        # Ajoute au planning
        commandes_du_jour.append({
            "prenom": prenom,
            "pizza": pizzas,
            "nb": nb,
            "heure": heure,
            "lancement": lancement,
            "extras": extras
        })

        # SMS immediat au pizzaiolo
        sms  = f"NOUVELLE COMMANDE\n"
        sms += f"Client : {prenom}\n"
        sms += f"Commande : {pizzas}"
        sms += f" ({extras})\n" if extras else "\n"
        sms += f"Retrait : {heure}\n"
        sms += f"Lancer a : {lancement}"
        envoyer_sms(sms)

        return JSONResponse({
            "status": "ok",
            "message": f"Commande de {prenom} enregistree",
            "lancement": lancement
        })

    except Exception as e:
        print(f"Erreur : {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)

@app.get("/planning")
def voir_planning():
    """Voir le planning du jour"""
    return {
        "date": datetime.now().strftime("%d/%m/%Y"),
        "commandes": commandes_du_jour,
        "planning": generer_planning()
    }

@app.post("/envoyer-planning")
async def envoyer_planning_complet():
    """Envoie le planning complet au pizzaiolo"""
    if not commandes_du_jour:
        return {"status": "aucune commande"}
    planning = generer_planning()
    envoyer_sms(planning)
    return {"status": "ok", "planning": planning}

@app.delete("/reset")
async def reset_planning():
    """Remet le planning a zero (chaque matin)"""
    commandes_du_jour.clear()
    return {"status": "planning remis a zero"}
