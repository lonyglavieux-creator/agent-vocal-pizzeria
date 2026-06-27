import os
import json
import httpx
from datetime import datetime

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

# Cache des configs pizzerias (evite trop de requetes Supabase)
_cache_pizzerias = {}
_cache_menus = {}

def get_headers():
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": "Bearer " + SUPABASE_KEY,
        "Content-Type": "application/json"
    }

# ──────────────────────────────────────────────
# RECUPERER UNE PIZZERIA PAR SON NUMERO TWILIO
# ──────────────────────────────────────────────

def get_pizzeria_by_numero(numero_twilio: str) -> dict | None:
    numero = numero_twilio.strip()
    if numero in _cache_pizzerias:
        return _cache_pizzerias[numero]
    try:
        r = httpx.get(
            SUPABASE_URL + "/rest/v1/pizzerias?numero_twilio=eq." + numero + "&actif=eq.true",
            headers=get_headers(),
            timeout=5
        )
        if r.status_code == 200:
            data = r.json()
            if data:
                _cache_pizzerias[numero] = data[0]
                return data[0]
        return None
    except Exception as e:
        print("Erreur get_pizzeria_by_numero : " + str(e))
        return None

def get_pizzeria_by_id(pizzeria_id: int) -> dict | None:
    try:
        r = httpx.get(
            SUPABASE_URL + "/rest/v1/pizzerias?id=eq." + str(pizzeria_id),
            headers=get_headers(),
            timeout=5
        )
        if r.status_code == 200:
            data = r.json()
            return data[0] if data else None
        return None
    except Exception as e:
        print("Erreur get_pizzeria_by_id : " + str(e))
        return None

def get_toutes_pizzerias() -> list:
    try:
        r = httpx.get(
            SUPABASE_URL + "/rest/v1/pizzerias?order=nom.asc",
            headers=get_headers(),
            timeout=5
        )
        return r.json() if r.status_code == 200 else []
    except Exception as e:
        print("Erreur get_toutes_pizzerias : " + str(e))
        return []

# ──────────────────────────────────────────────
# MENU D UNE PIZZERIA
# ──────────────────────────────────────────────

def get_menu(pizzeria_id: int) -> list:
    cache_key = str(pizzeria_id)
    if cache_key in _cache_menus:
        return _cache_menus[cache_key]
    try:
        r = httpx.get(
            SUPABASE_URL + "/rest/v1/menus?pizzeria_id=eq." + str(pizzeria_id) + "&disponible=eq.true&order=nom.asc",
            headers=get_headers(),
            timeout=5
        )
        if r.status_code == 200:
            menu = r.json()
            _cache_menus[cache_key] = menu
            return menu
        return []
    except Exception as e:
        print("Erreur get_menu : " + str(e))
        return []

def vider_cache_menu(pizzeria_id: int):
    cache_key = str(pizzeria_id)
    if cache_key in _cache_menus:
        del _cache_menus[cache_key]

def vider_cache_pizzeria(numero_twilio: str):
    if numero_twilio in _cache_pizzerias:
        del _cache_pizzerias[numero_twilio]

def get_prix_pizza(menu: list, nom_pizza: str) -> float:
    nom_lower = nom_pizza.lower()
    for item in menu:
        if item["nom"].lower() in nom_lower or nom_lower in item["nom"].lower():
            return float(item["prix"])
    return 12.0

def get_temps_pizza(menu: list, nom_pizza: str) -> int:
    nom_lower = nom_pizza.lower()
    for item in menu:
        if item["nom"].lower() in nom_lower or nom_lower in item["nom"].lower():
            return int(item.get("temps_prep", 13))
    return 13

def pizza_disponible_menu(menu: list, nom_pizza: str) -> bool:
    nom_lower = nom_pizza.lower()
    for item in menu:
        if item["nom"].lower() in nom_lower or nom_lower in item["nom"].lower():
            return item.get("disponible", True)
    return True

# ──────────────────────────────────────────────
# CREER / MODIFIER UNE PIZZERIA
# ──────────────────────────────────────────────

def creer_pizzeria(data: dict) -> dict | None:
    try:
        r = httpx.post(
            SUPABASE_URL + "/rest/v1/pizzerias",
            headers={**get_headers(), "Prefer": "return=representation"},
            json=data,
            timeout=10
        )
        if r.status_code in [200, 201]:
            return r.json()[0]
        print("Erreur creer_pizzeria : " + r.text)
        return None
    except Exception as e:
        print("Erreur creer_pizzeria : " + str(e))
        return None

def modifier_pizzeria(pizzeria_id: int, data: dict) -> bool:
    vider_cache_pizzeria("")
    try:
        r = httpx.patch(
            SUPABASE_URL + "/rest/v1/pizzerias?id=eq." + str(pizzeria_id),
            headers={**get_headers(), "Prefer": "return=representation"},
            json={**data, "updated_at": datetime.now().isoformat()},
            timeout=10
        )
        return r.status_code in [200, 204]
    except Exception as e:
        print("Erreur modifier_pizzeria : " + str(e))
        return False

def activer_pizzeria(pizzeria_id: int) -> bool:
    return modifier_pizzeria(pizzeria_id, {"actif": True, "statut_abonnement": "actif"})

def desactiver_pizzeria(pizzeria_id: int) -> bool:
    return modifier_pizzeria(pizzeria_id, {"actif": False, "statut_abonnement": "expire"})

def ajouter_pizza_menu(pizzeria_id: int, nom: str, prix: float, temps_prep: int = 13) -> dict | None:
    vider_cache_menu(pizzeria_id)
    try:
        r = httpx.post(
            SUPABASE_URL + "/rest/v1/menus",
            headers={**get_headers(), "Prefer": "return=representation"},
            json={"pizzeria_id": pizzeria_id, "nom": nom, "prix": prix, "temps_prep": temps_prep},
            timeout=10
        )
        if r.status_code in [200, 201]:
            return r.json()[0]
        return None
    except Exception as e:
        print("Erreur ajouter_pizza_menu : " + str(e))
        return None

def marquer_pizza_indisponible(pizzeria_id: int, nom_pizza: str, disponible: bool) -> bool:
    vider_cache_menu(pizzeria_id)
    try:
        r = httpx.patch(
            SUPABASE_URL + "/rest/v1/menus?pizzeria_id=eq." + str(pizzeria_id) + "&nom=eq." + nom_pizza,
            headers=get_headers(),
            json={"disponible": disponible},
            timeout=10
        )
        return r.status_code in [200, 204]
    except Exception as e:
        print("Erreur marquer_pizza_indisponible : " + str(e))
        return False

# ──────────────────────────────────────────────
# COMMANDES PAR PIZZERIA
# ──────────────────────────────────────────────

def sauvegarder_commande_v2(pizzeria_id: int, commande: dict) -> dict | None:
    try:
        payload = {
            "pizzeria_id": pizzeria_id,
            "prenom": commande.get("prenom", "?"),
            "telephone": commande.get("telephone", ""),
            "pizza": commande.get("pizza", "?"),
            "nb": commande.get("nb", 1),
            "heure": commande.get("heure", ""),
            "lancement": commande.get("lancement", ""),
            "extras": commande.get("extras", ""),
            "total": commande.get("total", 0),
            "source": commande.get("source", "vocal")
        }
        r = httpx.post(
            SUPABASE_URL + "/rest/v1/commandes_v2",
            headers={**get_headers(), "Prefer": "return=representation"},
            json=payload,
            timeout=10
        )
        if r.status_code in [200, 201]:
            return r.json()[0]
        return None
    except Exception as e:
        print("Erreur sauvegarder_commande_v2 : " + str(e))
        return None

def get_commandes_du_jour_v2(pizzeria_id: int) -> list:
    try:
        aujourd_hui = datetime.now().strftime("%Y-%m-%d")
        r = httpx.get(
            SUPABASE_URL + "/rest/v1/commandes_v2?pizzeria_id=eq." + str(pizzeria_id) +
            "&created_at=gte." + aujourd_hui + "T00:00:00&order=created_at.asc",
            headers=get_headers(),
            timeout=10
        )
        return r.json() if r.status_code == 200 else []
    except Exception as e:
        print("Erreur get_commandes_du_jour_v2 : " + str(e))
        return []

def generer_prompt_pizzeria(pizzeria: dict, menu: list) -> str:
    nom           = pizzeria.get("nom", "la pizzeria")
    heure_ouv     = pizzeria.get("heure_ouverture", "18h15")
    heure_ferm    = pizzeria.get("heure_fermeture", "22h00")
    jours_ferm    = pizzeria.get("jours_fermeture", "dimanche")
    max_pizzas    = pizzeria.get("max_pizzas_creneau", 2)

    carte_txt = ""
    for item in menu:
        carte_txt += item["nom"] + " : " + str(item["prix"]) + "euros | "

    return (
        "Tu es Nova, l assistante vocale de " + nom + ". "
        "Tu reponds UNIQUEMENT en francais, ton chaleureux et naturel. Maximum 2 phrases courtes.\n\n"
        "HORAIRES : Ouvert du lundi au samedi sauf " + jours_ferm + ", de " + heure_ouv + " a " + heure_ferm + ".\n"
        "FOUR : max " + str(max_pizzas) + " pizzas par 15 minutes.\n\n"
        "CARTE : " + carte_txt + "\n\n"
        "PROCESSUS : 1)Prenom 2)Pizza+quantite 3)Modifications 4)Heure retrait 5)Telephone "
        "6)Annoncer prix total 7)Confirmer commande\n\n"
        "REGLES : Jamais confirmer sans prix. Jamais avant " + heure_ouv + " ou apres " + heure_ferm + ". "
        "Toujours demander le telephone. Uniquement pour ce soir."
    )
