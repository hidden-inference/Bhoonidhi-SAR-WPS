"""Generate an Execute request centered in a catalogued scene's footprint."""
from xml.etree import ElementTree as ET

WPS='http://www.opengis.net/wps/1.0.0'
OWS='http://www.opengis.net/ows/1.1'
ET.register_namespace('wps',WPS)
ET.register_namespace('ows',OWS)


def execute_xml(scene, asynchronous=False, identifier='Subset'):
    points=scene['footprint'][:-1]
    lon=sum(p[0] for p in points)/len(points)
    lat=sum(p[1] for p in points)/len(points)
    root=ET.Element(f'{{{WPS}}}Execute',service='WPS',version='1.0.0')
    ET.SubElement(root,f'{{{OWS}}}Identifier').text=identifier
    inputs=ET.SubElement(root,f'{{{WPS}}}DataInputs')
    def inp(name):
        node=ET.SubElement(inputs,f'{{{WPS}}}Input')
        ET.SubElement(node,f'{{{OWS}}}Identifier').text=name
        return ET.SubElement(node,f'{{{WPS}}}Data')
    box=ET.SubElement(inp('bbox'),f'{{{WPS}}}BoundingBoxData',crs='urn:ogc:def:crs:OGC:1.3:CRS84',dimensions='2')
    ET.SubElement(box,f'{{{OWS}}}LowerCorner').text=f'{lon-.02:.6f} {lat-.02:.6f}'
    ET.SubElement(box,f'{{{OWS}}}UpperCorner').text=f'{lon+.02:.6f} {lat+.02:.6f}'
    pol='DH' if {'HH','HV'}.issubset(scene['channels']) else 'HH'
    fields=[('date',scene['datetime'][:10])]
    if identifier != 'polarisationRatio': fields.append(('polarization',pol))
    fields.append(('scene_id',scene['scene_id']))
    if identifier == 'waterCandidateMask': fields.append(('threshold_db','-20'))
    for name,value in fields:
        ET.SubElement(inp(name),f'{{{WPS}}}LiteralData').text=value
    form=ET.SubElement(root,f'{{{WPS}}}ResponseForm')
    document=ET.SubElement(form,f'{{{WPS}}}ResponseDocument',**({'storeExecuteResponse':'true','status':'true'} if asynchronous else {}))
    output=ET.SubElement(document,f'{{{WPS}}}Output',asReference='true')
    ET.SubElement(output,f'{{{OWS}}}Identifier').text='result'
    return ET.tostring(root,encoding='utf-8',xml_declaration=True)
