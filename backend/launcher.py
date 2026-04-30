#!/usr/bin/env python3
"""Launcher / supervisor del scanner — ejecutable único v1.

Modelo:
- Genera un bearer auto si no existe `data/bearer.txt`.
- Setea env vars para que `main()` arranque con:
    · static_dir = backend/static (sirve frontend buildeado en /)
    · frontend_bearer = bearer (inyectado como <meta> en index.html)
    · ws_idle_shutdown_s = 60 (cierre de tab → grace → shutdown)
    · api_keys = bearer (autenticación válida)
- Arranca uvicorn en thread principal.
- Abre el browser en `http://localhost:8000` con delay 1.5s.
- Cuando uvicorn exit: chequea si existe `data/restart_requested.flag`:
    · Si existe → unlink + re-arranca uvicorn (loop).
    · Si no existe → exit limpio.

Uso:

    cd backend
    python launcher.py

Para empaquetar con PyInstaller (futuro):

    pyinstaller --onefile launcher.py
"""

from __future__ import annotations

import contextlib
import os
import secrets
import sys
import threading
import time
import webbrowser
from pathlib import Path

# El launcher vive en backend/, así que el cwd debe ser backend/.
HERE = Path(__file__).resolve().parent
os.chdir(HERE)
# Aseguramos que main + módulos se puedan importar.
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))


BEARER_FILE = Path("data/bearer.txt")
RESTART_FLAG = Path("data/restart_requested.flag")
STATIC_DIR = Path("static")
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
DEFAULT_WS_IDLE_SHUTDOWN_S = 60.0


def ensure_bearer() -> str:
    """Lee `data/bearer.txt` si existe; si no, genera uno y lo guarda.

    Permisos POSIX 0600 (solo el dueño puede leer); en Windows el
    chmod se ignora silenciosamente.
    """
    BEARER_FILE.parent.mkdir(parents=True, exist_ok=True)
    if BEARER_FILE.is_file():
        token = BEARER_FILE.read_text(encoding="utf-8").strip()
        if token:
            return token
    token = "sk-" + secrets.token_urlsafe(32)
    BEARER_FILE.write_text(token + "\n", encoding="utf-8")
    with contextlib.suppress(OSError):
        os.chmod(BEARER_FILE, 0o600)
    print(f"[launcher] bearer generado · guardado en {BEARER_FILE}")
    return token


def open_browser_after(url: str, delay_s: float) -> None:
    """Abre el browser en `url` tras `delay_s` segundos.

    Corre en thread daemon — si el backend arranca rápido, el browser
    abre cuando uvicorn ya está sirviendo. Si arranca lento, el browser
    queda en "loading" hasta que el backend responde.
    """

    def _open() -> None:
        time.sleep(delay_s)
        try:
            webbrowser.open(url)
        except Exception as e:
            print(f"[launcher] no se pudo abrir browser: {e}")

    t = threading.Thread(target=_open, daemon=True)
    t.start()


def setup_env(bearer: str) -> None:
    """Setea env vars que `main()` lee via Settings."""
    os.environ.setdefault("SCANNER_API_KEYS", bearer)
    os.environ.setdefault("SCANNER_FRONTEND_BEARER_TOKEN", bearer)
    if STATIC_DIR.is_dir():
        os.environ.setdefault("SCANNER_STATIC_DIR", str(STATIC_DIR))
    else:
        print(
            f"[launcher] WARNING: {STATIC_DIR}/ no existe — "
            "el frontend buildeado no se servirá. "
            "Corré `scripts/build-launcher.sh` antes.",
        )
    os.environ.setdefault(
        "SCANNER_WS_IDLE_SHUTDOWN_S", str(DEFAULT_WS_IDLE_SHUTDOWN_S),
    )
    os.environ.setdefault("SCANNER_RESTART_FLAG_PATH", str(RESTART_FLAG))
    # En modo launcher el validator NO corre al arrancar (es lento) —
    # el usuario lo dispara desde Configuración cuando quiere.
    os.environ.setdefault("SCANNER_VALIDATOR_RUN_AT_STARTUP", "false")


def run_once(open_browser: bool = True) -> int:
    """Una iteración del supervisor: arranca main(), espera exit.

    Retorna el exit code de main(). Si uvicorn recibe SIGINT (que es
    como nuestros endpoints /system/{shutdown,restart} se autodetonan),
    asyncio propaga `KeyboardInterrupt` hasta acá — lo capturamos y
    tratamos como exit normal del subprocess. El loop de afuera decide
    si reiniciar via el flag.
    """
    if open_browser:
        url = f"http://{DEFAULT_HOST}:{DEFAULT_PORT}"
        print(f"[launcher] abriendo browser en {url}")
        open_browser_after(url, delay_s=1.5)

    # Import tardío para que `setup_env` ya haya seteado las vars.
    from main import main as scanner_main

    try:
        return scanner_main()
    except KeyboardInterrupt:
        # SIGINT esperado (Ctrl+C del usuario o autodetonación via
        # /system/shutdown|/system/restart). Exit code estándar SIGINT
        # = 130; el launcher lo trata igual que return 0 — el flag de
        # restart decide si reiniciar.
        return 130


def main() -> int:
    bearer = ensure_bearer()
    setup_env(bearer)

    print("=" * 60)
    print("Scanner V5 · launcher")
    print(f"  bearer: {bearer[:12]}…  (full en {BEARER_FILE})")
    print(f"  url:    http://{DEFAULT_HOST}:{DEFAULT_PORT}")
    print(f"  static: {STATIC_DIR if STATIC_DIR.is_dir() else '(no encontrado)'}")
    print("=" * 60)

    # Loop supervisor: si el backend pide restart (touchea el flag),
    # re-arrancamos. Si exit limpio, salimos.
    iteration = 0
    while True:
        iteration += 1
        # Solo abrir browser en la primera iteración. Restart no abre
        # un browser nuevo — el existente se reconecta al servidor.
        rc = run_once(open_browser=(iteration == 1))
        if RESTART_FLAG.is_file():
            with contextlib.suppress(OSError):
                RESTART_FLAG.unlink()
            print(f"[launcher] restart solicitado · re-arrancando (iter {iteration + 1})")
            # Pequeño delay para que el puerto se libere antes del rebind.
            time.sleep(0.5)
            continue
        print(f"[launcher] backend exit (rc={rc}) · sin flag de restart · saliendo")
        return rc


if __name__ == "__main__":
    sys.exit(main())
