"""Ayudantes de navegador (Chromium vía DrissionPage).

Solo lo importan los colectores que de verdad necesitan navegador (Indeed
y LinkedIn). OCC y Computrabajo NO lo tocan, así que siguen siendo rápidos.

Aporta dos cosas:
1. Perfil persistente configurable -> mantiene tu sesión iniciada
   (LinkedIn, Indeed) entre ejecuciones y dispara menos captcha.
2. Notificación de intervención manual: cuando aparece un captcha o un
   login, suena una alerta y aparece un banner bien visible, para que no
   tengas que estar vigilando la terminal. El captcha lo resuelves tú;
   solo dejas de estar pendiente.
"""

from __future__ import annotations

import sys

from DrissionPage import ChromiumOptions, ChromiumPage

from jobmatch import config
from jobmatch.console import console


def build_options(use_profile: bool = True) -> ChromiumOptions:
    """Opciones de Chromium. Con `use_profile` reutiliza el perfil persistente."""
    options = ChromiumOptions()
    if use_profile:
        if config.CHROME_BROWSER_PATH:
            options.set_browser_path(config.CHROME_BROWSER_PATH)
        if config.CHROME_USER_DATA_PATH:
            options.set_user_data_path(config.CHROME_USER_DATA_PATH)
        if config.CHROME_PROFILE_DIRECTORY:
            options.set_argument(f"--profile-directory={config.CHROME_PROFILE_DIRECTORY}")
    return options


def build_page(use_profile: bool = True) -> ChromiumPage:
    return ChromiumPage(addr_or_opts=build_options(use_profile))


def _beep(times: int = 3) -> None:
    """Alerta audible (multiplataforma; nunca revienta el flujo)."""
    try:
        if sys.platform == "win32":
            import winsound

            for _ in range(times):
                winsound.Beep(880, 250)
                winsound.Beep(660, 250)
        else:
            for _ in range(times):
                print("\a", end="", flush=True)
    except Exception:
        pass


def alert_manual_intervention(message: str) -> None:
    """Suena + muestra un banner visible avisando que hace falta tu intervención."""
    banner = "!" * 72
    console.blank()
    console.warning(banner)
    console.warning("⛔  INTERVENCIÓN MANUAL NECESARIA")
    console.warning(f"    {message}")
    console.warning(banner)
    console.blank()
    _beep()
