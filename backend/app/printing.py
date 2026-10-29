"""Direct printing from the Pi: render the frontend's /recipes/{id}/print page
to a PDF with headless Chromium, then hand it to CUPS with `lp`.

Configured through backend/.env (written by scripts/setup-printer.sh):
  PRINTER_NAME  CUPS queue to print to. Unset = direct printing disabled and
                the frontend falls back to the browser print dialog.
  FRONTEND_URL  Where the frontend is reachable from the Pi itself
                (default http://localhost:3001, the `npm run preview` port).
"""
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

CHROMIUM_CANDIDATES = ("chromium", "chromium-browser", "google-chrome")
RENDER_TIMEOUT = 60
PRINT_TIMEOUT = 30


class PrintError(Exception):
    pass


def printer_name() -> Optional[str]:
    return os.getenv("PRINTER_NAME") or None


def frontend_url() -> str:
    return (os.getenv("FRONTEND_URL") or "http://localhost:3001").rstrip("/")


def _chromium() -> str:
    for name in CHROMIUM_CANDIDATES:
        path = shutil.which(name)
        if path:
            return path
    raise PrintError("Chromium is niet geïnstalleerd op de Pi.")


def print_recipe(recipe_id: int) -> str:
    """Render and print one recipe. Returns the CUPS job line from `lp`."""
    printer = printer_name()
    if not printer:
        raise PrintError("Er is geen printer ingesteld op de Pi.")

    with tempfile.TemporaryDirectory() as tmp:
        pdf = Path(tmp) / "recept.pdf"
        # Own --user-data-dir so this never collides with a desktop Chromium
        # profile lock. --virtual-time-budget lets the page finish fetching
        # the recipe (and its photo) before the PDF is taken.
        cmd = [
            _chromium(), "--headless", "--disable-gpu", "--no-sandbox",
            f"--user-data-dir={tmp}/profile", "--no-pdf-header-footer",
            "--virtual-time-budget=15000", f"--print-to-pdf={pdf}",
            f"{frontend_url()}/recipes/{recipe_id}/print",
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True, timeout=RENDER_TIMEOUT)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            raise PrintError("Het recept kon niet naar PDF worden omgezet.") from e
        if not pdf.exists() or pdf.stat().st_size == 0:
            raise PrintError("Het recept kon niet naar PDF worden omgezet.")

        try:
            result = subprocess.run(
                ["lp", "-d", printer, "-o", "media=A4", "-t", f"Recept {recipe_id}", str(pdf)],
                check=True, capture_output=True, text=True, timeout=PRINT_TIMEOUT,
            )
        except FileNotFoundError as e:
            raise PrintError("CUPS (lp) is niet geïnstalleerd op de Pi.") from e
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            detail = getattr(e, "stderr", "") or ""
            raise PrintError(f"De printer gaf een fout. {detail}".strip()) from e
        return result.stdout.strip()
