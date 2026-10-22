import csv
from pathlib import Path

p = Path(__file__).resolve().parent.parent / "data" / "processed" / "eda_tools_clean.csv"
rows = list(csv.DictReader(open(p, encoding="utf-8")))
print(len(rows), "tools;", len(rows[0]), "columns")
print(list(rows[0].keys()))