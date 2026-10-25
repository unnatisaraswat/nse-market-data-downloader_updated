"""Normal-browser adapter. No stealth, challenge solving, or access-control bypass."""
import argparse
import json
import logging
import re
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright
from nse_downloader.storage import save_csv

log = logging.getLogger(__name__)


def clean(text):
    return re.sub(r"[^a-z0-9]", "", text.lower())


def check_access(page):
    text = page.locator("body").inner_text()
    for marker in ("access denied", "verify you are human", "unusual traffic", "request rejected"):
        if marker in text.lower():
            raise ValueError("Access restriction encountered; stopping without bypass")
    if page.locator('iframe[src*="captcha"]:visible, .g-recaptcha:visible').count():
        raise ValueError("CAPTCHA encountered; stopping without bypass")
    return text


def choose_view(page, label):
    pattern = re.compile(r"^(?:Top\s+(?:20\s+)?)?" + re.escape(label) + r"$", re.I)
    for role in ("tab", "button", "link"):
        controls = page.get_by_role(role, name=pattern)
        for i in range(controls.count()):
            control = controls.nth(i)
            if control.is_visible():
                control.click(timeout=10000)
                page.wait_for_timeout(1500)
                check_access(page)
                return
    raise ValueError(f"Cannot verify/select {label!r} view; inspect current page controls")


def find_table(page, required):
    tables = page.locator("table:visible")
    matches = []
    for i in range(tables.count()):
        table = tables.nth(i)
        heads = table.locator("thead tr").last.locator("th, td").all_inner_texts() if table.locator("thead tr").count() else table.locator("tr").first.locator("th, td").all_inner_texts()
        normalized = [clean(h) for h in heads]
        if all(any(needle in h for h in normalized) for needle in required):
            matches.append((table, heads))
    if len(matches) != 1:
        raise ValueError(f"Expected one matching visible market table; found {len(matches)}")
    return matches[0]

def table_records(table, headers):
    normalized = [clean(h) for h in headers]

    # NSE Volume Gainers has ten columns arranged under:
    # Today, 1 Week, and 2 Week.
    is_volume_gainers = (
        len(normalized) == 10
        and normalized[0] == "symbol"
        and normalized[1] == "securityname"
        and normalized[2] == "volume"
        and normalized[3] == "ltp"
        and normalized[4] in {"chng", "change", "percentchange"}
        and normalized[5].startswith("turnover")
        and normalized[6] in {"avgvolume", "averagevolume"}
        and normalized[7] == "changenooftimes"
        and normalized[8] in {"avgvolume", "averagevolume"}
        and normalized[9] == "changenooftimes"
    )

    if is_volume_gainers:
        keys = [
            "symbol",
            "security_name",
            "today_volume",
            "ltp",
            "percent_change",
            "turnover_inr_lakhs",
            "one_week_average_volume",
            "one_week_volume_multiple",
            "two_week_average_volume",
            "two_week_volume_multiple",
        ]
    else:
        keys = [
            re.sub(r"[^a-z0-9]+", "_", h.lower()).strip("_")
            or f"column_{i}"
            for i, h in enumerate(headers)
        ]

    if len(set(keys)) != len(keys):
        raise ValueError(
            f"Duplicate output column names; inspect headers: {headers!r}"
        )
    rows = []
    for cells in table.locator("tbody tr").evaluate_all("rs => rs.map(r => Array.from(r.querySelectorAll('td')).map(c => c.innerText.trim()))"):
        if not cells or all(not c for c in cells):
            continue
        if len(cells) != len(keys):
            raise ValueError("Unexpected row width or empty-result placeholder")
        row = dict(zip(keys,cells))
        symbol_keys = [k for k in keys if clean(k) == "symbol"]
        if not symbol_keys or not row[symbol_keys[0]].strip():
            raise ValueError("Missing symbol")
        for key,value in row.items():
            if clean(key) in ("ltp", "lastprice"):
                number = float(value.replace(",", ""))
                if not (0 <= number < float("inf")):
                    raise ValueError("Invalid LTP")
        rows.append(row)
    if not rows:
        raise ValueError("Empty market table")
    return rows


def collect(page, required):
    collected=[]
    seen=set()
    expected=None
    headers=None
    for _ in range(500):
        text=check_access(page)
        table,current_headers=find_table(page,required)
        if headers is not None and headers != current_headers:
            raise ValueError("Headers changed during pagination")
        headers=current_headers
        batch=table_records(table,headers)
        signature=json.dumps(batch,sort_keys=True)
        if signature in seen:
            raise ValueError("Repeated page; refusing incomplete result")
        seen.add(signature)
        collected.extend(batch)
        counts=re.findall(r"Displaying\s+[\d,]+\s*[-–]\s*[\d,]+\s+of\s+([\d,]+)\s+records",text,re.I)
        if counts:
            totals=set(int(c.replace(',','')) for c in counts)
            if len(totals)!=1:
                raise ValueError("Ambiguous displayed total")
            expected=totals.pop()
            if len(collected)==expected:
                return collected
            if len(collected)>expected:
                raise ValueError("Collected count exceeds displayed total")
        else:
            # These views may have no pager. Caller must verify their index/view scope.
            return collected
        clicked=False
        for selector in ('[title="Next Page"]:visible', '[aria-label="Next page"]:visible', 'a:visible', 'button:visible'):
            candidates=page.locator(selector)
            for i in range(candidates.count()):
                c=candidates.nth(i)
                label=(c.inner_text()+' '+(c.get_attribute('title') or '')+' '+(c.get_attribute('aria-label') or '')).strip()
                if re.fullmatch(r"(?:Next(?:\s+page)?\s*)+",label,re.I) and c.is_enabled() and c.get_attribute('aria-disabled')!='true' and 'disabled' not in (c.get_attribute('class') or '').lower():
                    c.click(timeout=10000)
                    page.wait_for_timeout(1500)
                    clicked=True
                    break
            if clicked:
                break
        if not clicked:
            raise ValueError(f"Only {len(collected)}/{expected} rows; Next control not verified")
    raise ValueError("Pagination limit exceeded")


def source_date(page):
    text=check_access(page)
    dates=re.findall(r"As on\s+(\d{2}-[A-Za-z]{3}-\d{4})\s+\d{2}:\d{2}(?::\d{2})?\s+IST",text,re.I)
    dates=set(dates)
    if len(dates)!=1:
        raise ValueError("Cannot identify an unambiguous dataset As on timestamp")
    return datetime.strptime(dates.pop(),'%d-%b-%Y').date().isoformat()


def main():
    parser=argparse.ArgumentParser(description='Browser-based retrieval from configured assignment URLs; use only where permitted')
    parser.add_argument('--dataset',action='append')
    parser.add_argument('--output-dir',default='output/live')
    parser.add_argument('--headless',action='store_true')
    parser.add_argument('--expected-date',type=lambda x:datetime.strptime(x,'%Y-%m-%d').date().isoformat())
    parser.add_argument('--browser-config',default='config/browser.json')
    args=parser.parse_args()
    output=Path(args.output_dir)
    output.mkdir(parents=True,exist_ok=True)
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s',handlers=[logging.StreamHandler(),logging.FileHandler(output/'downloader.log',encoding='utf-8')])
    specs=json.loads(Path(args.browser_config).read_text())
    names=list(dict.fromkeys(args.dataset or specs))
    if any(name not in specs for name in names):
        parser.error('Unknown dataset')
    failures=[]
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=args.headless)
        context=browser.new_context(locale='en-IN',timezone_id='Asia/Kolkata')
        for name in names:
            page=context.new_page()
            try:
                spec=specs[name]
                log.info('start dataset=%s url=%s',name,spec['url'])
                response=page.goto(spec['url'],wait_until='domcontentloaded',timeout=60000)
                if response is not None and response.status>=400:
                    raise ValueError(f'HTTP {response.status}; not bypassed')
                check_access(page)
                page.wait_for_function("() => Array.from(document.querySelectorAll('table')).some(t => /symbol/i.test(t.innerText) && t.querySelectorAll('tbody td').length > 3)",timeout=45000)
                rows=[]
                dates=set()
                for view in spec['views']:
                    if view.get('select'):
                        choose_view(page,view['select'])
                    batch=collect(page,spec['required_headers'])
                    date=source_date(page)
                    dates.add(date)
                    for row in batch:
                        row.update(dataset=name,trading_date=date,category=view['category'])
                    rows.extend(batch)
                if len(dates)!=1:
                    raise ValueError('Views disagree on source trading date')
                date=dates.pop()
                if args.expected_date and date!=args.expected_date:
                    raise ValueError(f'Stale/mismatched date {date}')
                unique={}
                for row in rows:
                    key=tuple(row.get(k,'') for k in ('symbol','series','category','trading_date'))
                    if key in unique and unique[key]!=row:
                        raise ValueError(f'Conflicting duplicate {key}')
                    unique[key]=row
                rows=[unique[k] for k in sorted(unique)]
                if len({tuple(r) for r in rows})!=1:
                    raise ValueError('Views have different schemas')
                save_csv(rows,list(rows[0]),output,name,date)
                log.info('success dataset=%s records=%d date=%s duplicates_removed=%d',name,len(rows),date,len(rows)-len(unique))
            except Exception:
                failures.append(name)
                log.exception('failure dataset=%s',name)
                try:
                    page.screenshot(path=str(output/f'{name}_failure.png'),full_page=True)
                except Exception:
                    pass
            finally:
                page.close()
        context.close()
        browser.close()
    log.info('summary attempted=%d failed=%d',len(names),len(failures))
    return 1 if failures else 0

if __name__=='__main__':
    raise SystemExit(main())
