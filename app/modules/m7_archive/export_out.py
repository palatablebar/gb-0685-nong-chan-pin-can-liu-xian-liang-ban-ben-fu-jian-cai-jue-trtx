import io, csv, json, hashlib
from decimal import Decimal


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=_default)


def _default(obj):
    if isinstance(obj, Decimal):
        return str(obj)
    raise TypeError('不可序列化的类型 %s' % type(obj))


def bundle(state):
    out = io.StringIO(newline='')
    writer = csv.writer(out)
    writer.writerow(['记录类型', '批次', '来源行', '业务ID', '原因码', '内容'])
    rid = state.get('run_id', 'preview')
    writer.writerow(['运行清单', rid, '', '', '', _json(state.get('manifest', {}))])
    writer.writerow(['对账', rid, '', '', '', _json(state.get('reconcile', {}))])
    for row in state.get('calculations', []):
        writer.writerow(['计算', rid, row.get('line', ''), row.get('id', ''), row.get('code', ''),
                         _json(row)])
    # 暂缓行：名称关系未裁决，原样留证，不得丢失也不得套用限量
    for row in state.get('held_rows', []):
        writer.writerow(['暂缓', rid, row.get('_line', ''), row.get('id', ''), 'NAME_PENDING',
                         _json({k: v for k, v in row.items() if not k.startswith('_')})])
    # 名称裁决清单：原名称、归并依据、采用标准名
    for row in state.get('name_decisions', []):
        writer.writerow(['名称裁决', rid, '', '', row.get('status', ''), _json(row)])
    for row in state['quarantine']:
        writer.writerow(['隔离', rid, row['line'], row.get('id', ''), row['code'],
                         _json(row.get('raw', {}))])
    return '﻿' + out.getvalue()


def checksum(state):
    return hashlib.sha256(bundle(state).encode('utf-8')).hexdigest()
