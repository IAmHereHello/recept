import subprocess
from pathlib import Path

import app.printing as printing
from tests.conftest import make_recipe


def test_status_disabled_without_printer(client, monkeypatch):
    monkeypatch.delenv("PRINTER_NAME", raising=False)
    assert client.get("/print/status").json() == {"enabled": False, "printer": None}


def test_status_enabled_with_printer(client, monkeypatch):
    monkeypatch.setenv("PRINTER_NAME", "recept-printer")
    assert client.get("/print/status").json() == {"enabled": True, "printer": "recept-printer"}


def test_print_without_printer_is_503(client, monkeypatch):
    monkeypatch.delenv("PRINTER_NAME", raising=False)
    recipe = make_recipe(client)
    assert client.post(f"/recipes/{recipe['id']}/print").status_code == 503


def test_print_unknown_recipe_is_404(client, monkeypatch):
    monkeypatch.setenv("PRINTER_NAME", "recept-printer")
    assert client.post("/recipes/999/print").status_code == 404


def test_print_renders_print_page_and_sends_pdf_to_lp(client, monkeypatch):
    monkeypatch.setenv("PRINTER_NAME", "recept-printer")
    monkeypatch.setenv("FRONTEND_URL", "http://localhost:3001/")
    monkeypatch.setattr(printing.shutil, "which", lambda name: f"/usr/bin/{name}")
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if cmd[0].endswith("chromium"):
            pdf = next(a for a in cmd if a.startswith("--print-to-pdf=")).split("=", 1)[1]
            Path(pdf).write_bytes(b"%PDF-1.4")
            return subprocess.CompletedProcess(cmd, 0, "", "")
        return subprocess.CompletedProcess(cmd, 0, "request id is recept-printer-7 (1 file(s))\n", "")

    monkeypatch.setattr(printing.subprocess, "run", fake_run)
    recipe = make_recipe(client)
    resp = client.post(f"/recipes/{recipe['id']}/print")

    assert resp.status_code == 200, resp.text
    assert resp.json() == {"ok": True, "job": "request id is recept-printer-7 (1 file(s))"}
    chromium, lp = calls
    assert chromium[-1] == f"http://localhost:3001/recipes/{recipe['id']}/print"
    assert lp[:3] == ["lp", "-d", "recept-printer"]
    assert lp[-1].endswith("recept.pdf")


def test_print_reports_lp_failure(client, monkeypatch):
    monkeypatch.setenv("PRINTER_NAME", "recept-printer")
    monkeypatch.setattr(printing.shutil, "which", lambda name: f"/usr/bin/{name}")

    def fake_run(cmd, **kwargs):
        if cmd[0] == "lp":
            raise subprocess.CalledProcessError(1, cmd, stderr="lp: printer offline")
        pdf = next(a for a in cmd if a.startswith("--print-to-pdf=")).split("=", 1)[1]
        Path(pdf).write_bytes(b"%PDF-1.4")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(printing.subprocess, "run", fake_run)
    recipe = make_recipe(client)
    resp = client.post(f"/recipes/{recipe['id']}/print")
    assert resp.status_code == 502
    assert "printer offline" in resp.json()["detail"]
