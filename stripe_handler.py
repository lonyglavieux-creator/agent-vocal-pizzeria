import os
import stripe

STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "")


def verifier_webhook(payload: bytes, signature: str):
    try:
        event = stripe.Webhook.construct_event(payload, signature, STRIPE_WEBHOOK_SECRET)
        return event
    except Exception as e:
        print("Erreur verifier_webhook : " + str(e))
        return None


def lister_abonnements_actifs() -> list:
    try:
        subs = stripe.Subscription.list(status="active", limit=100)
        return [
            {"id": s.id, "customer": s.customer, "status": s.status}
            for s in subs.auto_paging_iter()
        ]
    except Exception as e:
        print("Erreur lister_abonnements_actifs : " + str(e))
        return []
