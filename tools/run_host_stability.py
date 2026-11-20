"""Repeat the verified native-host route; watchdog exit is not normal game completion."""
from pathlib import Path
import argparse
import json
import game_host

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scenario',type=Path,default=ROOT/'config/scrapland/host-stability.json')
    args=parser.parse_args()
    scenario=json.loads(args.scenario.read_text(encoding='utf-8'))
    return game_host.run(**scenario['run'])


if __name__=='__main__':raise SystemExit(main())
