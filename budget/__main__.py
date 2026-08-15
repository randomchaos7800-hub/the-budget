"""python3 -m budget [serve|nightly|demo]"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .server import DEFAULT_DB, serve
from .service import Wallet


def main() -> None:
    parser = argparse.ArgumentParser(prog="budget")
    parser.add_argument("--db", default=os.environ.get("BUDGET_DB", str(DEFAULT_DB)))
    sub = parser.add_subparsers(dest="cmd", required=True)

    serve_p = sub.add_parser("serve", help="run the local web app")
    serve_p.add_argument("--host", default=os.environ.get("BUDGET_HOST", "127.0.0.1"))
    serve_p.add_argument("--port", type=int, default=int(os.environ.get("BUDGET_PORT", "8787")))

    sub.add_parser("nightly", help="crystallize ledger + emit alerts")
    sub.add_parser("demo", help="load the demo household")
    sub.add_parser("export", help="dump model as JSON")

    args = parser.parse_args()
    db = Path(args.db)
    if args.cmd == "serve":
        serve(args.host, args.port, db)
        return
    wallet = Wallet(db)
    if args.cmd == "nightly":
        print(json.dumps(wallet.nightly(), indent=2))
        return
    if args.cmd == "demo":
        wallet.load_demo()
        print(json.dumps(wallet.dashboard(), indent=2, default=str)[:2000])
        return
    if args.cmd == "export":
        print(json.dumps(wallet.export(), indent=2, default=str))


if __name__ == "__main__":
    main()
