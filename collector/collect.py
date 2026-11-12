#!/usr/bin/env python3
"""Recolector do Globo de Notícias: lê RSS + API do Banco de Portugal e escreve site/noticias.json.
Só biblioteca standard do Python (sem pip). Uma fonte que falhe não estraga as outras."""
import json, re, sys, unicodedata, urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from html import unescape

# ---------- CONFIGURAÇÃO (edita aqui) ----------
FEEDS = [
    # country: país fixo da fonte | cat: categoria por defeito (None = só entra se as palavras-chave a detetarem)
    {"name": "RTP Notícias",   "url": "https://www.rtp.pt/noticias/rss",                      "country": "Portugal", "cat": None},
    {"name": "BBC World",      "url": "https://feeds.bbci.co.uk/news/world/rss.xml",          "country": None,       "cat": None},
    {"name": "BBC Business",   "url": "https://feeds.bbci.co.uk/news/business/rss.xml",       "country": None,       "cat": "eco"},
]
# IDs de séries do BPstat (exemplos retirados de um laboratório do ISEG; troca pelos que quiseres em bpstat.bportugal.pt)
BPSTAT_SERIES = [12519805, 12533736]
MAX_PER_COUNTRY, MAX_AGE_DAYS = 6, 14
# -----------------------------------------------

CATS = {  # ordem = prioridade
 "fin": r"\bbanco\w*|\bbank\w*|\bjuros?\b|interest rates?|euribor|central bank|\bbce\b|\becb\b|\bfed\b|\bobrigac\w+|\bbonds?\b|\bdivida\b|\bdebt\b|\blucros?\b|\bprofits?\b|\bseguradora\w*",
 "mkt": r"\bbolsa\b|\bstocks?\b|\bshares\b|\bmercados?\b|\bmarkets?\b|\beuro\b|\bdolar\b|\bdollar\b|\bcambio\b|petroleo|\boil\b|\bouro\b|\bgold\b|\bbitcoin\b|\bcrypto\w*|\bpound\b|\bsterling\b",
 "eco": r"\beconomi\w+|\binflacao\b|\binflation\b|\bpib\b|\bgdp\b|\bcrescimento\b|\bgrowth\b|\bdesemprego\b|\bunemployment\b|\bcomercio\b|\btrade\b|\bexportac\w+|\btariffs?\b|\btarifas?\b|\borcamento\b|\bbudget\b|\brecession\b|\bimpostos?\b|\btax\w*|\bsalari\w+|\bwages?\b",
 "pol": r"\bgoverno\b|\bgovernment\b|\beleic\w+|\belections?\b|\bparlamento\b|\bparliament\b|\bpresidente\b|\bpresident\b|\bministr\w+|\bsancoes\b|\bsanctions\b|\bguerra\b|\bwar\b",
}
# aliases sem acentos, minúsculas; CS = siglas sensíveis a maiúsculas
ALIASES = {
 "Portugal": r"portugal|portugues\w*|lisboa|\bporto\b", "Estados Unidos": r"estados unidos|united states|casa branca|white house|wall street|federal reserve|reserva federal|norte-americ\w+|\bamerican\w*",
 "Reino Unido": r"reino unido|britain|british|england|bank of england|banco de inglaterra|london|londres", "Alemanha": r"alemanha|german\w*|berlim|berlin|bundesbank",
 "França": r"franca|france|french|paris", "Japão": r"japao|japan\w*|toquio|tokyo|\biene\b|\byen\b", "China": r"china|chines\w*|chinese|pequim|beijing|\byuan\b",
 "Índia": r"india|indian\w*|nova deli|new delhi|rupia|rupee", "Brasil": r"brasil|brazil\w*|brasileir\w+", "Canadá": r"canada|canadian\w*|canadiano\w*",
 "Austrália": r"australia\w*", "África do Sul": r"africa do sul|south africa\w*", "Emirados Árabes": r"emirados|emirates|dubai|abu dhabi",
 "Itália": r"italia\w*|italy|italian\w*|roma\b|rome\b", "Espanha": r"espanha|espanhol\w*|spain|spanish|madrid", "Países Baixos": r"paises baixos|holanda|netherlands|dutch|amesterdao|amsterdam|roterdao|rotterdam",
 "Suíça": r"suica|switzerland|swiss|zurique|zurich|genebra|geneva", "Rússia": r"russia\w*|moscovo|moscow|kremlin|\brublo\b|ruble", "Turquia": r"turquia|turkey|turkish|turk\w+|ancara|ankara|istambul|istanbul",
 "Arábia Saudita": r"arabia saudita|saudi\w*|riade|riyadh|opep|opec", "Coreia do Sul": r"coreia do sul|south korea\w*|seul|seoul", "Taiwan": r"taiwan\w*|taipei",
 "Indonésia": r"indonesia\w*|jacarta|jakarta", "México": r"mexico|mexican\w*|mexicano\w*", "Argentina": r"argentin\w+|buenos aires", "Singapura": r"singapura|singapore",
 "Nigéria": r"nigeria\w*|lagos", "Egito": r"egito|egypt\w*|cairo|suez",
}
CS = {"Estados Unidos": r"\bUS\b|\bUSA\b|\bU\.S\.", "Reino Unido": r"\bUK\b", "Emirados Árabes": r"\bUAE\b"}
UA = {"User-Agent": "GloboNoticias/1.0 (projeto pessoal; leitura de RSS)"}

def norm(s):
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()

def get(url, timeout=20):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return r.read()

def clean(s):
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()

def parse_date(s):
    if not s: return None
    try:
        d = parsedate_to_datetime(s)
    except Exception:
        try: d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except Exception: return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)

def parse_feed(xml_bytes):
    root = ET.fromstring(xml_bytes)
    out = []
    for it in root.iter():
        tag = it.tag.split("}")[-1]
        if tag not in ("item", "entry"): continue
        f = {c.tag.split("}")[-1]: c for c in it}
        link = (f["link"].text or f["link"].get("href") or "").strip() if "link" in f else ""
        date = (f.get("pubDate") if "pubDate" in f else f.get("updated") if "updated" in f else f.get("published"))
        out.append({"title": clean(f["title"].text) if "title" in f else "", "url": link,
                    "date": parse_date(date.text if date is not None else None)})
    return out

def classify(title):
    t = norm(title)
    for cat, rx in CATS.items():
        if re.search(rx, t): return cat
    return None

def countries_in(title):
    t, found = norm(title), []
    for c, rx in ALIASES.items():
        if re.search(r"\b(?:%s)" % rx, t): found.append(c)
    for c, rx in CS.items():
        if c not in found and re.search(rx, title): found.append(c)
    return found

def collect_news(fetch=get, now=None):
    now = now or datetime.now(timezone.utc)
    limit = now - timedelta(days=MAX_AGE_DAYS)
    by, seen, log = {}, set(), []
    for src in FEEDS:
        try:
            items = parse_feed(fetch(src["url"]))
        except Exception as e:
            log.append(f"AVISO {src['name']}: {e}"); continue
        kept = 0
        for it in items:
            if not it["title"] or not it["url"].startswith(("http://", "https://")) or it["url"] in seen: continue
            if it["date"] and it["date"] < limit: continue
            cat = classify(it["title"]) or src["cat"]
            if not cat: continue
            cs = [src["country"]] if src["country"] else countries_in(it["title"])
            for c in cs:
                by.setdefault(c, []).append({"cat": cat, "title": it["title"], "url": it["url"], "source": src["name"],
                                             "date": it["date"].isoformat() if it["date"] else None})
            if cs: seen.add(it["url"]); kept += 1
        log.append(f"{src['name']}: {len(items)} itens lidos, {kept} usados")
    for c in by:
        by[c].sort(key=lambda n: n["date"] or "", reverse=True)
        by[c] = by[c][:MAX_PER_COUNTRY]
    return by, log

BP = "https://bpstat.bportugal.pt/data/v1"
def latest_jsonstat(d):
    d = d.get("result", d) if isinstance(d.get("result"), dict) else d
    v = d["value"]
    pairs = list(v.items()) if isinstance(v, dict) else list(enumerate(v))
    pairs = [(int(k), x) for k, x in pairs if x is not None]
    idx, val = max(pairs)
    period = None
    try:
        tdim = d["role"]["time"][0]
        cat = d["dimension"][tdim]["category"]
        keys = list(cat["index"].keys()) if isinstance(cat["index"], dict) else list(cat["index"])
        k = keys[idx] if len(keys) == len(v) else keys[-1]
        period = (cat.get("label") or {}).get(k, k)
    except Exception:
        pass
    return val, period

def collect_bpstat(fetch=get):
    out, log = [], []
    for sid in BPSTAT_SERIES:
        try:
            meta = json.loads(fetch(f"{BP}/series/?lang=PT&series_ids={sid}"))[0]
            dom, ds = meta["domain_ids"][0], meta["dataset_id"]
            data = json.loads(fetch(f"{BP}/domains/{dom}/datasets/{ds}/?lang=PT&series_ids={sid}"))
            val, period = latest_jsonstat(data)
            out.append({"id": sid, "label": meta.get("label") or meta.get("name") or str(sid), "value": val, "period": period})
        except Exception as e:
            log.append(f"AVISO BPstat {sid}: {e}")
    log.append(f"BPstat: {len(out)}/{len(BPSTAT_SERIES)} séries")
    return out, log

def main(path="site/noticias.json"):
    news, l1 = collect_news()
    bp, l2 = collect_bpstat()
    print("\n".join(l1 + l2))
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"updated": datetime.now(timezone.utc).isoformat(timespec="minutes"), "countries": news, "portugal": bp},
                  f, ensure_ascii=False, indent=1)

if __name__ == "__main__":
    main(*sys.argv[1:])
