import os
import asyncpg
import asyncio
import stripe

STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_PRICE_ID = os.environ.get("STRIPE_PRICE_ID", "")
DATABASE_URL = os.environ.get("DATABASE_URL", "")

stripe.api_key = STRIPE_SECRET_KEY

def run_async(coro):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(asyncio.run, coro)
            return future.result(timeout=10)
    else:
        return asyncio.run(coro)


def creer_client_nova(nom: str, email: str, tel: str, pizzeria: str):
    try:
        customer = stripe.Customer.create(name=nom, email=email, phone=tel)
        session = stripe.checkout.Session.create(
            customer=customer.id,
            mode="subscription",
            line_items=[{"price": STRIPE_PRICE_ID, "quantity": 1}],
            success_url="https://web-production-967e41.up.railway.app/paiement/succes?session_id={CHECKOUT_SESSION_ID}",
            cancel_url="https://web-production-967e41.up.railway.app/paiement/annule"
        )
    except Exception as e:
        print("Erreur Stripe creer_client_nova : " + str(e))
        return None

    async def _do():
        conn = await asyncpg.connect(DATABASE_URL)
        try:
            await conn.execute("""
                INSERT INTO clients_nova (nom, email, telephone, pizzeria, stripe_customer_id, actif)
                VALUES ($1, $2, $3, $4, $5, false)
                """, nom, email, tel, pizzeria, customer.id)
        finally:
            await conn.close()

    try:
        run_async(_do())
    except Exception as e:
        print("Erreur DB creer_client_nova : " + str(e))

    return {
        "lien_paiement": session.url,
        "stripe_customer_id": customer.id
    }


def activer_client(customer_id: str, subscription_id: str) -> bool:
    async def _do():
        conn = await asyncpg.connect(DATABASE_URL)
        try:
            await conn.execute("""
                UPDATE clients_nova SET actif=true, stripe_subscription_id=$1
                WHERE stripe_customer_id=$2
                """, subscription_id, customer_id)
        finally:
            await conn.close()
    try:
        run_async(_do())
        return True
    except Exception as e:
        print("Erreur activer_client : " + str(e))
        return False


def desactiver_client(customer_id: str) -> bool:
    async def _do():
        conn = await asyncpg.connect(DATABASE_URL)
        try:
            await conn.execute("""
                UPDATE clients_nova SET actif=false WHERE stripe_customer_id=$1
                """, customer_id)
        finally:
            await conn.close()
    try:
        run_async(_do())
        return True
    except Exception as e:
        print("Erreur desactiver_client : " + str(e))
        return False


def get_clients_actifs() -> list:
    async def _do():
        conn = await asyncpg.connect(DATABASE_URL)
        try:
            rows = await conn.fetch("SELECT * FROM clients_nova WHERE actif=true ORDER BY id ASC")
            return [dict(r) for r in rows]
        finally:
            await conn.close()
    try:
        return run_async(_do())
    except Exception as e:
        print("Erreur get_clients_actifs : " + str(e))
        return []


def send_whatsapp_notification(to_number: str, message: str) -> bool:
    from twilio.rest import Client as TwilioClient
    sid = os.environ.get("TWILIO_SID", "")
    token = os.environ.get("TWILIO_TOKEN", "")
    from_whatsapp = os.environ.get("TWILIO_FROM", "")
    if not sid or not token or not from_whatsapp:
        print("Erreur send_whatsapp_notification : identifiants Twilio manquants")
        return False
    try:
        client = TwilioClient(sid, token)
        client.messages.create(from_=from_whatsapp, to="whatsapp:" + to_number, body=message)
        return True
    except Exception as e:
        print("Erreur send_whatsapp_notification : " + str(e))
        return False
