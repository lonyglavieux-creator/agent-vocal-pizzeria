import os
import json
import httpx
from datetime import datetime

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

def get_headers():
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": "Bearer " + SUPABASE_KEY,
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }

def supabase_ok() -> bool:
    return bool(SUPABASE_URL and SUPABASE_KEY)

def sauvegarder_commande(commande: dict):
    if not supabase_ok():
        return None
    try:
        payload = {
            "prenom": commande.get("prenom", "?"),
            "telephone": commande.get("telephone", ""),
            "pizza": commande.get("pizza", "?"),
            "nb": commande.get("nb", 1),
            "heure": commande.get("heure", ""),
            "lancement": commande.get("lancement", ""),
            "extras": commande.get("extras", ""),
            "total": commande.get("total", 0),
            "annulee": False,
            "source": commande.get("source", "vocal")
        }
        r = httpx.post(
            SUPABASE_URL + "/rest/v1/commandes",
            headers=get_headers(),
            json=payload,
            timeout=10
        )
        if r.status_code in [200, 201]:
            data = r.json()
            print("Supabase OK - commande ID : " + str(data[0].get("id")))
            return data[0]
        else:
            print("Erreur Supabase : " + str(r.status_code))
            return None
    except Exception as e:
        print("Erreur sauvegarder_commande : " + str(e))
        return None

def annuler_commande_db(commande_id: int, raison: str) -> bool:
    if not supabase_ok():
        return False
    try:
        payload = {
            "annulee": True,
            "annulee_at": datetime.now().isoformat(),
            "raison_annulation": raison
        }
        r = httpx.patch(
            SUPABASE_URL + "/rest/v1/commandes?id=eq." + str(commande_id),
            headers=get_headers(),
            json=payload,
            timeout=10
        )
        return r.status_code in [200, 204]
    except Exception as e:
        print("Erreur annuler_commande_db : " + str(e))
        return False

def charger_commandes_du_jour() -> list:
    if not supabase_ok():
        return []
    try:
        aujourd_hui = datetime.now().strftime("%Y-%m-%d")
        r = httpx.get(
            SUPABASE_URL + "/rest/v1/commandes?created_at=gte." + aujourd_hui + "T00:00:00&order=created_at.asc",
            headers=get_headers(),
            timeout=10
        )
        if r.status_code == 200:
            return r.json()
        return []
    except Exception as e:
        print("Erreur charger_commandes_du_jour : " + str(e))
        return []

def get_config(cle: str, defaut: str = "") -> str:
    if not supabase_ok():
        return defaut
    try:
        r = httpx.get(
            SUPABASE_URL + "/rest/v1/config?cle=eq." + cle,
            headers=get_headers(),
            timeout=10
        )
        if r.status_code == 200:
            data = r.json()
            return data[0]["valeur"] if data else defaut
        return defaut
    except Exception as e:
        print("Erreur get_config : " + str(e))
        return defaut

def set_config(cle: str, valeur: str) -> bool:
    if not supabase_ok():
        return False
    try:
        r = httpx.patch(
            SUPABASE_URL + "/rest/v1/config?cle=eq." + cle,
            headers=get_headers(),
            json={"valeur": valeur},
            timeout=10
        )
        if r.status_code in [200, 204]:
            return True
        r2 = httpx.post(
            SUPABASE_URL + "/rest/v1/config",
            headers=get_headers(),
            json={"cle": cle, "valeur": valeur},
            timeout=10
        )
        return r2.status_code in [200, 201]
    except Exception as e:
        print("Erreur set_config : " + str(e))
        return False

def get_fours_actifs() -> int:
    try:
        return int(get_config("fours_actifs", "1"))
    except:
        return 1

def set_fours_actifs(nb: int) -> bool:
    return set_config("fours_actifs", str(nb))

def get_indisponibles() -> dict:
    try:
        return json.loads(get_config("indisponibles", "{}"))
    except:
        return {}

def set_indisponibles(indispo: dict) -> bool:
    return set_config("indisponibles", json.dumps(indispo))

def log_appel(call_sid: str, prenom: str = "", duree_min: float = 0, commande_id: int = None):
    if not supabase_ok():
        return
    try:
        httpx.post(
            SUPABASE_URL + "/rest/v1/logs_appels",
            headers=get_headers(),
            json={"call_sid": call_sid, "prenom": prenom, "duree_min": duree_min, "commande_id": commande_id},
            timeout=5
        )
    except Exception as e:
        print("Erreur log_appel : " + str(e))

def get_commande_by_id(commande_id: int):
    if not supabase_ok():
        return None
    try:
        r = httpx.get(
            SUPABASE_URL + "/rest/v1/commandes?id=eq." + str(commande_id),
            headers=get_headers(),
            timeout=10
        )
        if r.status_code == 200:
            data = r.json()
            return data[0] if data else None
        return None
    except Exception as e:
        print("Erreur get_commande_by_id : " + str(e))
        return None
