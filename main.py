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

# ──────────────────────────────────────────────
# DONNEES DU JOUR
# ──────────────────────────────────────────────

commandes_du_jour = []

# Etat du four : nombre de fours actifs (1 ou 2)
# Quand un four tombe en panne, le pizzaiolo appelle POST /four avec {"actifs": 1}
config_four = {"fours_actifs": 2}

# Ingredients / pizzas indisponibles
# Format : {"margherita": "plus de tomates", "saumon": "rupture stock"}
indisponibles = {}

# ──────────────────────────────────────────────
# CAPACITE
# ──────────────────────────────────────────────

DUREE_CRENEAU = 15  # minutes

# Capacite de base par creneau selon nb de fours
def get_max_pizzas():
    return config_four["fours_actifs"] * 2

# ──────────────────────────────────────────────
# CARTE COMPLETE AVEC PRIX
# ──────────────────────────────────────────────

CARTE = {
    "margherita":     {"prix": 9.5,  "temps": 12},
    "reine":          {"prix": 11.5, "temps": 13},
    "regina":         {"prix": 11.5, "temps": 13},
    "4 fromage":      {"prix": 12.0, "temps": 14},
    "napolitaine":    {"prix": 10.5, "temps": 12},
    "parmigiano":     {"prix": 13.0, "temps": 15},
    "rucola":         {"prix": 13.5, "temps": 14},
    "thon":           {"prix": 11.0, "temps": 14},
    "palerme":        {"prix": 12.0, "temps": 13},
    "rucolini":       {"prix": 13.5, "temps": 14},
    "corleoni":       {"prix": 14.0, "temps": 14},
    "vegetarienne":   {"prix": 11.0, "temps": 13},
    "flammenkuche":   {"prix": 12.5, "temps": 14},
    "saumon":         {"prix": 14.5, "temps": 15},
    "chevre miel":    {"prix": 12.5, "temps": 14},
    "savoyarde":      {"prix": 13.5, "temps": 15},
    "carnivore":      {"prix": 14.0, "temps": 16},
    "roquefort":      {"prix": 12.5, "temps": 14},
    "cremosa":        {"prix": 12.0, "temps": 13},
    "buffalo":        {"prix": 14.5, "temps": 16},
    "kebab":          {"prix": 12.5, "temps": 14},
    "biggy burger":   {"prix": 13.0, "temps": 14},
    "calzone":        {"prix": 13.5, "temps": 18},
    "calzone kebab":  {"prix": 14.0, "temps": 18},
    "vittoria":       {"prix": 13.0, "temps": 15},
    "diavolita":      {"prix": 13.5, "temps": 16},
    "primavera":      {"prix": 12.0, "temps": 15},
    "calabrese":      {"prix": 13.0, "temps": 15},
    "alpin":          {"prix": 13.5, "temps": 14},
    "marco":          {"prix": 14.0, "temps": 16},
    "magretto":       {"prix": 13.5, "temps": 15},
    "nonna":          {"prix": 14.0, "temps": 16},
    "pollo pesto":    {"prix": 13.5, "temps": 15},
    "bergere":        {"prix": 12.5, "temps": 14},
}

PRIX_DEFAULT = 12.0
TEMPS_DEFAULT = 13


def get_info_pizza(pizza: str) -> dict:
    pizza = str(pizza).lower()
    for key in CARTE:
        if key in pizza:
            return CARTE[key]
    return {"prix": PRIX_DEFAULT, "temps": TEMPS_DEFAULT}


def get_temps(pizza: str) -> int:
    return get_info_pizza(pizza)["temps"]


def get_prix(pizza: str) -> float:
    return get_info_pizza(pizza)["prix"]


def calcul_total(pizzas_str: str, nb: int) -> float:
    pizza_principale = pizzas_str.split(",")[0].strip()
    prix_unitaire = get_prix(pizza_principale)
    return round(prix_unitaire * nb, 2)


def pizza_est_disponible(pizza: str) -> tuple:
    pizza_lower = str(pizza).lower()
    for key in indisponibles:
        if key in pizza_lower:
            return False, indisponibles[key]
    return True, ""


# ──────────────────────────────────────────────
# PLANNING
# ──────────────────────────────────────────────

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
        if pizzas_dans_creneau(heure_test) + nb_pizzas <= get_max_pizzas():
            return heure_test, True
    return None, False


def calcul_lancement(heure_str: str, pizza: str, nb: int) -> str:
    base = get_temps(pizza)
    # Avec 1 seul four, on ajoute 3 min de marge supplementaire
    marge = 5 if config_four["fours_actifs"] == 1 else 3
    total = base + (nb - 1) * 5 + marge
    retrait = str_to_min(heure_str)
    return min_to_str(retrait - total)


def generer_planning() -> str:
    date = datetime.now().strftime("%d/%m/%Y")
    actives = [c for c in commandes_du_jour if not c.get("annulee")]
    lignes = "PLANNING " + date + "\n"
    lignes += str(len(actives)) + " commande(s) active(s)\n"
    lignes += "Fours actifs : " + str(config_four["fours_actifs"]) + "\n"
    if indisponibles:
        lignes += "Indisponibles : " + ", ".join(indisponibles.keys()) + "\n"
    lignes += "\n"
    for cmd in sorted(actives, key=lambda x: x["lancement"]):
        extras = " (" + cmd["extras"] + ")" if cmd.get("extras") else ""
        tel = " - Tel : " + cmd["telephone"] if cmd.get("telephone") else ""
        lignes += "LANCER " + cmd["lancement"] + "\n"
        lignes += str(cmd["nb"]) + "x " + cmd["pizza"] + extras + "\n"
        lignes += "Pour : " + cmd["prenom"] + tel + "\n"
        lignes += "Retrait : " + cmd["heure"] + "\n"
        lignes += "Total : " + str(cmd["total"]) + " euros\n\n"
    lignes += "Bonne soiree !"
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
        "statut": "Nova Pizzeria API v2",
        "commandes_actives": len(actives),
        "fours_actifs": config_four["fours_actifs"],
        "capacite": str(get_max_pizzas()) + " pizzas par " + str(DUREE_CRENEAU) + "min",
        "indisponibles": indisponibles
    }


@app.get("/health")
def health():
    return {"status": "ok", "agent": "Nova Pizzeria v2"}


# ──────────────────────────────────────────────
# COMMANDE
# ──────────────────────────────────────────────

@app.post("/commande")
async def passer_commande(request: Request):
    try:
        data = await request.json()
        print("Commande recue : " + str(data))

        prenom    = data.get("prenom", "?")
        pizzas    = data.get("pizzas", "?")
        heure     = data.get("heure", "19h00")
        extras    = data.get("extras", "")
        telephone = data.get("telephone", "")

        try:
            nb = int(data.get("nb", 1))
        except (ValueError, TypeError):
            nb = 1

        # Verifier disponibilite pizza
        pizza_principale = pizzas.split(",")[0].strip()
        dispo, raison_indispo = pizza_est_disponible(pizza_principale)
        if not dispo:
            return JSONResponse({
                "statut": "pizza_indisponible",
                "message": "Desole, " + pizza_principale + " n'est pas disponible ce soir. Raison : " + raison_indispo,
                "pizza": pizza_principale,
                "raison": raison_indispo
            })

        # Verifier la capacite du creneau
        pizzas_prises = pizzas_dans_creneau(heure)
        if pizzas_prises + nb > get_max_pizzas():
            nouveau_creneau, trouve = prochain_creneau_libre(heure, nb)
            if trouve:
                return JSONResponse({
                    "statut": "creneau_plein",
                    "message": "Creneau " + heure + " plein (" + str(pizzas_prises) + "/" + str(get_max_pizzas()) + " pizzas). Prochain dispo : " + str(nouveau_creneau),
                    "prochain_creneau": nouveau_creneau
                })
            else:
                return JSONResponse({
                    "statut": "erreur",
                    "message": "Aucun creneau disponible ce soir"
                })

        # Calculs
        commande_id = len(commandes_du_jour) + 1
        lancement   = calcul_lancement(heure, pizza_principale, nb)
        total       = calcul_total(pizzas, nb)

        commandes_du_jour.append({
            "id":         commande_id,
            "prenom":     prenom,
            "telephone":  telephone,
            "pizza":      pizzas,
            "nb":         nb,
            "heure":      heure,
            "lancement":  lancement,
            "extras":     extras,
            "total":      total,
            "annulee":    False,
            "created_at": datetime.now().isoformat()
        })

        # WhatsApp au pizzaiolo
        msg  = "NOUVELLE COMMANDE #" + str(commande_id) + "\n"
        msg += "Client : " + str(prenom)
        if telephone:
            msg += " - " + str(telephone)
        msg += "\n"
        msg += "Commande : " + str(nb) + "x " + str(pizzas)
        msg += " (" + str(extras) + ")\n" if extras else "\n"
        msg += "Retrait : " + str(heure) + "\n"
        msg += "Lancer a : " + str(lancement) + "\n"
        msg += "Total : " + str(total) + " euros"
        send_whatsapp(msg)

        return JSONResponse({
            "statut":               "ok",
            "commande_id":          commande_id,
            "message":              "Commande de " + str(prenom) + " enregistree pour " + str(heure),
            "lancement":            lancement,
            "total":                total,
            "pizzas_dans_creneau":  pizzas_dans_creneau(heure)
        })

    except Exception as e:
        print("Erreur : " + str(e))
        return JSONResponse({"statut": "erreur", "message": str(e)}, status_code=500)


# ──────────────────────────────────────────────
# ANNULATION
# ──────────────────────────────────────────────

@app.delete("/commande/{commande_id}")
async def annuler_commande(commande_id: int, request: Request):
    try:
        data = {}
        try:
            data = await request.json()
        except Exception:
            pass

        raison = data.get("raison", "Non precisee")

        commande = next(
            (c for c in commandes_du_jour if c["id"] == commande_id), None
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

        commande["annulee"]            = True
        commande["annulee_at"]         = datetime.now().isoformat()
        commande["raison_annulation"]  = raison

        extras_txt = ""
        if commande.get("extras"):
            extras_txt = " (" + str(commande["extras"]) + ")"

        tel_txt = ""
        if commande.get("telephone"):
            tel_txt = " - " + str(commande["telephone"])

        msg  = "ANNULATION COMMANDE #" + str(commande_id) + "\n"
        msg += "Client : " + str(commande["prenom"]) + tel_txt + "\n"
        msg += "Commande : " + str(commande["nb"]) + "x " + str(commande["pizza"]) + extras_txt + "\n"
        msg += "Retrait prevu : " + str(commande["heure"]) + "\n"
        msg += "Lancement prevu : " + str(commande["lancement"]) + "\n"
        msg += "Raison : " + str(raison)
        send_whatsapp(msg)

        return JSONResponse({
            "statut":   "ok",
            "message":  "Commande #" + str(commande_id) + " de " + str(commande["prenom"]) + " annulee",
            "commande": commande
        })

    except Exception as e:
        print("Erreur annulation : " + str(e))
        return JSONResponse({"statut": "erreur", "message": str(e)}, status_code=500)


# ──────────────────────────────────────────────
# PRIX (pour que Nova puisse calculer avant confirmation)
# ──────────────────────────────────────────────

@app.post("/prix")
async def calculer_prix(request: Request):
    try:
        data  = await request.json()
        pizzas = data.get("pizzas", "")
        try:
            nb = int(data.get("nb", 1))
        except (ValueError, TypeError):
            nb = 1

        pizza_principale = pizzas.split(",")[0].strip()
        prix_unitaire    = get_prix(pizza_principale)
        total            = calcul_total(pizzas, nb)

        return JSONResponse({
            "statut":         "ok",
            "pizza":          pizza_principale,
            "prix_unitaire":  prix_unitaire,
            "nb":             nb,
            "total":          total,
            "message":        str(nb) + " pizza(s) " + pizza_principale + " = " + str(total) + " euros"
        })

    except Exception as e:
        return JSONResponse({"statut": "erreur", "message": str(e)}, status_code=500)


# ──────────────────────────────────────────────
# GESTION FOUR
# ──────────────────────────────────────────────

@app.post("/four")
async def modifier_fours(request: Request):
    try:
        data   = await request.json()
        actifs = int(data.get("actifs", 2))

        if actifs not in [1, 2]:
            return JSONResponse(
                {"statut": "erreur", "message": "Nombre de fours doit etre 1 ou 2"},
                status_code=400
            )

        ancien = config_four["fours_actifs"]
        config_four["fours_actifs"] = actifs

        msg_four = ""
        if actifs < ancien:
            msg_four = "ALERTE FOUR : " + str(actifs) + " four(s) actif(s) sur 2. Capacite reduite a " + str(get_max_pizzas()) + " pizzas par 15min."
        else:
            msg_four = "INFO FOUR : " + str(actifs) + " four(s) actif(s). Capacite normale retablie."

        send_whatsapp(msg_four)

        return JSONResponse({
            "statut":         "ok",
            "fours_actifs":   actifs,
            "capacite":       str(get_max_pizzas()) + " pizzas par 15min",
            "message":        msg_four
        })

    except Exception as e:
        return JSONResponse({"statut": "erreur", "message": str(e)}, status_code=500)


@app.get("/four")
def voir_fours():
    return {
        "fours_actifs": config_four["fours_actifs"],
        "capacite":     str(get_max_pizzas()) + " pizzas par 15min"
    }


# ──────────────────────────────────────────────
# GESTION INDISPONIBILITES
# ──────────────────────────────────────────────

@app.post("/indisponible")
async def ajouter_indisponible(request: Request):
    try:
        data   = await request.json()
        pizza  = str(data.get("pizza", "")).lower().strip()
        raison = str(data.get("raison", "Indisponible ce soir"))

        if not pizza:
            return JSONResponse(
                {"statut": "erreur", "message": "Nom de pizza requis"},
                status_code=400
            )

        indisponibles[pizza] = raison

        msg = "INDISPONIBILITE : " + pizza + " - " + raison
        send_whatsapp(msg)

        return JSONResponse({
            "statut":         "ok",
            "pizza":          pizza,
            "raison":         raison,
            "indisponibles":  indisponibles,
            "message":        pizza + " marque indisponible. Nova ne l'acceptera plus ce soir."
        })

    except Exception as e:
        return JSONResponse({"statut": "erreur", "message": str(e)}, status_code=500)


@app.delete("/indisponible/{pizza}")
async def retirer_indisponible(pizza: str):
    pizza = pizza.lower().strip()
    if pizza in indisponibles:
        del indisponibles[pizza]
        return JSONResponse({
            "statut":  "ok",
            "message": pizza + " est de nouveau disponible"
        })
    return JSONResponse(
        {"statut": "erreur", "message": pizza + " n'etait pas marque indisponible"},
        status_code=404
    )


@app.get("/indisponibles")
def voir_indisponibles():
    return {
        "indisponibles": indisponibles,
        "nb":            len(indisponibles)
    }


# ──────────────────────────────────────────────
# CRENEAUX / PLANNING
# ──────────────────────────────────────────────

@app.get("/creneaux")
def voir_creneaux():
    creneaux = {}
    for h in range(18 * 60, 22 * 60, DUREE_CRENEAU):
        heure_str = min_to_str(h)
        prises    = pizzas_dans_creneau(heure_str)
        creneaux[heure_str] = {
            "pizzas_prises":    prises,
            "disponible":       prises < get_max_pizzas(),
            "places_restantes": get_max_pizzas() - prises
        }
    return creneaux


@app.get("/planning")
def voir_planning():
    actives  = [c for c in commandes_du_jour if not c.get("annulee")]
    annulees = [c for c in commandes_du_jour if c.get("annulee")]
    return {
        "date":                datetime.now().strftime("%d/%m/%Y"),
        "fours_actifs":        config_four["fours_actifs"],
        "indisponibles":       indisponibles,
        "commandes_actives":   actives,
        "commandes_annulees":  annulees,
        "planning":            generer_planning()
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
    indisponibles.clear()
    config_four["fours_actifs"] = 2
    return {"statut": "planning remis a zero, fours et indisponibilites reinitialises"}


# ──────────────────────────────────────────────
# CARTE (pour que Nova puisse consulter les prix)
# ──────────────────────────────────────────────

@app.get("/carte")
def voir_carte():
    return {
        "pizzas": [
            {"nom": k, "prix": v["prix"], "temps_prep": v["temps"]}
            for k, v in CARTE.items()
        ]
    }
