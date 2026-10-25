# Browser URL integration update

This revision adds ordinary Playwright browser acquisition from the four assignment
page URLs in config/browser.json. `python main.py` now selects this browser adapter;
`--demo` keeps the synthetic demo, and `--json-source` selects the original JSON client.

## Windows setup
    .\.venv\Scripts\python.exe -m pip install -r requirements.txt
    .\.venv\Scripts\python.exe -m playwright install chromium
    .\.venv\Scripts\python.exe main.py

Run one dataset:
    .\.venv\Scripts\python.exe main.py --dataset volume-gainers-spurts

Run offline tests:
    .\.venv\Scripts\python.exe -m pytest -q

## Verification status — important
The four URLs were readable via the research web tool. This is NOT proof that a
local Playwright session will work. The browser adapter has NOT been end-to-end
verified against NSE and its UI selectors require local confirmation. In particular,
view controls (Gainers/Losers, Upper Band, 52 Week High) may use markup not matched
by accessible roles. Multirow volume headers may require an explicit selector or
header mapping adjustment. Such mismatches fail rather than output invented data.
The old 21 tests exercise the original pipeline, NOT this new live adapter.
Synthetic sample outputs remain synthetic. No genuine live CSV samples supplied.

## Behavior
Uses normal Chromium without stealth, proxy rotation, cookie harvesting or CAPTCHA
solving. A visible browser is the default. Use only where permitted by applicable
terms; browser automation does not itself grant authorization. HTTP errors and
recognized challenges fail the dataset. Dataset failures are isolated. Failure
screenshots and logs are saved under output/live. Review screenshots for private
information before sharing. Do not solve challenges to continue automation.

The adapter matches visible table headers, reads the selected view, uses the
explicit As on timestamp, checks displayed totals and follows recognizable Next
controls. It fails on ambiguous tables, conflicting duplicate keys, invalid LTP,
empty results and incomplete pagination. It preserves source display fields (and
units in headings), plus dataset/trading_date/category. It does not convert all
numeric fields; broader schema validation is still needed before submission.
If no displayed total exists, it cannot independently certify complete coverage.
The index scope is the website's current default; verify/document it locally.
Refresh after tab selection uses a short fixed wait and needs strengthening with
view-specific response/DOM assertions before calling this production-ready.

Do not present this revision as a completed assignment until all four genuine
outputs have been successfully tested on the permitted access path. If a selector
fails, inspect the corresponding failure screenshot and adjust browser_download.py
or config/browser.json. Never bypass an access restriction.

See README.md for the original pipeline documentation; its live CLI guidance
applies to --json-source only after this revision.
