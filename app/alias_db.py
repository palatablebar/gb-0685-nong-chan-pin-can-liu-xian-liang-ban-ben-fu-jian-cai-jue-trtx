"""名称裁决关系的持久化。

别名表按 (field, raw_name) 保存人工裁决，独立于 runs：
- 同源输入重跑只复用已有关系，不新增别名、不改写已确认关系；
- 关系变更只写入被裁决的那一条，其他项目不受影响；
- 关系带证据快照，补齐依据失败时旧版本保留，不覆盖。
"""
import json
from app.store import connection
from app.errors import DomainError

VALID_FIELDS = ('product', 'analyte')
VALID_STATUS = ('CONFIRMED', 'REJECTED')


def list_aliases():
    with connection() as db:
        rows = db.execute('SELECT field,raw_name,canonical_name,reason,status,evidence,updated_run,updated_at FROM aliases ORDER BY field,raw_name').fetchall()
    return [dict(r) for r in rows]


def get_alias(field, raw_name):
    with connection() as db:
        r = db.execute('SELECT * FROM aliases WHERE field=? AND raw_name=?', (field, raw_name)).fetchone()
    return dict(r) if r else None


def reset_alias(field, raw_name):
    """撤销人工裁决，使该名称回到系统证据态（PENDING/AUTO）。

    不触碰其他名称的关系；历史运行结果仍在 runs 表中保留。
    """
    if field not in VALID_FIELDS:
        raise DomainError('ALIAS_FIELD', '名称字段无效')
    with connection() as db:
        db.execute('DELETE FROM aliases WHERE field=? AND raw_name=?', (field, raw_name))
    return {'field': field, 'raw_name': raw_name, 'status': 'RESET'}


def save_alias(field, raw_name, canonical_name, reason, status, evidence, run_id):
    if field not in VALID_FIELDS:
        raise DomainError('ALIAS_FIELD', '名称字段无效')
    if status not in VALID_STATUS:
        raise DomainError('ALIAS_STATUS', '裁决状态无效')
    if not raw_name:
        raise DomainError('ALIAS_NAME', '原始名称不能为空')
    if status == 'CONFIRMED' and not canonical_name:
        raise DomainError('ALIAS_TARGET', '确认归并必须指定标准名称')
    payload = {
        'field': field, 'raw_name': raw_name,
        'canonical_name': canonical_name if status == 'CONFIRMED' else '',
        'reason': reason or 'MANUAL', 'status': status,
        'evidence': evidence or '', 'updated_run': run_id or '',
    }
    with connection() as db:
        db.execute(
            '''INSERT INTO aliases(field,raw_name,canonical_name,reason,status,evidence,updated_run,updated_at)
               VALUES(:field,:raw_name,:canonical_name,:reason,:status,:evidence,:updated_run,
                      COALESCE((SELECT updated_at FROM aliases WHERE field=:field AND raw_name=:raw_name),0)+1)
               ON CONFLICT(field,raw_name) DO UPDATE SET
                 canonical_name=excluded.canonical_name,reason=excluded.reason,status=excluded.status,
                 evidence=excluded.evidence,updated_run=excluded.updated_run,
                 updated_at=aliases.updated_at+1''', payload)
    return get_alias(field, raw_name)


def saved_decisions():
    """供工作流合并的精简结构。"""
    return list_aliases()


def ensure_table(db=None):
    own = db is None
    db = db or connection()
    db.execute(
        '''CREATE TABLE IF NOT EXISTS aliases (
             field TEXT NOT NULL, raw_name TEXT NOT NULL,
             canonical_name TEXT NOT NULL DEFAULT '', reason TEXT NOT NULL DEFAULT '',
             status TEXT NOT NULL DEFAULT 'PENDING', evidence TEXT NOT NULL DEFAULT '',
             updated_run TEXT NOT NULL DEFAULT '', updated_at INTEGER NOT NULL DEFAULT 0,
             PRIMARY KEY(field,raw_name))''')
    if own:
        db.commit()
