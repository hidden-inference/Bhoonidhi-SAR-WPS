import json
from datetime import date as Date, datetime, timezone
from pathlib import Path
from .metadata import read_scene
from .subset import validate_bbox


def build_catalog(raw, target):
    target = Path(target).resolve()
    entries = []
    for p in sorted(Path(raw).rglob('BAND_META.txt')):
        try:
            scene = read_scene(p.parent)
        except ValueError as exc:  # half-downloaded or unsupported product: skip, do not break the catalogue
            print(f'Skipping {p.parent.name}: {exc}')
            continue
        import os
        entries.append(dict(scene_id=scene.scene_id, datetime=scene.timestamp,
                            collection=f'EOS-04_SAR-{scene.mode}_L2B', mode=scene.mode, channels=list(scene.channels),
                            pixel_spacing_m=scene.pixel_spacing, rtc_applied=scene.rtc_applied,
                            product_dir=os.path.relpath(scene.root, target.parent), footprint=scene.footprint))
    target.parent.mkdir(parents=True, exist_ok=True)
    import tempfile
    with tempfile.NamedTemporaryFile('w',dir=target.parent,delete=False,suffix='.json') as handle:
        json.dump(entries,handle,indent=2)
        handle.write('\n')
        temporary = Path(handle.name)
    temporary.replace(target)
    return entries


def select_scene(catalog, bbox, date, polarization, scene_id=None):
    bbox = validate_bbox(bbox)
    try:
        day = Date.fromisoformat(date)
        if day.isoformat() != date:
            raise ValueError()
    except (ValueError, TypeError):
        raise ValueError('Date must be YYYY-MM-DD') from None
    if polarization not in ('HH','HV','DH'):
        raise ValueError('Polarization must be HH, HV or DH')
    channels = ['HH','HV'] if polarization == 'DH' else [polarization]
    path = Path(catalog).resolve()
    matches = []
    for item in json.loads(path.read_text()):
        if scene_id is not None and item['scene_id'] != scene_id:
            continue
        if datetime.fromisoformat(item['datetime']).astimezone(timezone.utc).date() != day:
            continue
        if not set(channels).issubset(item['channels']):
            continue
        if not footprint_overlaps(item['footprint'], bbox):
            continue
        matches.append(item)
    if not matches:
        raise ValueError('No scene matches date, footprint, polarization and scene_id')
    if len(matches) > 1:
        raise ValueError('Multiple matching scenes; specify scene_id: '+', '.join(m['scene_id'] for m in matches))
    scene = read_scene(path.parent / matches[0]['product_dir'])
    if scene.scene_id != matches[0]['scene_id'] or scene.timestamp != matches[0]['datetime']:
        raise ValueError('Catalogue is stale; rebuild it')
    return scene, channels


def footprint_overlaps(points, bbox):
    """Clip footprint to rectangle (Sutherland-Hodgman), then test positive area."""
    polygon = [tuple(p) for p in points]
    for axis, bound, sign in [(0,bbox[0],1),(0,bbox[2],-1),(1,bbox[1],1),(1,bbox[3],-1)]:
        clipped = []
        if not polygon:
            return False
        previous = polygon[-1]
        for current in polygon:
            pin = sign*(previous[axis]-bound) >= 0
            cin = sign*(current[axis]-bound) >= 0
            if pin != cin:
                t = (bound-previous[axis])/(current[axis]-previous[axis])
                clipped.append(tuple(previous[k]+t*(current[k]-previous[k]) for k in (0,1)))
            if cin:
                clipped.append(current)
            previous = current
        polygon = clipped
    return len(polygon) >= 3 and abs(sum(a[0]*b[1]-b[0]*a[1]
           for a,b in zip(polygon,polygon[1:]+polygon[:1]))) > 1e-12
