#!/usr/bin/env python3
"""Recolector do Globo de Notícias: lê RSS + API do Banco de Portugal e escreve site/noticias.json.
Só biblioteca standard do Python (sem pip). Uma fonte que falhe não estraga as outras."""
import json, os, re, sys, time, unicodedata, urllib.parse, urllib.request
from urllib.parse import urlencode
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from html import unescape

# ---------- CONFIGURAÇÃO (edita aqui) ----------
FEEDS = [
    # country: país fixo | fallback: país usado se o título não mencionar nenhum | cat: categoria por defeito
    # (None = só entra se as palavras-chave detetarem finanças, mercados, economia ou política)
    {"name": "RTP Notícias",   "url": "https://www.rtp.pt/noticias/rss",                 "country": None, "fallback": "Portugal", "cat": None},
    {"name": "Observador",     "url": "https://observador.pt/feed/",                     "country": None, "fallback": "Portugal", "cat": None},
    {"name": "ECO",            "url": "https://eco.pt/feed/",                            "country": None, "fallback": "Portugal", "cat": "eco"},
    {"name": "BBC World",      "url": "https://feeds.bbci.co.uk/news/world/rss.xml",     "country": None, "fallback": None, "cat": None},
    {"name": "BBC Business",   "url": "https://feeds.bbci.co.uk/news/business/rss.xml",  "country": None, "fallback": None, "cat": "eco"},
]
# GDELT (gratuito, sem chave): pesquisas de notícias do último dia; o país vem do título. Máx. ~1 pedido por 5 s.
GDELT_QUERIES = [
    '(economy OR inflation OR GDP OR tariffs) sourcelang:english',
    '("central bank" OR "interest rates" OR bonds OR banks) sourcelang:english',
    '(stocks OR "stock market" OR currency OR oil) sourcelang:english',
    '(economia OR inflação OR bolsa OR juros) sourcelang:portuguese',
]
# Índice principal de cada país (símbolos do Yahoo Finance; None = sem fonte gratuita conhecida). Troca/acrescenta à vontade.
INDICES = {
 "Portugal": "PSI20.LS", "Estados Unidos": "^GSPC", "Reino Unido": "^FTSE", "Alemanha": "^GDAXI", "França": "^FCHI", "Japão": "^N225", "China": "000001.SS",
 "Índia": "^NSEI", "Brasil": "^BVSP", "Canadá": "^GSPTSE", "Austrália": "^AXJO", "África do Sul": "^J200.JO", "Emirados Árabes": "^FTFADGI", "Itália": "FTSEMIB.MI",
 "Espanha": "^IBEX", "Países Baixos": "^AEX", "Suíça": "^SSMI", "Rússia": "IMOEX.ME", "Turquia": "XU100.IS", "Arábia Saudita": "^TASI.SR", "Coreia do Sul": "^KS11",
 "Taiwan": "^TWII", "Indonésia": "^JKSE", "México": "^MXX", "Argentina": "^MERV", "Singapura": "^STI", "Nigéria": None, "Egito": "^CASE30",
 "Polónia": "WIG20.WA", "Suécia": "^OMX", "Noruega": "OSEBX.OL", "Dinamarca": "^OMXC25", "Irlanda": "^ISEQ", "Bélgica": "^BFX", "Áustria": "^ATX", "Grécia": "GD.AT",
 "Israel": "^TA125.TA", "Hong Kong": "^HSI", "Tailândia": "^SET.BK", "Malásia": "^KLSE", "Vietname": None, "Filipinas": "PSEI.PS", "Chile": "^IPSA", "Colômbia": "^COLCAP",
 "Peru": None, "Marrocos": None, "Quénia": None, "Paquistão": None, "Qatar": None, "Nova Zelândia": "^NZ50",
}
BROWSER_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:138.0) Gecko/20100101 Firefox/138.0"}
ECB_FX = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist-90d.xml"
# IDs de séries do BPstat (exemplos retirados de um laboratório do ISEG; troca pelos que quiseres em bpstat.bportugal.pt)
BPSTAT_SERIES = [12519805, 12533736]
MAX_PER_COUNTRY, MAX_AGE_DAYS = 8, 14
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
 "Polónia": r"polonia|poland|polish|varsovia|warsaw", "Suécia": r"suecia|sweden|swedish|estocolmo|stockholm", "Noruega": r"noruega|norway|norwegian|oslo",
 "Dinamarca": r"dinamarca|denmark|danish|copenhaga|copenhagen", "Irlanda": r"irlanda|ireland|irish|dublin|dublim", "Bélgica": r"belgica|belgium|belgian|bruxelas|brussels",
 "Áustria": r"austria\w*|viena|vienna", "Grécia": r"grecia|greece|greek|atenas|athens", "Israel": r"israel\w*|tel aviv|telavive", "Hong Kong": r"hong kong",
 "Tailândia": r"tailandia|thailand|thai|bangkok|banguecoque", "Malásia": r"malasia|malaysia\w*|kuala lumpur", "Vietname": r"vietname|vietnam\w*|hanoi",
 "Filipinas": r"filipinas|philippines|filipino|manila", "Chile": r"chile|chilean\w*|chileno\w*", "Colômbia": r"colombia\w*|bogota", "Peru": r"peru|peruvian\w*",
 "Marrocos": r"marrocos|morocco|moroccan|rabat", "Quénia": r"quenia|kenya\w*|nairobi", "Paquistão": r"paquistao|pakistan\w*|islamabad", "Qatar": r"qatar|catar|doha",
 "Nova Zelândia": r"nova zelandia|new zealand\w*",
}
CS = {"Estados Unidos": r"\bUS\b|\bUSA\b|\bU\.S\.", "Reino Unido": r"\bUK\b", "Emirados Árabes": r"\bUAE\b"}
UA = {"User-Agent": "GloboNoticias/1.0 (projeto pessoal; leitura de RSS)"}

def norm(s):
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()

def get(url, timeout=20, headers=None):
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers or UA), timeout=timeout) as r:
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

def ingest(items, src, by, seen, limit):
    kept = 0
    for it in items:
        if not it["title"] or not it["url"].startswith(("http://", "https://")) or it["url"] in seen: continue
        if it["date"] and it["date"] < limit: continue
        cat = classify(it["title"]) or src["cat"]
        if not cat: continue
        cs = [src["country"]] if src["country"] else (countries_in(it["title"]) or ([src["fallback"]] if src["fallback"] else []))
        for c in cs:
            by.setdefault(c, []).append({"cat": cat, "title": it["title"], "url": it["url"], "source": it.get("source") or src["name"],
                                         "date": it["date"].isoformat() if it["date"] else None})
        if cs: seen.add(it["url"]); kept += 1
    return kept

def gdelt_items(fetch=get, sleep=time.sleep):
    items, log = [], []
    for n, q in enumerate(GDELT_QUERIES):
        if n: sleep(6)
        try:
            url = "https://api.gdeltproject.org/api/v2/doc/doc?" + urlencode(
                {"query": q, "mode": "ArtList", "format": "json", "maxrecords": 75, "timespan": "24h", "sort": "DateDesc"})
            for a in json.loads(fetch(url)).get("articles", []):
                try: d = datetime.strptime(a["seendate"], "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
                except Exception: d = None
                items.append({"title": clean(a.get("title")), "url": a.get("url", ""), "date": d, "source": "GDELT · " + a.get("domain", "")})
        except Exception as e:
            log.append(f"AVISO GDELT consulta {n+1}: {e}")
    return items, log

def collect_news(fetch=get, now=None, gdelt=True, sleep=time.sleep):
    now = now or datetime.now(timezone.utc)
    limit = now - timedelta(days=MAX_AGE_DAYS)
    by, seen, log = {}, set(), []
    for src in FEEDS:
        try:
            items = parse_feed(fetch(src["url"]))
        except Exception as e:
            log.append(f"AVISO {src['name']}: {e}"); continue
        log.append(f"{src['name']}: {len(items)} itens lidos, {ingest(items, src, by, seen, limit)} usados")
    if gdelt:
        items, l = gdelt_items(fetch, sleep)
        log += l + [f"GDELT: {len(items)} itens lidos, {ingest(items, {'name': 'GDELT', 'country': None, 'fallback': None, 'cat': None}, by, seen, limit)} usados"]
    for c in by:
        by[c].sort(key=lambda n: n["date"] or "", reverse=True)
        by[c] = by[c][:MAX_PER_COUNTRY]
    return by, log

def sma(v, n):
    return sum(v[-n:]) / n if len(v) >= n else None

def summarize_index(ts, closes):
    pts = [(datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%d"), float(c)) for t, c in zip(ts, closes) if c is not None]
    pts = pts[-126:]
    if len(pts) < 10: raise ValueError("poucos dados")
    v = [p[1] for p in pts]
    ch = lambda n: round((v[-1] / v[-1 - n] - 1) * 100, 2) if len(v) > n else None
    m20, m50 = sma(v, 20), sma(v, 50)
    trend = None
    if m20 and m50:
        trend = "alta" if v[-1] > m50 and m20 > m50 else "baixa" if v[-1] < m50 and m20 < m50 else "lateral"
    return {"last": round(v[-1], 2), "chg": {"1d": ch(1), "1w": ch(5), "1m": ch(21), "3m": ch(63)}, "trend": trend,
            "d": [p[0] for p in pts], "v": [round(x, 2) for x in v]}

# Plano B (opcional): Stooq, com chave gratuita obtida uma vez no site (stooq.com/q/d/?s=spy.us&get_apikey) e guardada
# no GitHub como segredo STOOQ_API_KEY. Símbolos não verificados; os que falharem ficam sem gráfico.
STOOQ = {"Estados Unidos": "^spx", "Reino Unido": "^ukx", "Alemanha": "^dax", "França": "^cac", "Japão": "^nkx", "China": "^shc", "Hong Kong": "^hsi",
         "Espanha": "^ibex", "Países Baixos": "^aex", "Suíça": "^smi", "Itália": "^fmib", "Polónia": "^wig20", "Brasil": "^bvp",
         "Coreia do Sul": "^kospi", "Austrália": "^aor", "Portugal": "^psi20"}

def err_text(e):
    code = getattr(e, "code", None)
    return f"HTTP {code}" if code else (str(e)[:80] or type(e).__name__)

def fetch_yahoo(sym, fetch):
    last = None
    for host in ("query1", "query2"):
        try:
            url = "https://%s.finance.yahoo.com/v8/finance/chart/%s?range=6mo&interval=1d" % (host, urllib.parse.quote(sym))
            r = json.loads(fetch(url, headers=BROWSER_UA))["chart"]["result"][0]
            return summarize_index(r["timestamp"], r["indicators"]["quote"][0]["close"])
        except Exception as e:
            last = e
    raise last

def fetch_stooq(sym, key, fetch):
    txt = fetch("https://stooq.com/q/d/l/?" + urlencode({"s": sym, "i": "d", "apikey": key}), headers=BROWSER_UA).decode("utf-8", "ignore")
    rows = [l.split(",") for l in txt.strip().splitlines()[1:]]
    rows = [r for r in rows if len(r) >= 5 and r[4] not in ("", "null")]
    if len(rows) < 10: raise ValueError("Stooq sem dados (chave em falta ou inválida)")
    ts = [int(datetime.strptime(r[0], "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp()) for r in rows]
    return summarize_index(ts, [float(r[4]) for r in rows])

def collect_indices(fetch=get, sleep=time.sleep, stooq_key=None):
    """Histórico diário (6 meses) dos índices: Yahoo Finance (API não oficial) e, se houver chave, Stooq como plano B."""
    key = stooq_key if stooq_key is not None else os.environ.get("STOOQ_API_KEY", "")
    out, fails, first_err, streak, yahoo_dead = {}, [], None, 0, False
    for country, sym in INDICES.items():
        data = None
        if sym and not yahoo_dead:
            try:
                data = dict(fetch_yahoo(sym, fetch), sym=sym, fonte="Yahoo Finance"); streak = 0
            except Exception as e:
                first_err = first_err or err_text(e); streak += 1
                if streak >= 5 and not out: yahoo_dead = True
            sleep(0.7)
        if data is None and key and country in STOOQ:
            try:
                data = dict(fetch_stooq(STOOQ[country], key, fetch), sym=STOOQ[country], fonte="Stooq"); sleep(0.7)
            except Exception as e:
                first_err = first_err or "Stooq: " + err_text(e)
        if data: out[country] = data
        elif sym or country in STOOQ: fails.append(country)
    total = sum(1 for c, v in INDICES.items() if v or (key and c in STOOQ))
    status = {"ok": len(out), "total": total, "error": first_err, "yahoo_bloqueado": yahoo_dead}
    log = [f"Índices: {len(out)}/{total} com dados" + (f"; primeiro erro: {first_err}" if first_err else "") +
           ("; Yahoo bloqueado, a usar só Stooq" if yahoo_dead and key else "; Yahoo bloqueado (sem chave Stooq)" if yahoo_dead else "")]
    return out, log, status

def collect_fx(fetch=get):
    """Câmbios de referência do BCE (moeda por 1 EUR) e variação face ao dia anterior, em %."""
    days = []
    for el in ET.fromstring(fetch(ECB_FX)).iter():
        if el.tag.endswith("Cube") and el.get("time"):
            days.append((el.get("time"), {c.get("currency"): float(c.get("rate")) for c in el if c.get("currency")}))
    days.sort(reverse=True)
    (d0, r0), (_, r1) = days[0], days[1]
    return {k: {"rate": v, "chg": round((v / r1[k] - 1) * 100, 3) if k in r1 else 0, "date": d0} for k, v in r0.items()}

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
    try:
        fx = collect_fx(); l3 = [f"BCE: {len(fx)} moedas"]
    except Exception as e:
        fx, l3 = {}, [f"AVISO BCE: {e}"]
    idx, l4, idx_status = collect_indices()
    print("\n".join(l1 + l2 + l3 + l4))
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"updated": datetime.now(timezone.utc).isoformat(timespec="minutes"), "countries": news, "portugal": bp, "fx": fx, "idx": idx, "idx_status": idx_status},
                  f, ensure_ascii=False, indent=1)

if __name__ == "__main__":
    main(*sys.argv[1:])
