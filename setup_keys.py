#!/usr/bin/env python3
"""
PriceWatch — setup_keys.py
Genera le chiavi VAPID necessarie per le notifiche push.
Esegui una volta sola: python setup_keys.py
"""
import base64, sys

try:
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.backends import default_backend
except ImportError:
    print("Installa le dipendenze prima: pip install pywebpush")
    sys.exit(1)

def generate_vapid_keys():
    # Genera coppia di chiavi EC
    private_key = ec.generate_private_key(ec.SECP256R1(), default_backend())
    public_key  = private_key.public_key()

    # Private key in formato PEM (per pywebpush)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption()
    ).decode('utf-8').strip()

    # Public key in formato uncompressed (per il browser)
    pub_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint
    )
    public_b64 = base64.urlsafe_b64encode(pub_bytes).rstrip(b'=').decode('utf-8')

    return private_pem, public_b64

if __name__ == '__main__':
    print()
    print('=' * 65)
    print('  PriceWatch — Generazione chiavi VAPID')
    print('=' * 65)

    priv, pub = generate_vapid_keys()

    print()
    print('┌─────────────────────────────────────────────────────────────┐')
    print('│  VAPID PUBLIC KEY — copia nella PWA (Impostazioni)          │')
    print('└─────────────────────────────────────────────────────────────┘')
    print(pub)

    print()
    print('┌─────────────────────────────────────────────────────────────┐')
    print('│  VAPID PRIVATE KEY — aggiungi come GitHub Secret            │')
    print('└─────────────────────────────────────────────────────────────┘')
    print(priv)

    print()
    print('=' * 65)
    print('  PROSSIMI PASSI')
    print('=' * 65)
    print()
    print('1. Copia la VAPID PUBLIC KEY nella schermata Impostazioni')
    print('   della PWA (campo "VAPID Public Key")')
    print()
    print('2. Nel tuo repo GitHub, vai su:')
    print('   Settings → Secrets and variables → Actions')
    print('   e aggiungi questi 4 secrets:')
    print()
    print('   VAPID_PRIVATE_KEY  → (la chiave PEM qui sopra, tutto il testo)')
    print('   VAPID_CLAIMS_EMAIL → mailto:tua@email.com')
    print('   GH_TOKEN           → token GitHub con scope "gist"')
    print('   GIST_ID            → ID del Gist (visibile nella PWA dopo setup)')
    print()
    print('3. Apri la PWA sul telefono, completa il setup e attiva')
    print('   le notifiche push dalla schermata Impostazioni')
    print()
    print('4. Il controllo prezzi partirà automaticamente ogni 6 ore.')
    print('   Puoi anche avviarlo manualmente da:')
    print('   GitHub → Actions → Check Prices → Run workflow')
    print()
    print('=' * 65)
