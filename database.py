import os
import json
from datetime import datetime

DATABASE_URL = os.environ.get("DATABASE_URL", "")

def get_conn():
    import psycopg2
    return psycopg2.connect(DATABASE_URL)

def supabase_ok() -> bool:
    return bool(DATABASE_URL)

# ──────────────────────────────────────────────
# COMMANDES
# ──────────────────────────────────────────────

def sauvegarder_commande(commande: dict):
    if not supabase_ok():
        return None
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO commandes (prenom, telephone, pizza, nb, heure, lancement, extras, total, annulee, source)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            commande.get("prenom", "?"),
            commande.get("telephone", ""),
            commande.get("pizza", "?"),
            commande.get("nb", 1),
            commande.get("heure", ""),
            commande.get("lancement", ""),
            commande.get("extras", ""),
            commande.get("total", 0),
            False,
            commande.get("source", "vocal")
        ))
        commande_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()
        print("Commande sauvegardee DB ID : " + str(commande_id))
        result = dict(commande)
        result["id"] = commande_id
        return result
    except Exception as e:
        print("Erreur sauvegarder_commande : " + str(e))
        return None

def annuler_commande_db(commande_id: int, raison: str) -> bool:
    if not supabase_ok():
        return False
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("""
            UPDATE commandes SET annulee = true, annulee_at = %s, raison_annulation = %s
            WHERE id = %s
        """, (datetime.now(), raison, commande_id))
        conn.commit()
        cur.close()
        conn.close()
        return True
    except Exception as e:
        print("Erreur annuler_commande_db : " + str(e))
        return False

def charger_commandes_du_jour() -> list:
    if not supabase_ok():
        return []
    try:
        conn = get_conn()
        cur = conn.cursor()
        aujourd_hui = datetime.now().strftime("%Y-%m-%d")
        cur.execute("""
            SELECT id, prenom, telephone, pizza, nb, heure, lancement, extras, total,
                   annulee, annulee_at, raison_annulation, source, created_at
            FROM commandes
            WHERE created_at >= %s
            ORDER BY created_at ASC
        """, (aujourd_hui + " 00:00:00",))
        rows = cur.fetchall()
        cols = ["id","prenom","telephone","pizza","nb","heure","lancement","extras","total",
                "annulee","annulee_at","raison_annulation","source","created_at"]
        result = []
        for row in rows:
            d = dict(zip(cols, row))
            if d.get("created_at"):
                d["created_at"] = str(d["created_at"])
            if d.get("annulee_at"):
                d["annulee_at"] = str(d["annulee_at"])
            result.append(d)
        cur.close()
        conn.close()
        print("Commandes chargees depuis DB : " + str(len(result)))
        return result
    except Exception as e:
        print("Erreur charger_commandes_du_jour : " + str(e))
        return []

def get_commande_by_id(commande_id: int):
    if not supabase_ok():
        return None
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT * FROM commandes WHERE id = %s", (commande_id,))
        row = cur.fetchone()
        if not row:
            return None
        cols = [desc[0] for desc in cur.description]
        cur.close()
        conn.close()
        return dict(zip(cols, row))
    except Exception as e:
        print("Erreur get_commande_by_id : " + str(e))
        return None

# ──────────────────────────────────────────────
# CONFIG
# ──────────────────────────────────────────────

def get_config(cle: str, defaut: str = "") -> str:
    if not supabase_ok():
        return defaut
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT valeur FROM config WHERE cle = %s", (cle,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        return row[0] if row else defaut
    except Exception as e:
        print("Erreur get_config : " + str(e))
        return defaut

def set_config(cle: str, valeur: str) -> bool:
    if not supabase_ok():
        return False
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO config (cle, valeur) VALUES (%s, %s)
            ON CONFLICT (cle) DO UPDATE SET valeur = EXCLUDED.valeur
        """, (cle, valeur))
        conn.commit()
        cur.close()
        conn.close()
        return True
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
    pass
