import streamlit as st
import xml.etree.ElementTree as ET
from io import BytesIO
import zipfile

RENAME_RULES = {
    'Kick-off': 'Start',
    'LCFC Shot Off/Blocked': 'LCFC Shot Off and Blocked',
    'Opp Shot Off/Blocked': 'Opp Shot Off and Blocked',
    'LCFC Wide/Deep Cross': 'LCFC Wide and Deep Cross',
    'Opp Wide/Deep Cross': 'Opp Wide and Deep Cross',
}

REMOVE_CONTAINS = [
    'Coach Review',
    'Post-match',
    'Half Time Organiser',
]

st.title('Sportscode → OpenField XML Converter')

uploaded = st.file_uploader('Upload raw Sportscode XML', type='xml')

if uploaded:
    raw = uploaded.read()

    try:
        text = raw.decode('utf-16')
    except Exception:
        text = raw.decode(errors='ignore')

    root = ET.fromstring(text)
    all_instances = root.find('ALL_INSTANCES')

    events = []
    kickoffs = []

    for inst in all_instances.findall('instance'):
        code = inst.findtext('code', '')

        if code == 'Kick-off':
            kickoffs.append(float(inst.findtext('start', '0')))

        remove = False

        if code and code[0].isdigit() and '. ' in code:
            remove = True

        if any(x in code for x in REMOVE_CONTAINS):
            remove = True

        if remove:
            continue

        code = RENAME_RULES.get(code, code)

        events.append({
            'start': float(inst.findtext('start', '0')),
            'end': float(inst.findtext('end', '0')),
            'code': code,
        })

    if len(kickoffs) < 2:
        st.error('Could not find a second Kick-off event.')
        st.stop()

    split_point = kickoffs[1]

    first_half = [e for e in events if e['start'] < split_point]
    second_half = [e for e in events if e['start'] >= split_point]

    def build_xml(event_list):
        root = ET.Element('file')
        all_i = ET.SubElement(root, 'ALL_INSTANCES')

        for idx, e in enumerate(event_list, start=1):
            inst = ET.SubElement(all_i, 'instance')
            ET.SubElement(inst, 'ID').text = str(idx)
            ET.SubElement(inst, 'start').text = str(e['start'])
            ET.SubElement(inst, 'end').text = str(e['end'])
            ET.SubElement(inst, 'code').text = e['code']

        return ET.tostring(root, encoding='utf-8', xml_declaration=True)

    zip_buffer = BytesIO()

    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('OpenField_1st_half.xml', build_xml(first_half))
        zf.writestr('OpenField_2nd_half.xml', build_xml(second_half))

    st.success('Conversion complete.')
    st.write(f'First-half events: {len(first_half)}')
    st.write(f'Second-half events: {len(second_half)}')

    st.download_button(
        'Download XML Files',
        data=zip_buffer.getvalue(),
        file_name='OpenField_XMLs.zip',
        mime='application/zip'
    )
