"""Rebuilds the scene catalogue, optionally after adding a manually downloaded L2B zip."""
import argparse
from pathlib import Path
import sys
import zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fetch_bhoonidhi import RAW, ROOT, wanted
from processing.catalog import build_catalog


def add_archive(path):
    with zipfile.ZipFile(path) as z:
        members=[i for i in z.infolist() if not i.is_dir() and wanted(i.filename)]
        roots={i.filename.split('/')[0] for i in members}
        if len(roots)!=1 or not any(i.filename.endswith('BAND_META.txt') for i in members):
            raise SystemExit('This does not look like an EOS-04 L2B product ZIP')
        root=roots.pop()
        for info in members:
            relative=Path(*Path(info.filename).parts[1:])
            if relative.is_absolute() or '..' in relative.parts: raise SystemExit('Unsafe member in ZIP')
            target=RAW/root/relative
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(z.read(info))
    return root


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--archive',type=Path)
    args=p.parse_args()
    if args.archive:
        print('Added',add_archive(args.archive))
    entries=build_catalog(RAW,ROOT/'data/catalog/scenes.json')
    print(f'{len(entries)} scenes catalogued')

if __name__=='__main__': main()
