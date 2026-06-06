#!/usr/bin/env python3
"""
Agent de recherche de voitures d'occasion
Sites : leboncoin.fr et lacentrale.fr
Auteur : Claude (Anthropic) — généré pour Anthony

Installation requise (une seule fois) :
    pip install requests beautifulsoup4 lxml playwright
    playwright install chromium
"""

import asyncio
import csv
import json
import os
import re
import sys
import time
import random
from datetime import datetime

# Force UTF-8 sur stdout/stderr (évite UnicodeEncodeError sur Windows cp1252)
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, 'reconfigure'):
    try:
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

import requests
from bs4 import BeautifulSoup

# ══════════════════════════════════════════════════════════════════════════════
#  CONFIGURATION — ajoutez / modifiez les recherches ici
#  Chaque entrée de SEARCHES = une voiture à surveiller indépendamment
# ══════════════════════════════════════════════════════════════════════════════

_TG_TOKEN   = os.environ.get("TELEGRAM_BOT_TOKEN", "8743026490:AAGXbfuTUJgoOUBbIg3V-kBcxegiRp9-Ra0")
_TG_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID",   "-5110629316")

SEARCHES = [

    # ── Recherche 1 : Toyota Auris Touring Sport Hybride Toit Pano ────────────
    {
        "nom_recherche":    "Toyota Auris Touring Sport Hybride Toit Panoramique",
        "lbc_keywords":     "toyota auris hybride",
        "lac_make_model":   "TOYOTA%3AAURIS",       # URL-encodé (: → %3A)
        "lac_option":       "TOIT_PANORAMIQUE",
        "lac_energy":       "HYBRID",
        "filtre_marque":    "auris",                # mot obligatoire dans le titre
        "filtre_carrosserie": ["touring", "break", "ts"],  # ts = titre seulement
        "filtre_pano":      ["panoramique", "toit pano", "toit ouvrant panoramique", "skyview"],
        "max_km":           250000,                  # kilométrage maximum accepté
        "csv_file":         "toyota_auris_panoramique.csv",
        "log_file":         "toyota_auris_log.txt",
        "dept_ref":         "09",                   # département de référence (Ariège)
        "telegram_token":   _TG_TOKEN,
        "telegram_chat_id": _TG_CHAT_ID,
    },

    # ── Recherche 2 : Toyota Corolla Break Hybride Toit Pano ──────────────────
    {
        "nom_recherche":    "Toyota Corolla Break Hybride Toit Panoramique",
        "lbc_keywords":     "toyota corolla break hybride",
        "lac_make_model":   "TOYOTA%3ACOROLLA",
        "lac_option":       "TOIT_PANORAMIQUE",
        "lac_energy":       "HYBRID",
        "filtre_marque":    "corolla",
        "filtre_pano":      ["panoramique", "toit pano", "toit ouvrant panoramique", "skyview"],
        "max_km":           250000,
        "csv_file":         "toyota_corolla_break.csv",
        "log_file":         "toyota_corolla_log.txt",
        "dept_ref":         "09",
        "telegram_token":   _TG_TOKEN,
        "telegram_chat_id": _TG_CHAT_ID,
    },

    # ── Recherche 3 : Tesla Model 3 Long Range ────────────────────────────────
    {
        "nom_recherche":    "Tesla Model 3 Long Range",
        "lbc_keywords":     "tesla model 3 long range",
        "lac_make_model":   "TESLA%3AMODEL+3",
        "lac_option":       "",
        "lac_energy":       "ELECTRIC",
        "filtre_marque":    "model 3",
        "filtre_carrosserie": ["long range"],        # doit mentionner "long range"
        "filtre_pano":      [],                      # pas de filtre toit pano
        "max_km":           250000,
        "csv_file":         "tesla_model3_longrange.csv",
        "log_file":         "tesla_model3_log.txt",
        "dept_ref":         "09",
        "telegram_token":   _TG_TOKEN,
        "telegram_chat_id": _TG_CHAT_ID,
    },

    # ── Recherche 4 : exemple commenté — décommentez et adaptez si besoin ─────
    # {
    #     "nom_recherche":    "Peugeot 308 SW Diesel Toit Panoramique",
    #     "lbc_keywords":     "peugeot 308 sw diesel",
    #     "lac_make_model":   "PEUGEOT%3A308",
    #     "lac_option":       "TOIT_PANORAMIQUE",
    #     "lac_energy":       "DIESEL",
    #     "filtre_marque":    "308",
    #     "filtre_carrosserie": ["sw", "break"],
    #     "filtre_pano":      ["panoramique", "toit pano", "skyview"],
    #     "max_km":           200000,
    #     "csv_file":         "peugeot_308_sw.csv",
    #     "log_file":         "peugeot_308_sw_log.txt",
    #     "dept_ref":         "09",
    #     "telegram_token":   _TG_TOKEN,
    #     "telegram_chat_id": _TG_CHAT_ID,
    # },
]

# ══════════════════════════════════════════════════════════════════════════════
#  FIN CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════════

# Variable globale active (mise à jour avant chaque recherche)
CONFIG = SEARCHES[0]

# ─── Variables globales internes (mises à jour par run_one_search) ───────────
TELEGRAM_BOT_TOKEN = CONFIG["telegram_token"]
TELEGRAM_CHAT_ID   = CONFIG["telegram_chat_id"]

OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_FILE   = os.path.join(OUTPUT_DIR, CONFIG["csv_file"])
LOG_FILE   = os.path.join(OUTPUT_DIR, CONFIG["log_file"])
CSV_FIELDS = ["source", "titre", "annee", "prix", "kilometrage", "localisation", "url", "date_trouvee"]

# ─── Utilitaires ──────────────────────────────────────────────────────────────

def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    try:
        print(line)
    except UnicodeEncodeError:
        print(line.encode('ascii', errors='replace').decode('ascii'))
    # Réessaie jusqu'à 3 fois si le fichier est temporairement verrouillé
    for attempt in range(3):
        try:
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(line + "\n")
            break
        except PermissionError:
            time.sleep(0.5)


def load_existing_urls():
    if not os.path.exists(CSV_FILE):
        return set()
    with open(CSV_FILE, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return {row["url"] for row in reader if row.get("url")}


def save_results(new_results):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    write_header = not os.path.exists(CSV_FILE)
    with open(CSV_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        if write_header:
            writer.writeheader()
        writer.writerows(new_results)


def fmt_prix(val):
    try:
        return f"{int(val):,} €".replace(",", " ")
    except (ValueError, TypeError):
        return str(val)


def fmt_km(val):
    try:
        return f"{int(val):,} km".replace(",", " ")
    except (ValueError, TypeError):
        return f"{val} km"


# ─── Distance depuis l'Ariège (département 09) ────────────────────────────────
# Priorité croissante = plus proche de l'Ariège
DIST_ARIEGE = {
    "09": 0,  "31": 1,  "11": 2,  "65": 3,  "66": 4,
    "12": 5,  "81": 6,  "82": 7,  "32": 8,  "34": 9,
    "46": 10, "48": 11, "30": 12, "47": 13, "64": 14,
    "33": 15, "40": 16, "13": 20, "84": 21, "83": 22,
    "06": 23, "38": 24, "69": 25, "63": 27, "15": 28,
    "43": 29, "07": 30, "26": 31, "16": 35, "17": 36,
    "44": 38, "75": 50, "77": 50, "78": 50, "91": 50,
    "92": 50, "93": 50, "94": 50, "95": 51, "59": 55,
}


def sort_key_annonce(row):
    """Clé de tri : proximité Ariège, puis km croissant, puis prix croissant."""
    loc  = row.get("localisation", "")
    m    = re.search(r'\((\d{2,3})\)', loc)
    dept = m.group(1)[:2] if m else "99"
    dist = DIST_ARIEGE.get(dept, 60)

    km_val = re.sub(r'[^\d]', '', row.get("kilometrage", ""))
    km_int = int(km_val) if km_val else 999_999

    prix_val = re.sub(r'[^\d]', '', row.get("prix", ""))
    prix_int = int(prix_val) if prix_val else 999_999

    return (dist, km_int, prix_int)


def is_auris(titre: str) -> bool:
    """Vérifie que l'annonce concerne bien le modèle recherché."""
    return CONFIG["filtre_marque"].lower() in titre.lower()


def is_touring_sport(titre: str, body: str = "") -> bool:
    """
    Vérifie que la carrosserie correspond aux mots-clés définis dans CONFIG["filtre_carrosserie"].
    - Liste vide [] ou clé absente → pas de filtre, toutes les annonces passent.
    - "ts" est cherché uniquement dans le titre pour éviter les faux positifs dans le body.
    - Les autres mots sont cherchés dans le titre ET la description.
    """
    filtres = CONFIG.get("filtre_carrosserie", [])
    if not filtres:
        return True   # pas de filtre = tout accepter

    titre_low = titre.lower()
    body_low  = body.lower()

    for mot in filtres:
        mot_escaped = re.escape(mot.lower())
        if mot.lower() == "ts":
            if re.search(r'\b' + mot_escaped + r'\b', titre_low):
                return True
        else:
            if re.search(r'\b' + mot_escaped + r'\b', titre_low + " " + body_low):
                return True
    return False


def trier_csv():
    """Relit le CSV, trie par proximité Ariège / km / prix, réécrit."""
    if not os.path.exists(CSV_FILE):
        return
    with open(CSV_FILE, "r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    rows.sort(key=sort_key_annonce)
    with open(CSV_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    log(f"  CSV trié ({len(rows)} annonces) : proximité Ariège → km → prix")


def nettoyer_annonces_mortes():
    """Vérifie chaque URL du CSV et supprime les annonces désactivées."""
    if not os.path.exists(CSV_FILE):
        return 0
    with open(CSV_FILE, "r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    actives    = []
    supprimees = 0
    ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36"

    log(f"  Vérification de {len(rows)} annonces en cours...")
    for row in rows:
        url = row.get("url", "")
        if not url:
            actives.append(row)
            continue

        vivante = True
        try:
            if "leboncoin.fr" in url:
                m = re.search(r'/(\d+)$', url)
                if m:
                    ad_id = m.group(1)
                    r = requests.get(
                        LBC_AD_URL.format(ad_id=ad_id),
                        headers=LBC_HEADERS, timeout=10
                    )
                    if r.status_code == 404:
                        vivante = False
                    elif r.status_code == 200:
                        status = r.json().get("status", "active")
                        if status in ("expired", "disabled", "deleted"):
                            vivante = False
            elif "lacentrale.fr" in url:
                r = requests.get(url, headers={"User-Agent": ua}, timeout=12)
                if r.status_code == 404:
                    vivante = False
                elif r.status_code == 200:
                    texte = r.text.lower()
                    if any(kw in texte for kw in ["annonce introuvable", "n'existe plus", "a été supprimée"]):
                        vivante = False
        except Exception:
            pass  # En cas d'erreur réseau, on garde l'annonce

        if vivante:
            actives.append(row)
        else:
            log(f"  🗑️  Supprimée (désactivée) : {row.get('titre','')[:70]}")
            supprimees += 1

        time.sleep(0.4)

    if supprimees > 0:
        with open(CSV_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
            writer.writeheader()
            writer.writerows(actives)
        log(f"  Nettoyage terminé : {supprimees} annonce(s) supprimée(s), {len(actives)} restantes")
    else:
        log(f"  Nettoyage terminé : toutes les {len(actives)} annonces sont encore actives")

    return supprimees


# ─── Telegram ─────────────────────────────────────────────────────────────────

def send_telegram(message: str):
    """Envoie un message dans le groupe Telegram. Réessaie 3 fois en cas d'erreur réseau."""
    if TELEGRAM_BOT_TOKEN == "TON_TOKEN_ICI" or TELEGRAM_CHAT_ID == "TON_CHAT_ID_ICI":
        log("⚠️  Telegram non configuré — modifie TELEGRAM_BOT_TOKEN et TELEGRAM_CHAT_ID dans le script.")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id":    TELEGRAM_CHAT_ID,
        "text":       message,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }
    for attempt in range(1, 4):  # 3 tentatives
        # Essai 1 : avec vérification SSL normale ; Essai 2-3 : sans vérification (antivirus/proxy)
        verify_ssl = (attempt == 1)
        try:
            import urllib3
            if not verify_ssl:
                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            r = requests.post(url, json=payload, timeout=20, verify=verify_ssl)
            if r.status_code == 200:
                log("  ✅ Message Telegram envoyé")
                return
            else:
                log(f"  ⚠️  Telegram HTTP {r.status_code} : {r.text[:300]}")
                return  # erreur HTTP = inutile de réessayer
        except Exception as e:
            log(f"  ⚠️  Telegram tentative {attempt}/3 échouée : {e}")
            if attempt < 3:
                time.sleep(3)
    log("  ❌ Telegram : impossible d'envoyer le message après 3 tentatives.")


def send_telegram_csv(caption: str = ""):
    """Envoie le fichier CSV complet en pièce jointe sur Telegram."""
    if TELEGRAM_BOT_TOKEN == "TON_TOKEN_ICI" or TELEGRAM_CHAT_ID == "TON_CHAT_ID_ICI":
        return
    if not os.path.exists(CSV_FILE):
        log("  ⚠️  CSV introuvable, impossible de l'envoyer.")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendDocument"
    for attempt in range(1, 4):
        verify_ssl = (attempt == 1)
        try:
            import urllib3
            if not verify_ssl:
                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            with open(CSV_FILE, "rb") as f:
                r = requests.post(
                    url,
                    data={"chat_id": TELEGRAM_CHAT_ID, "caption": caption},
                    files={"document": (os.path.basename(CSV_FILE), f, "text/csv")},
                    timeout=30,
                    verify=verify_ssl,
                )
            if r.status_code == 200:
                log("  ✅ CSV envoyé sur Telegram")
                return
            else:
                log(f"  ⚠️  Telegram CSV HTTP {r.status_code} : {r.text[:200]}")
                return
        except Exception as e:
            log(f"  ⚠️  Telegram CSV tentative {attempt}/3 échouée : {e}")
            if attempt < 3:
                time.sleep(3)
    log("  ❌ Telegram CSV : impossible d'envoyer après 3 tentatives.")


def notify_nouvelles_annonces(new_results: list, total_connues: int = 0):
    """Formate et envoie les nouvelles annonces sur Telegram, puis envoie le CSV complet."""
    if not new_results:
        msg_rien = (
            f"✅ <b>Recherche terminée</b> — {CONFIG['nom_recherche']}\n"
            f"📅 {datetime.now().strftime('%d/%m/%Y à %H:%M')}\n\n"
            f"Aucune nouvelle annonce depuis la dernière recherche.\n"
            f"📋 Total annonces connues : {total_connues}"
        )
        send_telegram(msg_rien)
        time.sleep(1)
        send_telegram_csv(caption=f"📋 Liste complète — {total_connues} annonces")
        return

    header = (
        f"🚗 <b>{len(new_results)} nouvelle(s) annonce(s)</b> — {CONFIG['nom_recherche']}\n"
        f"📅 {datetime.now().strftime('%d/%m/%Y à %H:%M')}\n"
    )

    messages = [header]
    current_msg = header

    for r in new_results:
        bloc = (
            f"\n{'─'*30}\n"
            f"📌 <b>{r['titre']}</b>\n"
            f"📅 Année        : {r['annee'] or 'N/A'}\n"
            f"💶 Prix         : {r['prix'] or 'N/A'}\n"
            f"🛣️  Kilométrage  : {r['kilometrage'] or 'N/A'}\n"
            f"📍 Localisation : {r['localisation'] or 'N/A'}\n"
            f"🔗 {r['url']}\n"
        )

        # Telegram limite : 4096 caractères par message
        if len(current_msg) + len(bloc) > 3800:
            messages.append(current_msg)
            current_msg = bloc
        else:
            current_msg += bloc

    messages.append(current_msg)

    # Envoyer chaque message (on saute le premier qui est vide ou le header déjà inclus)
    for msg in messages:
        if msg.strip():
            send_telegram(msg)
            time.sleep(0.5)  # petite pause entre les messages

    # Envoyer le CSV complet en pièce jointe
    time.sleep(1)
    send_telegram_csv(caption=f"📋 Liste complète mise à jour — {len(new_results)} nouvelle(s) sur {total_connues} total")


# ══════════════════════════════════════════════════════════════════════════════
#  LEBONCOIN — Playwright (vrai navigateur Chromium, contourne anti-bot)
#  L'API mobile et le scraping HTML simple retournent 403 depuis juin 2026.
# ══════════════════════════════════════════════════════════════════════════════

def has_panoramique(ad, body_text):
    """
    Détecte la mention d'un toit panoramique dans :
    - les attributs structurés de l'API
    - le titre de l'annonce
    - la description (body)
    """
    keywords = CONFIG.get("filtre_pano", [])
    if not keywords:
        return True   # pas de filtre panoramique = tout accepter

    # Attributs API
    for attr in ad.get("attributes", []):
        val = str(attr.get("value", "")).lower()
        key = str(attr.get("key", "")).lower()
        for kw in keywords:
            if kw in val or kw in key:
                return True

    # Titre
    titre = ad.get("subject", "").lower()
    for kw in keywords:
        if kw in titre:
            return True

    # Description
    if body_text:
        bt = body_text.lower()
        for kw in keywords:
            if kw in bt:
                return True

    return False


async def scrape_leboncoin_async():
    from playwright.async_api import async_playwright

    log("=== Leboncoin.fr — démarrage (Playwright/Chromium) ===")
    results       = []
    existing_urls = load_existing_urls()

    kw_encoded = CONFIG["lbc_keywords"].replace(" ", "+")
    # fuel=3 (hybride) supprimé : le code a changé côté LBC, les keywords suffisent
    search_url = f"https://www.leboncoin.fr/recherche?category=2&text={kw_encoded}"

    async with async_playwright() as p:
        # headless=False : contourne le challenge Cloudflare de LeBonCoin.
        # Une fenêtre Chrome s'ouvre brièvement pendant la recherche — c'est normal.
        browser = await p.chromium.launch(
            headless=False,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--start-maximized",
            ]
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1366, "height": 768},
            locale="fr-FR",
            timezone_id="Europe/Paris",
            extra_http_headers={"Accept-Language": "fr-FR,fr;q=0.9"},
        )
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'plugins',   { get: () => [1, 2, 3] });
            window.chrome = { runtime: {} };
        """)

        page = await context.new_page()

        # ── Warm-up : page d'accueil ──────────────────────────────────────────
        log("  Chargement accueil LeBonCoin...")
        try:
            await page.goto("https://www.leboncoin.fr/", wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(random.randint(2000, 4000))

            # Accepter les cookies
            for selector in [
                "button:has-text('Tout accepter')",
                "button:has-text('Accepter')",
                "#didomi-notice-agree-button",
                "[data-testid='cookie-accept']",
            ]:
                try:
                    btn = page.locator(selector)
                    if await btn.count() > 0:
                        await btn.first.click()
                        await page.wait_for_timeout(1000)
                        log("  Cookies acceptés")
                        break
                except Exception:
                    pass
        except Exception as e:
            log(f"  Avertissement accueil LBC : {e}")

        # ── Intercepter les réponses réseau contenant les annonces ───────────
        captured_ads = []

        async def on_response(response):
            try:
                url = response.url
                if response.status != 200:
                    return
                ct = response.headers.get("content-type", "")
                if "json" not in ct:
                    return
                # LBC appelle son API interne adfinder ou search
                if any(kw in url for kw in ["adfinder", "/search", "listing", "ads"]):
                    data = await response.json()
                    found = data.get("ads", data.get("data", {}).get("ads", []) if isinstance(data.get("data"), dict) else [])
                    if found:
                        captured_ads.extend(found)
                        log(f"  Capturé {len(found)} annonces depuis : {url[:100]}")
            except Exception:
                pass

        page.on("response", on_response)

        # ── Page de recherche ─────────────────────────────────────────────────
        log("  Chargement résultats de recherche LBC...")
        try:
            await page.goto(search_url, wait_until="networkidle", timeout=60000)
            await page.wait_for_timeout(random.randint(3000, 5000))
        except Exception as e:
            log(f"  Erreur chargement recherche LBC : {e}")
            await browser.close()
            return results

        ads = captured_ads
        log(f"  {len(ads)} annonces capturées via réseau")

        # ── Fallback __NEXT_DATA__ si l'interception n'a rien donné ──────────
        if not ads:
            html = await page.content()
            m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
            if m:
                try:
                    nd  = json.loads(m.group(1))
                    ads = (nd.get("props", {})
                              .get("pageProps", {})
                              .get("searchData", {})
                              .get("ads", []))
                    log(f"  {len(ads)} annonces via __NEXT_DATA__ (fallback)")
                except Exception as e:
                    log(f"  Erreur parsing __NEXT_DATA__ LBC : {e}")

        # ── Fallback final : liens dans le DOM ────────────────────────────────
        if not ads:
            log("  Fallback DOM : extraction des liens...")
            html     = await page.content()
            soup     = BeautifulSoup(html, "lxml")
            ad_links = []
            for a in soup.find_all("a", href=re.compile(r'/ad/voitures/\d+')):
                href = a["href"]
                full = f"https://www.leboncoin.fr{href}" if href.startswith("/") else href
                if full not in ad_links:
                    ad_links.append(full)
            log(f"  {len(ad_links)} liens d'annonces trouvés (DOM)")

            for ad_url in ad_links[:50]:
                if ad_url in existing_urls:
                    log(f"  (déjà connue) {ad_url}")
                    continue
                await page.wait_for_timeout(random.randint(1200, 2500))
                try:
                    await page.goto(ad_url, wait_until="domcontentloaded", timeout=30000)
                    await page.wait_for_timeout(random.randint(800, 1500))
                    ad_html  = await page.content()
                    soup_d   = BeautifulSoup(ad_html, "lxml")
                    full_txt = soup_d.get_text(" ", strip=True)

                    h1    = soup_d.find("h1")
                    titre = h1.get_text(strip=True) if h1 else ""

                    if not is_auris(titre):
                        log(f"  (pas le bon modèle) {titre[:70]}")
                        continue
                    if not has_panoramique({}, full_txt):
                        log(f"  (pas pano) {titre[:70]}")
                        continue
                    if not is_touring_sport(titre, full_txt):
                        log(f"  (pas Touring Sport) {titre[:70]}")
                        continue

                    prix, annee, km, lieu = "", "", "", ""
                    m_prix = re.search(r'([\d][\d\s]{2,})\s*€', full_txt)
                    if m_prix:
                        val = m_prix.group(1).replace(" ", "")
                        try:
                            if 1000 < int(val) < 100000:
                                prix = fmt_prix(int(val))
                        except ValueError:
                            pass
                    m_year = re.search(r'\b(20\d{2})\b', full_txt)
                    if m_year:
                        annee = m_year.group(1)
                    m_km = re.search(r'([\d][\d\s]{2,})\s*km', full_txt, re.IGNORECASE)
                    if m_km:
                        val = m_km.group(1).replace(" ", "")
                        try:
                            km = fmt_km(int(val))
                        except ValueError:
                            km = m_km.group(0).strip()
                    m_loc = re.search(r'([A-ZÀ-Ÿa-zà-ÿ\-]+(?:\s[A-ZÀ-Ÿa-zà-ÿ\-]+)*)\s*\((\d{2})\)', full_txt)
                    if m_loc:
                        lieu = f"{m_loc.group(1)} ({m_loc.group(2)})"

                    max_km = CONFIG.get("max_km", None)
                    if max_km is not None and km:
                        km_num = re.sub(r'[^\d]', '', km)
                        if km_num and int(km_num) > max_km:
                            log(f"  (km trop élevé : {km}) {titre[:60]}")
                            continue

                    results.append({
                        "source":       "leboncoin.fr",
                        "titre":        titre,
                        "annee":        annee,
                        "prix":         prix,
                        "kilometrage":  km,
                        "localisation": lieu,
                        "url":          ad_url,
                        "date_trouvee": datetime.now().strftime("%Y-%m-%d"),
                    })
                    log(f"  ✔ TROUVÉ : {titre} | {annee} | {prix} | {km} | {lieu}")
                except Exception as e:
                    log(f"  Erreur annonce LBC : {e}")

            await browser.close()
            log(f"=== Leboncoin : {len(results)} annonce(s) ===")
            return results

        # ── Traitement des annonces __NEXT_DATA__ ─────────────────────────────
        log(f"  Analyse de {len(ads)} annonces...")
        for ad in ads:
            ad_id = str(ad.get("list_id", ""))
            if not ad_id:
                continue

            ad_url = f"https://www.leboncoin.fr/ad/voitures/{ad_id}"
            if ad_url in existing_urls:
                log(f"  (déjà connue) {ad_url}")
                continue

            titre = ad.get("subject", "")
            if not is_auris(titre):
                log(f"  (pas le bon modèle) {titre[:70]}")
                continue

            # Body depuis les données JSON de la liste
            body = ad.get("body", "")

            # Si le body est absent, visiter la page de l'annonce
            if not body:
                await page.wait_for_timeout(random.randint(800, 1800))
                try:
                    await page.goto(ad_url, wait_until="domcontentloaded", timeout=30000)
                    await page.wait_for_timeout(random.randint(700, 1300))
                    ad_html = await page.content()
                    m_nd = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', ad_html, re.DOTALL)
                    if m_nd:
                        nd2    = json.loads(m_nd.group(1))
                        props  = nd2.get("props", {}).get("pageProps", {})
                        ad_obj = props.get("ad") or props.get("adView", {}).get("data") or {}
                        body   = ad_obj.get("body", "")
                    if not body:
                        soup_d = BeautifulSoup(ad_html, "lxml")
                        body   = soup_d.get_text(" ", strip=True)
                except Exception as e:
                    log(f"  Erreur body annonce LBC : {e}")

            if not has_panoramique(ad, body):
                log(f"  (pas pano) {titre[:70]}")
                continue

            if not is_touring_sport(titre, body):
                log(f"  (pas Touring Sport) {titre[:70]}")
                continue

            # Extraction des champs
            price_list = ad.get("price", [])
            prix = fmt_prix(price_list[0]) if price_list else ""

            location = ad.get("location", {})
            city = location.get("city", "")
            zip_ = str(location.get("zipcode", ""))
            lieu = f"{city} ({zip_[:2]})" if city and zip_ else city

            annee, km = "", ""
            for attr in ad.get("attributes", []):
                key = attr.get("key", "")
                val = str(attr.get("value", ""))
                if key == "regdate" and not annee:
                    annee = val[:4]
                elif key == "mileage" and not km:
                    km = fmt_km(val)

            max_km = CONFIG.get("max_km", None)
            if max_km is not None and km:
                km_num = re.sub(r'[^\d]', '', km)
                if km_num and int(km_num) > max_km:
                    log(f"  (km trop élevé : {km}) {titre[:60]}")
                    continue

            results.append({
                "source":       "leboncoin.fr",
                "titre":        titre,
                "annee":        annee,
                "prix":         prix,
                "kilometrage":  km,
                "localisation": lieu,
                "url":          ad_url,
                "date_trouvee": datetime.now().strftime("%Y-%m-%d"),
            })
            log(f"  ✔ TROUVÉ : {titre} | {annee} | {prix} | {km} | {lieu}")

        await browser.close()

    log(f"=== Leboncoin : {len(results)} annonce(s) ===")
    return results


def scrape_leboncoin():
    return asyncio.run(scrape_leboncoin_async())


# ══════════════════════════════════════════════════════════════════════════════
#  LA CENTRALE — Playwright (vrai navigateur Chromium, contourne anti-bot)
# ══════════════════════════════════════════════════════════════════════════════

async def scrape_lacentrale_async():
    from playwright.async_api import async_playwright

    log("=== La Centrale.fr — démarrage (Playwright/Chromium) ===")
    results      = []
    existing_urls = load_existing_urls()

    search_url = (
        "https://www.lacentrale.fr/listing"
        f"?makesModelsCommercialNames={CONFIG['lac_make_model']}"
        f"&options={CONFIG['lac_option']}"
        f"&energy={CONFIG['lac_energy']}"
    )

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--disable-infobars",
            ]
        )

        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1366, "height": 768},
            locale="fr-FR",
            timezone_id="Europe/Paris",
            extra_http_headers={"Accept-Language": "fr-FR,fr;q=0.9"},
        )

        # Masquer les indicateurs Playwright
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'plugins',   { get: () => [1, 2, 3] });
            window.chrome = { runtime: {} };
        """)

        page = await context.new_page()

        # ── Warm-up : page d'accueil ──────────────────────────────────────────
        log("  Chargement accueil La Centrale...")
        try:
            await page.goto("https://www.lacentrale.fr/", wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(random.randint(2000, 4000))

            # Accepter les cookies
            for selector in [
                "button:has-text('Tout accepter')",
                "button:has-text('Accepter')",
                "#didomi-notice-agree-button",
                "[data-testid='cookie-accept']",
            ]:
                try:
                    btn = page.locator(selector)
                    if await btn.count() > 0:
                        await btn.first.click()
                        await page.wait_for_timeout(1000)
                        log("  Cookies acceptés")
                        break
                except Exception:
                    pass
        except Exception as e:
            log(f"  Avertissement accueil : {e}")

        # ── Page de recherche ─────────────────────────────────────────────────
        log("  Chargement résultats de recherche...")
        try:
            await page.goto(search_url, wait_until="domcontentloaded", timeout=45000)
            await page.wait_for_timeout(random.randint(2000, 3500))
        except Exception as e:
            log(f"  Erreur chargement recherche : {e}")
            await browser.close()
            return results

        html = await page.content()
        soup = BeautifulSoup(html, "lxml")

        # Collecter les liens d'annonces
        ad_links = []
        for a in soup.find_all("a", href=re.compile(r"/auto-occasion-annonce-")):
            href = a["href"]
            full = f"https://www.lacentrale.fr{href}" if href.startswith("/") else href
            if full not in ad_links:
                ad_links.append(full)

        log(f"  {len(ad_links)} annonces trouvées")

        # ── Visiter chaque annonce ────────────────────────────────────────────
        for ad_url in ad_links[:40]:
            if ad_url in existing_urls:
                log(f"  (déjà connue) {ad_url}")
                continue

            await page.wait_for_timeout(random.randint(1500, 3000))

            try:
                await page.goto(ad_url, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(random.randint(1000, 2000))
            except Exception as e:
                log(f"  Erreur annonce : {e}")
                continue

            detail_html = await page.content()
            soup_d = BeautifulSoup(detail_html, "lxml")
            text   = soup_d.get_text(" ", strip=True)

            # Titre
            h1    = soup_d.find("h1")
            titre = h1.get_text(strip=True) if h1 else ""
            if not titre:
                t = soup_d.find("title")
                titre = t.get_text(strip=True) if t else ad_url

            # Vérifier que c'est bien une Auris
            if not is_auris(titre):
                log(f"  (pas une Auris) {titre[:70]}")
                continue

            # Vérifier que c'est bien une Touring Sport / break (pas une berline)
            if not is_touring_sport(titre, text):
                log(f"  (pas Touring Sport) {titre[:70]}")
                continue

            # Prix
            prix = ""
            for tag in soup_d.find_all(string=re.compile(r"\d[\d\s]{2,}\s*€")):
                m = re.search(r"([\d][\d\s]*)\s*€", tag)
                if m:
                    val = m.group(1).replace(" ", "")
                    try:
                        if 1000 < int(val) < 100000:
                            prix = fmt_prix(int(val))
                            break
                    except ValueError:
                        pass

            # Année
            annee = ""
            m = re.search(r'\b(20\d{2})\b', text)
            if m:
                annee = m.group(1)

            # Kilométrage
            km = ""
            m = re.search(r'([\d][\d\s]{2,})\s*km', text, re.IGNORECASE)
            if m:
                val = m.group(1).replace(" ", "")
                try:
                    km = fmt_km(int(val))
                except ValueError:
                    km = m.group(0).strip()

            # Localisation
            lieu = ""
            for sel in [
                soup_d.find(class_=re.compile(r'location', re.I)),
                soup_d.find(class_=re.compile(r'city',     re.I)),
                soup_d.find(attrs={"data-cy": "location"}),
            ]:
                if sel:
                    lieu = sel.get_text(strip=True)
                    if lieu:
                        break
            if not lieu:
                m = re.search(r'([A-ZÀ-Ÿa-zà-ÿ\-]+(?:\s[A-ZÀ-Ÿa-zà-ÿ\-]+)*)\s*\((\d{2})\)', text)
                if m:
                    lieu = f"{m.group(1)} ({m.group(2)})"

            results.append({
                "source":       "lacentrale.fr",
                "titre":        titre,
                "annee":        annee,
                "prix":         prix,
                "kilometrage":  km,
                "localisation": lieu,
                "url":          ad_url,
                "date_trouvee": datetime.now().strftime("%Y-%m-%d"),
            })
            log(f"  ✔ {titre} | {annee} | {prix} | {km} | {lieu}")

        await browser.close()

    log(f"=== La Centrale : {len(results)} annonce(s) ===")
    return results


def scrape_lacentrale():
    return asyncio.run(scrape_lacentrale_async())


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════════

def run_one_search(search_config: dict):
    """Exécute une recherche complète pour une configuration donnée."""
    global CONFIG, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, CSV_FILE, LOG_FILE

    # Activer cette configuration
    CONFIG             = search_config
    TELEGRAM_BOT_TOKEN = CONFIG["telegram_token"]
    TELEGRAM_CHAT_ID   = CONFIG["telegram_chat_id"]
    CSV_FILE           = os.path.join(OUTPUT_DIR, CONFIG["csv_file"])
    LOG_FILE           = os.path.join(OUTPUT_DIR, CONFIG["log_file"])

    nom   = CONFIG["nom_recherche"]
    bord  = "═" * (len(nom) + 4)
    log(f"╔{bord}╗")
    log(f"║  {nom}  ║")
    log(f"╚{bord}╝")

    # ── Nettoyage des annonces désactivées ────────────────────────────────────
    log("Vérification des annonces existantes...")
    nettoyer_annonces_mortes()

    existing_urls = load_existing_urls()
    log(f"Annonces actives connues : {len(existing_urls)}")

    all_results = []

    try:
        lbc = scrape_leboncoin()
        all_results.extend(lbc)
    except Exception as e:
        log(f"Leboncoin — erreur critique : {e}")

    # La Centrale désactivée — recherche leboncoin uniquement
    # log("Pause entre les deux sites...")
    # time.sleep(random.uniform(3, 6))
    # try:
    #     lac = scrape_lacentrale()
    #     all_results.extend(lac)
    # except Exception as e:
    #     log(f"La Centrale — erreur critique : {e}")

    new_results = [r for r in all_results if r["url"] not in existing_urls]

    if new_results:
        save_results(new_results)

    trier_csv()

    log("")
    log("══════════════════ RÉSUMÉ ══════════════════")
    log(f"Total trouvées : {len(all_results)}")
    log(f"Nouvelles      : {len(new_results)}")
    log(f"Déjà connues   : {len(all_results) - len(new_results)}")

    if new_results:
        log("")
        log("🆕 NOUVELLES ANNONCES :")
        for r in new_results:
            log(f"  [{r['source']}]")
            log(f"    Titre        : {r['titre']}")
            log(f"    Année        : {r['annee']}")
            log(f"    Prix         : {r['prix']}")
            log(f"    Kilométrage  : {r['kilometrage']}")
            log(f"    Localisation : {r['localisation']}")
            log(f"    URL          : {r['url']}")
            log("")
    else:
        log("Aucune nouvelle annonce depuis la dernière recherche.")

    log(f"Résultats sauvegardés dans : {CSV_FILE}")
    log("════════════════════════════════════════════")

    notify_nouvelles_annonces(new_results, total_connues=len(existing_urls) + len(new_results))
    return new_results


def main():
    """Lance toutes les recherches définies dans SEARCHES."""
    for i, search_config in enumerate(SEARCHES):
        if i > 0:
            log("⏳ Pause entre les recherches...")
            import time as _t
            _t.sleep(random.uniform(5, 10))
        run_one_search(search_config)


if __name__ == "__main__":
    main()
