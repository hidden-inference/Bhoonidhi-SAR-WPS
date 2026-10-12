from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import re
import numpy as np


@dataclass
class Scene:
    root: Path
    scene_id: str
    timestamp: str
    channels: dict
    mask: Path
    footprint: list
    mode: str
    pixel_spacing: float
    rtc_applied: bool


def read_meta(root):
    meta = {}
    for line in (Path(root) / 'BAND_META.txt').read_text().splitlines():
        if '=' in line:
            k, v = line.split('=', 1)
            meta[k.strip().lower()] = v.strip()
    return meta


def read_scene(root):
    root = Path(root).resolve()
    meta = read_meta(root)
    def required(key):
        if key.lower() not in meta:
            raise ValueError(f'Missing metadata: {key}')
        return meta[key.lower()]
    mode = required('ImagingMode').strip()
    if required('SatID') != 'EOS-04' or mode not in ('MRS', 'CRS'):
        raise ValueError('Only EOS-04 MRS and CRS products are supported')
    if required('ProductType') != 'L2B-ARD-PRODUCT':
        raise ValueError('Expected L2B-ARD-PRODUCT (terrain normalised Gamma0 imagery)')
    sid = required('OTSProductID')
    timestamp = re.sub(r'(\.\d{6})\d+', r'\1', required('SceneCenterTime'))
    timestamp = datetime.strptime(timestamp, '%d-%b-%Y %H:%M:%S.%f').replace(tzinfo=timezone.utc).isoformat()
    channels = {}
    for i in range(1, int(required('NoOfPolarizations')) + 1):
        ch = required(f'TxRxPol{i}').upper()
        # the Gamma0 calibration constant is the Beta0 one (spec section 6.3)
        k = float(required(f'Calibration_Constant_Beta0_{ch}'))
        n = float(required(f'Image_Noise_Bias_{ch}'))
        if not np.isfinite([k, n]).all() or k == -9999 or n < 0:
            raise ValueError(f'Invalid calibration metadata for {ch}')
        band = root / f'scene_{ch}' / f'imagery_{ch}.tif'
        if not band.is_file():
            raise ValueError(f'Missing product file: {band}')
        channels[ch] = dict(band=band, calibration_db=k, noise_bias=n)
    masks = sorted(root.glob('*_mask.tif'))
    if len(masks) != 1:
        raise ValueError('Expected exactly one quality mask')
    footprint = [[float(required(f'Image{p}Lon')), float(required(f'Image{p}Lat'))]
                 for p in ('UL', 'UR', 'LR', 'LL', 'UL')]
    return Scene(root, sid, timestamp, channels, masks[0], footprint, mode,
                 float(required('OutputPixelSpacing')), required('RTC_Apply_Flag') == '1')
