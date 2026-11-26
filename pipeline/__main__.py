"""Komanda sətri: python -m pipeline <komanda>

  load         sxemi yaradır, customers/products/avqust-oktyabr sifarişlərini yükləyir
  incremental  yeni sifariş faylını yükləyir (default: orders_2026_11_01.csv)
  check        keyfiyyət yoxlamaları
  report       SQL suallarının nəticələri
  all          load -> check -> report -> incremental -> check -> report

  --reset      əvvəlcə bütün cədvəlləri silir (təmiz bazadan başlamaq üçün)
"""
import argparse
import logging
import sys
from pathlib import Path

from pipeline import load, quality, report
from pipeline.config import DATA_DIR, INCREMENTAL_ORDERS_FILE
from pipeline.db import connect, drop_schema


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m pipeline", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["load", "incremental", "check", "report", "all"])
    parser.add_argument("--file", type=Path, default=DATA_DIR / INCREMENTAL_ORDERS_FILE,
                        help="incremental üçün sifariş faylı")
    parser.add_argument("--reset", action="store_true", help="əvvəlcə cədvəlləri sil")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    ok = True
    with connect() as conn:
        if args.reset:
            drop_schema(conn)
        if args.command in ("load", "all"):
            load.full_load(conn)
        if args.command == "all":
            ok &= quality.run_checks(conn)
            print("\n## Nəticələr: əsas yükləmədən sonra\n\n" + report.run_queries(conn))
        if args.command in ("incremental", "all"):
            load.incremental_load(conn, args.file)
        if args.command in ("check", "all"):
            ok &= quality.run_checks(conn)
        if args.command == "report":
            print(report.run_queries(conn))
        if args.command == "all":
            print("\n## Nəticələr: noyabr faylından sonra\n\n" + report.run_queries(conn))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
