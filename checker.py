#!/usr/bin/env python3
"""
PriceWatch — checker.py
Controlla i prezzi su Amazon IT e AliExpress, invia push notification se scendono.
Gira via GitHub Actions ogni 6 ore.
"""
import os, json, re, time, random, sys, base64
import requests
from bs4 import BeautifulSoup
from pywebpush import webpush, WebPushException

# ── Config da variabili d'ambiente ──────────────────────────────────────────
GH_TOKEN            = os.environ.get('GH_TOKEN', '')
GIST_ID             = os.environ.get('GIST_ID', '')
VAPID_PRIVATE_KEY   = os.environ.get('VAPID_PRIVATE_KEY', '')
VAPID_CLAIMS_EMAIL  = os.environ.get('VAPID_CLAIMS_EMAIL', 'mailto:pricewatch@example.com')
SCRAPER_API_KEY     = os.environ.get('SCRAPER_API_KEY', '')

def fix_pem(key):
    """Converte chiave base64url raw oppure PEM in PEM valido."""
    key = key.strip()
    if '-----BEGIN' in key:
        return key.replace('\\n', '\n')
    # Chiave raw base64url → converti in PEM
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import serialization
    padding = '=' * (4 - len(key) % 4) if len(key) % 4 else ''
    raw = base64.urlsafe_b64decode(key + padding)
    priv_int = int.from_bytes(raw, 'big')
    private_key = ec.derive_private_key(priv_int, ec.SECP256R1(), default_backend())
    return private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption()
    ).decode('utf-8')

VAPID_PRIVATE_KEY = fix_pem(VAPID_PRIVATE_KEY)

if not all([GH_TOKEN, GIST_ID, VAPID_PRIVATE_KEY]):
    print("❌ Variabili d'ambiente mancanti: GH_TOKEN, GIST_ID, VAPID_PRIVATE_KEY")
    sys.exit(1)

# ── Fetch via ScraperAPI (bypassa blocchi anti-bot) ─────────────────────────
def fetch_url(url, render_js=False):
    """Scarica una pagina tramite ScraperAPI se disponibile, altrimenti diretto."""
    if SCRAPER_API_KEY:
        params = {
            'api_key': SCRAPER_API_KEY,
            'url': url,
            'country_code': 'it',
        }
        if render_js:
            params['render'] = 'true'
        r = requests.get('http://api.scraperapi.com', params=params, timeout=60)
    else:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
            'Accept-Language': 'it-IT,it;q=0.9',
        }
        r = requests.get(url, headers=headers, timeout=15)
    return r

# ── GitHub Gist ─────────────────────────────────────────────────────────────
def gist_get():
    r = requests.get(
        f'https://api.github.com/gists/{GIST_ID}',
        headers={'Authorization': f'token {GH_TOKEN}', 'Accept': 'application/vnd.github.v3+json'},
        timeout=15
    )
    r.raise_for_status()
    data = r.json()
    products = []
    subs = []
    if 'products.json' in data.get('files', {}):
        products = json.loads(data['files']['products.json']['content'])
    if 'subscriptions.json' in data.get('files', {}):
        subs = json.loads(data['files']['subscriptions.json']['content'])
    return products, subs

def gist_update(products, subs):
    r = requests.patch(
        f'https://api.github.com/gists/{GIST_ID}',
        headers={'Authorization': f'token {GH_TOKEN}', 'Accept': 'application/vnd.github.v3+json'},
        json={
            'files': {
                'products.json':      {'content': json.dumps(products, indent=2, ensure_ascii=False)},
                'subscriptions.json': {'content': json.dumps(subs, indent=2)},
            }
        },
        timeout=15
    )
    r.raise_for_status()

# ── Price parsing ────────────────────────────────────────────────────────────
def parse_price(text):
    """Estrae float da stringhe tipo '€29,99' o '$15.50' o '1.299,99'"""
    if not text:
        return None
    # Rimuovi simboli valuta e spazi
    s = re.sub(r'[€$£¥\s\u00a0]', '', str(text)).strip()
    # Formato europeo: 1.299,99
    if ',' in s and '.' in s:
        s = s.replace('.', '').replace(',', '.')
    elif ',' in s:
        s = s.replace(',', '.')
    m = re.search(r'\d+(?:\.\d+)?', s)
    if m:
        try:
            return float(m.group())
        except ValueError:
            pass
    return None

# ── Amazon scraping ──────────────────────────────────────────────────────────
def get_amazon_price(url):
    try:
        r = fetch_url(url)
        if r.status_code == 503:
            print('  ⚠️  Amazon: CAPTCHA/503 rilevato')
            return None
        
        soup = BeautifulSoup(r.content, 'lxml')
        
        # Selettori in ordine di priorità
        selectors = [
            'span.a-price.a-text-price.a-size-medium.apexPriceToPay span.a-offscreen',
            'span#priceblock_ourprice',
            'span#priceblock_dealprice',
            'span#priceblock_saleprice',
            '.a-price.a-text-price span.a-offscreen',
            '.a-price .a-offscreen',
            'span[data-a-color="price"] span.a-offscreen',
        ]
        
        for sel in selectors:
            el = soup.select_one(sel)
            if el:
                price = parse_price(el.get_text())
                if price and price > 0:
                    return price
        
        # Fallback: whole + fraction
        whole = soup.select_one('span.a-price-whole')
        frac  = soup.select_one('span.a-price-fraction')
        if whole:
            raw = whole.get_text().strip().replace('.', '').replace(',', '')
            if frac:
                raw += '.' + frac.get_text().strip()
            try:
                return float(raw)
            except ValueError:
                pass
        
        print(f'  ⚠️  Amazon: prezzo non trovato (status {r.status_code})')
        return None
    except Exception as e:
        print(f'  ❌ Amazon error: {e}')
        return None

# ── AliExpress scraping ──────────────────────────────────────────────────────
def get_aliexpress_price(url):
    try:
        # Estrai item ID dall'URL
        match = re.search(r'/item/(\d+)', url)
        if not match:
            print('  ⚠️  AliExpress: item ID non trovato nell\'URL')
            return None
        item_id = match.group(1)

        # Prova prima con render JS (più affidabile per AliExpress)
        r = fetch_url(url, render_js=True)
        text = r.text

        # Pattern per estrarre il prezzo dal JSON embeddato
        patterns = [
            r'"minActivityAmount"\s*:\s*"?([\d.]+)"?',
            r'"minAmount"\s*:\s*"?([\d.]+)"?',
            r'"actPrice"\s*:\s*"?([\d.]+)"?',
            r'"salePrice"\s*:\s*\{[^}]*"value"\s*:\s*"?([\d.]+)"?',
            r'"currentPrice"\s*:\s*"?([\d.]+)"?',
            r'"price"\s*:\s*\{[^}]*"value"\s*:\s*"?([\d.]+)"?',
            r'promotionPrice["\s:]+(["\']?)([\d.]+)\1',
            r'"discountedPrice"\s*:\s*"?([\d.]+)"?',
            # Pattern per prezzi in formato "€X,XX"
            r'class="[^"]*price[^"]*"[^>]*>\s*[€$]?\s*([\d,]+(?:\.\d+)?)',
        ]

        for pat in patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                # Alcuni pattern hanno 2 gruppi
                val_str = m.group(2) if m.lastindex and m.lastindex >= 2 else m.group(1)
                try:
                    v = float(val_str.replace(',', '.'))
                    if 0.01 < v < 100000:
                        print(f'  → Pattern "{pat[:30]}..." → €{v}')
                        return v
                except ValueError:
                    continue

        # Fallback BeautifulSoup
        soup = BeautifulSoup(text, 'lxml')
        for sel in [
            'span.uniform-banner-box-price',
            'div.uniform-banner-box-price',
            '.product-price-value',
            'span[class*="Price_price"]',
            'div[class*="price--"]',
            'span[class*="price"]',
        ]:
            el = soup.select_one(sel)
            if el:
                price = parse_price(el.get_text())
                if price and price > 0:
                    return price

        print('  ⚠️  AliExpress: prezzo non trovato')
        return None
    except Exception as e:
        print(f'  ❌ AliExpress error: {e}')
        return None

# ── Web Push ─────────────────────────────────────────────────────────────────
import tempfile

# Scrivi la chiave in un file temporaneo (pywebpush preferisce il path)
_vapid_key_file = tempfile.NamedTemporaryFile(mode='w', suffix='.pem', delete=False)
_vapid_key_file.write(VAPID_PRIVATE_KEY)
_vapid_key_file.close()
VAPID_KEY_PATH = _vapid_key_file.name

def send_push(subscription, title, body, url, product_id=''):
    try:
        payload = json.dumps({
            'title': title,
            'body': body,
            'url': url,
            'productId': product_id
        })
        webpush(
            subscription_info=subscription,
            data=payload,
            vapid_private_key=VAPID_KEY_PATH,
            vapid_claims={'sub': VAPID_CLAIMS_EMAIL}
        )
        print(f'  ✅ Push inviato: {title}')
    except WebPushException as e:
        status = e.response.status_code if e.response else '?'
        print(f'  ❌ Push error (HTTP {status}): {e}')
        if e.response and e.response.status_code == 410:
            return 'expired'
    except Exception as e:
        print(f'  ❌ Push error: {e}')

# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    print('🔍 PriceWatch — avvio controllo prezzi')
    print(f'   Ora: {time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())}')
    
    products, subs = gist_get()
    print(f'   {len(products)} prodotti, {len(subs)} subscription(s)')
    
    if not subs:
        print('   ⚠️  Nessuna subscription trovata, skip notifiche')
    
    if not products:
        print('   ℹ️  Nessun prodotto da controllare')
        return
    
    alerts = []
    changed = False
    
    for p in products:
        platform = p.get('platform', 'amazon')
        url      = p.get('url', '')
        target   = float(p.get('target_price', 9999))
        name     = p.get('name', 'Prodotto')
        
        print(f'\n📦 {name} [{platform}]')
        print(f'   Target: €{target:.2f}')
        
        # Pausa anti-bot
        time.sleep(random.uniform(3, 7))
        
        if platform == 'amazon':
            price = get_amazon_price(url)
        else:
            price = get_aliexpress_price(url)
        
        if price is None:
            print('   → Prezzo non disponibile')
            continue
        
        print(f'   → Attuale: €{price:.2f}')
        
        old_price = p.get('current_price')
        p['current_price'] = price
        p['last_checked']  = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        changed = True
        
        # Alert se sotto target
        if price <= target:
            last_alert = p.get('last_alert_price')
            # Invia solo se prezzo non già notificato o è sceso ulteriormente
            if last_alert is None or price < last_alert:
                print(f'   🎯 SOTTO TARGET! (era €{old_price}, alerta a €{last_alert})')
                alerts.append({
                    'id':     p.get('id', ''),
                    'name':   name,
                    'price':  price,
                    'target': target,
                    'url':    url,
                })
                p['last_alert_price'] = price
        else:
            # Reset alert se il prezzo è risalito sopra il target
            if p.get('last_alert_price') is not None:
                p['last_alert_price'] = None
    
    # Aggiorna Gist
    if changed:
        print(f'\n💾 Aggiorno Gist...')
        gist_update(products, subs)
        print('   ✅ Gist aggiornato')
    
    # Invia notifiche
    if alerts and subs:
        print(f'\n🔔 Invio {len(alerts)} alert a {len(subs)} device(s)...')
        for alert in alerts:
            title = f'Hallelujah!'
            body  = f'{alert["name"]} è sceso di prezzo!'
            for sub in subs:
                send_push(sub, title, body, alert['url'], alert['id'])
    elif alerts:
        print(f'\n⚠️  {len(alerts)} alert trovati ma nessuna subscription!')
    else:
        print('\n✅ Nessun prezzo sotto target')
    
    print('\n✅ Controllo completato')

if __name__ == '__main__':
    main()
