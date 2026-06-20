Importer os
Importer json
Importer httpx
à partir de datetime datetime d'importation

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

def get_headers():
    retour {
        "apikey": SUPABASE_KEY,
        "Autorisation": "Porteur" + SUPABASE_KEY,
        "Type de contenu": "application/json",
        "Préférer": "retour = représentation"
    }

def supabase_ok() -> bool:
    retour bool(SUPABASE_URL et SUPABASE_KEY)

# ────────────────────────────────────────────────────────────────────────────────�──────�───────
# COMMANDES
# ────────────────────────────────────────────────────────────────────────────────�──────�───────

def protected_commande(commande: dict) -> dict | Aucun:
    sinon supabase_ok():
        print("Supabase non configure - commande non sauvegarde")
        Retour Aucun
    Essayez:
        charge utile = {
            "prenom": command.get("prenom", "?"),
            "téléphone": command.get("téléphone", ""),
            "pizza": command.get("pizza", "?"),
            "nb": command.get("nb", 1),
            "heure": command.get("heure", ""),
            "lancement": command.get("lancement", ""),
            "extras": command.get("extras", ""),
            "total": command.get("total", 0),
            "annulé": faux,
            "source": command.get("source", "vocal")
        }
        r = httpx.post(
            SUPABASE_URL + "/rest/v1/commandes",
            headers=get_headers(),
            json=payload,
            temps mort = 10
        )
        si r.status_code in [200, 201]:
            données = r.json()
            print("Commande sauvegarde Supabase ID: " + str(data[0].get("id")))
            Données de retour[0]
        autre:
            print("Erreur Supabase save : " + str(r.status_code) + " " + r.text)
            Retour Aucun
    sauf Exception comme e:
        print("Erreur Supabase : " + str(e))
        Retour Aucun


def_commande_db(commande_id: int, raison: str) -> bol:
    sinon supabase_ok():
        Retour Faux
    Essayez:
        charge utile = {
            "annulés": Vrai,
            "annulee_at": datetime.now().isoformat(),
            "raison_annulation": raison
        }
        r = httpx.patch(
            SUPABASE_URL + "/rest/v1/commandes? id=eq." + str(commande_id),
            headers=get_headers(),
            json=payload,
            temps mort = 10
        )
        retour r.status_code in [200, 204]
    sauf Exception comme e:
        print("Erreur annulation Supabase: " + str(e))
        Retour Faux


def charger_commandes_du_jour() -> liste:
    sinon supabase_ok():
        retour []
    Essayez:
        aujourd_hui = datetime.now().strftime("%Y-%m-%d")
        r = httpx.get(
            SUPABASE_URL + "/rest/v1/commandes? created_at=gte." + aujourd'hui_hui + "T00:00:00&order=created_at.asc",
            headers=get_headers(),
            temps mort = 10
        )
        si r.status_code == 200:
            commandes = r.json()
            print("Commandes charges Subase: " + str(len(commandes)))
            commandes de retour
        retour []
    sauf Exception comme e:
        print("Erreur Chargement Supabase: " + str(e))
        retour []


def get_commande_by_id(commande_id: int) -> dict | Aucun:
    sinon supabase_ok():
        Retour Aucun
    Essayez:
        r = httpx.get(
            SUPABASE_URL + "/rest/v1/commandes? id=eq." + str(commande_id),
            headers=get_headers(),
            temps mort = 10
        )
        si r.status_code == 200:
            données = r.json()
            retourner des données[0] si les données autres Aucune
        Retour Aucun
    sauf Exception comme e:
        print("Erreur get commande : " + str(e))
        Retour Aucun


# ────────────────────────────────────────────────────────────────────────────────�──────�───────
# CONFIG (quatre + in available)
# ────────────────────────────────────────────────────────────────────────────────�──────�───────

def get_config(cle: str, defaut: str = "") -> str:
    sinon supabase_ok():
        Retour de défaut
    Essayez:
        r = httpx.get(
            SUPABASE_URL + "/rest/v1/config? cle=eq." + cle,
            headers=get_headers(),
            temps mort = 10
        )
        si r.status_code == 200:
            données = r.json()
            retour de données[0]["valeur"] si les données autrement déchéance
        Retour de défaut
    sauf Exception comme e:
        print("Erreur get config : " + str(e))
        Retour de défaut


def set_config(cle: str, valeur: str) -> bool:
    sinon supabase_ok():
        Retour Faux
    Essayez:
        r = httpx.patch(
            SUPABASE_URL + "/rest/v1/config? cle=eq." + cle,
            headers=get_headers(),
            json={"valeur": valeur},
            temps mort = 10
        )
        si r.status_code in [200, 204]:
            Retour True
        # Si la cle n existe pas encore, sur l insere
        r2 = httpx.post(
            SUPABASE_URL + "/rest/v1/config",
            headers=get_headers(),
            json={"cle": cle, "valeur": valeur},
            temps mort = 10
        )
        retourner r2.status_code dans [200, 201]
    sauf Exception comme e:
        print("Erreur set config: " + str(e))
        Retour Faux


def get_fours_actifs() -> int:
    val = get_config("fours_actifs", "1")
    Essayez:
        Retour int(val)
    sauf:
        Retour 1


def set_fours_actifs(nb: int) -> bool:
    retour set_config("fours_actifs", str(nb))


def get_indisponibles() -> dict:
    val = get_config("invalites", "{}")
    Essayez:
        retour json.loads(val)
    sauf:
        retour {}


def set_indisponibles(indispo: dict) -> bool:
    retour set_config("indisponibles", json.dumps(indispo))


# ────────────────────────────────────────────────────────────────────────────────�──────�───────
# JOURNAUX APPELS
# ────────────────────────────────────────────────────────────────────────────────�──────�───────

def log_appel(call_sid: str, prenom: str = "", dure_min: float = 0, command_id: int = Aucun):
    sinon supabase_ok():
        retour
    Essayez:
        charge utile = {
            "call_sid": call_sid,
            "prenom": prenom,
            "duree_min": duree_min,
            "commande_id": command_id
        }
        httpx.post(
            SUPABASE_URL + "/rest/v1/logs_appels",
            headers=get_headers(),
            json=payload,
            timeout=5
        )
    sauf Exception comme e:
        print("Erreur log appel : " + str(e))
