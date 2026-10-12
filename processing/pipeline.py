from pathlib import Path
import time
import platform
import numpy as np
import scipy
import rasterio
from rasterio.vrt import WarpedVRT
from rasterio.enums import Resampling
from .catalog import select_scene
from .subset import windows, validate_bbox
from .calibration import gamma0_linear, to_db
from .speckle import lee3x3, statistics
from .export import write_raster, write_metadata, package

BASE = Path(__file__).resolve().parents[1]
PRODUCTS = ('subset', 'linear2db', 'water', 'ratio')
DEFAULT_WATER_THRESHOLD_DB = -20.0


def read_channel(scene, ch, bbox, max_pixels):
    band = scene.channels[ch]
    with rasterio.open(band['band']) as src, rasterio.open(scene.mask) as quality:
        requested, halo, trim, aoi = windows(src, bbox, max_pixels)
        dn = src.read(1, window=halo, masked=True)
        with WarpedVRT(quality, crs=src.crs, transform=src.transform, width=src.width, height=src.height,
                       resampling=Resampling.nearest, nodata=0) as aligned:
            mask = aligned.read(1, window=halo)
        return dict(dn=dn.data, valid=(mask == 128) & ~np.ma.getmaskarray(dn) & (dn.data > 0), mask=mask,
                    requested=requested, trim=trim, aoi=aoi, crs=src.crs, transform=src.window_transform(requested),
                    bounds=list(rasterio.windows.bounds(requested, src.transform)), band=band)


def run_pipeline(*, product, bbox, date, output_dir, polarization='DH', scene_id=None,
                 catalog=BASE/'data/catalog/scenes.json', max_pixels=4_000_000,
                 threshold_db=None, enl=None):
    start = time.perf_counter()
    if product not in PRODUCTS:
        raise ValueError(f'product must be one of {PRODUCTS}')
    bbox = validate_bbox(bbox)
    if product == 'ratio':
        polarization = 'DH'
    if product == 'water':
        threshold_db = DEFAULT_WATER_THRESHOLD_DB if threshold_db is None else threshold_db
        if not np.isfinite(threshold_db):
            raise ValueError('Threshold must be finite')
        if enl is not None and (not np.isfinite(enl) or enl <= 0):
            raise ValueError('ENL must be finite and positive')
    scene, channels = select_scene(catalog, bbox, date, polarization, scene_id)
    output_dir = Path(output_dir)
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError('Output directory must be empty to avoid overwriting results')
    output_dir.mkdir(parents=True, exist_ok=True)
    files, records, linear = [], {}, {}
    for ch in channels:
        d = read_channel(scene, ch, bbox, max_pixels)
        trim, aoi, band = d['trim'], d['aoi'], d['band']
        record = dict(calibration_db=band['calibration_db'], noise_bias=band['noise_bias'],
                      bounds=d['bounds'], crs=d['crs'].to_string(), transform=list(d['transform'])[:6])
        if product == 'subset':
            raw = np.where(d['aoi'], d['dn'][trim], 0).astype('uint16')
            if not (raw > 0).any():
                raise ValueError(f'No pixels in requested AOI ({ch})')
            files.append(write_raster(output_dir/f'{ch}_subset.tif', raw, d['crs'], d['transform'], f'{ch} raw DN subset', 0))
            record.update(shape=list(raw.shape), nonzero_pixels=int((raw > 0).sum()))
            if ch == channels[0]:
                m = np.where(d['aoi'], d['mask'][trim], 0).astype('uint8')
                files.append(write_raster(output_dir/'quality_mask.tif', m, d['crs'], d['transform'],
                                          '128 valid, 64 shadow, 16 layover, 0 outside', 0))
        else:
            gamma, below = gamma0_linear(d['dn'], band['calibration_db'], band['noise_bias'], d['valid'])
            if product == 'water' and enl is not None:
                gamma = lee3x3(gamma, enl)
            g = gamma[trim].copy()
            g[~aoi] = np.nan
            if not np.isfinite(g).any():
                raise ValueError(f'No valid positive backscatter pixels in requested AOI ({ch})')
            linear[ch] = g
            db = to_db(g)
            record.update(shape=list(g.shape), invalid_pixels=int((~np.isfinite(g)).sum()),
                          nonpositive_power_pixels=int((below[trim] & aoi).sum()), gamma0_linear_stats=statistics(g))
            if product == 'linear2db':
                files.append(write_raster(output_dir/f'{ch}_gamma0_db.tif', db, d['crs'], d['transform'], f'{ch} Gamma0 (dB)'))
            elif product == 'water':
                water = np.full(g.shape, 255, dtype=np.uint8)
                good = np.isfinite(db)
                water[good] = (db[good] < threshold_db).astype('uint8')
                files.append(write_raster(output_dir/f'{ch}_water_candidate.tif', water, d['crs'], d['transform'],
                                          '0=other, 1=candidate water, 255=invalid', 255))
                record.update(water_pixels=int((water == 1).sum()), valid_pixels=int(good.sum()))
            else:
                ref = (d['crs'], d['transform'])
    if product == 'ratio':
        hh, hv = linear['HH'], linear['HV']
        ratio = np.divide(hv, hh, out=np.full(hh.shape, np.nan), where=np.isfinite(hh) & np.isfinite(hv) & (hh > 0))
        files.append(write_raster(output_dir/'HV_HH_ratio.tif', ratio, ref[0], ref[1], 'HV/HH ratio (linear Gamma0 division)'))
        files.append(write_raster(output_dir/'HV_HH_ratio_db.tif', to_db(ratio), ref[0], ref[1], 'HV/HH ratio in dB = 10*log10(HV/HH)'))
    metadata = dict(product=product, scene_id=scene.scene_id, mode=scene.mode, acquisition_timestamp=scene.timestamp,
        rtc_applied=scene.rtc_applied, bbox=bbox, bbox_crs='OGC:CRS84', channels=records,
        ratio='HV/HH = linear Gamma0 of HV divided by linear Gamma0 of HH; dB version = 10*log10(ratio)' if product == 'ratio' else None,
        gamma0_linear='(DN^2 - noise_bias) / 10^(Kcal_Beta0_dB/10)  [EOS-04 format doc 6.3]; gamma0_dB = 10*log10(linear)',
        quality_policy='mask value 128 only; nearest-neighbour alignment; nonpositive power excluded',
        water_threshold_db=threshold_db if product == 'water' else None,
        water_threshold_note='demo default, not validated for the study area' if product == 'water' and threshold_db == DEFAULT_WATER_THRESHOLD_DB else None,
        lee_enl=enl if product == 'water' else None, duration_seconds=time.perf_counter()-start,
        versions=dict(python=platform.python_version(), numpy=np.__version__, scipy=scipy.__version__,
                      rasterio=rasterio.__version__, gdal=rasterio.__gdal_version__))
    path = output_dir/'metadata.json'
    write_metadata(path, metadata)
    files.append(path)
    return package(output_dir, files)
