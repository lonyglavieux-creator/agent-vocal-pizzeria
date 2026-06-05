from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from groq import Groq
import os

app = FastAPI()

client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

@app.get("/", response_class=HTMLResponse)
def home():
    return """
    <html>
    <head>
        <title>Agent Vocal Pizzeria</title>
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
            <button class="btn" onclick="testerSofia()">🎤 Tester Sofia</button>
        </div>
        <script>
        function testerSofia() {
            const msg = new SpeechSynthesisUtterance(
                "Bonjour ! Je suis Sofia, votre assistante vocale. Je peux prendre vos commandes de pizzas et envoyer le planning a votre pizzaiolo. Comment puis-je vous aider ?"
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
