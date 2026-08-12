"""Punto de entrada del pipeline (reemplaza el .bat con ruta hardcodeada).

Uso:
    python -m jobmatch.cli collect   # recolecta las 4 fuentes + merge
    python -m jobmatch.cli process   # analiza con IA (matcher + Gemini)
    python -m jobmatch.cli run       # todo; si quedó en pausa, solo reanuda
    python -m jobmatch.cli app       # abre el dashboard de Streamlit
"""

from __future__ import annotations

import argparse
import subprocess
import sys

from jobmatch.console import console
from jobmatch.pipeline import state


def _collect() -> None:
    from jobmatch.collectors import computrabajo, indeed, linkedin, occ
    from jobmatch.pipeline import merge

    computrabajo.run()
    occ.run()
    indeed.run()
    linkedin.run()
    merge.merge()


def _process() -> None:
    from jobmatch.pipeline.process import process_jobs

    process_jobs()


def _run() -> None:
    if state.load_status().get("status") == "Paused":
        console.warning("Análisis en pausa: reanudando sin recolectar de nuevo.")
        _process()
    else:
        _collect()
        _process()


def _app() -> None:
    subprocess.run([sys.executable, "-m", "streamlit", "run", "app.py"])


COMMANDS = {
    "collect": _collect,
    "process": _process,
    "run": _run,
    "app": _app,
}


def main() -> None:
    parser = argparse.ArgumentParser(prog="jobmatch", description="JobMatch Engine")
    parser.add_argument("command", choices=list(COMMANDS), help="Acción a ejecutar")
    args = parser.parse_args()
    COMMANDS[args.command]()


if __name__ == "__main__":
    main()
