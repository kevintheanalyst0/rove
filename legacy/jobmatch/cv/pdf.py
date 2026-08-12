"""Conversión de DOCX a PDF mediante Microsoft Word (COM).

Solo funciona en Windows con Word instalado. El import de win32com es
perezoso, así que este módulo se puede importar en cualquier sistema; el
error, si aplica, solo aparece al intentar convertir de verdad.
"""

from __future__ import annotations

import os


def convert_docx_to_pdf(docx_path: str, pdf_path: str) -> None:
    try:
        import pythoncom
        import win32com.client
    except ImportError as error:
        raise RuntimeError(
            "La conversión a PDF requiere Windows con Microsoft Word instalado "
            "(paquete pywin32). No está disponible en este sistema."
        ) from error

    pythoncom.CoInitialize()
    try:
        word = win32com.client.Dispatch("Word.Application")
        word.Visible = False
        document = word.Documents.Open(os.path.abspath(docx_path))
        document.SaveAs(os.path.abspath(pdf_path), FileFormat=17)  # 17 = PDF
        document.Close()
        word.Quit()
    finally:
        pythoncom.CoUninitialize()
