"""Build outputs/gallery.html: every plot (PNG) with its table (CSV) on one page."""
import base64, csv, html
from pathlib import Path

out = Path(__file__).resolve().parent.parent / "outputs"
parts = ["<html><head><meta charset='utf-8'><title>EDA tools - plots</title>"
         "<style>body{font-family:sans-serif;max-width:1000px;margin:2em auto}"
         "img{max-width:100%}table{border-collapse:collapse;font-size:13px}"
         "td,th{border:1px solid #ccc;padding:3px 8px}h2{margin-top:2em}</style></head><body>"
         "<h1>Global EDA Tools Explorer - plots and tables</h1>"]
for png in sorted(out.glob("*.png")):
    parts.append("<h2>%s</h2>" % html.escape(png.stem.replace("_", " ")))
    b64 = base64.b64encode(png.read_bytes()).decode()
    parts.append("<img src='data:image/png;base64,%s'>" % b64)
    csv_path = png.with_suffix(".csv")
    if csv_path.exists():
        with open(csv_path, newline="", encoding="utf-8") as f:
            rows = list(csv.reader(f))
        parts.append("<table>")
        for i, row in enumerate(rows[:26]):
            tag = "th" if i == 0 else "td"
            parts.append("<tr>%s</tr>" % "".join("<%s>%s</%s>" % (tag, html.escape(c), tag) for c in row))
        parts.append("</table>")
        if len(rows) > 26:
            parts.append("<p>... %d more rows in %s</p>" % (len(rows) - 26, csv_path.name))
parts.append("</body></html>")
(out / "gallery.html").write_text("\n".join(parts), encoding="utf-8")
print("wrote", out / "gallery.html")