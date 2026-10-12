"""Downloads EOS-04 L2B (MRS + CRS) scenes from Bhoonidhi.

Reads each zip's directory with HTTP Range requests and fetches only the imagery, mask and
metadata (the incidence-angle and area rasters are not needed), so downloads are much smaller and resumable.
Login comes from BHOONIDHI_USER / BHOONIDHI_PASSWORD or a prompt and is never stored.
"""
import argparse
import datetime as dt
import fcntl
import io
import threading
import zlib
import getpass
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import time
from urllib.parse import urljoin, urlparse
import zipfile
import requests
from processing.subset import validate_bbox

API = 'https://bhoonidhi-api.nrsc.gov.in'
COLLECTIONS = ['EOS-04_SAR-MRS_L2B', 'EOS-04_SAR-CRS_L2B']
DEFAULT_BBOX = [69.0, 8.0, 97.0, 37.0]
ROOT = Path(__file__).resolve().parent
RAW = ROOT / 'data/raw'
MANIFEST = ROOT / 'data/download_manifest.json'
PROGRESS = ROOT / 'data/download_progress.json'
CATALOGUE = ROOT / 'data/stac_items.json'


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(value, indent=2), encoding='utf-8')
    tmp.replace(path)


class Bhoonidhi:
    def __init__(self):
        self.session = requests.Session()
        self.user = os.environ.get('BHOONIDHI_USER') or input('Bhoonidhi userId: ')
        password = os.environ.get('BHOONIDHI_PASSWORD') or getpass.getpass('Bhoonidhi password: ')
        self.tokens = {}
        self.lock = threading.RLock()
        try:
            self.authenticate({'userId':self.user, 'password':password, 'grant_type':'password'})
        except Exception:
            self.session.close()
            raise
        finally:
            del password

    def authenticate(self, body):
        with self.session.post(f'{API}/auth/token', json=body, timeout=60, allow_redirects=False) as r:
            if r.status_code == 403:
                raise RuntimeError('Bhoonidhi denied authentication (403): API access or active-session limit. Check account access.')
            if r.status_code == 401:
                raise RuntimeError('Bhoonidhi login/refresh failed (401).')
            if r.status_code != 200:
                raise RuntimeError(f'Bhoonidhi authentication HTTP {r.status_code}')
            tokens = r.json()
        if not tokens.get('access_token') or not tokens.get('refresh_token'):
            raise RuntimeError('Authentication response is missing tokens')
        self.tokens = tokens
        self.expires = time.monotonic() + float(tokens.get('expires_in',1200)) - 60

    def refresh(self):
        self.authenticate({'userId':self.user, 'refresh_token':self.tokens['refresh_token'], 'grant_type':'refresh_token'})

    def request(self, method, url, headers=None, **kw):
        url = urljoin(API + '/', url)
        parsed = urlparse(url)
        if parsed.scheme != 'https' or parsed.netloc != urlparse(API).netloc:
            raise ValueError('Refusing to send authentication to a different origin')
        for attempt in range(6):
            with self.lock:
                if time.monotonic() >= self.expires:
                    self.refresh()
                token = self.tokens['access_token']
            try:
                r = self.session.request(method, url, headers={**(headers or {}), 'Authorization':f"Bearer {token}"},
                                         allow_redirects=False, **kw)
            except (requests.ConnectionError, requests.Timeout):
                if attempt == 5:
                    raise
                time.sleep(min(5*2**attempt, 60))
                continue
            if r.status_code == 401 and attempt < 5:
                r.close()
                with self.lock:
                    if self.tokens['access_token'] == token:
                        self.refresh()
                continue
            if r.status_code in (408,412,429,500,502,503,504) and attempt < 5:
                retry = r.headers.get('Retry-After','')
                delay = min(max(float(retry),1),60) if retry.isdigit() else min(5*2**attempt,60)
                r.close(); time.sleep(delay); continue
            if 300 <= r.status_code < 400:
                r.close()
                raise RuntimeError('Unexpected API redirect; refusing to forward credentials')
            return r

    def close(self):
        try:
            if self.tokens.get('refresh_token'):
                self.session.post(f'{API}/auth/logout',timeout=20,allow_redirects=False,
                                  headers={'Authorization':f"Bearer {self.tokens['refresh_token']}"}).close()
        except requests.RequestException:
            pass
        self.tokens.clear()
        self.session.close()


SKIP_BIG = ('_lia.tif', '_area.tif', '.jpg', '.kmz', '_grid.txt', '.xsd', '.wld', '.aux.xml', '_rgb.geo.png')


def wanted(name):
    low = name.lower()
    if low.endswith(SKIP_BIG) or low.endswith('.meta'):
        return False
    return low.endswith(('.tif', 'band_meta.txt', 'product.xml', 'browse.geo.png'))


def monthly_windows(start, end):
    # the search API rejects date ranges over 366 days
    a, b = dt.date.fromisoformat(start), dt.date.fromisoformat(end)
    day = a
    while day <= b:
        nxt = (day.replace(day=1) + dt.timedelta(days=32)).replace(day=1)
        last = min(nxt - dt.timedelta(days=1), b)
        yield day, last
        day = nxt


def search_window(client, collection, bbox, first, last):
    params = {'collections': collection, 'bbox': ','.join(str(v) for v in bbox), 'limit': 500,
              'datetime': f'{first}T00:00:00Z/{last}T23:59:59Z'}
    items, url = {}, f'{API}/data/search'
    for _ in range(50):
        with client.request('GET', url, params=params, timeout=180) as r:
            r.raise_for_status(); page = r.json()
        for item in page.get('features', []):
            if item.get('collection') != collection:
                raise ValueError('API returned an unexpected collection')
            items[item['id']] = item
        nxt = next((x for x in page.get('links', []) if x.get('rel') == 'next'), None)
        if not nxt or not page.get('features'):
            return list(items.values())
        url, params = urljoin(url, nxt['href']), None
        time.sleep(.4)
    raise RuntimeError('Too many pages in one month')


def search_all(client, a):
    found = {}
    for collection in a.collections:
        for first, last in monthly_windows(a.start, a.end):
            for item in search_window(client, collection, a.bbox, first, last):
                found[item['id']] = item
            time.sleep(.4)
        print(f'{collection}: {sum(1 for i in found.values() if i["collection"] == collection)} items', flush=True)
    return sorted(found.values(), key=lambda i: (i['collection'], i['properties'].get('datetime') or '', i['id']))


def choose(items, count, dual_only=True, mrs_every=4):
    # online products only, spread over time; every 4th one is MRS (bigger files), the rest CRS
    def spread(collection, n):
        pool = [i for i in items if i['collection'] == collection and i['properties'].get('Online') == 'Y'
                and (not dual_only or i['properties'].get('Polarization') == 'DH')]
        if not pool or n <= 0:
            return []
        step = len(pool) / min(n, len(pool))
        return [pool[int(k*step)] for k in range(min(n, len(pool)))]
    mrs_n = -(-count // mrs_every)
    mrs, crs = spread('EOS-04_SAR-MRS_L2B', mrs_n), spread('EOS-04_SAR-CRS_L2B', count - mrs_n)
    order = []
    while mrs or crs:
        if mrs: order.append(mrs.pop(0))
        for _ in range(mrs_every-1):
            if crs: order.append(crs.pop(0))
        if not mrs and crs: order.extend(crs); crs = []
    return order


class RemoteZip(io.RawIOBase):
    """Lets zipfile read the remote archive through Range requests."""
    def __init__(self, client, collection, item_id, size):
        self.client, self.params, self.size, self.pos = client, {'id': item_id, 'collection': collection}, size, 0

    def seekable(self): return True
    def readable(self): return True
    def tell(self): return self.pos

    def seek(self, offset, whence=0):
        self.pos = offset if whence == 0 else self.pos+offset if whence == 1 else self.size+offset
        return self.pos

    def readinto(self, buffer):
        n = min(len(buffer), self.size-self.pos)
        if n <= 0:
            return 0
        data = fetch_range(self.client, self.params, self.pos, self.pos+n-1)
        buffer[:len(data)] = data
        self.pos += len(data)
        return len(data)


def fetch_range(client, params, start, end):
    with client.request('GET', f'{API}/download', params=params, headers={'Range': f'bytes={start}-{end}'}, timeout=(30, 120)) as r:
        if r.status_code != 206:
            raise RuntimeError(f'Server ignored Range request (HTTP {r.status_code})')
        data = r.content
    if len(data) != end-start+1:
        raise requests.ConnectionError('Short range read')
    return data


def archive_size(client, collection, item_id):
    with client.request('GET', f'{API}/download', params={'id': item_id, 'collection': collection},
                        headers={'Range': 'bytes=0-0'}, timeout=(30, 120)) as r:
        if r.status_code != 206:
            raise RuntimeError(f'Download not available (HTTP {r.status_code}): {r.text[:120]}')
        return int(r.headers['Content-Range'].rsplit('/', 1)[1])


def download_member(client, params, info, target, reserve):
    target = Path(target)
    if target.exists() and target.stat().st_size == info.file_size:
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    part = target.with_name(target.name+'.part')
    head = fetch_range(client, params, info.header_offset, info.header_offset+29)
    if head[:4] != b'PK\x03\x04':
        raise ValueError('Bad zip local header')
    start = info.header_offset + 30 + int.from_bytes(head[26:28], 'little') + int.from_bytes(head[28:30], 'little')
    if shutil.disk_usage(target.parent).free < info.file_size*2 + reserve:
        raise RuntimeError('Insufficient disk space: stopping before the free-space reserve is consumed')
    for attempt in range(8):
        have = part.stat().st_size if part.exists() else 0
        if have > info.compress_size:
            part.unlink(); have = 0
        try:
            while have < info.compress_size:
                end = min(have + 4*2**20, info.compress_size) - 1
                chunk = fetch_range(client, params, start+have, start+end)
                with part.open('ab') as f:
                    f.write(chunk)
                have += len(chunk)
            break
        except (requests.RequestException, RuntimeError):
            if attempt == 7:
                raise
            time.sleep(min(5*2**attempt, 60))
    raw = part.read_bytes()
    data = raw if info.compress_type == zipfile.ZIP_STORED else zlib.decompress(raw, -15)
    if len(data) != info.file_size or zlib.crc32(data) != info.CRC:
        part.unlink()
        raise ValueError(f'CRC mismatch for {info.filename}; deleted, rerun to fetch again')
    tmp = target.with_name(target.name+'.tmp')
    tmp.write_bytes(data)
    tmp.replace(target)
    part.unlink()


def download_product(client, item, manifest, reserve):
    item_id = safe_id(item)
    collection = item['collection']
    destination = RAW/item_id
    if manifest.get(item_id, {}).get('complete') and destination.exists():
        return manifest[item_id]
    params = {'id': item_id, 'collection': collection}
    size = archive_size(client, collection, item_id)
    with zipfile.ZipFile(io.BufferedReader(RemoteZip(client, collection, item_id, size), buffer_size=2**16)) as z:
        members = [i for i in z.infolist() if not i.is_dir() and wanted(i.filename)]
        roots = {i.filename.split('/')[0] for i in members}
        if len(roots) != 1 or not any(i.filename.endswith('BAND_META.txt') for i in members):
            raise ValueError('Unexpected product layout')
        for info in members:
            relative = Path(info.filename)
            if relative.is_absolute() or '..' in relative.parts:
                raise ValueError('Unsafe archive member')
    for info in members:
        download_member(client, params, info, destination/Path(*Path(info.filename).parts[1:]), reserve)
    record = {'collection': collection, 'datetime': item['properties'].get('datetime'), 'archive_bytes': size,
              'downloaded_bytes': sum(i.compress_size for i in members), 'files': [Path(*Path(i.filename).parts[1:]).as_posix() for i in members],
              'downloaded_at': dt.datetime.now(dt.timezone.utc).isoformat(), 'complete': True}
    return record


def safe_id(item):
    if item.get('collection') not in COLLECTIONS:
        raise ValueError('Only EOS-04 L2B products can be ingested')
    value = item['id']
    if not re.fullmatch(r'[A-Za-z0-9_-]+', value):
        raise ValueError('Unsafe product identifier')
    return value


def rebuild_catalog():
    import subprocess, sys
    result = subprocess.run([sys.executable, str(ROOT/'scripts/ingest_local.py')], capture_output=True, text=True, cwd=ROOT)
    if result.returncode:
        print('Catalogue rebuild failed:', (result.stderr or result.stdout)[-300:], flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--bbox', nargs=4, type=float, default=DEFAULT_BBOX, metavar=('MIN_LON', 'MIN_LAT', 'MAX_LON', 'MAX_LAT'))
    ap.add_argument('--start', default='2021-01-01'); ap.add_argument('--end', default='2026-01-01')
    ap.add_argument('--collections', nargs='+', default=COLLECTIONS, choices=COLLECTIONS)
    ap.add_argument('--target', type=int, default=60, help='How many products to fetch, spread over time')
    ap.add_argument('--workers', type=int, default=4, help='Parallel downloads')
    ap.add_argument('--include-single-pol', action='store_true', help='Also allow products with only one channel')
    ap.add_argument('--reserve-gb', type=float, default=20)
    ap.add_argument('--saved-items', action='store_true', help='Reuse data/stac_items.json instead of searching again')
    ap.add_argument('--inventory-only', action='store_true')
    a = ap.parse_args()
    a.bbox = validate_bbox(a.bbox)
    for day in (a.start, a.end):
        if dt.date.fromisoformat(day).isoformat() != day:
            ap.error('Dates must be YYYY-MM-DD')
    if a.target <= 0 or a.workers <= 0 or a.reserve_gb < 0: ap.error('Invalid numbers')
    RAW.mkdir(parents=True, exist_ok=True)
    lock = (ROOT/'data/download.lock').open('w')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit('A downloader is already running')
    manifest = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}
    manifest = {k: v for k, v in manifest.items() if v.get('collection') in COLLECTIONS}
    client = None
    try:
        write_json(PROGRESS, {'status': 'awaiting_login'})
        client = Bhoonidhi()
        items = json.loads(CATALOGUE.read_text()) if a.saved_items else search_all(client, a)
        if not a.saved_items: write_json(CATALOGUE, items)
        by = {}
        for i in items: by[i['collection']] = by.get(i['collection'], 0) + 1
        print('Inventory:', by, '| dual-pol:', sum(1 for i in items if i['properties'].get('Polarization') == 'DH'), flush=True)
        if a.inventory_only:
            write_json(PROGRESS, {'status': 'inventory_only', 'inventory': by}); return
        queue = choose(items, a.target, dual_only=not a.include_single_pol)
        print(f'{len(queue)} products selected', flush=True)
        state = {'done': len([k for k in manifest if manifest[k].get('complete')]), 'failed': {}, 'bytes': 0, 'current': {}}
        mutex = threading.Lock()
        def progress(status='downloading'):
            write_json(PROGRESS, {'status': status, 'selected': len(queue), 'complete_products': state['done'],
                                  'failed': state['failed'], 'downloaded_bytes_this_run': state['bytes'], 'in_progress': sorted(state['current'])})
        def work(item):
            if stop.is_set(): return
            with mutex: state['current'][item['id']] = 1; progress()
            try:
                record = download_product(client, item, manifest, int(a.reserve_gb*2**30))
                with mutex:
                    manifest[item['id']] = record; write_json(MANIFEST, manifest)
                    state['done'] = len([k for k in manifest if manifest[k].get('complete')]); state['bytes'] += record['downloaded_bytes']
                    rebuild_catalog()
                print(f'[{state["done"]} complete] {item["id"]} ({record["downloaded_bytes"]/2**20:.0f} MiB)', flush=True)
            except Exception as exc:
                if 'Insufficient disk space' in str(exc): stop.set()
                with mutex: state['failed'][item['id']] = str(exc)[:200]
                print('FAILED', item['id'], exc, flush=True)
            finally:
                with mutex: state['current'].pop(item['id'], None); progress()
        stop = threading.Event()
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(a.workers) as pool:
            list(pool.map(work, queue))
        progress('complete')
    except Exception as exc:
        write_json(PROGRESS, {'status': 'failed', 'error': str(exc)})
        raise
    finally:
        if client: client.close()
        lock.close()


if __name__ == '__main__':
    main()
