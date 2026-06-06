from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from groq import Groq
import os

app = FastAPI()
client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

conversations = {}

MENU = """
PIZZA ROUGE :
- Margherita 10€ (Sauce Tomate, Mozzarella, Basilic)
- Jambon Fromage 12€ (Sauce Tomate, Mozzarella, Jambon, Emmental, Olives)
- Napolitaine 12.50€ (Sauce Tomate, Mozzarella, Anchois, Capres, Olives)
- Reine 13€ (Sauce Tomate, Mozzarella, Jambon, Champignons, Olives)
- 4 Fromage 14€ (Sauce Tomate, Mozzarella, Emmental, Chevre, Gorgonzola, Olives)
- Parmigiano 15€ (Sauce Tomate, Mozzarella, Aubergines, Poivrons, Viande hachee, Parmesan, Olives)
- Rucola 14€ (Sauce Tomate, Mozzarella, Jambon cru, Parmesan, Roquette, Olives)
- Thon 14€ (Sauce Tomate, Creme fraiche, Mozzarella, Thon, Poivrons, Capres, Oeuf, Olives)
- Palermo 13€ (Sauce Tomate, Mozzarella, Spianata, Poivrons, Olives)
- Rucolini VEGE 14€ (Sauce Tomate, Mozzarella, Ricotta, Tomates confites, Aubergines, Roquette, Parmesan, Olives)
- Corleoni 14.50€ (Sauce Tomate, Mozzarella, Viande hachee, Fromage ail et herbes, Oeuf, Olives)
- Vegetarienne VEGE 13.50€ (Sauce Tomate, Mozzarella, Aubergines, Brocolis)

PIZZA BLANCHE :
- Flammenkush 14.50€ (Creme Fraiche, Mozzarella, Jambons, Champignons, Oignons, Lardons, Ail, Persil, Olives)
- Salmone 15.50€ (Creme Fraiche, Mozzarella, Saumon, Ricotta, Asperges, Aneth, Olives)
- Chevre Miel VEGE 14€ (Creme Fraiche, Mozzarella, Chevre, Miel, Noix, Olives)
- Savoyarde 15€ (Creme Fraiche, Mozzarella, Lardons, Reblochon, Pommes de terre, Oignons, Olives)
- Carnivore 16.50€ (Creme Fraiche, Mozzarella, Viande hachee, Merguez, Kebab, Oignons, Olives)
- Roquefort 14.50€ (Creme Fraiche, Mozzarella, Roquefort, Jambon, Noix, Olives)
- Cremosa NEW 13€ (Creme Fraiche, Mozzarella, Gorgonzola, Jambon, Emmental, Poivre, Olives)

PIZZA SPECIALE :
- Buffalo 16€ (Sauce Barbecue, Mozzarella, Merguez, Poulet, Spianata, Olives)
- Kebab 14€ (Creme Fraiche, Mozzarella, Kebab, Champignons, Oignons, Sauce blanche, Olives)
- Biggy Burger 14.50€ (Sauce Biggy, Mozzarella, Viande hachee, Oignons, Cheddar, Olives)
- Calzone 13.50€ (Sauce tomate, Mozzarella, Emmental, Jambon, Oeuf, Olives)
- Calzone Kebab NEW 13.50€ (Creme Fraiche, Mozzarella, Kebab, Oignons, Sauce blanche)

CREATIONS DU CHEF :
- La Vittoria NEW 15.50€ (Sauce Tomate, Mozzarella, Chair a Saucisse, Aubergines Gratinees, Tomates cerises confites, Ail, Basilic, Olives)
- La Diavolita NEW 16€ (Sauce Tomate, Mozzarella, Nduja, Chair a Saucisse, Poivrons, Burratina, Huile d'Olive, Basilic, Olives)
- La Primavera VEGE 15€ (Sauce Tomate, Mozzarella, Tomates confites, Roquette, Burratina, Pesto Maison, Pignons, Olives)
- La Calabrese 15€ (Sauce Tomate, Mozzarella, Nduja, Ricotta, Oignons, Poivrons, Basilic, Olives)
- L'Alpine 14.50€ (Creme Fraiche, Mozzarella, Jambon, Chevre, Gorgonzola, Champignons, Ail, Persil, Olives)
- La Marco 16€ (Creme Fraiche, Mozzarella, Pesto de Pistache, Speck, Capes, Ail, Parmesan, Olives)
- La Magretto 15.50€ (Creme Fraiche, Mozzarella, Champignons, Magret de Canard seche, Confit d'Oignon, Zeste d'orange, Olives)
- La Nonna 16€ (Mozzarella, Pesto de Pistache, Gorgonzola, Poires, Speck, Poivre, Olives)
- La Pollo Pesto 15€ (Creme Fraiche, Mozzarella, Poulet, Tomates Confites, Oignons, Pesto maison, Pignons, Olives)
- La Bergere 14.50€ (Creme Fraiche, Mozzarella, Chevre, Miel, Lardons, Roquette, Noix, Olives)

SUPPLEMENTS : Viandes 1.50€, Oeuf 1€, Autres 1€
"""

SYSTEM_PROMPT = f"""Tu es Sofia, assistante vocale d'une pizzeria.
Tu reponds en francais, 2 phrases max, ton chaleureux.
Si tu ne comprends pas, tu redemandes poliment.

CARTE COMPLETE :
{MENU}

PROCESS DE COMMANDE :
1. Demande le prenom
2. Demande la pizza et la quantite
3. Note les modifications (sans oignons, sans fromage, etc.)
4. Demande l'heure de retrait
5. REPETE toute la commande et demande confirmation
6. Si modification, applique et reconfirme
7. Si tout est bon, confirme et dis au revoir

ANNULATION : demande le prenom, confirme l'annulation.
SUPPLEMENTS : propose si pertinent (ex: ajouter un oeuf sur la Thon)
Reponds UNIQUEMENT avec du texte simple sans symboles speciaux."""

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
        .header p { color: #aaa; margin-top: 5px; font-size: 13px; }
        .chat-container { max-width: 600px; margin: 20px auto; padding: 0 15px; }
        .messages { height: 420px; overflow-y: auto; background: #16213e; border-radius: 15px; padding: 15px; margin-bottom: 10px; }
        .message { margin: 10px 0; display: flex; align-items: flex-start; gap: 10px; }
        .message.sofia { justify-content: flex-start; }
        .message.client { justify-content: flex-end; flex-direction: row-reverse; }
        .bubble { padding: 10px 15px; border-radius: 18px; max-width: 80%; font-size: 14px; line-height: 1.5; }
        .sofia .bubble { background: #ff6b35; color: white; border-bottom-left-radius: 4px; }
        .client .bubble { background: #0f3460; color: white; border-bottom-right-radius: 4px; }
        .avatar { width: 32px; height: 32px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 16px; flex-shrink: 0; background: #ff6b3533; }
        .typing { color: #aaa; font-size: 12px; padding: 4px 15px; min-height: 20px; }
        .input-row { display: flex; gap: 8px; margin-top: 8px; }
        .input-row input { flex: 1; padding: 12px 15px; border-radius: 25px; border: 1px solid #333; background: #16213e; color: white; font-size: 14px; outline: none; }
        .input-row input:focus { border-color: #ff6b35; }
        .btn { padding: 12px 18px; border-radius: 25px; border: none; cursor: pointer; font-size: 14px; font-weight: bold; }
        .btn-send { background: #ff6b35; color: white; }
        .btn-voice { background: #0f3460; color: white; font-size: 18px; }
        .btn-voice.listening { background: #ff6b35; animation: pulse 1s infinite; }
        @keyframes pulse { 0%,100%{transform:scale(1)} 50%{transform:scale(1.1)} }
        .features { display: grid; grid-template-columns: repeat(2,1fr); gap: 10px; max-width: 600px; margin: 15px auto 20px; padding: 0 15px; }
        .feature { background: #16213e; border-radius: 10px; padding: 12px; text-align: center; font-size: 12px; color: #aaa; }
        .feature span { display: block; font-size: 22px; margin-bottom: 4px; }
    </style>
</head>
<body>
    <div class="header">
        <h1>🍕 Sofia</h1>
        <p>Assistante vocale IA — Commandez en parlant ou en ecrivant</p>
    </div>
    <div class="chat-container">
        <div class="messages" id="messages">
            <div class="message sofia">
                <div class="avatar">🍕</div>
                <div class="bubble">Bonjour ! Je suis Sofia, votre assistante vocale. Je connais toute la carte. Comment puis-je vous aider ?</div>
            </div>
        </div>
        <div class="typing" id="typing"></div>
        <div class="input-row">
            <button class="btn btn-voice" id="btnVoice" onclick="toggleVoice()" title="Parler">🎤</button>
            <input type="text" id="userInput" placeholder="Ex: Je voudrais une Reine sans champignons..." onkeydown="if(event.key==='Enter')envoyer()">
            <button class="btn btn-send" onclick="envoyer()">Envoyer</button>
        </div>
    </div>
    <div class="features">
        <div class="feature"><span>🗣️</span>Commande vocale ou texte</div>
        <div class="feature"><span>🍕</span>Carte complete 35+ pizzas</div>
        <div class="feature"><span>⏰</span>Planning automatique</div>
        <div class="feature"><span>📱</span>SMS au pizzaiolo</div>
    </div>
    <script>
    const sessionId = Math.random().toString(36).substr(2,9);
    let recognition = null, isListening = false;

    if('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
        const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
        recognition = new SR();
        recognition.lang = 'fr-FR';
        recognition.continuous = false;
        recognition.interimResults = false;
        recognition.onresult = e => {
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
        if(!recognition) { alert('Utilisez Chrome pour la reconnaissance vocale.'); return; }
        if(isListening) { recognition.stop(); }
        else {
            recognition.start();
            isListening = true;
            document.getElementById('btnVoice').classList.add('listening');
            document.getElementById('btnVoice').textContent = '🔴';
        }
    }

    function parler(texte) {
        if('speechSynthesis' in window) {
            window.speechSynthesis.cancel();
            const msg = new SpeechSynthesisUtterance(texte);
            msg.lang = 'fr-FR';
            msg.rate = 0.9;
            window.speechSynthesis.speak(msg);
        }
    }

    function ajouterMessage(texte, role) {
        const msgs = document.getElementById('messages');
        const div = document.createElement('div');
        div.className = 'message ' + role;
        div.innerHTML = '<div class="avatar">' + (role==='sofia'?'🍕':'👤') + '</div><div class="bubble">' + texte + '</div>';
        msgs.appendChild(div);
        msgs.scrollTop = msgs.scrollHeight;
    }

    async function envoyer() {
        const input = document.getElementById('userInput');
        const texte = input.value.trim();
        if(!texte) return;
        input.value = '';
        ajouterMessage(texte, 'client');
        document.getElementById('typing').textContent = 'Sofia est en train de repondre...';
        try {
            const res = await fetch('/chat', {
                method: 'POST',
                headers: {'Content-Type':'application/json'},
                body: JSON.stringify({message: texte, session_id: sessionId})
            });
            const data = await res.json();
            document.getElementById('typing').textContent = '';
            ajouterMessage(data.reponse, 'sofia');
            parler(data.reponse);
        } catch(e) {
            document.getElementById('typing').textContent = '';
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

    rep = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=conversations[session_id]
    )

    texte = rep.choices[0].message.content
    conversations[session_id].append({"role": "assistant", "content": texte})
    return JSONResponse({"reponse": texte})
