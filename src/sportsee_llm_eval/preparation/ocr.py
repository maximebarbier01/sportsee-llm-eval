"""OCR des PDF Reddit avec l'API Mistral OCR, résultats mis en cache.

Les PDF Reddit sont des captures d'écran (aucun texte extractible). Le prototype utilisait
EasyOCR, dont la sortie est très bruitée (« rInba » pour r/nba, noms d'équipes perdus).
Mistral OCR renvoie un markdown par page, de bien meilleure qualité.

L'OCR n'est lancé qu'une fois par fichier : le résultat est écrit dans data/interim/ocr/
et relu ensuite, ce qui rend le pipeline reproductible sans nouvel appel payant
(utiliser --force pour refaire l'OCR).

Usage :
    python -m sportsee_llm_eval.preparation.ocr
"""

import argparse
import base64
import json
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from mistralai.client import Mistral

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
RAW_DIR = PROJECT_ROOT / "data" / "raw"
OCR_CACHE_DIR = PROJECT_ROOT / "data" / "interim" / "ocr"
OCR_MODEL = "mistral-ocr-latest"


def cache_path(pdf_path: Path, cache_dir: Path = OCR_CACHE_DIR) -> Path:
    return cache_dir / f"{pdf_path.stem}.json"


def ocr_pdf(pdf_path: Path, client: Mistral) -> list[str]:
    """Renvoie le markdown de chaque page du PDF."""
    encoded = base64.b64encode(pdf_path.read_bytes()).decode()
    response = client.ocr.process(
        model=OCR_MODEL,
        document={
            "type": "document_url",
            "document_url": f"data:application/pdf;base64,{encoded}",
        },
    )
    return [page.markdown for page in response.pages]


def load_or_ocr(
    pdf_path: Path,
    client: Mistral | None = None,
    cache_dir: Path = OCR_CACHE_DIR,
    force: bool = False,
) -> list[str]:
    """Pages OCR du PDF : depuis le cache s'il existe, sinon via l'API (puis mise en cache)."""
    cached = cache_path(pdf_path, cache_dir)
    if cached.exists() and not force:
        return json.loads(cached.read_text(encoding="utf-8"))["pages"]
    if client is None:
        load_dotenv(PROJECT_ROOT / ".env")
        client = Mistral(api_key=os.environ["MISTRAL_API_KEY"])
    logger.info("OCR de %s (%s)...", pdf_path.name, OCR_MODEL)
    pages = ocr_pdf(pdf_path, client)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cached.write_text(
        json.dumps(
            {"source": pdf_path.name, "model": OCR_MODEL, "pages": pages},
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    logger.info("%s : %s pages -> %s", pdf_path.name, len(pages), cached)
    return pages


def reddit_pdfs(raw_dir: Path = RAW_DIR) -> list[Path]:
    return sorted(raw_dir.glob("Reddit *.pdf"))


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
    parser = argparse.ArgumentParser(description="OCR des PDF Reddit (Mistral OCR)")
    parser.add_argument(
        "--force", action="store_true", help="Refaire l'OCR même si en cache"
    )
    args = parser.parse_args()
    for pdf in reddit_pdfs():
        load_or_ocr(pdf, force=args.force)


if __name__ == "__main__":
    main()
