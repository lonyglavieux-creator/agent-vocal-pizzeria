import os
import json
import asyncpg
import asyncio
from datetime import datetime

DATABASE_URL = os.environ.get("DATABASE_URL", "").replace("postgresql://", "postgres://")

def supabase_ok() -> bool:
    return bool(DATABASE_URL)

def run_sync(coro):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, coro)
                return future.result()
        return loop.run_until_complete(coro)
    except Exception:
        return asyncio.run(coro)

async def _query(sql, *args):
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        result = await conn.fetch(sql, *args)
        return [dict(r) for r in result]
    finally:
        await conn.close()

async def _execute(sql, *args):
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        result = await conn.fetchrow(sql, *args) if "RETURNING" in sql else await conn.execute(sql, *args)
        return dict(result) if result and hasattr(result, 'keys') else result
    finally:
        await conn.close()

def fix_dates(d: dict) -> dict:
    for k, v in d.items():
        if hasattr(v, 'isoformat'):
            d[k] = str(v)
    return d

# ──────────────────────────────────────────────
# COMMANDES
# ──────────────────────────────────────────────

def sauvegarder_commande(commande: dict):
    if not supabase_ok():
        return None
    try:
        async def _do():
            conn = await asyncpg.connect(DATABASE_URL)
            try:
                row = await conn.fetchrow("""
                    INSERT INTO commandes (prenom, telephone, pizza, nb, heure, lancement, extras, total, annulee, source)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10) RETURNING id
                """,
                    commande.get("prenom","?"), commande.get("telephone",""),
                    commande.get("pizza","?"), commande.get("nb",1),
                    commande.get("heure",""), commande.get("lancement",""),
                    commande.get("extras",""), float(commande.get("total",0)),
                    False, commande.get("source","vocal")
                )
                return row["id"] if row else None
            finally:
                await conn.close()
        cid = asyncio.run(_do())
        result = dict(commande)
        result["id"] = cid
        print("Commande sauvegardee DB ID : " + str(cid))
        return result
    except Exception as e:
        print("Erreur sauvegarder_commande : " + str(e))
        return None

def annuler_commande_db(commande_id: int, raison: str) -> bool:
    if not supabase_ok():
        return False
    try:
        async def _do():
            conn = await asyncpg.connect(DATABASE_URL)
            try:
                await conn.execute("""
                    UPDATE commandes SET annulee=true, annulee_at=$1, raison_annulation=$2 WHERE id=$3
                """, datetime.now(), raison, commande_id)
            finally:
                await conn.close()
        asyncio.run(_do())
        return True
    except Exception as e:
        print("Erreur annuler_commande_db : " + str(e))
        return False

def charger_commandes_du_jour() -> list:
    if not supabase_ok():
        return []
    try:
        async def _do():
            conn = await asyncpg.connect(DATABASE_URL)
            try:
                today = datetime.now().strftime("%Y-%m-%d")
                rows = await conn.fetch("""
                    SELECT * FROM commandes WHERE created_at >= $1 ORDER BY created_at ASC
                """, today + " 00:00:00")
                return [fix_dates(dict(r)) for r in rows]
            finally:
                await conn.close()
        return asyncio.run(_do())
    except Exception as e:
        print("Erreur charger_commandes_du_jour : " + str(e))
        return []

def get_commande_by_id(commande_id: int):
    if not supabase_ok():
        return None
    try:
        async def _do():
            conn = await asyncpg.connect(DATABASE_URL)
            try:
                row = await conn.fetchrow("SELECT * FROM commandes WHERE id=$1", commande_id)
                return fix_dates(dict(row)) if row else None
            finally:
                await conn.close()
        return asyncio.run(_do())
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
        async def _do():
            conn = await asyncpg.connect(DATABASE_URL)
            try:
                row = await conn.fetchrow("SELECT valeur FROM config WHERE cle=$1", cle)
                return row["valeur"] if row else defaut
            finally:
                await conn.close()
        return asyncio.run(_do())
    except Exception as e:
        print("Erreur get_config : " + str(e))
        return defaut

def set_config(cle: str, valeur: str) -> bool:
    if not supabase_ok():
        return False
    try:
        async def _do():
            conn = await asyncpg.connect(DATABASE_URL)
            try:
                await conn.execute("""
                    INSERT INTO config (cle, valeur) VALUES ($1,$2)
                    ON CONFLICT (cle) DO UPDATE SET valeur=EXCLUDED.valeur
                """, cle, valeur)
            finally:
                await conn.close()
        asyncio.run(_do())
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
