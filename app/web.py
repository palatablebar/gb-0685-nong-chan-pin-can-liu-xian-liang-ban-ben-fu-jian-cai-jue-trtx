import base64
from flask import request, render_template, jsonify
from app.errors import DomainError
from app.config import TITLE, MODULES, SHORT
from app.workflow import run, load
from app import store, alias_db


def payload():
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        raise DomainError('PAYLOAD', '请求必须是对象')
    if 'csv' in data and not isinstance(data['csv'], str):
        raise DomainError('CSV', 'CSV内容必须是文本')
    sample = data.get('sample', request.args.get('sample', 'dirty.csv'))
    content = data.get('csv')
    return (content.encode() if isinstance(content, str) else load(sample)), data.get('parameters', {})


def api(stage):
    content, parameters = payload()
    return jsonify(run(content, parameters, stage, alias_db.saved_decisions()))


def _enrich_mapping_view(data, source, params):
    """为名称裁决清单补充：每个原名称对应的采用限量提示与复检结论。"""
    if 'name_decisions' not in data:
        return data
    # 标准名 -> 限量摘要
    from app.modules.m3_versions.standards import standards
    limit_hint = {}
    for s in standards():
        limit_hint.setdefault(('product', s['product']), set()).add(
            '%s %s mg/kg [%s,%s)' % (s['analyte'], s['limit_mgkg'], s['start'], s['end']))
    data['limit_hints'] = {
        (d['field'], d['raw_name']): '；'.join(sorted(limit_hint.get(
            ('product', d['canonical_name']), set()))) or '限量随采样日选版'
        for d in data['name_decisions']
    }
    # 同一来源跑完整管线，取每个原始名称当前可得的复检结论；暂缓项显示 HOLD
    full = run(source, params, 7, alias_db.saved_decisions())
    verdicts = {}
    for c in full.get('calculations', []):
        for field, raw in (('product', c.get('product_raw', '')),
                           ('analyte', c.get('analyte_raw', ''))):
            verdicts.setdefault((field, raw), set()).add(c['code'])
    held = set()
    for r in full.get('held_rows', []):
        held.add(('product', r.get('product_raw', '')))
        held.add(('analyte', r.get('analyte_raw', '')))
    view = {k: '/'.join(sorted(v)) for k, v in verdicts.items()}
    for k in held:
        view.setdefault(k, '暂缓未判级')
    # 被拒绝归并的名称：相关行已隔离，不产生判级结论
    for d in data['name_decisions']:
        if d['status'] == 'REJECTED':
            view[(d['field'], d['raw_name'])] = 'REJECTED'
    data['verdicts_by_name'] = view
    return data


def page(stage, template):
    latest = store.history()
    state = store.get(latest[0]['id']) if latest else run(
        load('dirty.csv'), {}, saved_aliases=alias_db.saved_decisions())
    source = (load(request.args['sample']) if 'sample' in request.args
              else base64.b64decode(state['source_b64']) if state.get('source_b64')
              else load('dirty.csv'))
    params = state.get('manifest', {}).get('parameters', {})
    data = run(source, params, stage, alias_db.saved_decisions())
    data['alias_registry_saved'] = alias_db.list_aliases()
    if stage >= 2:
        _enrich_mapping_view(data, source, params)
    return render_template(template, title=TITLE, short=SHORT, modules=MODULES,
                           current=stage, data=data, run=state, history=latest)
