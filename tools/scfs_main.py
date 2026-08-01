#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from scfs.editor import launch


def main() -> int:
    parser = argparse.ArgumentParser(description="+SCFS+ SignalCloud Font Studio")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    launch(args.root.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
