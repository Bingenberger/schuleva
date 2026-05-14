from __future__ import annotations
import io
import base64
from typing import Any
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np


def _chart_b64(question: dict[str, Any]) -> str:
    stats = question.get("stats", {})
    options = stats.get("options", [])
    counts = stats.get("counts", {})
    percents = stats.get("percents", {})
    total = stats.get("total", 0)

    if not options:
        return ""

    labels = [opt["label"] for opt in options]
    values = [percents.get(opt["value"], 0) for opt in options]
    raw = [counts.get(opt["value"], 0) for opt in options]

    colors = ["#2ecc71", "#f39c12", "#e67e22", "#e74c3c"]
    if len(labels) > len(colors):
        colors = plt.cm.tab10.colors[:len(labels)]  # type: ignore[attr-defined]

    fig, ax = plt.subplots(figsize=(7, 0.6 + 0.5 * len(labels)))
    y_pos = np.arange(len(labels))
    bars = ax.barh(y_pos, values, color=colors[:len(labels)], height=0.6, edgecolor="white")

    for i, (bar, pct, cnt) in enumerate(zip(bars, values, raw)):
        ax.text(
            bar.get_width() + 0.5,
            bar.get_y() + bar.get_height() / 2,
            f"{pct:.1f}% (n={cnt})",
            va="center",
            fontsize=8,
        )

    ax.set_yticks(y_pos)
    ax.set_yticklabels(labels, fontsize=9)
    ax.set_xlim(0, 110)
    ax.xaxis.set_major_formatter(mticker.PercentFormatter())
    ax.set_title(f"n={total}", fontsize=8, loc="right", pad=4)
    ax.spines[["top", "right"]].set_visible(False)
    plt.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=120, bbox_inches="tight")
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode()


def generate_report_pdf_bytes(
    survey_title: str,
    period: str,
    filter_label: str,
    eval_result: dict[str, Any],
) -> bytes:
    total = eval_result.get("total_responses", 0)

    toc_items = "".join(
        f'<li><a href="#{sec["id"]}">{sec["title"]}</a></li>'
        for sec in eval_result.get("sections", [])
    )

    sections_html = ""
    for sec in eval_result.get("sections", []):
        sections_html += f'<h2 id="{sec["id"]}">{sec["title"]}</h2>\n'
        for q in sec.get("questions", []):
            sections_html += f'<div class="question">\n'
            sections_html += f'<p class="q-text">{q["text"]}</p>\n'

            if q["type"] in ("scale", "single_choice", "conditional"):
                img_b64 = _chart_b64(q)
                if img_b64:
                    sections_html += (
                        f'<img class="chart" src="data:image/png;base64,{img_b64}" alt="Diagramm">\n'
                    )
                stats = q.get("stats", {})
                n = stats.get("total", 0)
                sections_html += f'<p class="n-total">Antworten gesamt: {n}</p>\n'
            elif q["type"] == "text":
                freitexte = q.get("freitexte", [])
                if freitexte:
                    items = "".join(f"<li>{t}</li>" for t in freitexte)
                    sections_html += f"<ul class='freitext-list'>{items}</ul>\n"
                else:
                    sections_html += "<p><em>Keine Antworten.</em></p>\n"

            sections_html += "</div>\n"

    html = f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<style>
  @page {{ size: A4; margin: 20mm 15mm; }}
  body {{
    font-family: "DejaVu Sans", Arial, sans-serif;
    font-size: 10pt;
    color: #222;
    line-height: 1.5;
  }}
  h1 {{ font-size: 18pt; color: #1a3a5c; margin-bottom: 4mm; }}
  h2 {{
    font-size: 13pt;
    color: #1a3a5c;
    border-bottom: 0.5mm solid #1a3a5c;
    padding-bottom: 2mm;
    margin-top: 10mm;
    page-break-after: avoid;
  }}
  .cover {{ text-align: center; padding-top: 40mm; page-break-after: always; }}
  .meta {{ color: #555; font-size: 9pt; }}
  .toc {{ page-break-after: always; }}
  .toc ul {{ list-style: none; padding: 0; }}
  .toc li {{ margin: 2mm 0; }}
  .toc a {{ color: #1a3a5c; text-decoration: none; }}
  .question {{ margin-bottom: 6mm; page-break-inside: avoid; }}
  .q-text {{ font-weight: bold; margin-bottom: 2mm; }}
  .chart {{ max-width: 100%; }}
  .n-total {{ font-size: 8pt; color: #666; }}
  .freitext-list {{ padding-left: 5mm; }}
  .freitext-list li {{ margin-bottom: 2mm; }}
</style>
</head>
<body>

<div class="cover">
  <h1>{survey_title}</h1>
  <p class="meta">Befragungszeitraum: {period}</p>
  <p class="meta">Filter: {filter_label}</p>
  <p class="meta">Rückläufe: {total}</p>
</div>

<div class="toc">
  <h2>Inhaltsverzeichnis</h2>
  <ul>{toc_items}</ul>
</div>

{sections_html}

</body>
</html>"""

    try:
        from weasyprint import HTML
        return HTML(string=html).write_pdf()
    except ImportError:
        raise RuntimeError(
            "weasyprint ist nicht installiert. Bitte 'pip install weasyprint' ausführen."
        )
