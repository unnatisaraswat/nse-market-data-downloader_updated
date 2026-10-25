

The four target pages are listed in config/datasets.json. They are web pages,
not assumed JSON endpoints. Configure authorized JSON exports/API feeds that
correspond to those pages, or implement a permitted acquisition adapter after
verifying access. An authorization flag is an attestation, not permission from NSE.
No CAPTCHA solving, proxy rotation, impersonation or cookie harvesting is included.



## Configure real acquisition
1. Confirm applicable terms and obtain any necessary permission/licensed feed.
2. Set each sources[].url to a permitted HTTPS JSON endpoint. Never place secrets
   in a URL or commit credentials; an authenticated provider requires an adapter
   that obtains secrets securely from the environment.
3. Set records_path and date_path to dot-separated object paths. date_path must
   select an explicit source trading date in YYYY-MM-DD form. Provider-specific
   timestamps require a normalizing acquisition adapter. Never infer trading date
   from the local execution date or unrelated page header timestamps.
4. Map normalized CSV column names to actual top-level record fields in columns.
   Adjust required numeric columns and uniqueness keys to the feed contract. The
   bundled schema is illustrative, not a verified NSE response schema; extend it
   to preserve all fields required for your chosen page view. Specify index scope
   for gainers/losers in your source configuration/documentation.
5. Run:

       python main.py --authorized-access --expected-date YYYY-MM-DD

The expected date is optional and detects stale data when supplied. This is not a
historical download flag; it only checks the returned source date. Without it, an
older source trading date is accepted and used explicitly in the filename.

## Architecture
- acquisition.py: HTTPS JSON retrieval, connection/read timeouts, bounded retries.
- validation.py: structure, required columns, finite decimals, nonnegative checks,
  explicit source dates, exact duplicate removal and conflicting duplicate rejection.
- storage.py: deterministic UTF-8 CSV, temporary file + atomic replace.
- pipeline.py: dataset-level failure isolation; partial multi-source data never saved.
- cli.py: selection, configuration, logging and exit statuses.
- config/: feed URLs, mappings, keys and fixture paths; no hardcoded live endpoints.

## Storage and duplicates
Files are DATASET_YYYY-MM-DD.csv using the source trading date. Identical reruns
leave files untouched; changed validated data atomically replaces that day's file.
Earlier dates remain separate. Exact duplicate rows collapse; conflicting values
for the same identity fail the dataset rather than silently selecting a record.
Failed refreshes preserve old files: check exit status/logs, not file existence,
to determine whether a run succeeded. There is no database or database schema.
Only one scheduled instance should write to a given output directory at a time.

## Errors and logs
Logs contain timestamps, attempts, outcomes, counts, duplicate counts and traceback
errors. Network failures, 429 and 5xx have up to three attempts with exponential
backoff/jitter. Numeric Retry-After values up to 120 seconds are honored; longer
values stop the run for external rescheduling. HTTP-date Retry-After is not parsed.
401/403, other HTTP errors, redirects, invalid content types, malformed JSON and
validation errors fail without attempts to circumvent restrictions. Other datasets
continue. Empty lists fail validation (including potentially legitimate zero-result
days); this strict policy follows the assignment's non-empty requirement.
Exit status: 0 all selected successful, 1 one or more failed, 2 configuration error.
No automatic holiday calendar or historical API support is supplied.

## Tests
Tests cover all four output files, identical reruns, duplicate conflict handling,
invalid/empty response formats, numeric validation, failure isolation, stale dates,
permission guard, successful mocked requests, HTTP errors, rate limiting, server
errors, timeouts, HTML responses and malformed JSON. These are offline unit and
fixture integration tests, not proof that live NSE access works.

## Automation
Example cron entry for Monday–Friday 18:00 in the scheduler's configured timezone
(set it to Asia/Kolkata). This is not a trading-calendar/holiday check:

    0 18 * * 1-5 cd /absolute/project/path && .venv/bin/python main.py --authorized-access >> scheduler.log 2>&1

Configure sources and permissions first. Do not overlap runs. Failure notifications,
provider authentication and trading-calendar integration are future extensions.

## Docker

    docker build -t nse-downloader .
    docker run --rm -v "$PWD/output:/app/output" nse-downloader --demo

## Before final submission
- Verify authorized acquisition of all four complete datasets.
- Implement and test provider-specific response/date normalization and pagination
  if needed; this generic JSON adapter expects the complete result in one response.
- Select and document the gainers/losers index scope.
- Replace synthetic CSV samples with genuine, dated outputs and keep provenance.
- Add sanitized actual-response fixtures and live opt-in integration tests.
- Verify schema coverage and legitimate zero-result-day handling with the reviewer.
