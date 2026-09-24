import os
import io
import json
import time
import uuid
import base64
import unicodedata
import httpx
from groq import Groq
from twilio.twiml.voice_response import VoiceResponse, Gather
 
groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
GROQ_MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")
 
VOXTRAL_API_URL = "https://api.mistral.ai/v1/audio/speech"
MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY", "")
MISTRAL_VOICE_ID = os.environ.get("MISTRAL_VOICE_ID", "")
 
API_BASE = os.environ.get("API_BASE_URL", "https://web-production-967e41.up.railway.app")
 
SYSTEM_PROMPT = """Tu es Nova, l'assistante vocale de Bella Pizza. Tu parles au téléphone avec un client.
 
FORME DES RÉPONSES (très important, ta réponse est lue à voix haute) :
- Français correct, avec tous les accents et les apostrophes.
- Deux phrases courtes maximum.
- Aucun emoji, aucun astérisque, aucune liste, aucun symbole.
- Écris les prix en toutes lettres : « douze euros cinquante », jamais « 12.50 » ni « 12,50 € ».
- Écris les heures en toutes lettres : « dix-neuf heures trente », jamais « 19h30 ».
 
HORAIRES : ouvert du lundi au samedi, de dix-huit heures quinze à vingt-deux heures. Fermé le dimanche.
 
RÈGLES DU FOUR : un seul four, deux pizzas maximum par tranche de quinze minutes.
 
DÉROULEMENT D'UNE COMMANDE (dans l'ordre, une question à la fois) :
1. Demande le prénom.
2. Demande la ou les pizzas et la quantité.
3. Demande s'il y a des modifications.
4. Demande l'heure de retrait (ce soir uniquement, entre dix-huit heures quinze et vingt-deux heures).
5. Demande le numéro de téléphone.
6. Annonce le prix total.
7. Demande confirmation : « Parfait [prénom], [nombre] pizza [nom] pour [heure], total [prix]. Je confirme ? »
8. Si le client dit oui, réponds exactement en commençant par : « Commande confirmée. » puis remercie-le et dis au revoir.
 
CARTE ET PRIX (en euros) :
Margherita 9,50 ; Napolitaine 10,50 ; Reine ou Regina 11,50 ; Thon 11 ; Végétarienne 11 ;
Quatre fromages 12 ; Cremosa 12 ; Palerme 12 ; Primavera 12 ;
Flammenkuche 12,50 ; Chèvre miel 12,50 ; Roquefort 12,50 ; Kebab 12,50 ; Bergère 12,50 ;
Parmigiano 13 ; Biggy Burger 13 ; Vittoria 13 ; Calabrese 13 ;
Rucola 13,50 ; Rucolini 13,50 ; Savoyarde 13,50 ; Alpin 13,50 ; Magretto 13,50 ; Diavolita 13,50 ; Pollo Pesto 13,50 ; Calzone 13,50 ;
Carnivore 14 ; Corleoni 14 ; Marco 14 ; Nonna 14 ; Calzone Kebab 14 ;
Saumon 14,50 ; Buffalo 14,50.
 
RÈGLES STRICTES :
- Ne jamais confirmer sans avoir annoncé le prix total.
- Refuser toute commande avant dix-huit heures quinze ou après vingt-deux heures.
- Refuser toute commande le dimanche ou pour un autre jour que ce soir.
- Toujours demander le numéro de téléphone."""
 
conversation_histories = {}
AUDIO_CACHE = {}  # id -> (bytes mp3, heure de creation)
 
 
def sans_accents(texte: str) -> str:
    """Enleve accents et apostrophes pour comparer des mots-cles."""
    texte = unicodedata.normalize("NFD", texte.lower())
    texte = "".join(c for c in texte if unicodedata.category(c) != "Mn")
    return texte.replace("'", " ").replace("\u2019", " ")
 
 
def get_or_create_history(call_sid: str) -> list:
    if call_sid not in conversation_histories:
        conversation_histories[call_sid] = []
    return conversation_histories[call_sid]
 
 
def clear_history(call_sid: str):
    if call_sid in conversation_histories:
        del conversation_histories[call_sid]
 
 
def transcribe_audio(audio_url: str) -> str:
    try:
        response = httpx.get(audio_url, timeout=15)
        audio_file = io.BytesIO(response.content)
        audio_file.name = "audio.wav"
        transcription = groq_client.audio.transcriptions.create(
            file=audio_file,
            model="whisper-large-v3-turbo",
            language="fr",
            response_format="text"
        )
        return str(transcription).strip()
    except Exception as e:
        print("Erreur transcription Whisper : " + str(e))
        return ""
 
 
def get_nova_response(call_sid: str, user_text: str, context: dict = None) -> str:
    history = get_or_create_history(call_sid)
 
    system = SYSTEM_PROMPT
    if context:
        system += "\n\nCONTEXTE ACTUEL :\n"
        if context.get("jour_semaine"):
            system += "Jour : " + context["jour_semaine"] + "\n"
        if context.get("heure_actuelle"):
            system += "Heure : " + context["heure_actuelle"] + "\n"
        if context.get("indisponibles"):
            system += "Pizzas indisponibles ce soir : " + ", ".join(context["indisponibles"].keys()) + "\n"
        if context.get("fours_actifs") == 0:
            system += "ATTENTION : le four est en panne, aucune commande possible.\n"
 
    history.append({"role": "user", "content": user_text})
 
    try:
        response = groq_client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "system", "content": system}] + history,
            max_tokens=1024,
            temperature=0.6,
            extra_body={"reasoning_effort": "low"}
        )
        nova_text = (response.choices[0].message.content or "").strip()
        if not nova_text:
            raise ValueError("reponse vide du modele")
        history.append({"role": "assistant", "content": nova_text})
        if len(history) > 20:
            conversation_histories[call_sid] = history[-20:]
        return nova_text
    except Exception as e:
        print("Erreur LLM Groq : " + str(e))
        return "Désolée, j'ai une petite difficulté technique. Pouvez-vous répéter ?"
 
 
def synthesize_voice(text: str) -> bytes | None:
    if not MISTRAL_API_KEY or not MISTRAL_VOICE_ID:
        print("Voxtral desactive : cle ou voice_id manquant")
        return None
    try:
        r = httpx.post(
            VOXTRAL_API_URL,
            headers={
                "Authorization": "Bearer " + MISTRAL_API_KEY,
                "Content-Type": "application/json"
            },
            json={
                "model": "voxtral-mini-tts-2603",
                "input": text,
                "voice_id": MISTRAL_VOICE_ID,
                "response_format": "mp3"
            },
            timeout=10
        )
        if r.status_code != 200:
            print("Erreur Voxtral : " + str(r.status_code) + " " + r.text[:300])
            return None
        if "application/json" in r.headers.get("content-type", ""):
            return base64.b64decode(r.json()["audio_data"])
        return r.content
    except Exception as e:
        print("Erreur TTS : " + str(e))
        return None
 
 
def stocker_audio(audio: bytes) -> str:
    maintenant = time.time()
    for k in list(AUDIO_CACHE):
        if maintenant - AUDIO_CACHE[k][1] > 300:
            del AUDIO_CACHE[k]
    audio_id = uuid.uuid4().hex
    AUDIO_CACHE[audio_id] = (audio, maintenant)
    return audio_id
 
 
def ajouter_voix(response: VoiceResponse, text: str):
    audio = synthesize_voice(text)
    if audio:
        response.play(API_BASE + "/audio/" + stocker_audio(audio) + ".mp3")
    else:
        response.say(text, voice="Polly.Lea", language="fr-FR")
 
 
def build_twiml_response(nova_text: str, gather_action: str, is_end: bool = False) -> str:
    response = VoiceResponse()
    ajouter_voix(response, nova_text)
    if not is_end:
        gather = Gather(
            input="speech",
            action=gather_action,
            method="POST",
            language="fr-FR",
            speech_timeout="auto",
            timeout=5
        )
        response.append(gather)
        response.redirect(gather_action)
    return str(response)
 
 
def extract_command_from_conversation(history: list) -> dict | None:
    if not history:
        return None
    try:
        extract_prompt = """Analyse cette conversation et extrais les informations de commande.
Réponds UNIQUEMENT avec un JSON valide, sans texte autour.
Format : {"prenom": "...", "pizzas": "...", "nb": 1, "heure": "19h30", "telephone": "...", "extras": ""}
L'heure doit être au format 19h30. Si une information manque, mets null."""
 
        conv_text = "\n".join([m["role"] + ": " + m["content"] for m in history[-10:]])
        response = groq_client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": extract_prompt},
                {"role": "user", "content": "Conversation :\n" + conv_text}
            ],
            max_tokens=1024,
            temperature=0,
            extra_body={"reasoning_effort": "low"}
        )
        raw = (response.choices[0].message.content or "").strip()
        debut, fin = raw.find("{"), raw.rfind("}")
        if debut == -1 or fin == -1:
            raise ValueError("pas de JSON dans : " + raw[:200])
        return json.loads(raw[debut:fin + 1])
    except Exception as e:
        print("Erreur extraction commande : " + str(e))
        return None
 
 
def needs_to_place_order(nova_text: str) -> bool:
    keywords = [
        "commande confirmee", "commande enregistree", "c est confirme",
        "votre commande est passee", "commande validee"
    ]
    texte = sans_accents(nova_text)
    return any(kw in texte for kw in keywords)
