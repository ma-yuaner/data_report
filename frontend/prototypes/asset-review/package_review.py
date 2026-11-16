"""Package locally held inventory metadata into the offline design review HTML."""
import argparse
import csv
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    data = {}
    for key, filename in [("tables", "tables"), ("columns", "columns"), ("edges", "lineage"), ("gaps", "gaps"), ("databases", "databases")]:
        with (args.inventory / (filename + ".csv")).open(encoding="utf-8-sig", newline="") as handle:
            data[key] = list(csv.DictReader(handle))
    for number, row in enumerate(data["edges"]):
        row["evidence_id"] = "e" + str(number)
    for number, row in enumerate(data["gaps"]):
        row["gap_id"] = "g" + str(number)
    html = (Path(__file__).parent / "dist/index.html").read_text(encoding="utf-8")
    if html.count("<!--ASSET_REVIEW_DATA-->") != 1:
        raise ValueError("review data placeholder missing or duplicated")
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    html = html.replace("<!--ASSET_REVIEW_DATA-->", "<script>window.__ASSET_REVIEW_DATA__=" + payload + ";</script>")
    if '<script type="module"' in html or '<script src=' in html:
        raise ValueError("offline bundle still requires external entry scripts")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(html, encoding="utf-8")
    print("Packaged offline review:", len(data["tables"]), "objects,", len(data["edges"]), "dependency evidence records")


if __name__ == "__main__":
    main()
