#!/usr/bin/env bash
# Build del launcher · v1
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Genera la versión "ejecutable única" del scanner:
#
#  1. Builds el frontend (pnpm build) → frontend/dist/
#  2. Copia frontend/dist/ → backend/static/  (FastAPI lo sirve en /)
#  3. Verifica que `backend/launcher.py` existe.
#
# Después del build, ejecutar:
#
#     cd backend
#     python launcher.py
#
# Para empaquetar como .exe Windows (futuro), usar PyInstaller con
# `backend/launcher.py` como entrypoint.
#
# Uso:
#     ./scripts/build-launcher.sh
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

set -euo pipefail

# Paths absolutos basados en la ubicación del script.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
FRONTEND="$REPO_ROOT/frontend"
BACKEND="$REPO_ROOT/backend"
DIST="$FRONTEND/dist"
STATIC="$BACKEND/static"

cd "$REPO_ROOT"

echo "▸ Verificando estructura del repo…"
[ -d "$FRONTEND" ] || { echo "✗ frontend/ no encontrado en $REPO_ROOT"; exit 1; }
[ -d "$BACKEND"  ] || { echo "✗ backend/  no encontrado en $REPO_ROOT"; exit 1; }
[ -f "$BACKEND/launcher.py" ] || { echo "✗ backend/launcher.py no encontrado"; exit 1; }
[ -f "$FRONTEND/package.json" ] || { echo "✗ frontend/package.json no encontrado"; exit 1; }

echo "▸ Frontend build (pnpm build)…"
cd "$FRONTEND"
if [ ! -d node_modules ]; then
  echo "  · node_modules ausente; corriendo pnpm install…"
  pnpm install
fi
pnpm build

[ -d "$DIST" ] || { echo "✗ pnpm build no generó $DIST"; exit 1; }
[ -f "$DIST/index.html" ] || { echo "✗ $DIST/index.html no existe tras el build"; exit 1; }

echo "▸ Copiando dist → backend/static…"
rm -rf "$STATIC"
mkdir -p "$STATIC"
cp -R "$DIST/." "$STATIC/"

echo ""
echo "✓ Build completo."
echo ""
echo "  Frontend buildeado:  $DIST"
echo "  Servido desde:       $STATIC"
echo ""
echo "Para arrancar el ejecutable único:"
echo ""
echo "    cd $BACKEND"
echo "    python launcher.py"
echo ""
echo "El launcher genera/lee el bearer en data/bearer.txt, arranca uvicorn"
echo "en :8000 sirviendo el frontend, y abre el browser."
