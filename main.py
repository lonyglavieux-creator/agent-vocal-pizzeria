de fastapi import FastAPI, Demande
de fastapi.responses import JSONResponse, Réponse
de twilio.rest import Client en tant que TwilioClient
Importer os
à partir de datetime datetime d'importation

application = FastAPI()

twilio_client = TwilioClient(
    os.environ.get("TWILIO_SID"),
    os.environ.get("TWILIO_TOKEN")
)
TWILIO_FROM = os.environ.get("TWILIO_FROM")
PIZZAIOLO_TEL = os.environ.get("PIZZAIOLO_TEL", "+33788705435")

# Planification du jour
commandes_du_jour = []

# Capacite du quatre
MAX_PIZZAS_PAR_CRENEAU = 2
DURE_CRENEAU = 15 # minutes

TEMPS_PREP = {
    "margherita":12,"reine":13,"regina":13,4 fromage":14,
    "napolitaine":12,,parmigiano":15,"rucola":14,"thon":14,
    "palerme":13,,rucolini":14,corleoni":14,"végétarienne":13,
    "flammenkush":14,"saumone":15,chevre miel":14,"savoyarde":15,
    "carnivore":16,"roquefort":14,crémose":13,"buffalo":16,
    "kebab":14,"biggy burger":14,calzone":18,calzone kebab":18,
    "vittoria":15,",diavolita":16,"primavera":15,"calabrese":15,
    "alpin":14,"marco":16,"magretto":15,"nonna":16,
    "pollo pesto":15,,bergère":14,"par défaut":13
}

def get_temps(pizza):
    pizza = str(pizza).lower()
    pour la clé dans TEMPS_PREP:
        si la clé dans la pizza:
            Retourner TEMPS_PREP[key]
    retourner TEMPS_PREP["default"]

def str_to_min(h):
    h = str(h).strip().replace("h","").replace("H",":")
    si ":" en h:
        p = h.split(":")
        retour int(p[0])*60 + (int(p[1]) si len(p)>1 et p[1] sinon 0)
    Retour int(h)*60

def min_to_str(m):
    m = int(m)
    retour f"{m//60:02d}h{m%60:02d}"

def pizzas_dans_creneau(heure_str):
    ""Compte le nombre de pizzas dans un nucane de 15 min"""
    = retrait str_to_min(heure_str)
    total = 0
    pour cmd dans commandes_du_jour:
        cmd_retrait = str_to_min(cmd['heure'])
        if abs(cmd_retrait -) < DUREE_CRENEAU:
            total += cmd.get('nb', 1)
    retour total

def prochain_creneau_libre(heure_str, nb_pizzas):
    ""Trouve le prochain disponible"""
    = retrait str_to_min(heure_str)
    # Essaie jusqu'à 2h plus tard
    pour i en gamme(0, 120, DUREE_CRENEAU):
        heure_test = min_to_str(retrait + i)
        si pizzas_dans_creneau(heure_test) + nb_pizzas <= MAX_PIZZAS_PAR_CRENEAU:
            Retour heure_test, Vrai
    Retour Aucun, Faux

def calcul_lancement(heure_str, pizza, nb):
    base = get_temps(pizza)
    total = base + (nb-1)*5 + 3
    = retrait str_to_min(heure_str)
    retour min_to_str(retrait - total)

def generer_planning():
    date = datetime.now().strftime("%d/%m/%Y")
    lignes = f"PLANNING {date}\n"
    lignes += f"{len(commandes_du_jour)} commande(s)\n\n"
    pour cmd dans tried(commandes_du_jour, key=lambda x: x['lancement']):
        extras = f" ({cmd['extras']})" si cmd.get('extras') else ""
        lignes += f"LANCER {cmd['lancement']}\n"
        lignes += f" {cmd['nb']}x {cmd['pizza']}{extras}\n"
        lignes += f" Pour : {cmd['prenom']}\n"
        lignes += f" Retrait : {cmd['heure']}\n\n"
    lignes += "Bonne soirée !"
    Retour de lignes

def_wheresapp(message):
    Essayez:
        twilio_client.messages.create(
            corps = message,
            from_=f"whatsapp:{TWILIO_FROM}",
            to=f"whatsapp:{PIZZAIOLO_TEL}"
        )
        print(f"WhatsApp envoyé !")
        Retour True
    sauf Exception comme e:
        print(f"Erreur WhatsApp : {e}")
        Retour Faux

@app.get("/")
def home():
    retour {
        "statut": "Nova Pizzeria API",
        "commandes": len(commandes_du_jour),
        "capacite": f"{MAX_PIZZAS_PAR_CRENEAU} pizzas par {DURE_CRENEAU}min"
    }

@app.get("/santé")
def health():
    retour {"status": "ok", "agent": "Nova Pizzeria"}

@app.post("/commande")
async def dexe_commande(demande: Demande):
    Essayez:
        données = attendre request.json()
        print(f"Commande recue : {data}")

        prenom = data.get("prenom", "?")
        pizzas = data.get("pizzas", "?")
        heure = data.get("heure", "19h00")
        extras = data.get("extras", "")

        # Compte le nombre de pizzas
        nb = data.get("nb", 1)
        Essayez:
            nb = int(nb)
        sauf:
            nb = 1

        # Vérifier la capacité du creneau
        pizzas_prises = pizzas_dans_creneau(heure)
        si pizzas_prises + nb > MAX_PIZZAS_PAR_CRENEAU:
            # Trouve le prochain creneau libre
            nouveau_creneau, trouve = prochain_creneau_libre(heure, nb)
            si trouve:
                message_erreur = f"Creneau {heure} plein ({pizzas_prises}/{MAX_PIZZAS_PAR_CRENEAU} pizzas). Dispo Prochain : {nouveau_creneau}"
                Retour JSONResponse({
                    "statu": "creneau_plein",
                    "message": message_erreur,
                    "prochain_creneau": nouveau_creneau
                })
            autre:
                Retour JSONResponse({
                    "statut": "erreur",
                    "message": "Aucun creneau disponible ce soir"
                })

        # Creneau OK - enregistre la commande
        pizza_principale = pizzas.split(",")[0].strip()
        lancement = calcul_lancement(heure, pizza_principale, nb)

        commandes_du_jour.append({
            "prenom": prenom,
            "pizza": pizzas,
            "nb": nb,
            "heure": heure,
            "lancement": lancement,
            "extras": extras
        })

        # WhatsApp immediat au pizzaiolo
        msg = f"NOUVELLE COMMANDE\n"
        msg += f"Client : {prenom}\n"
        msg += f"Commande : {nb}x {pizzas}"
        msg += f" ({extras})\n" si extras else "\n"
        msg += f"Retrait : {heure}\n"
        msg += f"Lancer a : {lancement}"
        sender_whatsapp(msg)

        Retour JSONResponse({
            "statut": "ok",
            "message": f"Commande de {prenom}e enregistre pour {heure}",
            "lancement": lancement,
            "pizzas_dans_creneau": pizzas_dans_creneau(heure)
        })

    sauf Exception comme e:
        print(f"Erreur : {e}")
        retour JSONResponse({"status": "erreur", "message": str(e)}, status_code=500)

@app.get("/creneaux")
def voir_creneaux():
    ""Voir les neunes disponibles"""
    Creneaux = {}
    pour h en rang(18*60, 22*60, DUREE_CRENEAU):
        heure_str = min_to_str(h)
        prises = pizzas_dans_creneau(heure_str)
        creneaux[heure_str] = {
            "pizzas_prises": prises,
            "disponible": prises < MAX_PIZZAS_PAR_CRENEAU,
            "places_restantes": MAX_PIZZAS_PAR_CRENEAU - prises
        }
    retour creneaux

@app.get("/planification")
def voir_planning():
    retour {
        "date": datetime.now().strftime("%d/%m/%Y"),
        "commandes": commandes_du_jour,
        "planning": generer_planning()
    }

@app.post("(envoyé/planification")
async def send_planning_complet():
    sinon commandes_du_jour:
        retour {"status": "annexe commande"}
    Planification = generer_planning()
    envoyer_whatsapp(planification)
    retour {"status": "ok", "planification": planification}

@app.delete("/reset")
async def reset_planning():
    commandes_du_jour.clear()
    retour {"statu": "planifier la rémission a zéro"}
