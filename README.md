# 📈 PriceWatch

PWA per monitorare i prezzi su **Amazon IT** e **AliExpress** con notifiche push sul telefono.  
Tutto gratis, ospitato su GitHub Pages + GitHub Actions.

---

## Come funziona

```
GitHub Actions (ogni 6h)
   └─ checker.py scrapa i prezzi
      └─ se sotto target → Web Push (VAPID)
            └─ Service Worker della PWA
                  └─ notifica sul telefono 📱
```

I dati (prodotti + subscription push) sono salvati in un **GitHub Gist privato**.

---

## Setup completo

### 1. Fork / crea il repo

Crea un repo GitHub (può essere privato) e carica tutti questi file.  
Poi abilita **GitHub Pages** dal repo:  
`Settings → Pages → Source: Deploy from a branch → main / (root)`

### 2. Genera le chiavi VAPID

```bash
pip install pywebpush
python setup_keys.py
```

Tieni da parte la **VAPID Public Key** e la **VAPID Private Key**.

### 3. Crea un GitHub Token

Vai su [github.com/settings/tokens](https://github.com/settings/tokens/new?scopes=gist,workflow&description=PriceWatch)  
Crea un **Classic token** con scope: `gist` + `workflow`

### 4. Aggiungi i GitHub Secrets

Nel tuo repo: `Settings → Secrets and variables → Actions → New repository secret`

| Secret | Valore |
|--------|--------|
| `VAPID_PRIVATE_KEY` | La chiave PEM generata al passo 2 |
| `VAPID_CLAIMS_EMAIL` | `mailto:tua@email.com` |
| `GH_TOKEN` | Il token creato al passo 3 |
| `GIST_ID` | Lo trovi dopo il primo avvio della PWA |

### 5. Apri la PWA sul telefono

Vai su `https://tuo-username.github.io/price-alert/`

Inserisci nella schermata di setup:
- GitHub Token (quello del passo 3)
- VAPID Public Key (dal passo 2)
- Lascia vuoto il Gist ID → la PWA lo crea automaticamente

### 6. Copia il Gist ID nei Secrets

Dopo il setup, la PWA mostra il Gist ID.  
Aggiungilo come secret `GIST_ID` nel repo (passo 4).

### 7. Installa la PWA sul telefono

**Android (Chrome):** menu ⋮ → "Aggiungi a schermata Home"  
**iOS (Safari):** pulsante condividi → "Aggiungi a schermata Home"

### 8. Attiva le notifiche push

Nella PWA: `Impostazioni → Attiva Notifiche Push`  
Accetta il permesso quando richiesto dal browser.

---

## Avvio manuale del controllo

`GitHub repo → Actions → Check Prices → Run workflow`

---

## Struttura file

```
price-alert/
├── index.html               # PWA (UI + logica)
├── sw.js                    # Service Worker (push notifications)
├── manifest.json            # PWA manifest
├── icon-192.png             # Icona app
├── icon-512.png             # Icona app
├── checker.py               # Script controllo prezzi
├── requirements.txt         # Dipendenze Python
├── setup_keys.py            # Generatore chiavi VAPID
└── .github/
    └── workflows/
        └── check_prices.yml # GitHub Actions workflow
```

---

## Note sullo scraping

Amazon e AliExpress implementano misure anti-bot.  
Il checker usa User-Agent rotation e pause casuali, ma **non è garantito al 100%**.  
Se i prezzi non vengono rilevati, controlla i log in `GitHub → Actions`.

---

## Dati salvati nel Gist

`products.json` — lista prodotti monitorati  
`subscriptions.json` — subscription Web Push del telefono

Il Gist è **privato** e accessibile solo con il tuo token.
