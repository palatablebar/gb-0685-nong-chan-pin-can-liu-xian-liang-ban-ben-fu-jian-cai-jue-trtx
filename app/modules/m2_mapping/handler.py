from flask import Blueprint, request
from app.web import api, page
from app.errors import DomainError
from app import alias_db, store
from app.workflow import run

bp = Blueprint('m2_mapping', __name__)


@bp.get('/m2_mapping')
def screen():
    return page(2, 'm2_mapping.html')


@bp.route('/api/m2_mapping', methods=['GET', 'POST'])
def preview():
    return api(2)


@bp.get('/api/m2_mapping/aliases')
def list_aliases():
    from flask import jsonify
    return jsonify(alias_db.list_aliases())


def _latest_source():
    latest = store.history()
    if not latest:
        raise DomainError('NOT_FOUND', '尚无运行批次，请先采信报告', 404)
    state = store.get(latest[0]['id'])
    import base64
    content = base64.b64decode(state['source_b64']) if state.get('source_b64') else None
    if content is None:
        raise DomainError('NOT_FOUND', '批次缺少来源快照', 404)
    params = state.get('manifest', {}).get('parameters', {})
    return content, params, state['run_id']


@bp.post('/api/m2_mapping/aliases')
def decide_alias():
    """确认或拒绝一条名称归并关系。

    关系写入独立别名表后，仅以同一来源重跑受影响链路：已确认关系不会因
    重跑新增别名或被改写；写入失败时不触碰任何旧结果。
    """
    from flask import jsonify
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        raise DomainError('PAYLOAD', '请求必须是对象')
    field = data.get('field')
    raw_name = data.get('raw_name')
    status = data.get('status')
    target = data.get('canonical_name', '') or ''
    reason = data.get('reason', 'MANUAL')
    evidence = data.get('evidence', '')
    if field not in ('product', 'analyte'):
        raise DomainError('ALIAS_FIELD', '名称字段无效')
    content, params, run_id = _latest_source()
    # 先校验目标名称确实存在于限量标准，防止把错误限量品种写入已确认关系
    from app.modules.m3_versions.standards import standards
    standard_names = {s[field] for s in standards()}
    if status == 'CONFIRMED' and target not in standard_names:
        raise DomainError('ALIAS_TARGET', '归并目标不在限量标准名称表中，已保留旧版结果')
    saved = alias_db.save_alias(field, raw_name, target, reason, status, evidence, run_id)
    # 同一来源重跑；别名表已更新，其他项目结果由确定性管线保持不变
    new_state = run(content, params, saved_aliases=alias_db.saved_decisions())
    return jsonify({'alias': saved,
                    'mapping_summary': new_state['mapping_summary'],
                    'held_rows': len(new_state['held_rows']),
                    'decisions': new_state['name_decisions']})


@bp.post('/api/m2_mapping/aliases/reset')
def reset_alias():
    """暂缓：撤销该名称的人工归并关系，回到系统证据态，仅重算受影响链路。"""
    from flask import jsonify
    data = request.get_json(silent=True) or {}
    field, raw_name = data.get('field'), data.get('raw_name')
    content, params, _ = _latest_source()
    result = alias_db.reset_alias(field, raw_name)
    new_state = run(content, params, saved_aliases=alias_db.saved_decisions())
    result.update(mapping_summary=new_state['mapping_summary'],
                  held_rows=len(new_state['held_rows']),
                  decisions=new_state['name_decisions'])
    return jsonify(result)
