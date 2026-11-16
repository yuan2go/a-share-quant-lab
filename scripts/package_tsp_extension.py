"""Create a trusted TSP extension ZIP without embedding data/credentials/dependencies."""
from __future__ import annotations

import sys
import zipfile
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1] / "integrations" / "tsp"
    destination = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("dist/aql-tsp-extension.zip")
    destination.parent.mkdir(parents=True, exist_ok=True)
    paths = ("extension.yaml", "backend/__init__.py", "backend/extension.py", "frontend/extension.mjs")
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for item in paths:
            z.write(root / item, arcname=item)
    print(f"created: {destination} (no token/data included)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
