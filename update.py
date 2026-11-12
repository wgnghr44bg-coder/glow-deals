"""Haalt Charlotte Tilbury-prijzen op bij webwinkels die naar Nederland leveren en schrijft docs/data.json.

Elke winkel staat los: lukt het ophalen bij een winkel niet, dan blijven de vorige prijzen van die winkel
staan (met de oude datum), zodat de site nooit leeg raakt.

Gebruik: python update.py            (alle winkels)
         python update.py notino     (alleen deze winkel, om te testen)
"""

import html
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

DATA = Path(__file__).parent / "docs" / "data.json"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")
HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "nl-NL,nl;q=0.9,en;q=0.8",
}
PAUZE = 3  # seconden tussen twee verzoeken bij dezelfde winkel

# Winkels: land, of het binnen de EU is (anders komen er btw/invoerkosten bij) en de startpagina voor de site.
WINKELS = {
    "ct_officieel": {"naam": "Charlotte Tilbury (officieel)", "land": "NL", "eu": True,
                     "levering": "Levert in Nederland.", "home": "https://www.charlottetilbury.com/nl"},
    "notino": {"naam": "Notino", "land": "NL", "eu": True, "levering": "Levert in Nederland.",
               "home": "https://www.notino.nl/charlotte-tilbury/"},
    "breuninger": {"naam": "Breuninger", "land": "DE", "eu": True, "levering": "Levert in Nederland (vanuit Duitsland).",
                   "home": "https://www.breuninger.com/nl/merken/charlotte-tilbury/"},
    "spacenk": {"naam": "Space NK", "land": "VK", "eu": True,
                "levering": "Levert in Nederland via de Nederlandse webshop, prijzen in euro.",
                "home": "https://www.spacenk.com/nl/merken/c/charlotte-tilbury"},
    "cultbeauty": {"naam": "Cult Beauty", "land": "VK", "eu": False,
                   "levering": "Levert in Nederland vanuit het VK; controleer bij afrekenen of er btw of invoerkosten bijkomen.",
                   "home": "https://www.cultbeauty.com/c/brands/charlotte-tilbury/"},
    "amazon_us": {"naam": "Amazon USA", "land": "VS", "eu": False,
                  "levering": "Niet elk product wordt naar Nederland verstuurd: Amazon laat dit zien bij het product. "
                              "Invoerkosten worden bij het afrekenen bijgeteld.",
                  "home": "https://www.amazon.com/s?k=charlotte+tilbury&rh=p_89%3ACharlotte+Tilbury"},
}

def haal(url):
    # curl in plaats van requests: sommige winkels (Amazon, Notino) weigeren requests maar niet curl.
    cmd = ["curl", "-s", "-L", "--compressed", "--max-time", "30", "-w", "\n%{http_code}"]
    for k, v in HEADERS.items():
        cmd += ["-H", f"{k}: {v}"]
    r = subprocess.run(cmd + [url], capture_output=True)
    tekst, _, code = r.stdout.decode("utf-8", "ignore").rpartition("\n")
    if code != "200":
        raise RuntimeError(f"HTTP {code or 'geen antwoord'} voor {url}")
    return tekst


def ld_json(tekst):
    for m in re.finditer(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', tekst, re.S):
        try:
            yield json.loads(m.group(1))
        except ValueError:
            continue


def schoon(s):
    return re.sub(r"\s+", " ", html.unescape(s or "")).strip()


def getal(s):
    """'EUR 1.234,56', '£25.00', '25,9' -> float."""
    s = re.sub(r"[^\d.,]", "", s or "")
    if not s:
        return None
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    return float(s)


# ---------- winkels ----------

def ct_officieel():
    """De officiële Nederlandse webshop zet alle producten met prijs in __NEXT_DATA__."""
    def producten(x):
        if isinstance(x, dict):
            if isinstance(x.get("price"), dict) and x.get("href") and x.get("title"):
                yield x
            for v in x.values():
                yield from producten(v)
        elif isinstance(x, list):
            for v in x:
                yield from producten(v)

    uit, gezien = [], set()
    for cat in ["best-sellers", "black-friday-beauty-deals", "magical-beauty-savings", "makeup",
                "skin-care", "setting-spray", "gifts", "new", "online-exclusives"]:
        try:
            t = haal(f"https://www.charlottetilbury.com/nl/products/{cat}")
        except RuntimeError:
            continue  # categorieën wisselen (bv. Black Friday); een ontbrekende is geen fout
        m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', t, re.S)
        if not m:
            continue
        for p in producten(json.loads(m.group(1))):
            if p["href"] in gezien:
                continue
            prijs = (p["price"].get("purchasePrice") or {}).get("value")
            if prijs is None:
                continue
            gezien.add(p["href"])
            was = (p["price"].get("listingPrice") or {}).get("value")
            img = (p.get("image") or {}).get("imageSrc")
            naam = " ".join(w[:1].upper() + w[1:].lower() for w in schoon(p["title"]).split())
            maat = re.search(r"\d+(?:[.,]\d+)?\s?(?:ml|g)\b", p.get("subtitle") or "", re.I)
            if maat and maat.group(0).lower().replace(" ", "") not in naam.lower().replace(" ", ""):
                naam += " " + maat.group(0).lower()  # zonder inhoud zijn 15 ml en 50 ml niet te onderscheiden
            if re.search(r"refill", p.get("subtitle") or "", re.I) and "refill" not in naam.lower():
                naam += " (navulling)"
            uit.append({"naam": "Charlotte Tilbury " + naam, "prijs": float(prijs), "munt": "EUR",
                        "was": float(was) if was and was > prijs else None,
                        "url": "https://www.charlottetilbury.com/nl/product/" + p["href"],
                        "img": ("https:" + img if img.startswith("//") else img) + "?w=300&fm=jpg" if img else None,
                        "voorraad": p.get("availability") != "OUT_OF_STOCK"})
        time.sleep(PAUZE)
    return uit


def notino():
    uit, pagina = [], 1
    while pagina <= 15:
        url = WINKELS["notino"]["home"] + (f"?f={pagina}-1-348509" if pagina > 1 else "")
        try:
            t = haal(url)
        except RuntimeError:
            if not uit:
                raise
            break  # Notino weigert soms volgende pagina's; houd dan wat er al is
        nieuw = 0
        for d in ld_json(t):
            for p in d.get("mainEntity", []) if isinstance(d, dict) else []:
                o = p.get("offers") or {}
                prijs = o.get("price") or o.get("lowPrice")
                if prijs is None:
                    continue
                uit.append({"naam": schoon(p["name"]), "prijs": float(prijs), "munt": o.get("priceCurrency", "EUR"),
                            "url": o.get("url") or p.get("url"), "img": p.get("image"),
                            "voorraad": "OutOfStock" not in str(o.get("availability", ""))})
                nieuw += 1
        if nieuw < 20:
            break
        pagina += 1
        time.sleep(PAUZE)
    return uit


def breuninger():
    uit, gezien = [], set()
    for pagina in range(1, 21):
        url = WINKELS["breuninger"]["home"] + (f"?page={pagina}" if pagina > 1 else "")
        nieuw = 0
        for d in ld_json(haal(url)):
            for x in d if isinstance(d, list) else [d]:
                if x.get("@type") != "ItemList":
                    continue
                for e in x["itemListElement"]:
                    p = e["item"]
                    u = "https://www.breuninger.com" + p["url"]
                    if u in gezien:
                        continue
                    gezien.add(u)
                    o = p.get("offers") or {}
                    uit.append({"naam": schoon(p["name"]), "prijs": float(o["price"]),
                                "munt": o.get("priceCurrency", "EUR"), "url": u,
                                "img": (p.get("image") or [None])[0], "voorraad": True})
                    nieuw += 1
        if not nieuw:
            break
        time.sleep(PAUZE)
    return uit


def spacenk():
    uit, gezien = [], set()
    for pagina in range(1, 41):  # Space NK geeft ±10 producten per keer; zonder 'page' komt steeds pagina 1
        url = ("https://www.spacenk.com/on/demandware.store/Sites-spacenkgb-Site/nl/Search-UpdateGrid"
               f"?cgid=Charlotte%20Tilbury&orderableOnly=&srule=Best_sellers_7days"
               f"&start={(pagina - 1) * 10}&sz=10&page={pagina}")
        nieuw = 0
        for blok in haal(url).split('<div class="product" data-pid=')[1:]:
            a = re.search(r'pdp-link.*?href="([^"]+)".*?>\s*([^<]+?)\s*</a>', blok, re.S)
            prijs = re.search(r'class="sales[^"]*">\s*<span class="value" content="([\d.]+)"', blok)
            if not (a and prijs) or a.group(1) in gezien:
                continue
            gezien.add(a.group(1))
            oud = re.search(r'class="strike-through[^"]*">.*?content="([\d.]+)"', blok, re.S)
            img = re.search(r'<img[^>]+src="([^"]+)"', blok)
            uit.append({"naam": "Charlotte Tilbury " + schoon(a.group(2)), "prijs": float(prijs.group(1)),
                        "munt": "EUR", "was": float(oud.group(1)) if oud else None,
                        "url": "https://www.spacenk.com" + a.group(1), "img": img and img.group(1),
                        "voorraad": "Uitverkocht" not in blok})
            nieuw += 1
        if not nieuw:
            break
        time.sleep(1)
    return uit


def cultbeauty():
    uit, gezien = [], set()
    for pagina in range(1, 11):
        url = WINKELS["cultbeauty"]["home"] + (f"?pageNumber={pagina}" if pagina > 1 else "")
        t = haal(url)
        nieuw = 0
        for blok in t.split("<product-card-wrapper")[1:]:
            pad = re.search(r'data-quicklook-url="([^"]+)"', blok)
            naam = re.search(r'data-title="([^"]+)"', blok)
            # Alleen het prijsvak: elders op de kaart staan acties als 'gratis €15-bon vanaf €65'.
            vak = " ".join(re.findall(r'<(?:p|span) class="[^"]*\b(?:price|rrp)\b[^"]*">(.*?)</(?:p|span)>', blok, re.S))
            prijs = re.findall(r"([\d.,]+)\s?€|€\s?([\d.,]+)", re.sub(r"<[^>]+>", " ", vak))
            prijs = [a or b for a, b in prijs]
            if not (pad and naam and prijs) or pad.group(1) in gezien:
                continue
            gezien.add(pad.group(1))
            bedragen = sorted({getal(x) for x in prijs})
            img = re.search(r'<img[^>]+src="([^"]+)"', blok)
            uit.append({"naam": schoon(naam.group(1)), "prijs": bedragen[0], "munt": "EUR",
                        "was": bedragen[-1] if len(bedragen) > 1 else None,
                        "url": "https://www.cultbeauty.com" + pad.group(1),
                        "img": img and html.unescape(img.group(1)), "voorraad": True})
            nieuw += 1
        if not nieuw:
            break
        time.sleep(PAUZE)
    return uit


def amazon_us():
    uit, gezien = [], set()
    for pagina in range(1, 4):
        url = WINKELS["amazon_us"]["home"] + (f"&page={pagina}" if pagina > 1 else "")
        t = haal(url)
        if "captcha" in t.lower()[:20000]:
            raise RuntimeError("Amazon vraagt om een captcha")
        for blok in re.split(r'data-component-type="s-search-result"', t)[1:]:
            asin = re.search(r'data-asin="(\w+)"', blok)
            alt = re.search(r'<img[^>]+class="s-image"[^>]+alt="([^"]+)"', blok) or \
                re.search(r'<img[^>]+alt="([^"]+)"[^>]+class="s-image"', blok)
            prijs = re.search(r'<span class="a-price"[^>]*><span class="a-offscreen">([^<]+)<', blok)
            if not (asin and alt and prijs) or asin.group(1) in gezien:
                continue
            naam = schoon(alt.group(1))
            if not naam.lower().startswith("charlotte tilbury"):
                continue  # Amazon toont ook andere merken
            gezien.add(asin.group(1))
            ruw = prijs.group(1)
            munt = "EUR" if "EUR" in ruw or "€" in ruw else "USD"
            oud = re.search(r'a-text-price"[^>]*data-a-strike="true"[^>]*><span class="a-offscreen">([^<]+)<', blok)
            img = re.search(r'<img[^>]+class="s-image"[^>]+src="([^"]+)"', blok) or \
                re.search(r'<img[^>]+src="([^"]+)"[^>]+class="s-image"', blok)
            uit.append({"naam": naam, "prijs": getal(ruw), "munt": munt, "was": getal(oud.group(1)) if oud else None,
                        "url": f"https://www.amazon.com/dp/{asin.group(1)}", "img": img and img.group(1),
                        "voorraad": True})
        time.sleep(PAUZE)
    return uit


OPHALERS = {"ct_officieel": ct_officieel, "notino": notino, "breuninger": breuninger, "spacenk": spacenk,
            "cultbeauty": cultbeauty, "amazon_us": amazon_us}


def koersen():
    """Wisselkoersen naar euro (ECB, via frankfurter.app). Valt terug op de vorige koersen."""
    try:
        r = requests.get("https://api.frankfurter.app/latest?from=EUR&to=GBP,USD", timeout=20)
        r.raise_for_status()
        return {m: 1 / v for m, v in r.json()["rates"].items()} | {"EUR": 1.0}
    except Exception as e:
        print("Wisselkoersen niet opgehaald:", e)
        return None


def main():
    alleen = sys.argv[1:]
    oud = json.loads(DATA.read_text(encoding="utf-8")) if DATA.exists() else {}
    winkels = oud.get("winkels", {})
    nu = datetime.now(timezone.utc).isoformat(timespec="minutes")

    for sleutel, ophaler in OPHALERS.items():
        if alleen and sleutel not in alleen:
            continue
        try:
            items = ophaler()
            if not items:
                raise RuntimeError("geen producten gevonden")
            winkels[sleutel] = {**WINKELS[sleutel], "bijgewerkt": nu, "fout": None, "items": items}
            print(f"{sleutel}: {len(items)} producten")
        except Exception as e:
            vorige = winkels.get(sleutel, {})
            winkels[sleutel] = {**WINKELS[sleutel], "bijgewerkt": vorige.get("bijgewerkt"),
                                "fout": str(e)[:200], "items": vorige.get("items", [])}
            print(f"{sleutel}: MISLUKT ({e}); vorige prijzen blijven staan")
        time.sleep(PAUZE)

    koers = koersen() or oud.get("koersen") or {"EUR": 1.0, "GBP": 1.17, "USD": 0.92}
    DATA.parent.mkdir(exist_ok=True)
    DATA.write_text(json.dumps({"bijgewerkt": nu, "koersen": koers, "winkels": winkels},
                               ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
