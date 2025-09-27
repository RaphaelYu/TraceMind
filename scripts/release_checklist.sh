#!/usr/bin/env bash
set -euo pipefail

have_build=true
python3 -m build --help >/dev/null 2>&1 || have_build=false
have_twine=true
python3 -m twine --help >/dev/null 2>&1 || have_twine=false

if [[ $have_build == false || $have_twine == false ]]; then
  echo "[release-checklist] Missing required packaging tools (build and/or twine)."
  echo "[release-checklist] This is common on offline environments."
  echo "[release-checklist] Install locally via: python -m pip install -U build twine"
  echo "[release-checklist] or run the GitHub Actions workflow: Package Check."
  exit 0
fi

rm -rf dist
python3 -m build
python3 -m twine check dist/*

python3 - <<'PY'
import glob, tarfile, zipfile
from pathlib import Path
out = Path("housekeeping/pkg-contents.txt")
out.parent.mkdir(parents=True, exist_ok=True)
with out.open("w", encoding="utf-8") as fh:
    for wheel in glob.glob("dist/*.whl"):
        z = zipfile.ZipFile(wheel)
        fh.write(f"== WHEEL {wheel} ==\n")
        fh.write("\n".join(z.namelist()) + "\n")
    for sdist in glob.glob("dist/*.tar.gz"):
        fh.write(f"== SDIST {sdist} ==\n")
        with tarfile.open(sdist, "r:gz") as tar:
            fh.write("\n".join(m.name for m in tar.getmembers()) + "\n")
print("wrote housekeeping/pkg-contents.txt")
PY

PYTHON_BIN=$(command -v python3)
echo "[release-checklist] Build completed using ${PYTHON_BIN}."
