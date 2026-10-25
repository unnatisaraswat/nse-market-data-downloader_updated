import argparse
import json
import logging
from pathlib import Path
from .pipeline import run
from .validation import validate_date


def main():
    parser = argparse.ArgumentParser(description="Four-dataset CSV pipeline; demo fixtures are synthetic")
    parser.add_argument("--config", default="config/datasets.json")
    parser.add_argument("--dataset", action="append", help="Repeat to select multiple datasets")
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--authorized-access", action="store_true", help="Attest you have verified permission for configured sources")
    parser.add_argument("--expected-date", type=validate_date, help="Reject source dates other than YYYY-MM-DD")
    args = parser.parse_args()
    output = Path(args.output_dir or ("output/demo" if args.demo else "output/live"))
    output.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s",
                        handlers=[logging.StreamHandler(), logging.FileHandler(output / "downloader.log", encoding="utf-8")])
    try:
        config_path = Path(args.config).resolve()
        config = json.loads(config_path.read_text(encoding="utf-8"))
        for spec in config["datasets"].values():
            for source in spec["sources"]:
                source["fixture"] = str((config_path.parent / source["fixture"]).resolve())
        names = args.dataset or list(config["datasets"])
        if any(name not in config["datasets"] for name in names):
            parser.error("Unknown dataset; see config/datasets.json")
        names = list(dict.fromkeys(names))
        return 1 if run(config, names, output, demo=args.demo, authorized=args.authorized_access,
                        expected_date=args.expected_date) else 0
    except (OSError, ValueError, KeyError):
        logging.exception("Configuration/execution error")
        return 2
