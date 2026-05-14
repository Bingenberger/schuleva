from __future__ import annotations
import io
import os
import qrcode
import base64
from typing import Any

SCHOOL_DOMAIN = os.getenv("SCHOOL_DOMAIN", "befragung.meine-schule.de")
SCHOOL_LOGO = os.getenv("SCHOOL_LOGO", "")


def _qr_png_b64(url: str) -> str:
    img = qrcode.make(url, border=2)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def generate_tan_pdf_bytes(
    survey_title: str,
    class_tans: list[dict[str, Any]],
) -> bytes:
    """
    class_tans: [{"class_name": "4a", "tans": ["K4-ABCD-1234", ...]}, ...]
    Returns PDF bytes.
    """
    cards_html = ""
    for group in class_tans:
        cls = group["class_name"]
        for tan in group["tans"]:
            url = f"https://{SCHOOL_DOMAIN}/start#{tan}"
            qr_b64 = _qr_png_b64(url)
            cards_html += f"""
            <div class="card">
              <div class="card-header">
                <span class="class-name">Klasse {cls}</span>
                <span class="survey-title">{survey_title}</span>
              </div>
              <div class="card-body">
                <img class="qr" src="data:image/png;base64,{qr_b64}" alt="QR-Code">
                <div class="tan-text">{tan}</div>
                <div class="instructions">
                  1. QR-Code scannen<br>
                  oder<br>
                  2. Auf <strong>{SCHOOL_DOMAIN}</strong> gehen<br>
                  und TAN eingeben
                </div>
              </div>
            </div>
            """

    html = f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<style>
  @page {{ size: A4 landscape; margin: 10mm; }}
  body {{ margin: 0; font-family: Arial, sans-serif; }}
  .page {{ display: flex; flex-wrap: wrap; gap: 4mm; }}
  .card {{
    width: 88mm; height: 61mm;
    border: 0.5mm solid #999;
    border-radius: 2mm;
    padding: 3mm;
    box-sizing: border-box;
    display: flex;
    flex-direction: column;
    page-break-inside: avoid;
  }}
  .card-header {{
    display: flex;
    justify-content: space-between;
    font-size: 8pt;
    color: #555;
    border-bottom: 0.3mm solid #ddd;
    padding-bottom: 1mm;
    margin-bottom: 2mm;
  }}
  .class-name {{ font-weight: bold; font-size: 10pt; color: #222; }}
  .survey-title {{ font-size: 7pt; }}
  .card-body {{
    display: flex;
    align-items: center;
    gap: 3mm;
    flex: 1;
  }}
  .qr {{ width: 28mm; height: 28mm; }}
  .tan-text {{
    font-family: monospace;
    font-size: 14pt;
    font-weight: bold;
    letter-spacing: 1px;
    margin-bottom: 2mm;
  }}
  .instructions {{
    font-size: 7pt;
    color: #444;
    line-height: 1.4;
  }}
  .right-col {{ display: flex; flex-direction: column; }}
  .cut-line {{
    width: 100%;
    border-top: 0.3mm dashed #bbb;
    margin: 2mm 0;
  }}
</style>
</head>
<body>
<div class="page">
{cards_html}
</div>
</body>
</html>"""

    try:
        from weasyprint import HTML
        pdf_bytes = HTML(string=html).write_pdf()
        return pdf_bytes
    except ImportError:
        raise RuntimeError(
            "weasyprint ist nicht installiert. Bitte 'pip install weasyprint' ausführen."
        )
