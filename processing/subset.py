"""CRS84 AOIs, native-grid windows, and one-pixel Lee halos."""
import math
import numpy as np
from rasterio.windows import Window, from_bounds
from rasterio.warp import transform_bounds, transform_geom
from rasterio.features import geometry_mask

CRS84 = 'OGC:CRS84'


def validate_bbox(bbox):
    try:
        a = np.asarray(bbox, dtype=float)
    except (TypeError, ValueError) as exc:
        raise ValueError('BBOX requires four numeric coordinates') from exc
    if a.shape != (4,) or not np.isfinite(a).all():
        raise ValueError('BBOX requires four finite coordinates')
    x0, y0, x1, y1 = a
    if not (-180 <= x0 < x1 <= 180 and -90 < y0 < y1 < 90):
        raise ValueError('Invalid CRS84 BBOX; antimeridian and poles are unsupported')
    return a.tolist()


def aoi_polygon(bbox):
    x0, y0, x1, y1 = validate_bbox(bbox)
    # Densify edges before nonlinear map projection.
    edges = [((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)),
             ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))]
    coords = [list(np.asarray(a) * (1-t) + np.asarray(b) * t)
              for a, b in edges for t in np.linspace(0, 1, 65, endpoint=False)]
    return {'type': 'Polygon', 'coordinates': [coords + [coords[0]]]}


def windows(src, bbox, max_pixels=1_000_000):
    if src.crs is None or src.transform.b or src.transform.d or src.transform.a <= 0 or src.transform.e >= 0:
        raise ValueError('A north-up georeferenced raster is required')
    bbox = validate_bbox(bbox)
    bounds = transform_bounds(CRS84, src.crs, *bbox, densify_pts=64)
    w = from_bounds(*bounds, transform=src.transform)
    left, top = math.floor(w.col_off), math.floor(w.row_off)
    right, bottom = math.ceil(w.col_off+w.width), math.ceil(w.row_off+w.height)
    if (right-left)*(bottom-top) > max_pixels:
        raise ValueError(f'AOI exceeds {max_pixels} requested pixels')
    left, top, right, bottom = max(0,left), max(0,top), min(src.width,right), min(src.height,bottom)
    if left >= right or top >= bottom:
        raise ValueError('AOI outside raster coverage')
    requested = Window(left, top, right-left, bottom-top)
    halo = Window(max(0,left-1), max(0,top-1), min(src.width,right+1)-max(0,left-1),
                  min(src.height,bottom+1)-max(0,top-1))
    trim = (slice(int(top-halo.row_off), int(bottom-halo.row_off)),
            slice(int(left-halo.col_off), int(right-halo.col_off)))
    polygon = transform_geom(CRS84, src.crs, aoi_polygon(bbox))
    mask = geometry_mask([polygon], out_shape=(int(requested.height),int(requested.width)),
                         transform=src.window_transform(requested), invert=True)
    return requested, halo, trim, mask
