-- ============================================================
-- SCHEMA COMPLET NOVA PIZZERIA V3
-- ============================================================
-- CREATE TABLE IF NOT EXISTS config
CREATE TABLE IF NOT EXISTS config (
 cle TEXT PRIMARY KEY,
 valeur TEXT NOT NULL
);
-- CREATE TABLE IF NOT EXISTS commandes (legacy, single pizzeria)
CREATE TABLE IF NOT EXISTS commandes (
 id SERIAL PRIMARY KEY,
 prenom TEXT NOT NULL,
 telephone TEXT,
 pizza TEXT NOT NULL,
 nb INTEGER DEFAULT 1,
 heure TEXT,
 lancement TEXT,
 extras TEXT,
 total FLOAT,
 annulee BOOLEAN DEFAULT FALSE,
 annulee_at TIMESTAMP,
 raison_annulation TEXT,
 source TEXT DEFAULT 'vocal',
 created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
-- CREATE TABLE IF NOT EXISTS pizzerias
CREATE TABLE IF NOT EXISTS pizzerias (
 id SERIAL PRIMARY KEY,
 nom TEXT NOT NULL UNIQUE,
 email TEXT NOT NULL,
 telephone_proprietaire TEXT,
 numero_twilio TEXT NOT NULL UNIQUE,
 ville TEXT,
 heure_ouverture TEXT DEFAULT '18h15',
 heure_fermeture TEXT DEFAULT '22h00',
 jours_fermeture TEXT DEFAULT 'dimanche',
 max_pizzas_creneau INTEGER DEFAULT 2,
 actif BOOLEAN DEFAULT TRUE,
 statut_abonnement TEXT DEFAULT 'actif',
 stripe_customer_id TEXT,
 stripe_subscription_id TEXT,
 created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
 updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
-- CREATE TABLE IF NOT EXISTS menus (pizzas by pizzeria)
CREATE TABLE IF NOT EXISTS menus (
 id SERIAL PRIMARY KEY,
 pizzeria_id INTEGER NOT NULL REFERENCES pizzerias(id) ON DELETE CASCADE,
 nom TEXT NOT NULL,
 prix FLOAT NOT NULL,
 temps_prep INTEGER DEFAULT 13,
 disponible BOOLEAN DEFAULT TRUE,
 created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
-- CREATE TABLE IF NOT EXISTS commandes_v2 (multi-pizzeria)
CREATE TABLE IF NOT EXISTS commandes_v2 (
 id SERIAL PRIMARY KEY,
 pizzeria_id INTEGER NOT NULL REFERENCES pizzerias(id) ON DELETE CASCADE,
 prenom TEXT NOT NULL,
 telephone TEXT,
 pizza TEXT NOT NULL,
 nb INTEGER DEFAULT 1,
 heure TEXT,
 lancement TEXT,
 extras TEXT,
 total FLOAT,
 annulee BOOLEAN DEFAULT FALSE,
 annulee_at TIMESTAMP,
 raison_annulation TEXT,
 source TEXT DEFAULT 'vocal',
 created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
-- CREATE TABLE IF NOT EXISTS minutes_usage (tracking appels vocaux)
CREATE TABLE IF NOT EXISTS minutes_usage (
 id SERIAL PRIMARY KEY,
 pizzeria_id INTEGER NOT NULL REFERENCES pizzerias(id) ON DELETE CASCADE,
 mois TEXT NOT NULL,
 minutes_utilisees FLOAT DEFAULT 0,
 minutes_facturees FLOAT DEFAULT 0,
 depassement_facture BOOLEAN DEFAULT FALSE,
 tranches_facturees INTEGER DEFAULT 0,
 montant_facture FLOAT DEFAULT 0,
 invoice_id TEXT,
 facture_at TIMESTAMP,
 created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
 updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
 UNIQUE(pizzeria_id, mois)
);
-- ============================================================
-- INDEXES
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_commandes_created_at ON commandes(created_at);
CREATE INDEX IF NOT EXISTS idx_commandes_v2_pizzeria_id ON commandes_v2(pizzeria_id);
CREATE INDEX IF NOT EXISTS idx_commandes_v2_created_at ON commandes_v2(created_at);
CREATE INDEX IF NOT EXISTS idx_menus_pizzeria_id ON menus(pizzeria_id);
CREATE INDEX IF NOT EXISTS idx_pizzerias_numero_twilio ON pizzerias(numero_twilio);
CREATE INDEX IF NOT EXISTS idx_minutes_usage_pizzeria_mois ON minutes_usage(pizzeria_id, mois);

