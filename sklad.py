# -*- coding: utf-8 -*-
"""Sklad Cotton Classics -> cc.json pro online katalog Markmade.

Spouští GitHub Actions (.github/workflows/sklad.yml). Přihlašovací údaje k FTP jsou v tajných údajích repozitáře
(Settings -> Secrets and variables -> Actions): CC_FTP_HOST, CC_FTP_USER, CC_FTP_PASS – nikdy se nevypisují.

Výstup cc.json obsahuje JEN kód SKU a počet kusů (žádné ceny) a jen kódy, které jsou v katalogu (skus.txt).
Do výpisu (veřejný log) jde jen název souboru, názvy sloupců a počty – žádné hodnoty ze souboru.
"""
import csv, datetime, ftplib, io, json, os, re, sys, zipfile

HOST = (os.environ.get("CC_FTP_HOST") or "service.cottonclassics.com").replace("ftp://", "").strip("/ ")
USER = os.environ.get("CC_FTP_USER", "")
PASS = os.environ.get("CC_FTP_PASS", "")
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "cc.json")

SKU_RX = re.compile(r"^(sku|artikel|artikelnummer|artnr|art[._ -]?nr|article|articleno|article[_ ]?number|itemno|item|ean_?sku)$", re.I)
QTY_RX = re.compile(r"(bestand|lager|stock|menge|qty|quantity|available|verf[uü]gbar|free|frei)", re.I)
PREFER = re.compile(r"(bestand|stock|lager|inventory|availability|verf)", re.I)
DATA_EXT = (".csv", ".txt", ".zip", ".xlsx")


def log(*a):
    print(*a, flush=True)


SKIP_DIRS = {"picture_db", "stock_upload"}      # fotky a složka pro nahrávání – nejsou to zásoby


def is_dir(ftp, path):
    here = ftp.pwd()
    try:
        ftp.cwd(path)
        return True
    except ftplib.all_errors:
        return False
    finally:
        try:
            ftp.cwd(here)
        except ftplib.all_errors:
            pass


def listing(ftp, path=""):
    """(cesta, velikost, čas) pro soubory v kořeni a o úroveň níž (server nemusí umět MLSD -> NLST + zkouška CWD)"""
    out = []
    def walk(p, depth):
        try:
            items = list(ftp.mlsd(p or "."))
        except ftplib.all_errors:
            items = []
            try:
                names = ftp.nlst(p or ".")
            except ftplib.all_errors:
                return
            for n in names:
                name = n.split("/")[-1]
                full = f"{p}/{name}" if p else name
                items.append((name, {"type": "dir" if is_dir(ftp, full) else "file"}))
        for name, facts in items:
            if name in (".", "..") or name in SKIP_DIRS:
                continue
            full = f"{p}/{name}" if p else name
            if facts.get("type") == "dir":
                if depth < 1:
                    walk(full, depth + 1)
            elif facts.get("type") in ("file", None):
                size, mod = int(facts.get("size", 0) or 0), facts.get("modify", "")
                if not mod:
                    try:
                        mod = (ftp.sendcmd(f"MDTM {full}").split() + [""])[1]
                    except ftplib.all_errors:
                        mod = ""
                out.append((full, size, mod))
    walk(path, 0)
    return out


def pick(files):
    data = [f for f in files if f[0].lower().endswith(DATA_EXT)]
    if not data:
        return None
    data.sort(key=lambda f: (bool(PREFER.search(f[0])), f[2], f[1]), reverse=True)
    return data[0][0]


def rows_from(name, raw):
    low = name.lower()
    if low.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            inner = next((n for n in z.namelist() if n.lower().endswith((".csv", ".txt", ".xlsx"))), None)
            if not inner:
                sys.exit("V zipu není CSV/TXT/XLSX.")
            log("  soubor v zipu:", inner)
            return rows_from(inner, z.read(inner))
    if low.endswith(".xlsx"):
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
        ws = wb.worksheets[0]
        return [[("" if v is None else str(v)) for v in r] for r in ws.iter_rows(values_only=True)]
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    sample = text[:20000]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=";,\t|")
    except csv.Error:
        dialect = csv.excel
        dialect.delimiter = ";" if sample.count(";") > sample.count(",") else ","
    return list(csv.reader(io.StringIO(text), dialect))


def to_int(s):
    s = str(s).strip().replace(" ", "").replace(" ", "")
    if not s:
        return None
    s = re.sub(r"[.,](\d{3})(?!\d)", r"\1", s)          # 1.234 / 1,234 -> 1234
    s = s.replace(",", ".")
    try:
        return max(0, int(float(s)))
    except ValueError:
        return None


def main():
    if not USER or not PASS:
        sys.exit("Chybí tajné údaje CC_FTP_USER / CC_FTP_PASS (Settings -> Secrets and variables -> Actions).")
    wanted = set()
    p = os.path.join(HERE, "skus.txt")
    if os.path.exists(p):
        wanted = {l.strip() for l in open(p, encoding="utf-8") if l.strip()}
    log("Kódů v katalogu:", len(wanted))
    ftp = ftplib.FTP(HOST, timeout=90)
    ftp.login(USER, PASS)
    ftp.set_pasv(True)
    files = listing(ftp)
    log(f"Souborů na FTP: {len(files)}")
    for f, size, mod in sorted(files)[:40]:
        log(f"  {f}  ({size} B, {mod})")
    name = os.environ.get("CC_FTP_FILE") or pick(files)
    if not name:
        sys.exit("Na FTP není žádný CSV/TXT/ZIP/XLSX soubor.")
    log("Vybraný soubor:", name)
    buf = io.BytesIO()
    ftp.retrbinary(f"RETR {name}", buf.write)
    ftp.quit()
    rows = [r for r in rows_from(name, buf.getvalue()) if any(c.strip() for c in r)]
    if not rows:
        sys.exit("Soubor je prázdný.")
    header = [c.strip() for c in rows[0]]
    log("Sloupce:", header)
    si = next((i for i, h in enumerate(header) if SKU_RX.match(h.replace(" ", ""))), None)
    qi = next((i for i, h in enumerate(header) if QTY_RX.search(h)), None)
    if os.environ.get("CC_SKU_COL"):
        si = header.index(os.environ["CC_SKU_COL"])
    if os.environ.get("CC_QTY_COL"):
        qi = header.index(os.environ["CC_QTY_COL"])
    if si is None or qi is None:
        # soubor bez hlavičky: sloupec s 11místným kódem + první číselný sloupec za ním
        first = rows[0]
        si = next((i for i, c in enumerate(first) if re.fullmatch(r"\d{10,13}", c.strip())), None)
        qi = next((i for i, c in enumerate(first) if i != si and re.fullmatch(r"\d{1,7}([.,]\d+)?", c.strip())), None) if si is not None else None
        if si is None or qi is None:
            sys.exit("Nepodařilo se najít sloupec s kódem a se zásobou – nastavte CC_SKU_COL a CC_QTY_COL v sklad.yml.")
        log("Soubor bez hlavičky – kód ve sloupci", si + 1, ", zásoba ve sloupci", qi + 1)
        data = rows
    else:
        log("Kód:", header[si], "| zásoba:", header[qi])
        data = rows[1:]
    stock = {}
    for r in data:
        if len(r) <= max(si, qi):
            continue
        code = r[si].strip()
        if re.fullmatch(r"\d+\.0", code):
            code = code[:-2]
        q = to_int(r[qi])
        if not code or q is None:
            continue
        if wanted and code not in wanted:
            continue
        stock[code] = stock.get(code, 0) + q
    log(f"Řádků: {len(data)} | kódů z katalogu se zásobou: {len(stock)} | skladem > 0: {sum(1 for v in stock.values() if v > 0)}")
    if wanted and len(stock) < len(wanted) * 0.2:
        sys.exit("Našlo se méně než 20 % kódů z katalogu – zřejmě jiný soubor nebo sloupec. cc.json se nemění.")
    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=2)))
    json.dump({"t": now.strftime("%d. %m. %Y %H:%M"), "src": os.path.basename(name), "n": len(stock), "v": stock},
              open(OUT, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    log("Zapsáno cc.json")


if __name__ == "__main__":
    main()
