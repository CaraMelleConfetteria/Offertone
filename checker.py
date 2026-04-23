#!/usr/bin/env python3
"""
PriceWatch — checker.py
Controlla i prezzi su Amazon IT e AliExpress, invia push notification se scendono.
Gira via GitHub Actions ogni 6 ore.
"""
import os, json, re, time, random, sys
import requests
from bs4 import BeautifulSoup
from pywebpush import webpush, WebPushException

# ── Config da variabili d'ambiente ──────────────────────────────────────────
GH_TOKEN            = os.environ.get('GH_TOKEN', '')
GIST_ID             = os.environ.get('GIST_ID', '')
VAPID_PRIVATE_KEY   = os.environ.get('VAPID_PRIVATE_KEY', '')
VAPID_CLAIMS_EMAIL  = os.environ.get('VAPID_CLAIMS_EMAIL', 'mailto:pricewatch@example.com')

if not all([GH_TOKEN, GIST_ID, VAPID_PRIVATE_KEY]):
    print("❌ Variabili d'ambiente mancanti: GH_TOKEN, GIST_ID, VAPID_PRIVATE_KEY")
    sys.exit(1)

# ── Headers per scraping ────────────────────────────────────────────────────
UA_LIST = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
]

def get_headers():
    return {
        'User-Agent': random.choice(UA_LIST),
        'Accept-Language': 'it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Cache-Control': 'no-cache',
    }

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
        s = requests.Session()
        # Prima richiesta per cookie
        s.get('https://www.amazon.it', headers=get_headers(), timeout=10)
        time.sleep(random.uniform(1, 3))
        
        r = s.get(url, headers=get_headers(), timeout=15)
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
        r = requests.get(url, headers=get_headers(), timeout=15)
        text = r.text
        
        # Prova a estrarre il JSON embeddato nella pagina
        patterns = [
            r'"minActivityAmount"\s*:\s*(\d+\.?\d*)',
            r'"minAmount"\s*:\s*(\d+\.?\d*)',
            r'"salePrice"\s*:\s*\{\s*"value"\s*:\s*"?(\d+\.?\d*)',
            r'"discountedPrice"\s*:\s*"?(\d+\.?\d*)',
            r'"price"\s*:\s*\{\s*"value"\s*:\s*"?(\d+\.?\d*)',
            r'"currentPrice"\s*:\s*(\d+\.?\d*)',
            r'promotionPrice["\s:]+(\d+\.?\d*)',
            r'"actPrice"\s*:\s*(\d+\.?\d*)',
        ]
        
        for pat in patterns:
            m = re.search(pat, text)
            if m:
                v = float(m.group(1))
                if 0.01 < v < 100000:
                    return v
        
        # Fallback BeautifulSoup
        soup = BeautifulSoup(text, 'lxml')
        for sel in [
            'span.uniform-banner-box-price',
            '.product-price-value',
            'span[class*="Price"]',
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
            vapid_private_key=VAPID_PRIVATE_KEY,
            vapid_claims={'sub': VAPID_CLAIMS_EMAIL}
        )
        print(f'  ✅ Push inviato: {title}')
    except WebPushException as e:
        status = e.response.status_code if e.response else '?'
        print(f'  ❌ Push error (HTTP {status}): {e}')
        # 410 = subscription scaduta, potrebbe essere da rimuovere
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
            title = f'💰 Prezzo giù: {alert["name"]}'
            body  = f'€{alert["price"]:.2f} (target €{alert["target"]:.2f})'
            for sub in subs:
                send_push(sub, title, body, alert['url'], alert['id'])
    elif alerts:
        print(f'\n⚠️  {len(alerts)} alert trovati ma nessuna subscription!')
    else:
        print('\n✅ Nessun prezzo sotto target')
    
    print('\n✅ Controllo completato')

if __name__ == '__main__':
    main()
