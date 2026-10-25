import csv
import io
import logging
import os
import tempfile
from pathlib import Path

log = logging.getLogger(__name__)


def save_csv(rows, columns, output_dir, dataset, trading_date):
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{dataset}_{trading_date}.csv"
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    content = buffer.getvalue().encode("utf-8")
    if path.exists() and path.read_bytes() == content:
        log.info("unchanged file=%s records=%d", path, len(rows))
        return path
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=directory, delete=False) as handle:
            temporary = handle.name
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)
    log.info("saved file=%s records=%d", path, len(rows))
    return path
