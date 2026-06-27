from fastapi import FastAPI, Request, Form
from fastapi.responses import JSONResponse, Response, FileResponse, HTMLResponse
from twilio.rest import Client as TwilioClient
from twilio.twiml.voice_response import VoiceResponse, Gather
import os
import json
import httpx
from datetime import datetime
from voice_handler import (
    transcribe_audio, get_nova_response, build_twiml_response,
    extract_command_from_conversation, needs_to_place_order,
    get_or_create_history, clear_history, conversation_histories
)
from database import (
    sauvegarder_commande, annuler_commande_db, charger_commandes_du_jour,
    get_commande_by_id, get_fours_actifs, set_fours_actifs,
    get_indisponibles, set_indisponibles, log_appel, supabase_ok
)

# Cache statut client (mis a jour toutes les heures)
_cache_statut = {"actif": True, "last_check": None}

def nova_est_active() -> bool:
    from datetime import datetime, timedelta
    import httpx
    global _cache_statut
    now = datetime.now()
    # Verifier toutes les heures
    if _cache_statut["last_check"] and (now - _cache_statut["last_check"]) < timedelta(hours=1):
        return _cache_statut["actif"]
    try:
        SUPABASE_URL_CHECK = os.environ.get("SUPABASE_URL", "")
        SUPABASE_KEY_CHECK = os.environ.get("SUPABASE_KEY", "")
        PIZZERIA_EMAIL     = os.environ.get("PIZZERIA_EMAIL", "")
        if not (SUPABASE_URL_CHECK and SUPABASE_KEY_CHECK and PIZZERIA_EMAIL):
            _cache_statut = {"actif": True, "last_check": now}
            return True
        r = httpx.get(
            SUPABASE_URL_CHECK + "/rest/v1/clients_nova?email=eq." + PIZZERIA_EMAIL,
            headers={
                "apikey": SUPABASE_KEY_CHECK,
                "Authorization": "Bearer " + SUPABASE_KEY_CHECK
            },
            timeout=5
        )
        if r.status_code == 200:
            data = r.json()
            if data:
                statut = data[0].get("statut", "actif")
                est_actif = statut == "actif"
                _cache_statut = {"actif": est_actif, "last_check": now}
                return est_actif
        _cache_statut = {"actif": True, "last_check": now}
        return True
    except Exception as e:
        print("Erreur verif statut Nova : " + str(e))
        return True

app = FastAPI()

twilio_client = TwilioClient(
    os.environ.get("TWILIO_SID"),
    os.environ.get("TWILIO_TOKEN")
)
TWILIO_FROM      = os.environ.get("TWILIO_FROM")
PIZZAIOLO_TEL    = os.environ.get("PIZZAIOLO_TEL", "+33788705435")
API_BASE         = os.environ.get("API_BASE_URL", "https://web-production-967e41.up.railway.app")

# ──────────────────────────────────────────────
# DONNEES DU JOUR (memoire + Supabase)
# ──────────────────────────────────────────────

commandes_du_jour = []
config_four       = {"fours_actifs": 1}
indisponibles     = {}

def init_depuis_supabase():
    """Charge les donnees du jour depuis Supabase au demarrage."""
    global commandes_du_jour, config_four, indisponibles
    if not supabase_ok():
        print("Supabase non configure - mode memoire uniquement")
        return
    try:
        commandes_db = charger_commandes_du_jour()
        if commandes_db:
            commandes_du_jour = commandes_db
            print("Commandes rechargees depuis Supabase : " + str(len(commandes_db)))
        config_four["fours_actifs"] = get_fours_actifs()
        indisponibles = get_indisponibles()
        print("Config rechargee depuis Supabase")
    except Exception as e:
        print("Erreur init Supabase : " + str(e))

# Charger au demarrage
init_depuis_supabase()

# ──────────────────────────────────────────────
# CAPACITE ET REGLES PLANNING
# ──────────────────────────────────────────────

DUREE_CRENEAU    = 15
MAX_PIZZAS       = 2
HEURE_OUVERTURE  = 18 * 60 + 15
HEURE_FERMETURE  = 22 * 60

def get_max_pizzas():
    return MAX_PIZZAS

def pizzeria_ouverte_aujourd_hui() -> tuple:
    jour = datetime.now().weekday()
    if jour == 6:
        return False, "Desole, Bella Pizza est fermee le dimanche. Nous sommes ouverts du lundi au samedi de 18h15 a 22h00 !"
    return True, ""

def heure_valide(heure_str: str) -> tuple:
    m = str_to_min(heure_str)
    if m < HEURE_OUVERTURE:
        return False, "Le four n est pas encore pret. Premiere commande possible a 18h15."
    if m > HEURE_FERMETURE:
        return False, "Nous n acceptons plus de commandes apres 22h00."
    return True, ""

def commande_aujourd_hui(heure_str: str) -> tuple:
    maintenant        = datetime.now()
    heure_actuelle    = maintenant.hour * 60 + maintenant.minute
    if heure_actuelle > HEURE_FERMETURE:
        return False, "La pizzeria est fermee pour ce soir. Revenez des demain a 18h15 !"
    return True, ""

# ──────────────────────────────────────────────
# CARTE AVEC PRIX
# ──────────────────────────────────────────────

CARTE = {
    "margherita":   {"prix": 9.5,  "temps": 12},
    "reine":        {"prix": 11.5, "temps": 13},
    "regina":       {"prix": 11.5, "temps": 13},
    "4 fromage":    {"prix": 12.0, "temps": 14},
    "napolitaine":  {"prix": 10.5, "temps": 12},
    "parmigiano":   {"prix": 13.0, "temps": 15},
    "rucola":       {"prix": 13.5, "temps": 14},
    "thon":         {"prix": 11.0, "temps": 14},
    "palerme":      {"prix": 12.0, "temps": 13},
    "rucolini":     {"prix": 13.5, "temps": 14},
    "corleoni":     {"prix": 14.0, "temps": 14},
    "vegetarienne": {"prix": 11.0, "temps": 13},
    "flammenkuche": {"prix": 12.5, "temps": 14},
    "saumon":       {"prix": 14.5, "temps": 15},
    "chevre miel":  {"prix": 12.5, "temps": 14},
    "savoyarde":    {"prix": 13.5, "temps": 15},
    "carnivore":    {"prix": 14.0, "temps": 16},
    "roquefort":    {"prix": 12.5, "temps": 14},
    "cremosa":      {"prix": 12.0, "temps": 13},
    "buffalo":      {"prix": 14.5, "temps": 16},
    "kebab":        {"prix": 12.5, "temps": 14},
    "biggy burger": {"prix": 13.0, "temps": 14},
    "calzone":      {"prix": 13.5, "temps": 18},
    "calzone kebab":{"prix": 14.0, "temps": 18},
    "vittoria":     {"prix": 13.0, "temps": 15},
    "diavolita":    {"prix": 13.5, "temps": 16},
    "primavera":    {"prix": 12.0, "temps": 15},
    "calabrese":    {"prix": 13.0, "temps": 15},
    "alpin":        {"prix": 13.5, "temps": 14},
    "marco":        {"prix": 14.0, "temps": 16},
    "magretto":     {"prix": 13.5, "temps": 15},
    "nonna":        {"prix": 14.0, "temps": 16},
    "pollo pesto":  {"prix": 13.5, "temps": 15},
    "bergere":      {"prix": 12.5, "temps": 14},
}

PRIX_DEFAULT  = 12.0
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
    return round(get_prix(pizza_principale) * nb, 2)

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
    total   = 0
    for cmd in commandes_du_jour:
        if exclure_id is not None and cmd.get("id") == exclure_id:
            continue
        if cmd.get("annulee"):
            continue
        if abs(str_to_min(cmd["heure"]) - retrait) < DUREE_CRENEAU:
            total += cmd.get("nb", 1)
    return total

def prochain_creneau_libre(heure_str: str, nb_pizzas: int):
    retrait = str_to_min(heure_str)
    for i in range(DUREE_CRENEAU, 120, DUREE_CRENEAU):
        heure_test = min_to_str(retrait + i)
        m_test     = str_to_min(heure_test)
        if m_test < HEURE_OUVERTURE or m_test > HEURE_FERMETURE:
            continue
        if pizzas_dans_creneau(heure_test) + nb_pizzas <= get_max_pizzas():
            return heure_test, True
    return None, False

def calcul_lancement(heure_str: str, pizza: str, nb: int) -> str:
    base   = get_temps(pizza)
    marge  = 5 if config_four["fours_actifs"] == 1 else 3
    total  = base + (nb - 1) * 5 + marge
    return min_to_str(str_to_min(heure_str) - total)

def generer_planning() -> str:
    date    = datetime.now().strftime("%d/%m/%Y")
    actives = [c for c in commandes_du_jour if not c.get("annulee")]
    lignes  = "PLANNING " + date + "\n"
    lignes += str(len(actives)) + " commande(s) active(s)\n"
    lignes += "Fours actifs : " + str(config_four["fours_actifs"]) + "\n"
    if indisponibles:
        lignes += "Indisponibles : " + ", ".join(indisponibles.keys()) + "\n"
    lignes += "\n"
    for cmd in sorted(actives, key=lambda x: x["lancement"]):
        extras = " (" + cmd["extras"] + ")" if cmd.get("extras") else ""
        tel    = " - Tel : " + cmd["telephone"] if cmd.get("telephone") else ""
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

def get_context():
    jours = ["Lundi","Mardi","Mercredi","Jeudi","Vendredi","Samedi","Dimanche"]
    now   = datetime.now()
    return {
        "jour_semaine":   jours[now.weekday()],
        "heure_actuelle": now.strftime("%Hh%M"),
        "fours_actifs":   config_four["fours_actifs"],
        "indisponibles":  indisponibles
    }

# ──────────────────────────────────────────────
# ROUTES VOCALES TWILIO
# ──────────────────────────────────────────────

@app.post("/voice/incoming")
async def voice_incoming(request: Request):
    """Twilio appelle cette route quand quelqu un appelle le numero."""
    form    = await request.form()
    call_sid = str(form.get("CallSid", "unknown"))
    clear_history(call_sid)

    # Detecter la pizzeria via le numero appele
    called_number = str(form.get("Called", form.get("To", "")))
    pizzeria = None
    try:
        from pizzeria_config import get_pizzeria_by_numero, get_menu, generer_prompt_pizzeria
        pizzeria = get_pizzeria_by_numero(called_number)
    except Exception as e:
        print("Erreur detection pizzeria : " + str(e))

    # Verifier si abonnement actif
    if pizzeria and not pizzeria.get("actif", True):
        resp = VoiceResponse()
        resp.say(
            "Bonjour. Ce service est temporairement indisponible. Veuillez contacter le responsable. Merci.",
            voice="Polly.Lea", language="fr-FR"
        )
        resp.hangup()
        return Response(content=str(resp), media_type="application/xml")

    if not pizzeria:
        if not nova_est_active():
            resp = VoiceResponse()
            resp.say(
                "Bonjour. Ce service est temporairement indisponible. Merci.",
                voice="Polly.Lea", language="fr-FR"
            )
            resp.hangup()
            return Response(content=str(resp), media_type="application/xml")

    ok_jour, msg_jour = pizzeria_ouverte_aujourd_hui()
    if not ok_jour:
        resp = VoiceResponse()
        resp.say(msg_jour, voice="Polly.Lea", language="fr-FR")
        resp.hangup()
        return Response(content=str(resp), media_type="application/xml")

    now = datetime.now()
    heure_actuelle = now.hour * 60 + now.minute
    if heure_actuelle > HEURE_FERMETURE:
        resp = VoiceResponse()
        resp.say(
            "Bonjour ! Bella Pizza est fermee pour ce soir. Nous vous attendons du lundi au samedi a partir de 18h15. A bientot !",
            voice="Polly.Lea", language="fr-FR"
        )
        resp.hangup()
        return Response(content=str(resp), media_type="application/xml")

    message_accueil = "Bonjour, Bella Pizza a l ecoute, je vous ecoute. Que puis-je faire pour vous ?"
    gather = Gather(
        input="speech",
        action=API_BASE + "/voice/respond",
        method="POST",
        language="fr-FR",
        speech_timeout="auto",
        timeout=6
    )
    resp = VoiceResponse()
    resp.say(message_accueil, voice="Polly.Lea", language="fr-FR")
    resp.append(gather)
    resp.redirect(API_BASE + "/voice/incoming")
    return Response(content=str(resp), media_type="application/xml")


@app.post("/voice/respond")
async def voice_respond(request: Request):
    """Twilio envoie ici chaque reponse du client."""
    form         = await request.form()
    call_sid     = str(form.get("CallSid", "unknown"))
    speech_result = str(form.get("SpeechResult", "")).strip()
    recording_url = str(form.get("RecordingUrl", "")).strip()

    # Transcription
    user_text = speech_result
    if not user_text and recording_url:
        user_text = transcribe_audio(recording_url)

    if not user_text:
        user_text = "je n ai pas compris"

    print("Client [" + call_sid + "] : " + user_text)

    # Recuperer le contexte du jour
    context = get_context()

    # Obtenir la reponse de Nova via Groq LLM
    nova_text = get_nova_response(call_sid, user_text, context)
    print("Nova [" + call_sid + "] : " + nova_text)

    # Verifier si Nova veut enregistrer une commande
    if needs_to_place_order(nova_text):
        history  = get_or_create_history(call_sid)
        cmd_data = extract_command_from_conversation(history)
        if cmd_data and cmd_data.get("prenom") and cmd_data.get("pizzas"):
            await _enregistrer_commande_auto(cmd_data, call_sid)

    # Verifier si l appel se termine
    fin_appel = any(kw in nova_text.lower() for kw in [
        "au revoir", "bonne soiree", "a bientot", "a tout a l heure", "bonne journee"
    ])

    # Construire la reponse TwiML avec TTS
    twiml = build_twiml_response(
        nova_text,
        gather_action=API_BASE + "/voice/respond",
        is_end=fin_appel
    )

    if fin_appel:
        clear_history(call_sid)
        # Enregistrer les minutes consommees
        try:
            from minutes_tracker import enregistrer_minutes
            from pizzeria_config import get_pizzeria_by_numero
            called = str(form.get("Called", form.get("To", "")))
            pizzeria_fin = get_pizzeria_by_numero(called)
            if pizzeria_fin:
                duree = float(form.get("CallDuration", 0))
                if duree > 0:
                    enregistrer_minutes(pizzeria_fin["id"], duree)
        except Exception as e:
            print("Erreur enregistrement minutes : " + str(e))

    return Response(content=twiml, media_type="application/xml")


async def _enregistrer_commande_auto(cmd_data: dict, call_sid: str):
    """Enregistre automatiquement la commande detectee dans la conversation."""
    try:
        prenom    = cmd_data.get("prenom", "?")
        pizzas    = cmd_data.get("pizzas", "?")
        heure     = cmd_data.get("heure", "19h00")
        nb        = int(cmd_data.get("nb", 1) or 1)
        extras    = cmd_data.get("extras", "") or ""
        telephone = cmd_data.get("telephone", "") or ""

        ok_jour, _ = pizzeria_ouverte_aujourd_hui()
        if not ok_jour:
            return

        pizza_principale = pizzas.split(",")[0].strip()
        dispo, _         = pizza_est_disponible(pizza_principale)
        if not dispo:
            return

        pizzas_prises = pizzas_dans_creneau(heure)
        if pizzas_prises + nb > get_max_pizzas():
            return

        commande_id = len(commandes_du_jour) + 1
        lancement   = calcul_lancement(heure, pizza_principale, nb)
        total       = calcul_total(pizzas, nb)

        nouvelle_cmd = {
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
            "created_at": datetime.now().isoformat(),
            "source":     "vocal"
        }
        commandes_du_jour.append(nouvelle_cmd)
        db_result = sauvegarder_commande(nouvelle_cmd)
        if db_result and db_result.get("id"):
            commande_id = db_result["id"]
            nouvelle_cmd["id"] = commande_id

        msg  = "NOUVELLE COMMANDE #" + str(commande_id) + " (appel vocal)\n"
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
        print("Commande #" + str(commande_id) + " enregistree automatiquement")

    except Exception as e:
        print("Erreur enregistrement auto : " + str(e))


# ──────────────────────────────────────────────
# ROUTES API (identiques a v2)
# ──────────────────────────────────────────────

@app.get("/")
def home():
    actives = [c for c in commandes_du_jour if not c.get("annulee")]
    jours   = ["Lundi","Mardi","Mercredi","Jeudi","Vendredi","Samedi","Dimanche"]
    jour    = datetime.now().weekday()
    return {
        "statut":            "Nova Pizzeria API v3 - Stack maison",
        "jour":              jours[jour],
        "ouvert":            jour != 6,
        "commandes_actives": len(actives),
        "fours_actifs":      config_four["fours_actifs"],
        "capacite":          str(get_max_pizzas()) + " pizzas par " + str(DUREE_CRENEAU) + "min",
        "indisponibles":     indisponibles
    }

@app.get("/health")
def health():
    return {"status": "ok", "agent": "Nova Pizzeria v3", "stack": "Groq+Twilio+Voxtral"}

@app.post("/commande")
async def passer_commande(request: Request):
    try:
        data      = await request.json()
        prenom    = data.get("prenom", "?")
        pizzas    = data.get("pizzas", "?")
        heure     = data.get("heure", "19h00")
        extras    = data.get("extras", "")
        telephone = data.get("telephone", "")
        try:
            nb = int(data.get("nb", 1))
        except (ValueError, TypeError):
            nb = 1

        ok_jour, msg_jour = pizzeria_ouverte_aujourd_hui()
        if not ok_jour:
            return JSONResponse({"statut": "ferme", "message": msg_jour})

        ok_soir, msg_soir = commande_aujourd_hui(heure)
        if not ok_soir:
            return JSONResponse({"statut": "ferme", "message": msg_soir})

        ok_heure, msg_heure = heure_valide(heure)
        if not ok_heure:
            return JSONResponse({"statut": "heure_invalide", "message": msg_heure})

        pizza_principale = pizzas.split(",")[0].strip()
        dispo, raison    = pizza_est_disponible(pizza_principale)
        if not dispo:
            return JSONResponse({"statut": "pizza_indisponible", "message": "Desole, " + pizza_principale + " indisponible. Raison : " + raison})

        pizzas_prises = pizzas_dans_creneau(heure)
        if pizzas_prises + nb > get_max_pizzas():
            nouveau_creneau, trouve = prochain_creneau_libre(heure, nb)
            if trouve:
                return JSONResponse({"statut": "creneau_plein", "message": "Creneau plein. Prochain dispo : " + str(nouveau_creneau), "prochain_creneau": nouveau_creneau})
            return JSONResponse({"statut": "erreur", "message": "Aucun creneau disponible ce soir"})

        commande_id = len(commandes_du_jour) + 1
        lancement   = calcul_lancement(heure, pizza_principale, nb)
        total       = calcul_total(pizzas, nb)

        nouvelle_cmd = {
            "id": commande_id, "prenom": prenom, "telephone": telephone,
            "pizza": pizzas, "nb": nb, "heure": heure, "lancement": lancement,
            "extras": extras, "total": total, "annulee": False,
            "created_at": datetime.now().isoformat(), "source": "api"
        }
        commandes_du_jour.append(nouvelle_cmd)
        db_result = sauvegarder_commande(nouvelle_cmd)
        if db_result and db_result.get("id"):
            commande_id = db_result["id"]
            nouvelle_cmd["id"] = commande_id

        msg  = "NOUVELLE COMMANDE #" + str(commande_id) + "\n"
        msg += "Client : " + str(prenom)
        if telephone: msg += " - " + str(telephone)
        msg += "\nCommande : " + str(nb) + "x " + str(pizzas)
        msg += " (" + str(extras) + ")\n" if extras else "\n"
        msg += "Retrait : " + str(heure) + "\nLancer a : " + str(lancement) + "\nTotal : " + str(total) + " euros"
        send_whatsapp(msg)

        return JSONResponse({"statut": "ok", "commande_id": commande_id,
            "message": "Commande de " + str(prenom) + " enregistree pour " + str(heure),
            "lancement": lancement, "total": total})

    except Exception as e:
        return JSONResponse({"statut": "erreur", "message": str(e)}, status_code=500)


@app.delete("/commande/{commande_id}")
async def annuler_commande(commande_id: int, request: Request):
    try:
        data = {}
        try: data = await request.json()
        except: pass
        raison   = data.get("raison", "Non precisee")
        commande = next((c for c in commandes_du_jour if c["id"] == commande_id), None)
        if not commande:
            return JSONResponse({"statut": "erreur", "message": "Commande introuvable"}, status_code=404)
        if commande.get("annulee"):
            return JSONResponse({"statut": "erreur", "message": "Deja annulee"}, status_code=400)

        commande["annulee"]           = True
        commande["annulee_at"]        = datetime.now().isoformat()
        commande["raison_annulation"] = raison
        # Sauvegarder annulation dans Supabase
        annuler_commande_db(commande_id, raison)

        extras_txt = " (" + str(commande["extras"]) + ")" if commande.get("extras") else ""
        tel_txt    = " - " + str(commande["telephone"]) if commande.get("telephone") else ""
        msg  = "ANNULATION #" + str(commande_id) + "\n"
        msg += "Client : " + str(commande["prenom"]) + tel_txt + "\n"
        msg += str(commande["nb"]) + "x " + str(commande["pizza"]) + extras_txt + "\n"
        msg += "Retrait prevu : " + str(commande["heure"]) + "\nRaison : " + str(raison)
        send_whatsapp(msg)

        return JSONResponse({"statut": "ok", "message": "Commande #" + str(commande_id) + " annulee"})
    except Exception as e:
        return JSONResponse({"statut": "erreur", "message": str(e)}, status_code=500)


@app.post("/prix")
async def calculer_prix(request: Request):
    try:
        data  = await request.json()
        pizzas = data.get("pizzas", "")
        try: nb = int(data.get("nb", 1))
        except: nb = 1
        pizza_principale = pizzas.split(",")[0].strip()
        total = calcul_total(pizzas, nb)
        return JSONResponse({"statut": "ok", "pizza": pizza_principale,
            "prix_unitaire": get_prix(pizza_principale), "nb": nb, "total": total})
    except Exception as e:
        return JSONResponse({"statut": "erreur", "message": str(e)}, status_code=500)


@app.post("/four")
async def modifier_fours(request: Request):
    try:
        data   = await request.json()
        actifs = int(data.get("actifs", 1))
        if actifs not in [0, 1]:
            return JSONResponse({"statut": "erreur", "message": "actifs doit etre 0 ou 1"}, status_code=400)
        config_four["fours_actifs"] = actifs
        set_fours_actifs(actifs)
        msg = "FOUR EN PANNE - aucune commande acceptee" if actifs == 0 else "FOUR OK - 2 pizzas par 15min"
        send_whatsapp(msg)
        return JSONResponse({"statut": "ok", "fours_actifs": actifs, "message": msg})
    except Exception as e:
        return JSONResponse({"statut": "erreur", "message": str(e)}, status_code=500)

@app.get("/four")
def voir_fours():
    return {"fours_actifs": config_four["fours_actifs"], "capacite": str(get_max_pizzas()) + " pizzas/15min"}


@app.post("/indisponible")
async def ajouter_indisponible(request: Request):
    try:
        data   = await request.json()
        pizza  = str(data.get("pizza", "")).lower().strip()
        raison = str(data.get("raison", "Indisponible ce soir"))
        if not pizza:
            return JSONResponse({"statut": "erreur", "message": "Nom requis"}, status_code=400)
        indisponibles[pizza] = raison
        set_indisponibles(indisponibles)
        send_whatsapp("INDISPONIBLE : " + pizza + " - " + raison)
        return JSONResponse({"statut": "ok", "pizza": pizza, "raison": raison, "indisponibles": indisponibles})
    except Exception as e:
        return JSONResponse({"statut": "erreur", "message": str(e)}, status_code=500)

@app.delete("/indisponible/{pizza}")
async def retirer_indisponible(pizza: str):
    pizza = pizza.lower().strip()
    if pizza in indisponibles:
        del indisponibles[pizza]
        set_indisponibles(indisponibles)
        return JSONResponse({"statut": "ok", "message": pizza + " de nouveau disponible"})
    return JSONResponse({"statut": "erreur", "message": pizza + " n etait pas bloque"}, status_code=404)

@app.get("/indisponibles")
def voir_indisponibles():
    return {"indisponibles": indisponibles, "nb": len(indisponibles)}


@app.get("/creneaux")
def voir_creneaux():
    creneaux = {}
    for h in range(HEURE_OUVERTURE, HEURE_FERMETURE, DUREE_CRENEAU):
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
    return {"date": datetime.now().strftime("%d/%m/%Y"), "fours_actifs": config_four["fours_actifs"],
        "indisponibles": indisponibles, "commandes_actives": actives,
        "commandes_annulees": annulees, "planning": generer_planning()}

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
    config_four["fours_actifs"] = 1
    return {"statut": "reset complet"}

@app.get("/carte")
def voir_carte():
    return {"pizzas": [{"nom": k, "prix": v["prix"], "temps_prep": v["temps"]} for k, v in CARTE.items()]}

@app.get("/admin")
def admin_page():
    return FileResponse("admin.html")

# ──────────────────────────────────────────────
# ROUTES STRIPE
# ──────────────────────────────────────────────

@app.post("/stripe/client")
async def nouveau_client_stripe(request: Request):
    try:
        from abonnements import creer_client_nova
        data = await request.json()
        nom      = data.get("nom", "")
        email    = data.get("email", "")
        tel      = data.get("telephone", "")
        pizzeria = data.get("pizzeria", "")
        if not nom or not email:
            return JSONResponse({"statut": "erreur", "message": "Nom et email requis"}, status_code=400)
        client = creer_client_nova(nom, email, tel, pizzeria)
        if not client:
            return JSONResponse({"statut": "erreur", "message": "Erreur creation client"}, status_code=500)
        return JSONResponse({
            "statut": "ok",
            "message": "Client cree - lien de paiement genere",
            "lien_paiement": client.get("lien_paiement", ""),
            "stripe_customer_id": client.get("stripe_customer_id", "")
        })
    except Exception as e:
        return JSONResponse({"statut": "erreur", "message": str(e)}, status_code=500)


@app.post("/stripe/webhook")
async def stripe_webhook(request: Request):
    try:
        from abonnements import activer_client, desactiver_client, send_whatsapp_notification
        from stripe_handler import verifier_webhook
        payload   = await request.body()
        signature = request.headers.get("stripe-signature", "")
        event     = verifier_webhook(payload, signature)
        if not event:
            return JSONResponse({"statut": "erreur", "message": "Signature invalide"}, status_code=400)

        event_type = event.get("type", "")
        data_obj   = event.get("data", {}).get("object", {})
        print("Webhook Stripe : " + event_type)

        if event_type == "customer.subscription.created":
            customer_id     = data_obj.get("customer", "")
            subscription_id = data_obj.get("id", "")
            activer_client(customer_id, subscription_id)
            # Reactiver Nova
            global _cache_statut
            _cache_statut = {"actif": True, "last_check": None}
            print("Nova reactivee via webhook Stripe")

        elif event_type == "customer.subscription.deleted":
            customer_id = data_obj.get("customer", "")
            desactiver_client(customer_id)
            # Desactiver Nova
            _cache_statut = {"actif": False, "last_check": None}
            print("Nova desactivee via webhook Stripe")

        elif event_type == "invoice.payment_succeeded":
            customer_id = data_obj.get("customer", "")
            # Paiement recu - reactiver si besoin
            _cache_statut = {"actif": True, "last_check": None}
            print("Paiement recu - Nova reactivee : " + customer_id)

        elif event_type == "invoice.payment_failed":
            customer_id = data_obj.get("customer", "")
            print("Paiement echoue pour : " + customer_id)

        return JSONResponse({"statut": "ok"})
    except Exception as e:
        print("Erreur webhook : " + str(e))
        return JSONResponse({"statut": "erreur", "message": str(e)}, status_code=500)


@app.get("/paiement/succes")
async def paiement_succes(request: Request):
    session_id = request.query_params.get("session_id", "")
    html = """<!DOCTYPE html>
<html lang="fr">
<head><meta charset="UTF-8"><title>Paiement confirme - Nova.AI</title>
<style>
body{font-family:system-ui,sans-serif;background:#F8F9FC;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0}
.box{background:white;border-radius:16px;padding:48px;text-align:center;max-width:440px;box-shadow:0 4px 24px rgba(0,0,0,.08)}
.icon{font-size:64px;margin-bottom:16px}
h1{font-size:24px;color:#0D1524;margin-bottom:8px}
p{color:#5A677E;font-size:15px;line-height:1.6;margin-bottom:24px}
.btn{display:inline-block;background:#1A6EF5;color:white;padding:12px 28px;border-radius:10px;text-decoration:none;font-weight:600}
</style></head>
<body>
<div class="box">
<div class="icon">🎉</div>
<h1>Paiement confirme !</h1>
<p>Votre abonnement Nova.AI est actif. Vous allez recevoir les instructions de configuration par email dans quelques minutes.</p>
<a href="https://web-production-967e41.up.railway.app" class="btn">Retour au site</a>
</div>
</body></html>"""
    return HTMLResponse(content=html)


@app.get("/paiement/annule")
def paiement_annule():
    html = """<!DOCTYPE html>
<html lang="fr">
<head><meta charset="UTF-8"><title>Paiement annule - Nova.AI</title>
<style>
body{font-family:system-ui,sans-serif;background:#F8F9FC;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0}
.box{background:white;border-radius:16px;padding:48px;text-align:center;max-width:440px;box-shadow:0 4px 24px rgba(0,0,0,.08)}
.icon{font-size:64px;margin-bottom:16px}
h1{font-size:24px;color:#0D1524;margin-bottom:8px}
p{color:#5A677E;font-size:15px;line-height:1.6;margin-bottom:24px}
.btn{display:inline-block;background:#1A6EF5;color:white;padding:12px 28px;border-radius:10px;text-decoration:none;font-weight:600}
</style></head>
<body>
<div class="box">
<div class="icon">😕</div>
<h1>Paiement annule</h1>
<p>Votre paiement a ete annule. Aucun montant n a ete debite. Revenez quand vous voulez !</p>
<a href="https://web-production-967e41.up.railway.app" class="btn">Retour au site</a>
</div>
</body></html>"""
    return HTMLResponse(content=html)


# ──────────────────────────────────────────────
# ROUTES NOTIFICATIONS
# ──────────────────────────────────────────────

# ──────────────────────────────────────────────
# ROUTES MINUTES ET FACTURATION
# ──────────────────────────────────────────────

@app.get("/minutes/{pizzeria_id}")
async def voir_minutes(pizzeria_id: int):
    try:
        from minutes_tracker import get_minutes_mois
        usage = get_minutes_mois(pizzeria_id)
        return JSONResponse(usage)
    except Exception as e:
        return JSONResponse({"statut": "erreur", "message": str(e)}, status_code=500)

@app.post("/facturation/run")
async def run_facturation(request: Request):
    try:
        from minutes_tracker import run_facturation_mensuelle
        result = run_facturation_mensuelle()
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"statut": "erreur", "message": str(e)}, status_code=500)

@app.post("/facturation/{pizzeria_id}")
async def facturer_pizzeria(pizzeria_id: int, request: Request):
    try:
        from minutes_tracker import facturer_depassement
        from pizzeria_config import get_pizzeria_by_id
        pizzeria = get_pizzeria_by_id(pizzeria_id)
        if not pizzeria:
            return JSONResponse({"statut": "erreur", "message": "Pizzeria introuvable"}, status_code=404)
        customer_id = pizzeria.get("stripe_customer_id", "")
        if not customer_id:
            return JSONResponse({"statut": "erreur", "message": "Pas de stripe_customer_id"}, status_code=400)
        result = facturer_depassement(pizzeria_id, customer_id)
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"statut": "erreur", "message": str(e)}, status_code=500)

@app.get("/dashboard")
async def dashboard():
    try:
        from pizzeria_config import get_toutes_pizzerias
        from minutes_tracker import get_minutes_mois
        pizzerias = get_toutes_pizzerias()
        mois = datetime.now().strftime("%Y-%m")
        total_revenu = 0
        total_benef = 0
        data_pizzerias = []
        for p in pizzerias:
            usage = get_minutes_mois(p["id"])
            abonnement = 59.0
            depassement = usage.get("montant_depassement", 0)
            revenu = abonnement + depassement
            cout_min = usage.get("minutes_utilisees", 0) * 0.021
            cout_total = cout_min + 1 + (revenu * 0.029) + 0.30
            benef = round(revenu - cout_total, 2)
            total_revenu += revenu
            total_benef += benef
            data_pizzerias.append({
                "nom": p["nom"],
                "actif": p["actif"],
                "minutes": usage.get("minutes_utilisees", 0),
                "revenu_mois": round(revenu, 2),
                "benefice_mois": benef
            })
        return JSONResponse({
            "mois": mois,
            "nb_pizzerias_actives": len([p for p in pizzerias if p["actif"]]),
            "revenu_total": round(total_revenu, 2),
            "benefice_total": round(total_benef, 2),
            "pizzerias": data_pizzerias
        })
    except Exception as e:
        return JSONResponse({"statut": "erreur", "message": str(e)}, status_code=500)

@app.post("/notifications/run")
async def run_notifications(request: Request):
    try:
        from notifications import run_notifications_j1
        result = run_notifications_j1()
        return JSONResponse({"statut": "ok", "result": result})
    except Exception as e:
        return JSONResponse({"statut": "erreur", "message": str(e)}, status_code=500)

@app.get("/nova/statut")
def statut_nova():
    actif = nova_est_active()
    return JSONResponse({
        "nova_active": actif,
        "message": "Nova est active" if actif else "Nova est desactivee - abonnement expire"
    })

@app.post("/nova/activer")
async def activer_nova(request: Request):
    global _cache_statut
    _cache_statut = {"actif": True, "last_check": None}
    return JSONResponse({"statut": "ok", "message": "Nova reactivee"})

@app.post("/nova/desactiver")
async def desactiver_nova(request: Request):
    global _cache_statut
    _cache_statut = {"actif": False, "last_check": None}
    return JSONResponse({"statut": "ok", "message": "Nova desactivee"})

@app.get("/clients")
async def voir_clients(request: Request):
    try:
        from abonnements import get_clients_actifs
        from pizzeria_config import get_toutes_pizzerias
        clients = get_clients_actifs()
        pizzerias = get_toutes_pizzerias()
        abonnements = []
        try:
            from stripe_handler import lister_abonnements_actifs
            abonnements = lister_abonnements_actifs()
        except:
            pass
        return JSONResponse({
            "clients_nova": clients,
            "pizzerias": pizzerias,
            "nb_clients": len(clients),
            "nb_pizzerias": len(pizzerias),
            "abonnements_stripe": len(abonnements)
        })
    except Exception as e:
        return JSONResponse({"statut": "erreur", "message": str(e)}, status_code=500)

# ──────────────────────────────────────────────
# ROUTES MULTI-CLIENT
# ──────────────────────────────────────────────

@app.post("/pizzeria/ajouter")
async def ajouter_pizzeria(request: Request):
    try:
        from pizzeria_config import creer_pizzeria, ajouter_pizza_menu
        data = await request.json()
        nom      = data.get("nom", "")
        email    = data.get("email", "")
        tel      = data.get("telephone_proprietaire", "")
        numero   = data.get("numero_twilio", "")
        ville    = data.get("ville", "")
        if not nom or not email or not numero:
            return JSONResponse({"statut": "erreur", "message": "nom, email et numero_twilio requis"}, status_code=400)
        pizzeria = creer_pizzeria({
            "nom": nom, "email": email,
            "telephone_proprietaire": tel,
            "numero_twilio": numero,
            "ville": ville,
            "heure_ouverture": data.get("heure_ouverture", "18h15"),
            "heure_fermeture": data.get("heure_fermeture", "22h00"),
            "jours_fermeture": data.get("jours_fermeture", "dimanche"),
            "max_pizzas_creneau": data.get("max_pizzas_creneau", 2),
            "actif": True,
            "statut_abonnement": "actif"
        })
        if not pizzeria:
            return JSONResponse({"statut": "erreur", "message": "Erreur creation pizzeria"}, status_code=500)
        # Ajouter menu par defaut si fourni
        menu = data.get("menu", [])
        for item in menu:
            ajouter_pizza_menu(pizzeria["id"], item["nom"], item["prix"], item.get("temps_prep", 13))
        return JSONResponse({"statut": "ok", "pizzeria": pizzeria, "message": nom + " ajoutee avec succes !"})
    except Exception as e:
        return JSONResponse({"statut": "erreur", "message": str(e)}, status_code=500)

@app.get("/pizzeria/{pizzeria_id}")
async def voir_pizzeria(pizzeria_id: int):
    try:
        from pizzeria_config import get_menu, get_commandes_du_jour_v2
        import httpx as _httpx
        _url = os.environ.get("SUPABASE_URL", "")
        _key = os.environ.get("SUPABASE_KEY", "")
        _headers = {
            "apikey": _key,
            "Authorization": "Bearer " + _key,
            "Content-Type": "application/json"
        }
        r = _httpx.get(
            _url + "/rest/v1/pizzerias?id=eq." + str(pizzeria_id),
            headers=_headers,
            timeout=10
        )
        if r.status_code != 200 or not r.json():
            return JSONResponse({"statut": "erreur", "message": "Pizzeria introuvable"}, status_code=404)
        pizzeria = r.json()[0]
        menu      = get_menu(pizzeria_id)
        commandes = get_commandes_du_jour_v2(pizzeria_id)
        actives   = [c for c in commandes if not c.get("annulee")]
        return JSONResponse({
            "pizzeria": pizzeria,
            "menu": menu,
            "commandes_aujourd_hui": actives,
            "nb_commandes": len(actives)
        })
    except Exception as e:
        return JSONResponse({"statut": "erreur", "message": str(e)}, status_code=500)

@app.patch("/pizzeria/{pizzeria_id}")
async def modifier_pizzeria_route(pizzeria_id: int, request: Request):
    try:
        from pizzeria_config import modifier_pizzeria
        data = await request.json()
        ok = modifier_pizzeria(pizzeria_id, data)
        return JSONResponse({"statut": "ok" if ok else "erreur"})
    except Exception as e:
        return JSONResponse({"statut": "erreur", "message": str(e)}, status_code=500)

@app.post("/pizzeria/{pizzeria_id}/activer")
async def activer_pizzeria_route(pizzeria_id: int):
    try:
        from pizzeria_config import activer_pizzeria
        ok = activer_pizzeria(pizzeria_id)
        return JSONResponse({"statut": "ok" if ok else "erreur", "message": "Pizzeria activee"})
    except Exception as e:
        return JSONResponse({"statut": "erreur", "message": str(e)}, status_code=500)

@app.post("/pizzeria/{pizzeria_id}/desactiver")
async def desactiver_pizzeria_route(pizzeria_id: int):
    try:
        from pizzeria_config import desactiver_pizzeria
        ok = desactiver_pizzeria(pizzeria_id)
        return JSONResponse({"statut": "ok" if ok else "erreur", "message": "Pizzeria desactivee"})
    except Exception as e:
        return JSONResponse({"statut": "erreur", "message": str(e)}, status_code=500)

@app.post("/pizzeria/{pizzeria_id}/menu")
async def ajouter_pizza_route(pizzeria_id: int, request: Request):
    try:
        from pizzeria_config import ajouter_pizza_menu, vider_cache_menu
        data = await request.json()
        nom       = data.get("nom", "")
        prix      = float(data.get("prix", 12.0))
        temps     = int(data.get("temps_prep", 13))
        if not nom:
            return JSONResponse({"statut": "erreur", "message": "Nom requis"}, status_code=400)
        pizza = ajouter_pizza_menu(pizzeria_id, nom, prix, temps)
        vider_cache_menu(pizzeria_id)
        return JSONResponse({"statut": "ok", "pizza": pizza})
    except Exception as e:
        return JSONResponse({"statut": "erreur", "message": str(e)}, status_code=500)

@app.patch("/pizzeria/{pizzeria_id}/menu/{nom_pizza}")
async def modifier_dispo_pizza(pizzeria_id: int, nom_pizza: str, request: Request):
    try:
        from pizzeria_config import marquer_pizza_indisponible, vider_cache_menu
        data      = await request.json()
        disponible = data.get("disponible", True)
        ok = marquer_pizza_indisponible(pizzeria_id, nom_pizza, disponible)
        vider_cache_menu(pizzeria_id)
        return JSONResponse({"statut": "ok" if ok else "erreur"})
    except Exception as e:
        return JSONResponse({"statut": "erreur", "message": str(e)}, status_code=500)
