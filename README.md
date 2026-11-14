# katalog-sklad
Skladové zásoby Cotton Classics (SOL'S, James & Nicholson, Myrtle Beach) pro online katalog Markmade – https://www.markmade.cz/onlinekatalog/

- `.github/workflows/sklad.yml` – GitHub Actions každé 2 hodiny (6–20 h) spustí `sklad.py`
- `sklad.py` – stáhne soubor se zásobami z FTP Cotton Classics a zapíše `cc.json` (jen kód SKU → počet kusů, žádné ceny)
- `skus.txt` – kódy SKU v katalogu (generuje `katalog-malfini/build_katalog.py`)
- přihlašovací údaje k FTP jsou jen v Settings → Secrets and variables → Actions: `CC_FTP_HOST`, `CC_FTP_USER`, `CC_FTP_PASS`
- katalog čte https://markmadecz.github.io/katalog-sklad/cc.json
