import os
import io
import json
import httpx
import tempfile
from groq import Groq
from twilio.twiml.voice_response import VoiceResponse, Gather
from datetime import datetime

groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

VOXTRAL_API_URL = "https://api.mistral.ai/v1/audio/speech"
MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY", "")

API_BASE = os.environ.get("API_BASE_URL", "https://web-production-967e41.up.railway.app")

SYSTEM_PROMPT = """Tu es Nova, l assistante vocale de Bella Pizza. Tu reponds UNIQUEMENT en francais, ton chaleureux et naturel. Maximum 2 phrases courtes a la fois.

HORAIRES : Ouvert lundi-samedi, 18h15 a 22h00. Dimanche ferme : dis "Bella Pizza est fermee le dimanche. Nous sommes ouverts du lundi au samedi de 18h15 a 22h00."

REGLES FOUR : 1 four, 2 etages, max 2 pizzas par 15 minutes. 15 min minimum entre commandes.

PROCESSUS COMMANDE (dans l ordre) :
1. Demande le prenom
2. Demande la ou les pizzas et la quantite
3. Demande les modifications eventuelles
4. Demande l heure de retrait (entre 18h15 et 22h00, ce soir uniquement)
5. Demande le numero de telephone
6. Annonce le prix total avant confirmation
7. Confirme : "Parfait [prenom] ! [nb] pizza(s) [nom] pour [heure], total [prix] euros. Je confirme ?"
8. Si oui : appelle l outil passer_commande

PRIX CARTE :
Margherita 9.50 | Napolitaine 10.50 | Reine/Regina 11.50 | Thon 11 | Vegetarienne 11
4 Fromages 12 | Cremosa 12 | Palerme 12 | Primavera 12
Flammenkuche 12.50 | Chevre Miel 12.50 | Roquefort 12.50 | Kebab 12.50 | Bergere 12.50
Parmigiano 13 | Biggy Burger 13 | Vittoria 13 | Calabrese 13
Rucola 13.50 | Rucolini 13.50 | Savoyarde 13.50 | Alpin 13.50 | Magretto 13.50 | Diavolita 13.50 | Pollo Pesto 13.50 | Calzone 13.50
Carnivore 14 | Corleoni 14 | Marco 14 | Nonna 14 | Calzone Kebab 14
Saumon 14.50 | Buffalo 14.50

REGLES IMPORTANTES :
- Jamais confirmer sans annoncer le prix total
- Jamais accepter avant 18h15 ou apres 22h00
- Jamais accepter le dimanche
- Jamais pour un autre jour que ce soir
- Toujours demander le numero de telephone"""

conversation_histories = {}


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
        audio_data = response.content
        audio_file = io.BytesIO(audio_data)
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

    if context:
        context_str = "\n\nCONTEXTE ACTUEL :\n"
        if context.get("jour_semaine"):
            context_str += "Jour : " + context["jour_semaine"] + "\n"
        if context.get("heure_actuelle"):
            context_str += "Heure : " + context["heure_actuelle"] + "\n"
        if context.get("indisponibles"):
            context_str += "Pizzas indisponibles ce soir : " + ", ".join(context["indisponibles"].keys()) + "\n"
        if context.get("fours_actifs") == 0:
            context_str += "ATTENTION : Le four est en panne, aucune commande possible.\n"
        system = SYSTEM_PROMPT + context_str
    else:
        system = SYSTEM_PROMPT

    history.append({"role": "user", "content": user_text})

    try:
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "system", "content": system}] + history,
            max_tokens=200,
            temperature=0.7
        )
        nova_text = response.choices[0].message.content.strip()
        history.append({"role": "assistant", "content": nova_text})
        if len(history) > 20:
            conversation_histories[call_sid] = history[-20:]
        return nova_text
    except Exception as e:
        print("Erreur LLM Groq : " + str(e))
        return "Desolee, j ai une petite difficulte technique. Pouvez-vous repeter ?"


def synthesize_voice(text: str) -> bytes | None:
    if not MISTRAL_API_KEY:
        return None
    try:
        response = httpx.post(
            VOXTRAL_API_URL,
            headers={
                "Authorization": "Bearer " + MISTRAL_API_KEY,
                "Content-Type": "application/json"
            },
            json={
                "model": "voxtral-tts-1",
                "input": text,
                "voice": "nova-fr",
                "response_format": "mp3"
            },
            timeout=15
        )
        if response.status_code == 200:
            return response.content
        else:
            print("Erreur Voxtral : " + str(response.status_code))
            return None
    except Exception as e:
        print("Erreur TTS : " + str(e))
        return None


def build_twiml_response(nova_text: str, gather_action: str, is_end: bool = False) -> str:
    response = VoiceResponse()
    audio_bytes = synthesize_voice(nova_text)

    if audio_bytes:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as f:
            f.write(audio_bytes)
            tmp_path = f.name
        response.play(API_BASE + "/audio/" + os.path.basename(tmp_path))
    else:
        response.say(nova_text, voice="Polly.Lea", language="fr-FR")

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
        extract_prompt = """Analyse cette conversation et extrait les informations de commande en JSON.
Reponds UNIQUEMENT avec un JSON valide, rien d autre.
Format : {"prenom": "...", "pizzas": "...", "nb": 1, "heure": "...", "telephone": "...", "extras": ""}
Si une info manque mets null."""

        messages = [{"role": "system", "content": extract_prompt}]
        conv_text = "\n".join([m["role"] + ": " + m["content"] for m in history[-10:]])
        messages.append({"role": "user", "content": "Conversation :\n" + conv_text})

        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            max_tokens=200,
            temperature=0
        )
        raw = response.choices[0].message.content.strip()
        raw = raw.replace("```json", "").replace("```", "").strip()
        return json.loads(raw)
    except Exception as e:
        print("Erreur extraction commande : " + str(e))
        return None


def needs_to_place_order(nova_text: str) -> bool:
    keywords = [
        "commande confirmee", "commande enregistree", "c est confirme",
        "c'est confirme", "bien note", "parfait je confirme",
        "votre commande est passee", "commande validee"
    ]
    text_lower = nova_text.lower()
    return any(kw in text_lower for kw in keywords)
