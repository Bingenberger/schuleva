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


CARDS_PER_ROW = 3
ROWS_PER_PAGE = 2
CARDS_PER_PAGE = CARDS_PER_ROW * ROWS_PER_PAGE


def _card_html(cls: str, tan: str, survey_title: str) -> str:
    url = f"https://{SCHOOL_DOMAIN}/start#{tan}"
    qr_b64 = _qr_png_b64(url)
    return f"""<div class="card">
  <div class="card-header">
    <span class="class-name">Klasse {cls}</span>
    <span class="survey-title">{survey_title}</span>
  </div>
  <div class="card-body">
    <img class="qr" src="data:image/png;base64,{qr_b64}" alt="QR-Code">
    <div class="right-col">
      <div class="tan-text">{tan}</div>
      <div class="instructions">
        1. QR-Code scannen<br>
        oder<br>
        2. Auf <strong>{SCHOOL_DOMAIN}</strong> gehen<br>
        und TAN eingeben
      </div>
    </div>
  </div>
</div>"""


def generate_tan_pdf_bytes(
    survey_title: str,
    class_tans: list[dict[str, Any]],
) -> bytes:
    """
    class_tans: [{"class_name": "4a", "tans": ["K4-ABCD-1234", ...]}, ...]
    Only unused TANs are passed in (used_at IS NULL filtered by caller).
    Returns PDF bytes.
    """
    # Flatten all cards into one list, preserving class order
    all_cards: list[str] = []
    for group in class_tans:
        cls = group["class_name"]
        for tan in group["tans"]:
            all_cards.append(_card_html(cls, tan, survey_title))

    # Split into fixed-size pages so WeasyPrint doesn't drop cards
    # when paginating a large flex container.
    pages_html = ""
    for i in range(0, len(all_cards), CARDS_PER_PAGE):
        chunk = all_cards[i : i + CARDS_PER_PAGE]
        page_break = "" if i + CARDS_PER_PAGE >= len(all_cards) else ' style="page-break-after:always"'
        pages_html += f'<div class="page"{page_break}>\n'
        pages_html += "\n".join(chunk)
        pages_html += "\n</div>\n"

    html = f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<style>
  @page {{ size: A4 landscape; margin: 10mm; }}
  body {{ margin: 0; font-family: Arial, sans-serif; }}
  .page {{
    display: grid;
    grid-template-columns: repeat({CARDS_PER_ROW}, 88mm);
    grid-template-rows: repeat({ROWS_PER_PAGE}, 61mm);
    gap: 4mm;
  }}
  .card {{
    width: 88mm; height: 61mm;
    border: 0.5mm solid #999;
    border-radius: 2mm;
    padding: 3mm;
    box-sizing: border-box;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }}
  .card-header {{
    display: flex;
    justify-content: space-between;
    font-size: 8pt;
    color: #555;
    border-bottom: 0.3mm solid #ddd;
    padding-bottom: 1mm;
    margin-bottom: 2mm;
    flex-shrink: 0;
  }}
  .class-name {{ font-weight: bold; font-size: 10pt; color: #222; }}
  .survey-title {{ font-size: 7pt; }}
  .card-body {{
    display: flex;
    align-items: center;
    gap: 3mm;
    flex: 1;
    min-height: 0;
  }}
  .qr {{ width: 28mm; height: 28mm; flex-shrink: 0; }}
  .right-col {{ display: flex; flex-direction: column; }}
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
</style>
</head>
<body>
{pages_html}
</body>
</html>"""

    try:
        from weasyprint import HTML
        return HTML(string=html).write_pdf()
    except ImportError:
        raise RuntimeError(
            "weasyprint ist nicht installiert. Bitte 'pip install weasyprint' ausführen."
        )
