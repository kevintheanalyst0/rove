"""Lectura y escritura de JSON en un único lugar, con escritura atómica.

Antes había cinco implementaciones distintas de "cargar/guardar JSON"
repartidas por el proyecto, y ninguna era realmente transaccional: si el
proceso moría a mitad de escritura, el archivo quedaba corrupto.

Aquí la escritura va primero a un archivo temporal en la misma carpeta y
luego se renombra sobre el destino. `os.replace` es atómico, así que el
archivo final o queda entero y correcto, o no se toca. Nunca a medias.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def read_json(path: str | Path, default: Any = None) -> Any:
    """Lee un JSON. Devuelve `default` si no existe, está vacío o corrupto."""
    path = Path(path)

    if not path.exists():
        return default

    try:
        content = path.read_text(encoding="utf-8").strip()
    except OSError:
        return default

    if not content:
        return default

    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return default


def write_json(path: str | Path, data: Any) -> None:
    """Escribe un JSON de forma atómica (temporal + rename)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(
        dir=path.parent,
        prefix=path.name + ".",
        suffix=".tmp",
    )

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)
    except BaseException:
        # Si algo falla, se limpia el temporal y se propaga el error.
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
