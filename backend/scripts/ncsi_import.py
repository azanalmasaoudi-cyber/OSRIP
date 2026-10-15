"""Convert an NCSI data-portal CSV export into an OSRIP import file.

Step 1, inventory (no mapping yet): lists every indicator / region / unit combination
in the export, so a data manager can decide which series match OSRIP indicators.

    python scripts/ncsi_import.py inventory electricity.csv \
        --indicator-col Indicators --region-col Regions --date-col Date --value-col Value

Step 2, convert with a reviewed mapping file (JSON):

    {"indicators": {"<NCSI indicator name exactly as in the file>":
                    {"code": "ELEC_GENERATION", "unit": "GWh"}}}

    python scripts/ncsi_import.py convert electricity.csv mapping.json out.csv \
        --indicator-col Indicators --region-col Regions --date-col Date --value-col Value

Then register the source (publisher: National Centre for Statistics and Information;
URL of the statistical table; access date; Open Government License - Sultanate of
Oman) and upload out.csv in Data Management, where it is validated, reviewed,
approved and published like any other file. Column names differ between exports,
so they are options; check them against the file's header row.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.ncsi import convert  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["inventory", "convert"])
    parser.add_argument("source")
    parser.add_argument("mapping", nargs="?")
    parser.add_argument("output", nargs="?")
    for name, default in (
        ("indicator", "Indicators"),
        ("region", "Regions"),
        ("date", "Date"),
        ("value", "Value"),
        ("frequency", "Frequency"),
        ("unit", "Unit"),
    ):
        parser.add_argument(f"--{name}-col", default=default)
    args = parser.parse_args()
    text = Path(args.source).read_text(encoding="utf-8-sig")
    columns = {
        "indicator": args.indicator_col,
        "region": args.region_col,
        "date": args.date_col,
        "value": args.value_col,
        "frequency": args.frequency_col,
        "unit": args.unit_col,
    }
    if args.command == "inventory":
        result = convert(text, {"indicators": {}}, columns=columns, today=date.today())
        for (name, region, unit), n in sorted(result.inventory.items()):
            print(f"{n:5d}  {name} | {region} | {unit}")
        return
    if not args.mapping or not args.output:
        parser.error("convert needs a mapping file and an output path")
    mapping = json.loads(Path(args.mapping).read_text(encoding="utf-8"))
    result = convert(text, mapping, columns=columns, today=date.today())
    Path(args.output).write_text(result.csv_text(), encoding="utf-8")
    print(f"{len(result.rows)} rows written to {args.output}")
    for reason, n in sorted(result.skipped.items()):
        print(f"skipped {n:5d}: {reason}")
    if result.unknown_regions:
        print(
            "regions not in the registry (not guessed):", ", ".join(sorted(result.unknown_regions))
        )


if __name__ == "__main__":
    main()
