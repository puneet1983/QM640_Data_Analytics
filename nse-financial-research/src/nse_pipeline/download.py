"""Download and resume NSE XMLs listed in a screened metadata manifest."""
import argparse
import csv
import hashlib
import json
import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urljoin, urlsplit
import pandas as pd
import requests

ROOT_TAG = '{http://www.xbrl.org/2003/instance}xbrl'
LOG_FIELDS = ['url', 'status', 'local_path', 'bytes', 'sha256', 'http_status',
              'undefined_context_refs', 'detail', 'checked_utc']


class StopBatch(Exception):
    def __init__(self, status):
        self.status = status
        super().__init__(f'HTTP {status}; stop this batch and retry later if permitted.')


def allowed_url(url):
    try:
        parts = urlsplit(url)
        host = (parts.hostname or '').lower()
        return (parts.scheme == 'https' and not parts.username and not parts.password
                and (host == 'nseindia.com' or host.endswith('.nseindia.com')))
    except ValueError:
        return False


def xml_details(content):
    if not content:
        raise ValueError('Empty response')
    if re.search(br'<!\s*(?:DOCTYPE|ENTITY)\b', content, re.I):
        raise ValueError('DTD/entity declarations are unsupported')
    root = ET.fromstring(content)
    if root.tag != ROOT_TAG:
        raise ValueError('Response is not an XBRL instance XML (possibly HTML or Inline XBRL)')
    defined = {c.get('id') for c in root.findall('{http://www.xbrl.org/2003/instance}context')}
    referenced = {e.get('contextRef') for e in root.iter() if e.get('contextRef')}
    return len(referenced - defined)


def load_jobs(manifest_path):
    frame = pd.read_csv(manifest_path, dtype=str, low_memory=False)
    required = {'symbol', 'consolidated', 'cumulative', 'period', 'xbrl', '_QUARTER', '_COMPANY_KEY'}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f'Use the screened download_manifest.csv; missing {sorted(missing)}')
    if frame.empty:
        raise ValueError('Manifest is empty')
    frame['xbrl'] = frame.xbrl.str.strip()
    expected = set(pd.period_range('2022Q1', '2024Q4', freq='Q'))
    frame['_QUARTER'] = pd.PeriodIndex(frame._QUARTER, freq='Q')
    if not frame._QUARTER.isin(expected).all():
        raise ValueError('Manifest contains reporting periods outside 2022-2024')
    basis = frame.consolidated.str.strip().str.casefold()
    if not basis.isin(['standalone', 'non-consolidated', 'non consolidated']).all():
        raise ValueError('Manifest contains non-standalone records')
    if not frame.cumulative.str.strip().str.casefold().isin(['non-cumulative', 'non cumulative']).all():
        raise ValueError('Manifest contains cumulative records')
    if not frame.period.str.strip().str.casefold().eq('quarterly').all():
        raise ValueError('Manifest contains non-quarterly records')
    periods = frame.groupby('_COMPANY_KEY')._QUARTER.agg(set)
    if not periods.map(lambda values: values == expected).all():
        raise ValueError('Every manifest company must have all 12 quarters of 2022-2024')
    if not frame.xbrl.map(lambda value: isinstance(value, str) and allowed_url(value)).all():
        raise ValueError('Manifest has a missing or non-HTTPS NSE URL')
    if not frame.xbrl.map(lambda value: Path(urlsplit(value).path).suffix.lower() in {'.xml', '.xbrl'}).all():
        raise ValueError('Manifest contains non-XML links; use a separate Inline XBRL reader for HTML')
    conflicts = frame.groupby('xbrl')[['_COMPANY_KEY', '_QUARTER']].nunique().gt(1).any(axis=1)
    if conflicts.any():
        raise ValueError('A link is associated with conflicting company/period metadata')
    return frame, frame.drop_duplicates('xbrl').sort_values(['_QUARTER', 'symbol', 'xbrl'])


def fetch_xml(session, url, timeout, delay, max_bytes, attempts=3):
    for attempt in range(attempts):
        current = url
        try:
            for redirect in range(6):
                if not allowed_url(current):
                    raise ValueError('Redirect is outside HTTPS NSE domains')
                time.sleep(delay)
                with session.get(current, timeout=timeout, stream=True, allow_redirects=False) as response:
                    status = response.status_code
                    if status in {401, 403, 429}:
                        raise StopBatch(status)
                    if status in {301, 302, 303, 307, 308}:
                        location = response.headers.get('Location')
                        if not location:
                            raise ValueError('Redirect without Location')
                        current = urljoin(current, location)
                        continue
                    response.raise_for_status()
                    content = bytearray()
                    for chunk in response.iter_content(chunk_size=65536):
                        content.extend(chunk)
                        if len(content) > max_bytes:
                            raise ValueError('Response exceeds the configured file-size limit')
                    return bytes(content), status
            raise ValueError('Too many redirects')
        except requests.RequestException as exc:
            code = exc.response.status_code if exc.response is not None else None
            retryable = code is None or code >= 500
            if not retryable or attempt + 1 == attempts:
                raise
            time.sleep(min(5 * (2 ** attempt), 30))


def download(manifest_path, output_dir, limit=None, delay=1.5, session=None):
    if delay < 0 or (limit is not None and limit < 1):
        raise ValueError('Delay must be nonnegative; limit must be positive or None')
    frame, jobs = load_jobs(manifest_path)
    if limit is not None:
        jobs = jobs.head(limit)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    log_path = output_dir / 'download_log.csv'
    previous = pd.read_csv(log_path, dtype=str).drop_duplicates('url', keep='last').set_index('url') if log_path.exists() else pd.DataFrame()
    own_session = session is None
    if session is None:
        session = requests.Session()
        session.headers.update({'User-Agent': 'NSEAcademicResearchDownloader/1.0',
                                'Accept': 'application/xml,text/xml,*/*',
                                'Referer': 'https://www.nseindia.com/'})
    print(f'Manifest: {frame._COMPANY_KEY.nunique():,} company identifiers; {frame.xbrl.nunique():,} unique XML links.')
    print(f'This run: at most {len(jobs):,} files. Existing validated files will be skipped.')
    processed = 0
    stopped = False
    try:
        with log_path.open('a', newline='', encoding='utf-8') as log_file:
            writer = csv.DictWriter(log_file, fieldnames=LOG_FIELDS)
            if log_path.stat().st_size == 0:
                writer.writeheader()
            for _, row in jobs.iterrows():
                url = row.xbrl
                basename = re.sub(r'[^A-Za-z0-9_.-]', '_', Path(urlsplit(url).path).name)
                digest = hashlib.sha256(url.encode()).hexdigest()[:16]
                path = output_dir / str(row._QUARTER.year) / f'{Path(basename).stem}__{digest}.xml'
                record = dict.fromkeys(LOG_FIELDS, '')
                record.update(url=url, local_path=str(path), checked_utc=pd.Timestamp.now(tz='UTC').isoformat())
                try:
                    if path.exists():
                        content = path.read_bytes()
                        checksum = hashlib.sha256(content).hexdigest()
                        prior_hash = previous.loc[url, 'sha256'] if url in previous.index else None
                        if prior_hash == checksum:
                            missing_contexts = xml_details(content)
                            record.update(status='existing_validated', bytes=len(content), sha256=checksum,
                                          undefined_context_refs=missing_contexts)
                        else:
                            record['detail'] = 'Existing file has no matching log checksum; refreshed.'
                    if not record['status']:
                        content, http_status = fetch_xml(session, url, timeout=(15, 60), delay=delay,
                                                         max_bytes=25 * 1024 * 1024)
                        missing_contexts = xml_details(content)
                        path.parent.mkdir(parents=True, exist_ok=True)
                        temporary = path.with_suffix('.part')
                        temporary.write_bytes(content)
                        temporary.replace(path)
                        record.update(status='downloaded', bytes=len(content), http_status=http_status,
                                      sha256=hashlib.sha256(content).hexdigest(), undefined_context_refs=missing_contexts)
                except StopBatch as exc:
                    record.update(status='blocked_stop', http_status=exc.status, detail=str(exc))
                    stopped = True
                except (requests.RequestException, ET.ParseError, ValueError, OSError) as exc:
                    record.update(status='failed', detail=str(exc))
                writer.writerow(record)
                log_file.flush()
                processed += 1
                if processed % 25 == 0 or stopped:
                    print(f'Processed {processed:,}/{len(jobs):,}; latest status: {record["status"]}')
                if stopped:
                    print('NSE returned an access/rate-limit response; this batch has stopped.')
                    break
    except KeyboardInterrupt:
        print('Interrupted. Progress is saved; rerun the same command to resume.')
    finally:
        if own_session:
            session.close()
    latest = pd.read_csv(log_path, dtype=str).drop_duplicates('url', keep='last')
    result = frame.merge(latest.rename(columns={'url': 'xbrl'}), on='xbrl', how='left', validate='many_to_one')
    result['status'] = result.status.fillna('not_attempted')
    result.to_csv(output_dir / 'metadata_with_download_status.csv', index=False)
    run_status = result[['xbrl', 'status']].drop_duplicates().status.value_counts().to_dict()
    summary = {'manifest_company_identifiers': int(frame._COMPANY_KEY.nunique()),
               'manifest_unique_links': int(frame.xbrl.nunique()),
               'unique_link_status': run_status,
               'stopped_on_access_or_rate_limit': stopped,
               'financial_attribute_completeness_verified': False}
    (output_dir / 'download_summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(json.dumps(summary, indent=2))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=Path('nse_xml_2022_2024'))
    parser.add_argument('--limit', type=int, default=None)
    parser.add_argument('--delay', type=float, default=1.5)
    args = parser.parse_args()
    download(args.manifest, args.output, args.limit, args.delay)
