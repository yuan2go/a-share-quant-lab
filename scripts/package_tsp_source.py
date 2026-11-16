"""Package the standalone TSP source adapter without data or credentials."""

from pathlib import Path
import sys
import zipfile


def main():
    root = Path(__file__).resolve().parents[1] / "integrations/tsp/tushare_source"
    out = (
        Path(sys.argv[1]) if len(sys.argv) > 1 else Path("dist/aql-tushare-source.zip")
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in ["plugin.yaml", "provider.py", "client.py", "normalize.py"]:
            archive.write(root / name, arcname=name)
    print(f"created: {out} (code only)")


if __name__ == "__main__":
    main()
