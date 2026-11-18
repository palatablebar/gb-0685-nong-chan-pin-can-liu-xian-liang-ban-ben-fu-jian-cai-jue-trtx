"""名称裁决：全角规整自动采信、简称/旧称人工确认、近似编号暂缓。

裁决原则：
- 只有逐字一致或 NFKC 字符层面规整（无歧义）可 AUTO 直接判级；
- 院内简称/旧称即使有登记表也必须人工 CONFIRMED；
- 编号/品种相近只给候选证据，默认 PENDING，禁止套用限量；
- 同源重跑不新增别名、不改写已确认关系；关系变化产生新 run_id；
- 拒绝归并按 ALIAS 隔离，原始名称与隔离数据不丢失。
"""
import pytest
from app.workflow import run, load
from app.modules.m2_mapping.matching import (
    canonical_form, key_form, similarity, build_decisions, merge_manual,
    resolve_name, AliasDecision,
)
from app.modules.m2_mapping.alias_registry import load_alias_table
from app.modules.m3_versions.standards import standards


@pytest.fixture
def alias_state():
    return run(load('aliases.csv'), {}, 2)


def _decision(state, field, raw):
    return next(d for d in state['name_decisions']
                if d['field'] == field and d['raw_name'] == raw)


def test_fullwidth_analyte_auto_normalized(alias_state):
    # 全角 Ｐ０１ 属于 NFKC 确定性规整，自动采信，可直接判级
    d = _decision(alias_state, 'analyte', 'Ｐ０１')
    assert d['status'] == 'AUTO' and d['canonical_name'] == 'P01'
    assert d['reason'] == 'NFKC_FULLWIDTH'
    rows = {r['id']: r for r in alias_state['rows']}
    assert rows['A0002']['analyte'] == 'P01'
    assert rows['A0002']['analyte_raw'] == 'Ｐ０１'  # 原名称保形


def test_exact_standard_name_is_auto(alias_state):
    assert _decision(alias_state, 'product', '苹果')['reason'] == 'EXACT'
    assert _decision(alias_state, 'analyte', 'P01')['status'] == 'AUTO'


def test_registry_alias_still_requires_manual(alias_state):
    # 院内旧称/简称：登记表只给证据，默认暂缓，不得自动套限量
    for field, raw in (('product', '红富士'), ('product', 'apple'),
                       ('analyte', '有机磷P01'), ('analyte', '甲拌磷项')):
        d = _decision(alias_state, field, raw)
        assert d['status'] == 'PENDING' and d['reason'] == 'ALIAS_TABLE'
        assert d['canonical_name'] == ''


def test_similar_code_must_stay_pending(alias_state):
    # P010/P10 与 P01 编号相近，只能作为候选证据，必须暂缓
    for raw in ('P010', 'P10'):
        d = _decision(alias_state, 'analyte', raw)
        assert d['status'] == 'PENDING' and d['reason'] == 'SIMILAR_CODE'
        assert any(c['name'] == 'P01' for c in d['candidates'])
    held = {r['id'] for r in alias_state['held_rows']}
    assert {'A0006', 'A0007'} <= held


def test_pending_rows_are_not_quarantined_or_graded(alias_state):
    held_ids = {r['id'] for r in alias_state['held_rows']}
    quarantined = {q['id'] for q in alias_state['quarantine']}
    assert held_ids.isdisjoint(quarantined)
    full = run(load('aliases.csv'), {})
    graded = {c['id'] for c in full['calculations']}
    assert held_ids.isdisjoint(graded)
    assert full['reconcile']['balanced']


def test_manual_confirmation_unblocks_grading():
    saved = [
        {'field': 'product', 'raw_name': '红富士', 'canonical_name': '苹果',
         'reason': 'ALIAS_TABLE', 'status': 'CONFIRMED', 'evidence': ''},
    ]
    state = run(load('aliases.csv'), {}, saved_aliases=saved)
    d = _decision(state, 'product', '红富士')
    assert d['status'] == 'CONFIRMED' and d['canonical_name'] == '苹果'
    # 红富士行进入判级：P02 限量 0.02，结果 30ug/kg=0.03 超限
    calc = next(c for c in state['calculations'] if c['id'] == 'A0003')
    assert calc['code'] == 'FAIL' and calc['product_raw'] == '红富士'


def test_rejected_alias_is_quarantined_without_losing_raw():
    saved = [{'field': 'analyte', 'raw_name': 'P010', 'canonical_name': '',
              'reason': 'SIMILAR_CODE', 'status': 'REJECTED', 'evidence': ''}]
    state = run(load('aliases.csv'), {}, saved_aliases=saved)
    q = next(q for q in state['quarantine'] if q['id'] == 'A0006')
    assert q['code'] == 'ALIAS' and q['raw']['analyte'] == 'P010'
    assert all(c['id'] != 'A0006' for c in state['calculations'])


def test_same_source_rerun_keeps_confirmed_relation():
    saved = [{'field': 'product', 'raw_name': '红富士', 'canonical_name': '苹果',
              'reason': 'ALIAS_TABLE', 'status': 'CONFIRMED', 'evidence': ''}]
    a = run(load('aliases.csv'), {}, saved_aliases=saved)
    b = run(load('aliases.csv'), {}, saved_aliases=saved)
    assert a['run_id'] == b['run_id']  # 关系不变则同源重跑幂等
    assert _decision(a, 'product', '红富士') == _decision(b, 'product', '红富士')


def test_relation_change_only_affects_its_projects():
    base = run(load('aliases.csv'), {})
    saved = [{'field': 'analyte', 'raw_name': 'P010', 'canonical_name': '',
              'reason': 'SIMILAR_CODE', 'status': 'REJECTED', 'evidence': ''}]
    changed = run(load('aliases.csv'), {}, saved_aliases=saved)
    assert changed['run_id'] != base['run_id']
    # 未涉及该名称的项目结论保持不变
    before = {c['id']: c['code'] for c in base['calculations']}
    after = {c['id']: c['code'] for c in changed['calculations']}
    common = set(before) & set(after)
    assert all(before[i] == after[i] for i in common)
    assert 'A0006' not in after  # 仅受影响项目改变（进入隔离）


def test_frozen_history_relation_kept_when_name_disappears():
    system = build_decisions([], standards(), load_alias_table())
    saved = [{'field': 'product', 'raw_name': '旧称X', 'canonical_name': '苹果',
              'reason': 'ALIAS_TABLE', 'status': 'CONFIRMED', 'evidence': '历史'}]
    merged = merge_manual(system, saved)
    d = merged[('product', '旧称X')]
    assert d.status == 'CONFIRMED' and '历史裁决' in d.evidence


def test_resolve_name_gates_on_status():
    d = AliasDecision(field='analyte', raw_name='P010', status='PENDING')
    assert resolve_name('analyte', 'P010', {('analyte', 'P010'): d}) == ('', 'PENDING')
    d.status = 'CONFIRMED'
    d.canonical_name = 'P01'
    assert resolve_name('analyte', 'P010', {('analyte', 'P010'): d}) == ('P01', 'CONFIRMED')


def test_key_forms_and_similarity_helpers():
    assert canonical_form('Ｐ０１') == 'P01'
    assert key_form('p 01') == 'P01'
    assert similarity('P010', 'P01') >= 0.8
    assert similarity('P01', 'P01') == 1.0


def test_ambiguous_key_collision_does_not_auto_match():
    # 两个标准名规整后同键时，不得自动归并，避免套错限量
    from app.modules.m2_mapping.matching import _index
    names, exact, keyed = _index(
        [{'product': 'AB', 'analyte': 'X'}, {'product': 'A B', 'analyte': 'X'}], 'product')
    assert 'AB' not in keyed
