import logging
from .acquisition import fetch_json
from .validation import normalize, deduplicate, ValidationError
from .storage import save_csv

log = logging.getLogger(__name__)


def run(config, names, output_dir, *, demo=False, authorized=False, expected_date=None, fetcher=fetch_json):
    failures = []
    for name in names:
        log.info("start dataset=%s mode=%s", name, "demo" if demo else "live")
        try:
            if not demo and not authorized:
                raise ValidationError("Live access requires permission verification and --authorized-access")
            spec = config["datasets"][name]
            rows, dates = [], set()
            for source in spec["sources"]:
                payload = fetcher(source, demo=demo)
                batch, trading_date = normalize(payload, source, spec, name)
                rows.extend(batch)
                dates.add(trading_date)
            if len(dates) != 1:
                raise ValidationError("Sources disagree on trading date")
            trading_date = dates.pop()
            if expected_date and trading_date != expected_date:
                raise ValidationError(f"Expected {expected_date}, received {trading_date}; stale/mismatched data")
            rows = deduplicate(rows, spec["keys"])
            save_csv(rows, list(spec["columns"]) + ["dataset", "trading_date", "category"],
                     output_dir, name, trading_date)
            log.info("success dataset=%s records=%d trading_date=%s", name, len(rows), trading_date)
        except Exception:
            log.exception("failure dataset=%s", name)
            failures.append(name)
    log.info("summary attempted=%d succeeded=%d failed=%d", len(names), len(names)-len(failures), len(failures))
    return failures
