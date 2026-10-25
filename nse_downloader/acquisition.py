import logging
import random
import time
from pathlib import Path
from urllib.parse import urlparse

import requests

log = logging.getLogger(__name__)


class AcquisitionError(ValueError):
    pass


def fetch_json(source, *, demo=False, session=None, attempts=3, sleep=time.sleep):
    if demo:
        import json
        return json.loads(Path(source["fixture"]).read_text(encoding="utf-8"))
    url = source.get("url")
    if not url or urlparse(url).scheme != "https":
        raise AcquisitionError("Configure an authorized HTTPS JSON source URL first")
    session = session or requests.Session()
    for attempt in range(1, attempts + 1):
        log.info("request url=%s attempt=%d", url, attempt)
        try:
            response = session.get(url, timeout=(10, 30), allow_redirects=False,
                                   headers={"Accept": "application/json", "User-Agent": "NSEAssignmentDownloader/1.0"})
            if response.status_code in (401, 403):
                raise AcquisitionError("Access denied; no bypass or access-denied retries attempted")
            if response.status_code == 429 or 500 <= response.status_code <= 599:
                if attempt < attempts:
                    delay = min(30, 2 ** (attempt - 1) + random.random())
                    retry_after = response.headers.get("Retry-After", "")
                    if retry_after.isdigit():
                        if int(retry_after) > 120:
                            raise AcquisitionError("Rate limited; retry after the server's requested interval")
                        delay = max(delay, int(retry_after))
                    log.warning("transient_status=%s retry_delay=%.2f", response.status_code, delay)
                    sleep(delay)
                    continue
            if not 200 <= response.status_code < 300:
                raise AcquisitionError(f"HTTP {response.status_code}; redirects are not followed")
            if "json" not in response.headers.get("Content-Type", "").lower():
                raise AcquisitionError("Expected JSON content type; refusing HTML/challenge response")
            try:
                return response.json()
            except ValueError as exc:
                raise AcquisitionError("Invalid JSON response") from exc
        except (requests.Timeout, requests.ConnectionError) as exc:
            if attempt == attempts:
                raise AcquisitionError(f"Network failure after {attempts} attempts") from exc
            sleep(min(30, 2 ** (attempt - 1) + random.random()))
        except requests.RequestException as exc:
            raise AcquisitionError(str(exc)) from exc
    raise AcquisitionError("Retry limit exceeded")
