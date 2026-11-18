from copy import deepcopy
from app.config import REQUIRED, NUMERIC, DATES, TIMES
from app.errors import DomainError
from app.modules.m2_mapping.coerce import number, day, instant, SENTINELS
from app.modules.m2_mapping.matching import build_decisions, merge_manual, resolve_name
from app.modules.m2_mapping.alias_registry import load_alias_table


def normalize(state, saved_aliases=None):
    state = deepcopy(state)
    good = []
    groups = {}
    for row in state['rows']:
        try:
            for field in REQUIRED:
                if str(row.get(field, '')).strip().upper() in SENTINELS:
                    raise DomainError('MISSING', '必填值缺失')
            item = dict(row)
            for field in NUMERIC:
                if field in item and item[field] != '':
                    item[field] = number(item[field])
            for field in DATES:
                if field in item and item[field] != '':
                    item[field] = day(item[field])
            for field in TIMES:
                if field in item and item[field] != '':
                    item[field] = instant(item[field])
            key = (item['id'], str(item.get('version', '1')))
            groups.setdefault(key, []).append(item)
        except DomainError as error:
            state['quarantine'].append({'line': row['_line'], 'id': row.get('id', ''), 'code': error.code, 'raw': row['_raw']})
    for key, rows in groups.items():
        unique = {str(sorted((k, str(v)) for k, v in r.items() if not k.startswith('_'))) for r in rows}
        if len(unique) > 1:
            for r in rows:
                state['quarantine'].append({'line': r['_line'], 'id': r['id'], 'code': 'CONFLICT', 'raw': r['_raw']})
        else:
            good.append(rows[0])
            state['duplicate_count'] += len(rows) - 1

    # 名称裁决：系统证据 + 持久化的人工关系。原始名称保形保留，
    # 归并后的标准名单独存放，供限量选版使用。
    standards = _load_standards()
    system = build_decisions(good, standards, load_alias_table())
    decisions = merge_manual(system, saved_aliases or [])

    accepted, held = [], []
    for item in good:
        product_std, product_status = resolve_name('product', item['product'], decisions)
        analyte_std, analyte_status = resolve_name('analyte', item['analyte'], decisions)
        item['product_raw'] = item['product']
        item['analyte_raw'] = item['analyte']
        item['product_mapping'] = product_status
        item['analyte_mapping'] = analyte_status
        if product_status == 'REJECTED' or analyte_status == 'REJECTED':
            field = 'product' if product_status == 'REJECTED' else 'analyte'
            state['quarantine'].append({
                'line': item['_line'], 'id': item['id'], 'code': 'ALIAS',
                'raw': item['_raw'], 'reason': '%s 名称归并被拒绝，禁止套用限量' % field,
            })
            continue
        if not product_std or not analyte_std:
            # 暂缓：不隔离、不判级，原始名称完整保形，等待人工裁决后只重算受影响行
            item['product'] = item['product_raw']
            item['analyte'] = item['analyte_raw']
            held.append(item)
            continue
        item['product'] = product_std
        item['analyte'] = analyte_std
        accepted.append(item)

    state['rows'] = accepted
    state['held_rows'] = held
    state['name_decisions'] = [d.to_dict() for d in sorted(decisions.values(), key=lambda x: (x.field, x.raw_name))]
    state['mapping_summary'] = {
        'total_names': len(decisions),
        'auto': sum(d.status == 'AUTO' for d in decisions.values()),
        'confirmed': sum(d.status == 'CONFIRMED' for d in decisions.values()),
        'pending': sum(d.status == 'PENDING' for d in decisions.values()),
        'rejected': sum(d.status == 'REJECTED' for d in decisions.values()),
        'held_rows': len(held),
    }
    return state


def _load_standards():
    from app.modules.m3_versions.standards import standards
    return standards()
