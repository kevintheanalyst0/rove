"""Colectores de vacantes.

- occ, computrabajo: HTTP puro (rápidos, sin navegador).
- indeed, linkedin: navegador (Chromium vía DrissionPage).

Todos comparten `utils` (funciones puras) y `filters` (criterios de
calidad uniformes). El navegador vive en `browser` y solo lo importan
los colectores que de verdad lo necesitan.
"""
