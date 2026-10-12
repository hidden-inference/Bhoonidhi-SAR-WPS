from pathlib import Path
import json
import zipfile
import numpy as np
import rasterio


def write_raster(path, data, crs, transform, description, nodata=-9999.0):
    dtype = data.dtype.name if data.dtype in (np.uint8, np.uint16) else 'float32'
    with rasterio.open(path, 'w', driver='GTiff', width=data.shape[1], height=data.shape[0],
                       count=1, dtype=dtype, crs=crs, transform=transform, nodata=nodata,
                       compress='deflate', predictor=3 if dtype == 'float32' else 2) as dst:
        dst.write(np.where(np.isfinite(data), data, nodata).astype(dtype), 1)
        dst.set_band_description(1, description)
    return Path(path)


def write_metadata(path, metadata):
    Path(path).write_text(json.dumps(metadata, indent=2, allow_nan=False)+'\n')


def package(directory, files):
    path = Path(directory) / 'result.zip'
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as archive:
        for file in files:
            archive.write(file, arcname=Path(file).name)
    return path
