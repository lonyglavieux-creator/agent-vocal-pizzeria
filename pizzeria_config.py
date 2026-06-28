import os
import json
from datetime import datetime

DATABASE_URL = os.environ.get("DATABASE_URL", "")

def get_conn():
    import psycopg2
    return psycopg2.connect(DATABASE_URL)

def row_to_dict(cur, row):
    cols = [desc[0] for desc in cur.description]
    d = dict(zip(cols, row))
    for k, v in d.items():
        if hasattr(v, 'isoformat'):
            d[k] = str(v)
    return d

# ──────────────────────────────────────────────
# PIZZERIAS
# ──────────────────────────────────────────────

def get_pizzeria_by_numero(numero_twilio: str):
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT * FROM pizzerias WHERE numero_twilio = %s AND actif = true", (numero_twilio.strip(),))
        row = cur.fetchone()
        cur.close()
        conn.close()
        return row_to_dict(cur, row) if row else None
    except Exception as e:
        print("Erreur get_pizzeria_by_numero : " + str(e))
        return None

def get_pizzeria_by_id(pizzeria_id: int):
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT * FROM pizzerias WHERE id = %s", (pizzeria_id,))
        row = cur.fetchone()
        result = row_to_dict(cur, row) if row else None
        cur.close()
        conn.close()
        return result
    except Exception as e:
        print("Erreur get_pizzeria_by_id : " + str(e))
        return None

def get_toutes_pizzerias() -> list:
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT * FROM pizzerias ORDER BY nom ASC")
        rows = cur.fetchall()
        result = [row_to_dict(cur, r) for r in rows]
        cur.close()
        conn.close()
        return result
    except Exception as e:
        print("Erreur get_toutes_pizzerias : " + str(e))
        return []

def creer_pizzeria(data: dict):
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO pizzerias (nom, email, telephone_proprietaire, numero_twilio, ville,
                heure_ouverture, heure_fermeture, jours_fermeture, max_pizzas_creneau, actif, statut_abonnement)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING *
        """, (
            data.get("nom"), data.get("email"), data.get("telephone_proprietaire"),
            data.get("numero_twilio"), data.get("ville", ""),
            data.get("heure_ouverture", "18h15"), data.get("heure_fermeture", "22h00"),
            data.get("jours_fermeture", "dimanche"), data.get("max_pizzas_creneau", 2),
            data.get("actif", True), data.get("statut_abonnement", "actif")
        ))
        row = cur.fetchone()
        result = row_to_dict(cur, row)
        conn.commit()
        cur.close()
        conn.close()
        return result
    except Exception as e:
        print("Erreur creer_pizzeria : " + str(e))
        return None

def modifier_pizzeria(pizzeria_id: int, data: dict) -> bool:
    try:
        conn = get_conn()
        cur = conn.cursor()
        sets = ", ".join([k + " = %s" for k in data.keys()])
        vals = list(data.values()) + [datetime.now(), pizzeria_id]
        cur.execute("UPDATE pizzerias SET " + sets + ", updated_at = %s WHERE id = %s", vals)
        conn.commit()
        cur.close()
        conn.close()
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
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT * FROM menus WHERE pizzeria_id = %s AND disponible = true ORDER BY nom ASC", (pizzeria_id,))
        rows = cur.fetchall()
        result = [row_to_dict(cur, r) for r in rows]
        cur.close()
        conn.close()
        return result
    except Exception as e:
        print("Erreur get_menu : " + str(e))
        return []

def ajouter_pizza_menu(pizzeria_id: int, nom: str, prix: float, temps_prep: int = 13):
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO menus (pizzeria_id, nom, prix, temps_prep)
            VALUES (%s, %s, %s, %s) RETURNING *
        """, (pizzeria_id, nom, prix, temps_prep))
        row = cur.fetchone()
        result = row_to_dict(cur, row)
        conn.commit()
        cur.close()
        conn.close()
        return result
    except Exception as e:
        print("Erreur ajouter_pizza_menu : " + str(e))
        return None

def marquer_pizza_indisponible(pizzeria_id: int, nom_pizza: str, disponible: bool) -> bool:
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("UPDATE menus SET disponible = %s WHERE pizzeria_id = %s AND nom = %s",
                    (disponible, pizzeria_id, nom_pizza))
        conn.commit()
        cur.close()
        conn.close()
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
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO commandes_v2 (pizzeria_id, prenom, telephone, pizza, nb, heure, lancement, extras, total, source)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id
        """, (
            pizzeria_id,
            commande.get("prenom", "?"), commande.get("telephone", ""),
            commande.get("pizza", "?"), commande.get("nb", 1),
            commande.get("heure", ""), commande.get("lancement", ""),
            commande.get("extras", ""), commande.get("total", 0),
            commande.get("source", "vocal")
        ))
        commande_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()
        result = dict(commande)
        result["id"] = commande_id
        return result
    except Exception as e:
        print("Erreur sauvegarder_commande_v2 : " + str(e))
        return None

def get_commandes_du_jour_v2(pizzeria_id: int) -> list:
    try:
        conn = get_conn()
        cur = conn.cursor()
        aujourd_hui = datetime.now().strftime("%Y-%m-%d")
        cur.execute("""
            SELECT * FROM commandes_v2
            WHERE pizzeria_id = %s AND created_at >= %s
            ORDER BY created_at ASC
        """, (pizzeria_id, aujourd_hui + " 00:00:00"))
        rows = cur.fetchall()
        result = [row_to_dict(cur, r) for r in rows]
        cur.close()
        conn.close()
        return result
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
