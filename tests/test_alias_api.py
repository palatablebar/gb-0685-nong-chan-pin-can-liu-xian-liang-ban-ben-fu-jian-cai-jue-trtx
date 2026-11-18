"""名称裁决 HTTP 接口：确认、拒绝、暂缓（reset）、非法目标防护与同源重跑。"""


def _submit_alias_batch(client):
    return client.post('/api/runs', json={'sample': 'aliases.csv'}).get_json()


def test_confirm_alias_recalculates_affected(client):
    _submit_alias_batch(client)
    r = client.post('/api/m2_mapping/aliases', json={
        'field': 'product', 'raw_name': '红富士', 'status': 'CONFIRMED',
        'canonical_name': '苹果', 'reason': 'ALIAS_TABLE'})
    assert r.status_code == 200
    body = r.get_json()
    assert body['mapping_summary']['confirmed'] == 1
    assert body['held_rows'] == 4


def test_confirm_unknown_target_rejected_and_old_result_kept(client):
    before = _submit_alias_batch(client)
    r = client.post('/api/m2_mapping/aliases', json={
        'field': 'product', 'raw_name': '红富士', 'status': 'CONFIRMED',
        'canonical_name': '不存在的品种', 'reason': 'ALIAS_TABLE'})
    assert r.status_code == 422 and r.get_json()['code'] == 'ALIAS_TARGET'
    # 补齐依据失败：旧版运行结果仍在
    runs = client.get('/api/runs').get_json()
    assert any(x['id'] == before['run_id'] for x in runs)
    assert client.get('/api/m2_mapping/aliases').get_json() == []


def test_reject_alias_quarantines_and_persists(client):
    _submit_alias_batch(client)
    r = client.post('/api/m2_mapping/aliases', json={
        'field': 'analyte', 'raw_name': 'P010', 'status': 'REJECTED',
        'reason': 'SIMILAR_CODE'})
    assert r.status_code == 200 and r.get_json()['mapping_summary']['rejected'] == 1
    state = client.post('/api/runs', json={'sample': 'aliases.csv'}).get_json()
    assert any(q['id'] == 'A0006' and q['code'] == 'ALIAS' for q in state['quarantine'])
    # 原始名称在隔离证据中保留
    q = next(q for q in state['quarantine'] if q['id'] == 'A0006')
    assert q['raw']['analyte'] == 'P010'


def test_reset_returns_name_to_pending(client):
    _submit_alias_batch(client)
    client.post('/api/m2_mapping/aliases', json={
        'field': 'product', 'raw_name': '红富士', 'status': 'CONFIRMED',
        'canonical_name': '苹果', 'reason': 'ALIAS_TABLE'})
    r = client.post('/api/m2_mapping/aliases/reset',
                    json={'field': 'product', 'raw_name': '红富士'})
    assert r.status_code == 200 and r.get_json()['status'] == 'RESET'
    state = client.post('/api/runs', json={'sample': 'aliases.csv'}).get_json()
    assert any(row['id'] == 'A0003' for row in state['held_rows'])


def test_rerun_with_same_relations_is_idempotent(client):
    _submit_alias_batch(client)
    client.post('/api/m2_mapping/aliases', json={
        'field': 'analyte', 'raw_name': 'P010', 'status': 'REJECTED',
        'reason': 'SIMILAR_CODE'})
    a = client.post('/api/runs', json={'sample': 'aliases.csv'}).get_json()
    b = client.post('/api/runs', json={'sample': 'aliases.csv'}).get_json()
    assert a['run_id'] == b['run_id']
    # 重跑不新增别名
    assert len(client.get('/api/m2_mapping/aliases').get_json()) == 1


def test_alias_decisions_visible_on_mapping_page(client):
    _submit_alias_batch(client)
    page = client.get('/m2_mapping')
    assert page.status_code == 200
    html = page.data.decode()
    for token in ('名称裁决清单', 'Ｐ０１', '红富士', 'P010', '暂缓'):
        assert token in html


def test_invalid_alias_field_rejected(client):
    _submit_alias_batch(client)
    r = client.post('/api/m2_mapping/aliases', json={
        'field': 'batch', 'raw_name': 'X', 'status': 'CONFIRMED',
        'canonical_name': '苹果'})
    assert r.status_code == 422 and r.get_json()['code'] == 'ALIAS_FIELD'


def test_archive_contains_held_and_adjudication_rows(client):
    _submit_alias_batch(client)
    state = client.post('/api/runs', json={'sample': 'aliases.csv'}).get_json()
    export = client.get('/api/archive/%s/export.csv' % state['run_id']).data.decode('utf-8-sig')
    assert '暂缓' in export and '名称裁决' in export
