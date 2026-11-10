"""Structured handbook content and dependency-free Word export."""

import re
from io import BytesIO
from xml.etree import ElementTree as ET
from zipfile import ZIP_DEFLATED, ZipFile

from .risk_verification_flow import FlowError

ID = re.compile(r'[a-z0-9-]{1,80}')
CASE_ID = re.compile(r'[a-f0-9]{32}')
KINDS = {'paragraph', 'list', 'table', 'question', 'note'}
W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
REL = 'http://schemas.openxmlformats.org/package/2006/relationships'
CT = 'http://schemas.openxmlformats.org/package/2006/content-types'
ET.register_namespace('w', W)
ET.register_namespace('r', R)


def _string(value, limit):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise FlowError(f'手册文字不能为空，单项最多{limit}字')
    if re.search(r'[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]', value):
        raise FlowError('手册文字含无效字符')
    return value.strip()


def validate_handbook(value):
    if not isinstance(value, dict):
        raise FlowError('手册格式不正确')
    seen = set()
    total_text = 0

    def nodes(items, depth):
        nonlocal total_text
        if not isinstance(items, list) or len(items) > 80 or (depth > 3 and items):
            raise FlowError('手册目录最多三级')
        result = []
        for node in items:
            if not isinstance(node, dict):
                raise FlowError('章节格式不正确')
            identifier = node.get('id')
            if not isinstance(identifier, str) or not ID.fullmatch(identifier) or identifier in seen or len(seen) >= 80:
                raise FlowError('章节编号重复或无效，整本最多80节')
            seen.add(identifier)
            blocks = node.get('blocks', [])
            if not isinstance(blocks, list) or len(blocks) > 40:
                raise FlowError('每节最多40个内容块')
            normalized = []
            for block in blocks:
                if not isinstance(block, dict) or not isinstance(block.get('kind'), str) or block['kind'] not in KINDS:
                    raise FlowError('内容块类型不正确')
                content = _string(block.get('text'), 4000)
                if block['kind'] == 'table':
                    rows = [line.split('|') for line in content.splitlines() if line.strip()]
                    if not rows or len(rows) > 40 or not 2 <= len(rows[0]) <= 8 or any(len(row) != len(rows[0]) for row in rows):
                        raise FlowError('表格每行须有相同列数，支持2至8列、最多40行')
                total_text += len(content)
                normalized.append({'kind': block['kind'], 'text': content})
            links = node.get('cases', [])
            if not isinstance(links, list) or len(links) > 10:
                raise FlowError('每节最多关联10个案例')
            cases = []
            for link in links:
                if not isinstance(link, dict) or not isinstance(link.get('id'), str) or not CASE_ID.fullmatch(link['id']):
                    raise FlowError('专项案例编号无效')
                cases.append({'id': link['id'], 'title': _string(link.get('title'), 150)})
            if len({case['id'] for case in cases}) != len(cases):
                raise FlowError('同一小节不能重复关联同一案例')
            examples = node.get('examples', [])
            if not isinstance(examples, list) or len(examples) > 10:
                raise FlowError('每节最多10个培训示例')
            normalized_examples = []
            for example in examples:
                if not isinstance(example, dict):
                    raise FlowError('培训示例格式不正确')
                detail = _string(example.get('detail'), 3000)
                total_text += len(detail)
                normalized_examples.append({'title': _string(example.get('title'), 150), 'detail': detail})
            title = _string(node.get('title'), 100)
            total_text += len(title)
            children = nodes(node.get('children', []), depth + 1)
            if not (normalized or children or cases or normalized_examples):
                raise FlowError(f'「{title}」还没有内容')
            result.append({'id': identifier, 'title': title, 'blocks': normalized,
                           'cases': cases, 'examples': normalized_examples, 'children': children})
        return result

    chapters = nodes(value.get('chapters'), 1)
    if not chapters or total_text > 80000:
        raise FlowError('手册至少需要一章，整本正文最多8万字')
    return {'source': _string(value.get('source'), 500), 'chapters': chapters}


def case_links(nodes):
    for node in nodes:
        yield from node['cases']
        yield from case_links(node['children'])


def _tag(namespace, name):
    return f'{{{namespace}}}{name}'


def _w(parent, name, value=None):
    element = ET.SubElement(parent, _tag(W, name))
    if value is not None:
        element.set(_tag(W, 'val'), value)
    return element


def _paragraph(parent, text, style=None):
    paragraph = _w(parent, 'p')
    if style:
        _w(_w(paragraph, 'pPr'), 'pStyle', style)
    _run(paragraph, text)
    return paragraph


def _run(parent, text, style=None):
    run = _w(parent, 'r')
    if style:
        _w(_w(run, 'rPr'), 'rStyle', style)
    for index, line in enumerate(text.split('\n')):
        if index:
            _w(run, 'br')
        element = _w(run, 't')
        element.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
        element.text = line


def export_word(payload, base_url):
    if not isinstance(payload, dict):
        raise FlowError('导出范围无效')
    handbook = validate_handbook(payload.get('handbook'))
    name = _string(payload.get('name'), 100)
    version = _string(payload.get('policyVersion'), 60)
    selected = payload.get('chapterId')
    chapters = [(str(i), node) for i, node in enumerate(handbook['chapters'], 1)
                if selected is None or node['id'] == selected]
    if not chapters:
        raise FlowError('请选择有效章节')

    def numbered(items, depth=1):
        for number, node in items:
            yield number, node, depth
            yield from numbered(((f'{number}.{index}', child)
                                 for index, child in enumerate(node['children'], 1)), depth + 1)

    outline = list(numbered(chapters))
    document = ET.Element(_tag(W, 'document'))
    body = _w(document, 'body')
    rels = ET.Element('Relationships', xmlns=REL)
    ET.SubElement(rels, 'Relationship', Id='rIdStyles', Type=f'{R}/styles', Target='styles.xml')
    _paragraph(body, name, 'Title')
    _paragraph(body, f'版本 {version}　范围：{"整本手册" if selected is None else chapters[0][1]["title"]}')
    _paragraph(body, f'来源：{handbook["source"]}')
    if payload.get('scope'):
        _paragraph(body, f'适用：{_string(payload["scope"], 1000)}')
    if payload.get('start') and payload.get('end'):
        _paragraph(body, f'适用日期：{_string(payload["start"], 10)} 至 {_string(payload["end"], 10)}')
    _paragraph(body, '目录', 'Title')
    for index, (number, node, depth) in enumerate(outline, 1):
        paragraph = _w(body, 'p')
        indent = _w(_w(paragraph, 'pPr'), 'ind')
        indent.set(_tag(W, 'left'), str((depth - 1) * 360))
        link = _w(paragraph, 'hyperlink')
        link.set(_tag(W, 'anchor'), f'chapter{index}')
        _run(link, f'{number}  {node["title"]}', 'Hyperlink')
    _w(_w(_w(body, 'p'), 'r'), 'br').set(_tag(W, 'type'), 'page')
    for index, (number, node, depth) in enumerate(outline, 1):
        heading = _w(body, 'p')
        _w(_w(heading, 'pPr'), 'pStyle', f'Heading{depth}')
        start = _w(heading, 'bookmarkStart')
        start.set(_tag(W, 'id'), str(index))
        start.set(_tag(W, 'name'), f'chapter{index}')
        _run(heading, f'{number}  {node["title"]}')
        _w(heading, 'bookmarkEnd').set(_tag(W, 'id'), str(index))
        for block in node['blocks']:
            if block['kind'] == 'table':
                table = _w(body, 'tbl')
                properties = _w(table, 'tblPr')
                borders = _w(properties, 'tblBorders')
                for edge in ('top', 'left', 'bottom', 'right', 'insideH', 'insideV'):
                    _w(borders, edge, 'single').set(_tag(W, 'color'), 'D9D9D9')
                rows = [line.split('|') for line in block['text'].splitlines() if line.strip()]
                grid = _w(table, 'tblGrid')
                for _ in rows[0]:
                    _w(grid, 'gridCol').set(_tag(W, 'w'), str(9000 // len(rows[0])))
                for cells in rows:
                    row = _w(table, 'tr')
                    for cell in cells:
                        _paragraph(_w(row, 'tc'), cell.strip())
            elif block['kind'] == 'list':
                for item_index, line in enumerate(block['text'].splitlines(), 1):
                    _paragraph(body, f'{item_index}. {line}')
            else:
                prefix = {'question': '问答　', 'note': '提示　'}.get(block['kind'], '')
                _paragraph(body, prefix + block['text'])
        for example in node['examples']:
            _paragraph(body, f'培训示例：{example["title"]}')
            _paragraph(body, example['detail'])
        for case in node['cases']:
            relation_id = f'rIdCase{len(rels)}'
            ET.SubElement(rels, 'Relationship', Id=relation_id, Type=f'{R}/hyperlink',
                          Target=f'{base_url}/risk-followup/library?case={case["id"]}', TargetMode='External')
            paragraph = _paragraph(body, '专项案例：')
            link = _w(paragraph, 'hyperlink')
            link.set(_tag(R, 'id'), relation_id)
            _run(link, case['title'], 'Hyperlink')

    page = _w(body, 'sectPr')
    size = _w(page, 'pgSz')
    size.set(_tag(W, 'w'), '11906')
    size.set(_tag(W, 'h'), '16838')
    margins = _w(page, 'pgMar')
    for side in ('top', 'right', 'bottom', 'left'):
        margins.set(_tag(W, side), '1440')
    for side in ('header', 'footer', 'gutter'):
        margins.set(_tag(W, side), '0')

    styles = ET.Element(_tag(W, 'styles'))
    for style_id, label, size, depth in [('Title', 'Title', '38', None), *(
            (f'Heading{i}', f'heading {i}', str(34 - 4 * i), i - 1) for i in range(1, 4))]:
        style = _w(styles, 'style')
        style.set(_tag(W, 'type'), 'paragraph')
        style.set(_tag(W, 'styleId'), style_id)
        _w(style, 'name', label)
        if depth is not None:
            _w(_w(style, 'pPr'), 'outlineLvl', str(depth))
        run = _w(style, 'rPr')
        _w(run, 'b')
        _w(run, 'sz', size)
    hyperlink = _w(styles, 'style')
    hyperlink.set(_tag(W, 'type'), 'character')
    hyperlink.set(_tag(W, 'styleId'), 'Hyperlink')
    _w(hyperlink, 'name', 'Hyperlink')
    _w(_w(hyperlink, 'rPr'), 'color', '185ABD')

    types = ET.Element('Types', xmlns=CT)
    ET.SubElement(types, 'Default', Extension='rels', ContentType='application/vnd.openxmlformats-package.relationships+xml')
    ET.SubElement(types, 'Default', Extension='xml', ContentType='application/xml')
    for part in ('document', 'styles'):
        suffix = 'document.main' if part == 'document' else 'styles'
        ET.SubElement(types, 'Override', PartName=f'/word/{part}.xml',
                      ContentType=f'application/vnd.openxmlformats-officedocument.wordprocessingml.{suffix}+xml')
    package = ET.Element('Relationships', xmlns=REL)
    ET.SubElement(package, 'Relationship', Id='rId1', Type=f'{R}/officeDocument', Target='word/document.xml')
    output = BytesIO()
    with ZipFile(output, 'w', ZIP_DEFLATED) as archive:
        for path, data in {
            '[Content_Types].xml': types, '_rels/.rels': package, 'word/document.xml': document,
            'word/styles.xml': styles, 'word/_rels/document.xml.rels': rels,
        }.items():
            archive.writestr(path, ET.tostring(data, encoding='utf-8', xml_declaration=True))
    output.seek(0)
    return output
