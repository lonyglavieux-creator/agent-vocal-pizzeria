import os
import json
import asyncpg
import asyncio
from datetime import datetime

DATABASE_URL = os.environ.get("DATABASE_URL", "").replace("postgresql://", "postgres://")

def fix_dates(d: dict) -> dict:
    for k, v in d.items():
        if hasattr(v, 'isoformat'):
            d[k] = str(v)
    return d

async def _get_conn():
    return await asyncpg.connect(DATABASE_URL)

# ──────────────────────────────────────────────
# PIZZERIAS
# ──────────────────────────────────────────────

def get_pizzeria_by_numero(numero_twilio: str):
    try:
        async def _do():
            conn = await _get_conn()
            try:
                row = await conn.fetchrow(
                    "SELECT * FROM pizzerias WHERE numero_twilio=$1 AND actif=true",
                    numero_twilio.strip()
                )
                return fix_dates(dict(row)) if row else None
            finally:
                await conn.close()
        return asyncio.run(_do())
    except Exception as e:
        print("Erreur get_pizzeria_by_numero : " + str(e))
        return None

def get_pizzeria_by_id(pizzeria_id: int):
    try:
        async def _do():
            conn = await _get_conn()
            try:
                row = await conn.fetchrow("SELECT * FROM pizzerias WHERE id=$1", pizzeria_id)
                return fix_dates(dict(row)) if row else None
            finally:
                await conn.close()
        return asyncio.run(_do())
    except Exception as e:
        print("Erreur get_pizzeria_by_id : " + str(e))
        return None

def get_toutes_pizzerias() -> list:
    try:
        async def _do():
            conn = await _get_conn()
            try:
                rows = await conn.fetch("SELECT * FROM pizzerias ORDER BY nom ASC")
                return [fix_dates(dict(r)) for r in rows]
            finally:
                await conn.close()
        return asyncio.run(_do())
    except Exception as e:
        print("Erreur get_toutes_pizzerias : " + str(e))
        return []

def creer_pizzeria(data: dict):
    try:
        async def _do():
            conn = await _get_conn()
            try:
                row = await conn.fetchrow("""
                    INSERT INTO pizzerias (nom, email, telephone_proprietaire, numero_twilio, ville,
                        heure_ouverture, heure_fermeture, jours_fermeture, max_pizzas_creneau, actif, statut_abonnement)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11) RETURNING *
                """,
                    data.get("nom"), data.get("email"), data.get("telephone_proprietaire"),
                    data.get("numero_twilio"), data.get("ville",""),
                    data.get("heure_ouverture","18h15"), data.get("heure_fermeture","22h00"),
                    data.get("jours_fermeture","dimanche"), data.get("max_pizzas_creneau",2),
                    data.get("actif",True), data.get("statut_abonnement","actif")
                )
                return fix_dates(dict(row)) if row else None
            finally:
                await conn.close()
        return asyncio.run(_do())
    except Exception as e:
        print("Erreur creer_pizzeria : " + str(e))
        return None

def modifier_pizzeria(pizzeria_id: int, data: dict) -> bool:
    try:
        async def _do():
            conn = await _get_conn()
            try:
                keys = list(data.keys())
                vals = list(data.values())
                sets = ", ".join([k + "=$" + str(i+1) for i, k in enumerate(keys)])
                vals.append(datetime.now())
                vals.append(pizzeria_id)
                await conn.execute(
                    "UPDATE pizzerias SET " + sets + ", updated_at=$" + str(len(keys)+1) + " WHERE id=$" + str(len(keys)+2),
                    *vals
                )
            finally:
                await conn.close()
        asyncio.run(_do())
        return True
    except Exception as e:
        print("Erreur modifier_pizzeria : " + str(e))
        return False

def activer_pizzeria(pizzeria_id: int) -> bool:
    return modifier_pizzeria(pizzeria_id, {"actif": True, "statut_abonnement": "actif"})

def desactiver_pizzeria(pizzeria_id: int) -> bool:
    return modifier_pizzeria(pizzeria_id, {"actif": False, "statut_abonnement": "expire"})

# ──────────────────────────────────────────────
# MENU
# ──────────────────────────────────────────────

def get_menu(pizzeria_id: int) -> list:
    try:
        async def _do():
            conn = await _get_conn()
            try:
                rows = await conn.fetch(
                    "SELECT * FROM menus WHERE pizzeria_id=$1 AND disponible=true ORDER BY nom ASC",
                    pizzeria_id
                )
                return [fix_dates(dict(r)) for r in rows]
            finally:
                await conn.close()
        return asyncio.run(_do())
    except Exception as e:
        print("Erreur get_menu : " + str(e))
        return []

def ajouter_pizza_menu(pizzeria_id: int, nom: str, prix: float, temps_prep: int = 13):
    try:
        async def _do():
            conn = await _get_conn()
            try:
                row = await conn.fetchrow("""
                    INSERT INTO menus (pizzeria_id, nom, prix, temps_prep)
                    VALUES ($1,$2,$3,$4) RETURNING *
                """, pizzeria_id, nom, prix, temps_prep)
                return fix_dates(dict(row)) if row else None
            finally:
                await conn.close()
        return asyncio.run(_do())
    except Exception as e:
        print("Erreur ajouter_pizza_menu : " + str(e))
        return None

def marquer_pizza_indisponible(pizzeria_id: int, nom_pizza: str, disponible: bool) -> bool:
    try:
        async def _do():
            conn = await _get_conn()
            try:
                await conn.execute(
                    "UPDATE menus SET disponible=$1 WHERE pizzeria_id=$2 AND nom=$3",
                    disponible, pizzeria_id, nom_pizza
                )
            finally:
                await conn.close()
        asyncio.run(_do())
        return True
    except Exception as e:
        print("Erreur marquer_pizza_indisponible : " + str(e))
        return False

def vider_cache_menu(pizzeria_id: int):
    pass

def vider_cache_pizzeria(numero: str):
    pass

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
# COMMANDES V2
# ──────────────────────────────────────────────

def sauvegarder_commande_v2(pizzeria_id: int, commande: dict):
    try:
        async def _do():
            conn = await _get_conn()
            try:
                row = await conn.fetchrow("""
                    INSERT INTO commandes_v2 (pizzeria_id, prenom, telephone, pizza, nb, heure, lancement, extras, total, source)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10) RETURNING id
                """,
                    pizzeria_id,
                    commande.get("prenom","?"), commande.get("telephone",""),
                    commande.get("pizza","?"), commande.get("nb",1),
                    commande.get("heure",""), commande.get("lancement",""),
                    commande.get("extras",""), float(commande.get("total",0)),
                    commande.get("source","vocal")
                )
                return row["id"] if row else None
            finally:
                await conn.close()
        cid = asyncio.run(_do())
        result = dict(commande)
        result["id"] = cid
        return result
    except Exception as e:
        print("Erreur sauvegarder_commande_v2 : " + str(e))
        return None

def get_commandes_du_jour_v2(pizzeria_id: int) -> list:
    try:
        async def _do():
            conn = await _get_conn()
            try:
                today = datetime.now().strftime("%Y-%m-%d")
                rows = await conn.fetch("""
                    SELECT * FROM commandes_v2
                    WHERE pizzeria_id=$1 AND created_at >= $2
                    ORDER BY created_at ASC
                """, pizzeria_id, today + " 00:00:00")
                return [fix_dates(dict(r)) for r in rows]
            finally:
                await conn.close()
        return asyncio.run(_do())
    except Exception as e:
        print("Erreur get_commandes_du_jour_v2 : " + str(e))
        return []

def generer_prompt_pizzeria(pizzeria: dict, menu: list) -> str:
    nom = pizzeria.get("nom", "la pizzeria")
    heure_ouv = pizzeria.get("heure_ouverture", "18h15")
    heure_ferm = pizzeria.get("heure_fermeture", "22h00")
    jours_ferm = pizzeria.get("jours_fermeture", "dimanche")
    max_pizzas = pizzeria.get("max_pizzas_creneau", 2)
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
