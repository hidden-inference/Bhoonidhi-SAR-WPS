"""Portable WPS application: WPS_PUBLIC_URL controls advertised service/result URLs."""
import configparser
import json
import os
from pathlib import Path
import tempfile
from urllib.parse import urlparse
from flask import Flask, jsonify, send_from_directory, Response, abort
from pywps import Service
from werkzeug.middleware.dispatcher import DispatcherMiddleware
from jinja2 import ChoiceLoader, FileSystemLoader
import pywps.response.basic as pywps_basic
from xml.etree import ElementTree as ET
from processes.eos04_process import make_processes
from scripts.example_request import execute_xml

BASE = Path(__file__).resolve().parent

# Use our own capabilities template (no position/phone, only the contact fields we fill in).
if not getattr(pywps_basic, '_custom_templates', False):
    _package_loader = pywps_basic.PackageLoader
    pywps_basic.PackageLoader = lambda *a, **k: ChoiceLoader([FileSystemLoader(str(BASE/'templates')), _package_loader(*a, **k)])
    pywps_basic._custom_templates = True


def simple_xml(root):
    ET.indent(root)
    return Response(ET.tostring(root, encoding='unicode'), mimetype='text/xml')


def create_application(config=None):
    settings = configparser.ConfigParser(interpolation=None)
    settings.read(config or BASE/'pywps.cfg')
    for section in ['server','logging']:
        if not settings.has_section(section): settings.add_section(section)
    def folder(key, default, section='server'):
        value = Path(settings.get(section,key,fallback=str(BASE/default)))
        if not value.is_absolute(): value = BASE/value
        value.mkdir(parents=True,exist_ok=True)
        settings.set(section,key,str(value))
        return value
    work = folder('workdir','work')
    outputs = folder('outputpath','outputs')
    logs = BASE/'logs'; logs.mkdir(exist_ok=True)
    logpath = settings.get('logging','file',fallback=str(logs/'pywps.log'))
    if not Path(logpath).is_absolute(): logpath = str(BASE/logpath)
    settings.set('logging','file',logpath)
    if not config:
        settings.set('logging','database',f'sqlite:///{logs}/pywps.sqlite3')
    public = os.environ.get('WPS_PUBLIC_URL')
    if not public and (BASE/'config/public-url.txt').exists():
        public = (BASE/'config/public-url.txt').read_text().strip()
    if public:
        public = public.rstrip('/')
        parsed = urlparse(public)
        if parsed.scheme not in ('http','https') or not parsed.netloc or parsed.path or parsed.query or parsed.fragment or parsed.username:
            raise ValueError('WPS_PUBLIC_URL must be an HTTP(S) origin, e.g. https://name.trycloudflare.com')
        settings.set('server','url',public+'/wps')
        settings.set('server','outputurl',public+'/outputs/')
    catalog = Path(os.environ.get('WPS_CATALOG',str(BASE/'data/catalog/scenes.json')))
    inventory = Path(os.environ.get('WPS_INVENTORY',str(BASE/'data/stac_items.json')))
    downloads = Flask(__name__)
    downloads.config['MAX_CONTENT_LENGTH'] = 1024*1024

    def scenes():
        return json.loads(catalog.read_text()) if catalog.exists() else []

    @downloads.route('/')
    def index():
        endpoint = settings.get('server','url')
        return jsonify(service='EOS-04 L2B (MRS and CRS) WPS',
            GetCapabilities=endpoint+'?service=WPS&request=GetCapabilities&acceptversions=1.0.0',
            DescribeProcess=endpoint+'?service=WPS&version=1.0.0&request=DescribeProcess&identifier=Subset',
            Execute={'method':'POST','url':endpoint,'body':'Download /example.xml and submit as text/xml'},
            available_scenes='/scenes',simple_capabilities='/simple/capabilities',simple_describe='/simple/describe?identifier=Subset',example='/example.xml?process=Subset',scene_count=len(scenes()))

    @downloads.route('/health')
    def health():
        return jsonify(status='ok',scene_count=len(scenes()))

    @downloads.route('/scenes')
    def available_scenes():
        """Scenes stored on this server (these can be processed). Add ?all=1 to also list everything
        Bhoonidhi has online for the region (from the saved search), marked offline true/false."""
        from flask import request
        local = {item['scene_id']: item for item in scenes()}
        rows = [dict(scene_id=k, offline=True, **{f: v.get(f) for f in ('datetime','collection','mode','channels','pixel_spacing_m','footprint')})
                for k, v in local.items()]
        if request.args.get('all') in ('1','true','yes') and inventory.exists():
            for item in json.loads(inventory.read_text()):
                if item['id'] in local: continue
                props = item.get('properties',{})
                rows.append(dict(scene_id=item['id'], offline=False, datetime=props.get('datetime'), collection=item.get('collection'),
                    mode=props.get('Mode'), channels={'DH':['HH','HV']}.get(props.get('Polarization'),[props.get('Polarization')]),
                    footprint=[[float(x),float(y)] for x,y in props.get('ImgLatLon',[])] or None))
        rows.sort(key=lambda r: (r['datetime'] or '', r['scene_id']))
        return jsonify(count=len(rows), offline_count=len(local), scenes=rows)

    @downloads.route('/example.xml')
    def example():
        from flask import request
        items = scenes()
        selected = next((s for s in items if s['scene_id']==request.args.get('scene_id')),None) if request.args.get('scene_id') else (items[0] if items else None)
        identifier = request.args.get('process','Subset')
        if not selected or identifier not in [p.identifier for p in procs]: abort(404)
        return Response(execute_xml(selected,identifier=identifier),mimetype='text/xml')

    @downloads.route('/simple/capabilities')
    def simple_capabilities():
        root = ET.Element('service', name='EOS-04 SAR WPS')
        ET.SubElement(root,'about').text = 'This service works on EOS-04 (RISAT-1A) C-band SAR Level-2B scenes (MRS and CRS) that we downloaded to our own server.'
        ET.SubElement(root,'made_by').text = 'Aryan Agrawal, CyberGIS project'
        data = ET.SubElement(root,'data_we_have')
        for item in scenes():
            ET.SubElement(data,'scene', id=item['scene_id'], date=item['datetime'][:10], mode=item.get('mode',''), channels=' '.join(item['channels']))
        procs_el = ET.SubElement(root,'things_you_can_run')
        for process in procs:
            ET.SubElement(procs_el,'process', id=process.identifier, does=process.title)
        ET.SubElement(root,'more_info').text = 'Use /simple/describe?identifier=<process id> to see the inputs of a process'
        return simple_xml(root)

    @downloads.route('/simple/describe')
    def simple_describe():
        from flask import request
        process = next((p for p in procs if p.identifier==request.args.get('identifier')),None)
        if process is None: abort(404)
        root = ET.Element('process', id=process.identifier)
        ET.SubElement(root,'what_it_does').text = process.abstract
        inputs = ET.SubElement(root,'you_give_me')
        for item in process.inputs:
            ET.SubElement(inputs,'input', name=item.identifier, required='yes' if item.min_occurs else 'no').text = item.title
        ET.SubElement(root,'you_get_back').text = 'A ZIP file (link in the response) with GeoTIFFs and metadata.json'
        ET.SubElement(root,'example_request').text = f'/example.xml?process={process.identifier}'
        return simple_xml(root)

    @downloads.route('/outputs/<path:filename>')
    def output_file(filename):
        return send_from_directory(outputs,filename)

    with tempfile.NamedTemporaryFile('w',suffix='.cfg',dir=work,delete=False) as f:
        settings.write(f)
        runtime_config = Path(f.name)
    try:
        procs = make_processes(catalog)
        service = Service(procs,[str(runtime_config)])
    finally:
        runtime_config.unlink(missing_ok=True)
    return DispatcherMiddleware(downloads,{'/wps':service})


application = create_application()
