"""The WPS processes. All of them read scenes from the local catalogue (data/catalog/scenes.json)."""
import json
import logging
from pathlib import Path
import tempfile
from pywps import Process, LiteralInput, BoundingBoxInput, ComplexOutput, Format
from pywps.inout.literaltypes import AnyValue
from pywps.app.exceptions import ProcessError
from processing.pipeline import run_pipeline, BASE

CRS84 = 'urn:ogc:def:crs:OGC:1.3:CRS84'


def scene_summary(catalog):
    """Short text for the abstracts. The full list is always at /scenes."""
    try:
        scenes = json.loads(Path(catalog).read_text())
    except (OSError, ValueError):
        return 'no scenes loaded yet'
    if not scenes:
        return 'no scenes loaded yet'
    modes = {}
    for s in scenes:
        modes[s.get('mode', '?')] = modes.get(s.get('mode', '?'), 0) + 1
    days = sorted(s['datetime'][:10] for s in scenes)
    return f"{len(scenes)} scenes offline ({', '.join(f'{n} {m}' for m, n in sorted(modes.items()))}), from {days[0]} to {days[-1]}; see /scenes for the full list"


class EOS04Process(Process):
    """One class for all the processes. `product` decides what the pipeline computes."""

    def __init__(self, catalog, identifier, title, abstract, product, polarization=True, water=False):
        self.catalog = Path(catalog)
        self.product = product
        inputs = [BoundingBoxInput('bbox', 'Area of interest as lon lat (lower-left and upper-right corner)', crss=[CRS84], dimensions=2),
                  LiteralInput('date', 'Acquisition date, written like 2025-10-31', data_type='string', allowed_values=AnyValue())]
        if polarization:
            inputs.append(LiteralInput('polarization', 'Which channel: HH, HV or DH (DH = both)', data_type='string', allowed_values=['HH', 'HV', 'DH']))
        inputs.append(LiteralInput('scene_id', 'Scene id from /scenes (optional, needed if two scenes match)', data_type='string', min_occurs=0, allowed_values=AnyValue()))
        if water:
            inputs += [LiteralInput('threshold_db', 'Pixels darker than this (dB) become water. Optional, default -20 (a demo value, not validated)', data_type='float', min_occurs=0, allowed_values=AnyValue()),
                       LiteralInput('enl', 'Optional: ENL number above 0. If given, a 3x3 Lee speckle filter runs before the threshold', data_type='float', min_occurs=0, allowed_values=AnyValue())]
        super().__init__(self._handler, identifier=identifier, title=title, version='1.0.0',
            abstract=f'{abstract} Data: {scene_summary(catalog)}.',
            store_supported=True, status_supported=True, inputs=inputs,
            outputs=[ComplexOutput('result', 'ZIP file with the GeoTIFFs and a metadata.json', supported_formats=[Format('application/zip')], as_reference=True)])

    def _handler(self, request, response):
        def value(name):
            items = request.inputs.get(name, [])
            return items[0].data if items else None
        try:
            b = request.inputs['bbox'][0]
            if b.crs != CRS84:
                raise ValueError('BBOX CRS must be CRS84 (longitude, latitude)')
            response.update_status('Checking the request and loading the scene', 10)
            output = Path(tempfile.mkdtemp(prefix='sar-', dir=self.workdir))
            number = lambda name: None if value(name) is None else float(value(name))
            archive = run_pipeline(product=self.product, bbox=list(b.ll) + list(b.ur), date=value('date'),
                polarization=value('polarization') or 'DH', scene_id=value('scene_id'),
                threshold_db=number('threshold_db'), enl=number('enl'), catalog=self.catalog, output_dir=output)
            response.update_status('Done, ZIP is ready', 95)
            response.outputs['result'].file = str(archive)
            return response
        except ValueError as exc:
            raise ProcessError(str(exc)) from exc
        except Exception as exc:
            logging.getLogger(__name__).exception('EOS-04 processing failed')
            raise ProcessError('Processing failed; consult server logs') from exc


def make_processes(catalog):
    return [
        EOS04Process(catalog, 'Subset', 'Subset',
            'Cuts out the part of the scene inside your bounding box. You get the raw digital numbers (DN) and the quality mask, nothing else is changed.',
            'subset'),
        EOS04Process(catalog, 'Linear2dB', 'Linear to dB',
            'Cuts your bounding box and converts the DN to Gamma0 backscatter in dB: (DN^2 - noise bias) / 10^(K/10) gives linear Gamma0, then 10*log10.',
            'linear2db'),
        EOS04Process(catalog, 'waterCandidateMask', 'Water candidate mask',
            'Marks dark (low backscatter) pixels as possible water: 1 = candidate water, 0 = other, 255 = no data. This is a simple threshold, not a flood map.',
            'water', water=True),
        EOS04Process(catalog, 'polarisationRatio', 'HV/HH polarisation ratio',
            'Divides the HV backscatter by the HH backscatter (HV / HH) for your bounding box. You get the plain ratio and the same ratio in dB. Needs a scene that has both HH and HV.',
            'ratio', polarization=False),
    ]
