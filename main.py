from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from groq import Groq
import os

app = FastAPI()
client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

# Memoire des conversations
conversations = {}

SYSTEM_PROMPT = """Tu es Sofia, assistante vocale d'une pizzeria.
Tu reponds en francais, 2 phrases max, ton chaleureux.
Tu collectes : prenom, pizza, heure de retrait.
Tu connais ces pizzas : Margherita, Regina, Reine, 4 Fromages, Pepperoni, Calzone, Diavola, Vegetarienne, Napolitaine, Royale, Forestiere, Saumon.
Tu notes les modifications (sans oignons, sans fromage etc).
Tu repetes la commande et demandes confirmation avant de valider.
Si annulation, tu demandes le prenom et confirmes."""

@app.get("/", response_class=HTMLResponse)
def home():
    return """<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Sofia — Agent Vocal Pizzeria</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: Arial, sans-serif; background: #1a1a2e; color: white; min-height: 100vh; }
        .header { background: #16213e; padding: 20px; text-align: center; border-bottom: 2px solid #ff6b35; }
        .header h1 { color: #ff6b35; font-size: 1.8em; }
        .header p { color: #aaa; margin-top: 5px; }
        .chat-container { max-width: 600px; margin: 20px auto; padding: 0 15px; }
        .messages { height: 400px; overflow-y: auto; background: #16213e; border-radius: 15px; padding: 15px; margin-bottom: 15px; }
        .message { margin: 10px 0; display: flex; align-items: flex-start; gap: 10px; }
        .message.sofia { justify-content: flex-start; }
        .message.client { justify-content: flex-end; }
        .bubble { padding: 10px 15px; border-radius: 18px; max-width: 80%; font-size: 14px; line-height: 1.5; }
        .sofia .bubble { background: #ff6b35; color: white; border-bottom-left-radius: 4px; }
        .client .bubble { background: #0f3460; color: white; border-bottom-right-radius: 4px; }
        .avatar { width: 35px; height: 35px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 18px; flex-shrink: 0; }
        .sofia .avatar { background: #ff6b35; }
        .client .avatar { background: #0f3460; }
        .input-row { display: flex; gap: 10px; }
        .input-row input { flex: 1; padding: 12px 15px; border-radius: 25px; border: none; background: #16213e; color: white; font-size: 14px; outline: none; border: 1px solid #333; }
        .input-row input:focus { border-color: #ff6b35; }
        .btn { padding: 12px 20px; border-radius: 25px; border: none; cursor: pointer; font-size: 14px; font-weight: bold; transition: all 0.2s; }
        .btn-send { background: #ff6b35; color: white; }
        .btn-send:hover { background: #e55a25; }
        .btn-voice { background: #0f3460; color: white; font-size: 18px; }
        .btn-voice.listening { background: #ff6b35; animation: pulse 1s infinite; }
        @keyframes pulse { 0%,100%{transform:scale(1)} 50%{transform:scale(1.1)} }
        .typing { display: none; color: #aaa; font-size: 12px; padding: 5px 15px; }
        .typing.show { display: block; }
        .features { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; margin-top: 20px; max-width: 600px; margin-left: auto; margin-right: auto; padding: 0 15px 20px; }
        .feature { background: #16213e; border-radius: 10px; padding: 15px; text-align: center; font-size: 13px; color: #aaa; }
        .feature span { display: block; font-size: 24px; margin-bottom: 5px; }
    </style>
</head>
<body>
    <div class="header">
        <h1>🍕 Sofia</h1>
        <p>Assistante vocale IA pour votre pizzeria</p>
    </div>

    <div class="chat-container">
        <div class="messages" id="messages">
            <div class="message sofia">
                <div class="avatar">🍕</div>
                <div class="bubble">Bonjour ! Je suis Sofia, votre assistante vocale. Comment puis-je vous aider ?</div>
            </div>
        </div>
        <div class="typing" id="typing">Sofia est en train d'écrire...</div>
        <div class="input-row">
            <button class="btn btn-voice" id="btnVoice" onclick="toggleVoice()">🎤</button>
            <input type="text" id="userInput" placeholder="Tapez votre message..." onkeydown="if(event.key==='Enter') envoyer()">
            <button class="btn btn-send" onclick="envoyer()">Envoyer</button>
        </div>
    </div>

    <div class="features">
        <div class="feature"><span>📞</span>Prend les commandes</div>
        <div class="feature"><span>⏰</span>Calcule les horaires</div>
        <div class="feature"><span>📱</span>SMS au pizzaiolo</div>
        <div class="feature"><span>❌</span>Gere les annulations</div>
    </div>

    <script>
    const sessionId = Math.random().toString(36).substr(2, 9);
    let recognition = null;
    let isListening = false;

    // Initialise la reconnaissance vocale
    if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
        const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
        recognition = new SR();
        recognition.lang = 'fr-FR';
        recognition.continuous = false;
        recognition.interimResults = false;
        recognition.onresult = (e) => {
            document.getElementById('userInput').value = e.results[0][0].transcript;
            envoyer();
        };
        recognition.onend = () => {
            isListening = false;
            document.getElementById('btnVoice').classList.remove('listening');
            document.getElementById('btnVoice').textContent = '🎤';
        };
    }

    function toggleVoice() {
        if (!recognition) { alert('Reconnaissance vocale non supportee sur ce navigateur. Utilisez Chrome.'); return; }
        if (isListening) {
            recognition.stop();
        } else {
            recognition.start();
            isListening = true;
            document.getElementById('btnVoice').classList.add('listening');
            document.getElementById('btnVoice').textContent = '🔴';
        }
    }

    function parler(texte) {
        if ('speechSynthesis' in window) {
            window.speechSynthesis.cancel();
            const msg = new SpeechSynthesisUtterance(texte);
            msg.lang = 'fr-FR';
            msg.rate = 0.9;
            window.speechSynthesis.speak(msg);
        }
    }

    function ajouterMessage(texte, role) {
        const messages = document.getElementById('messages');
        const div = document.createElement('div');
        div.className = 'message ' + role;
        const avatar = role === 'sofia' ? '🍕' : '👤';
        div.innerHTML = '<div class="avatar">' + avatar + '</div><div class="bubble">' + texte + '</div>';
        messages.appendChild(div);
        messages.scrollTop = messages.scrollHeight;
    }

    async function envoyer() {
        const input = document.getElementById('userInput');
        const texte = input.value.trim();
        if (!texte) return;
        input.value = '';
        ajouterMessage(texte, 'client');
        document.getElementById('typing').classList.add('show');
        try {
            const res = await fetch('/chat', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({message: texte, session_id: sessionId})
            });
            const data = await res.json();
            document.getElementById('typing').classList.remove('show');
            ajouterMessage(data.reponse, 'sofia');
            parler(data.reponse);
        } catch(e) {
            document.getElementById('typing').classList.remove('show');
            ajouterMessage('Desolee, une erreur est survenue.', 'sofia');
        }
    }
    </script>
</body>
</html>"""

@app.get("/health")
def health():
    return {"status": "ok", "agent": "Sofia Pizzeria"}

@app.post("/chat")
async def chat(request: Request):
    data = await request.json()
    message = data.get("message", "")
    session_id = data.get("session_id", "default")

    if session_id not in conversations:
        conversations[session_id] = [{"role": "system", "content": SYSTEM_PROMPT}]

    conversations[session_id].append({"role": "user", "content": message})

    reponse = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=conversations[session_id]
    )

    texte = reponse.choices[0].message.content
    conversations[session_id].append({"role": "assistant", "content": texte})

    return JSONResponse({"reponse": texte})

@app.post("/appel")
async def appel_entrant(request: Request):
    twiml = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say language="fr-FR" voice="Polly.Lea">
        Bonjour ! Je suis Sofia, l'assistante vocale de la pizzeria.
        Je peux prendre votre commande.
    </Say>
    <Gather input="speech" language="fr-FR" action="/reponse" method="POST" timeout="5" speechTimeout="auto">
        <Say language="fr-FR" voice="Polly.Lea">Je vous ecoute.</Say>
    </Gather>
</Response>"""
    from fastapi.responses import Response
    return Response(content=twiml, media_type="application/xml")

@app.post("/reponse")
async def reponse_appel(request: Request):
    form = await request.form()
    texte_client = form.get("SpeechResult", "")
    call_sid = form.get("CallSid", "default")

    if not texte_client:
        twiml = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say language="fr-FR" voice="Polly.Lea">Je n'ai pas entendu. Pouvez-vous repeter ?</Say>
    <Gather input="speech" language="fr-FR" action="/reponse" method="POST" timeout="5" speechTimeout="auto">
    </Gather>
</Response>"""
        from fastapi.responses import Response
        return Response(content=twiml, media_type="application/xml")

    if call_sid not in conversations:
        conversations[call_sid] = [{"role": "system", "content": SYSTEM_PROMPT}]

    conversations[call_sid].append({"role": "user", "content": texte_client})
    rep = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=conversations[call_sid]
    )
    texte_sofia = rep.choices[0].message.content
    conversations[call_sid].append({"role": "assistant", "content": texte_sofia})

    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say language="fr-FR" voice="Polly.Lea">{texte_sofia}</Say>
    <Gather input="speech" language="fr-FR" action="/reponse" method="POST" timeout="5" speechTimeout="auto">
    </Gather>
</Response>"""
    from fastapi.responses import Response
    return Response(content=twiml, media_type="application/xml")
    return Response(content=twiml, media_type="application/xml")
