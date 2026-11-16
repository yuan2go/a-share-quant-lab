"""Run an independent official TSP checkout with all writable paths external.

Credentials are inherited from the process or read from an owner-only env file;
they are never placed in arguments, generated config, or diagnostics.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import stat
import sys


def external_path(value: str) -> Path:
    path = Path(value).expanduser().resolve()
    parent = path
    while not parent.exists():
        parent = parent.parent
    # This deployment targets a mounted macOS external volume. Fail closed if
    # unplugged, rather than silently recreating /Volumes/... on the system disk.
    if len(path.parts) < 3 or path.parts[1] != "Volumes":
        raise ValueError("TSP writable paths must be on a mounted /Volumes volume")
    volume = Path(*path.parts[:3])
    if not volume.is_mount() or parent.stat().st_dev == Path("/").stat().st_dev:
        raise ValueError("external volume is not mounted")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tsp-source", required=True)
    parser.add_argument("--python", required=True)
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--runtime-dir", required=True)
    parser.add_argument("--credential-env")
    parser.add_argument("--port", type=int, default=3018)
    args = parser.parse_args()
    source = external_path(args.tsp_source)
    python = Path(args.python).absolute()  # Preserve the virtualenv entry point.
    data = external_path(args.data_dir)
    runtime = external_path(args.runtime_dir)
    if not (source / "backend/app/main.py").is_file() or not python.is_file():
        raise ValueError("official TSP checkout / Python environment missing")
    if not 1024 <= args.port <= 65535:
        raise ValueError("invalid local port")
    env = os.environ.copy()
    if args.credential_env:
        secret = external_path(args.credential_env)
        if stat.S_IMODE(secret.stat().st_mode) & 0o077:
            raise ValueError("credential env must be owner-only (chmod 600)")
        for line in secret.read_text().splitlines():
            if not line.strip() or line.startswith("#"):
                continue
            key, value = line.split("=", 1)
            if key not in {"TUSHARE_TOKEN", "TUSHARE_HTTP_URL"}:
                raise ValueError("credential env contains an unexpected variable")
            env[key] = value
    paths = {
        "DATA_DIR": data,
        "TMPDIR": runtime / "tmp",
        "TMP": runtime / "tmp",
        "TEMP": runtime / "tmp",
        "XDG_CACHE_HOME": runtime / "cache",
        "UV_CACHE_DIR": runtime / "cache/uv",
        "PIP_CACHE_DIR": runtime / "cache/pip",
        "MPLCONFIGDIR": runtime / "cache/matplotlib",
        "JOBLIB_TEMP_FOLDER": runtime / "tmp/joblib",
        "npm_config_cache": runtime / "cache/npm",
        "PYTHONPYCACHEPREFIX": runtime / "cache/pycache",
    }
    for key, path in paths.items():
        path.mkdir(parents=True, exist_ok=True)
        env[key] = str(path)
    env.update(
        TICKFLOW_ENV_FILE=str(runtime / "empty.env"),
        BACKTEST_MATRIX_CACHE_PREWARM="false",
        POLARS_MAX_THREADS="4",
    )
    (runtime / "empty.env").touch(exist_ok=True)
    logs = runtime / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    (runtime / "process.json").write_text(
        json.dumps(
            {
                "pid": os.getpid(),
                "url": f"http://127.0.0.1:{args.port}",
                "data_dir": str(data),
                "runtime_dir": str(runtime),
                "tsp_source": str(source),
                "writable_paths": {k: str(v) for k, v in paths.items()},
            },
            indent=2,
        )
        + "\n"
    )
    with (logs / "server.log").open("a") as output:
        os.dup2(output.fileno(), 1)
        os.dup2(output.fileno(), 2)
    os.chdir(source / "backend")
    os.execve(
        str(python),
        [
            str(python),
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(args.port),
        ],
        env,
    )


if __name__ == "__main__":
    main()
