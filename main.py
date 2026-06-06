from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, Response
from groq import Groq
import os

app = FastAPI()

client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

# Historique conversation par appel
conversations = {}

@app.get("/", response_class=HTMLResponse)
def home():
    return """
    <html>
    <head>
        <title>Sofia — Agent Vocal Pizzeria</title>
        <style>
            body { font-family: Arial; text-align: center; padding: 50px; background: #1a1a2e; color: white; }
            h1 { color: #ff6b35; font-size: 2.5em; }
            p { font-size: 1.2em; color: #ccc; }
            .btn { background: #ff6b35; color: white; padding: 15px 30px; border: none; border-radius: 25px; font-size: 1.1em; cursor: pointer; margin: 10px; }
            .btn:hover { background: #e55a25; }
            .demo-box { background: #16213e; padding: 30px; border-radius: 15px; margin: 30px auto; max-width: 600px; }
        </style>
    </head>
    <body>
        <h1>🍕 Sofia — Agent Vocal IA</h1>
        <p>Votre assistante vocale intelligente pour pizzeria</p>
        <div class="demo-box">
            <h2>Ce que Sofia fait pour vous</h2>
            <p>✅ Repond aux appels 24h/24</p>
            <p>✅ Prend les commandes en francais</p>
            <p>✅ Calcule les heures de preparation</p>
            <p>✅ Envoie le planning au pizzaiolo</p>
            <p>✅ Gere les annulations</p>
            <br>
            <button class="btn" onclick="testerSofia()">🎤 Ecouter Sofia</button>
        </div>
        <script>
        function testerSofia() {
            const msg = new SpeechSynthesisUtterance(
                "Bonjour ! Je suis Sofia, votre assistante vocale de pizzeria. Je prends vos commandes et envoie le planning au pizzaiolo. Comment puis-je vous aider ?"
            );
            msg.lang = "fr-FR";
            window.speechSynthesis.speak(msg);
        }
        </script>
    </body>
    </html>
    """

@app.get("/health")
def health():
    return {"status": "ok", "agent": "Sofia Pizzeria"}

@app.post("/appel")
async def appel_entrant(request: Request):
    """Reçoit l'appel Twilio et lance la conversation"""
    twiml = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say language="fr-FR" voice="Polly.Lea">
        Bonjour ! Je suis Sofia, l'assistante vocale de la pizzeria.
        Je peux prendre votre commande.
        Dites votre prenom, la pizza souhaitee et l'heure de retrait.
    </Say>
    <Gather input="speech" language="fr-FR" action="/reponse" method="POST" timeout="5" speechTimeout="auto">
        <Say language="fr-FR" voice="Polly.Lea">Je vous ecoute.</Say>
    </Gather>
</Response>"""
    return Response(content=twiml, media_type="application/xml")

@app.post("/reponse")
async def reponse(request: Request):
    """Traite ce que le client dit et répond avec Sofia"""
    form = await request.form()
    texte_client = form.get("SpeechResult", "")
    call_sid     = form.get("CallSid", "inconnu")

    if not texte_client:
        twiml = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say language="fr-FR" voice="Polly.Lea">Je n'ai pas entendu. Pouvez-vous repeter ?</Say>
    <Gather input="speech" language="fr-FR" action="/reponse" method="POST" timeout="5" speechTimeout="auto">
        <Say language="fr-FR" voice="Polly.Lea">Je vous ecoute.</Say>
    </Gather>
</Response>"""
        return Response(content=twiml, media_type="application/xml")

    # Initialise l'historique si nouveau appel
    if call_sid not in conversations:
        conversations[call_sid] = [{
            "role": "system",
            "content": """Tu es Sofia, assistante vocale d'une pizzeria.
Reponds en francais, 2 phrases max, ton chaleureux.
Tu collectes : prenom, pizza, heure de retrait.
Repete la commande et demande confirmation.
Reponds UNIQUEMENT avec du texte simple, sans symboles speciaux."""
        }]

    conversations[call_sid].append({
        "role": "user",
        "content": texte_client
    })

    # Appel à Groq
    reponse_ia = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=conversations[call_sid]
    )
    texte_sofia = reponse_ia.choices[0].message.content
    conversations[call_sid].append({
        "role": "assistant",
        "content": texte_sofia
    })

    # Répond et réecoute
    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say language="fr-FR" voice="Polly.Lea">{texte_sofia}</Say>
    <Gather input="speech" language="fr-FR" action="/reponse" method="POST" timeout="5" speechTimeout="auto">
    </Gather>
</Response>"""
    return Response(content=twiml, media_type="application/xml")
