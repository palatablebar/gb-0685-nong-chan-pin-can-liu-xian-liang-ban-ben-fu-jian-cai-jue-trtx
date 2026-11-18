"""名称裁决引擎：全角/半角规整、别名/简称/旧称的候选匹配与证据分级。

裁决状态：
  AUTO      确定性规整后唯一命中标准名，系统自动确认，可直接判级
  CONFIRMED 复核员人工确认的归并关系
  PENDING   相似但存在歧义（编号/品种相近等），暂缓，不得套用限量
  REJECTED  复核员拒绝归并，相关行按 ALIAS 隔离

只有 AUTO / CONFIRMED 两类关系可以作为限量匹配与判级依据；
PENDING 暂缓不判级，REJECTED 隔离。任何状态下报告原始名称都原样保留。
"""
import unicodedata
from dataclasses import dataclass, field

ALIAS_STATUSES = ('AUTO', 'CONFIRMED', 'PENDING', 'REJECTED')
# 确定性归并依据：字符层面规整，无歧义
AUTO_REASONS = ('EXACT', 'NFKC_FULLWIDTH', 'KEY_NORMALIZE')
# 必须人工裁决的依据
MANUAL_REASONS = ('ALIAS_TABLE', 'SIMILAR_CODE', 'SIMILAR_NAME')


def canonical_form(name):
    """NFKC 归一（全角字母数字→半角、兼容字符合并），保留中文与大小写。"""
    return unicodedata.normalize('NFKC', str(name)).strip()


def key_form(name):
    """匹配键：NFKC 后去全部空白并大写，用于代码类名称（P01／p 01）比较。"""
    return ''.join(canonical_form(name).split()).upper()


def similarity(a, b):
    """0~1 的相似度，仅用于排序候选与提示，绝不单独作为自动归并依据。"""
    ka, kb = key_form(a), key_form(b)
    if not ka or not kb:
        return 0.0
    if ka == kb:
        return 1.0
    if ka in kb or kb in ka:
        return 0.85
    sa, sb = set(ka), set(kb)
    return round(len(sa & sb) / len(sa | sb), 3)


@dataclass
class AliasDecision:
    field: str                    # product | analyte
    raw_name: str                 # 报告原始名称（保形，不做改写）
    canonical_name: str = ''      # 归并目标标准名；PENDING/REJECTED 为空
    reason: str = ''              # 归并依据码
    status: str = 'PENDING'
    candidates: list = field(default_factory=list)   # [{name,score}] 仅证据展示
    evidence: str = ''            # 人读的归并依据说明
    affected_lines: list = field(default_factory=list)
    affected_ids: list = field(default_factory=list)

    def key(self):
        return (self.field, self.raw_name)

    def to_dict(self):
        return {
            'field': self.field, 'raw_name': self.raw_name,
            'canonical_name': self.canonical_name, 'reason': self.reason,
            'status': self.status, 'candidates': self.candidates,
            'evidence': self.evidence, 'affected_lines': self.affected_lines,
            'affected_ids': self.affected_ids,
        }


def _index(standards, field):
    """标准名索引：NFKC 精确形式、key_form 形式（冲突键标记为歧义）。"""
    names = sorted({s[field] for s in standards})
    exact = {canonical_form(n): n for n in names}
    keyed, ambiguous = {}, set()
    for n in names:
        k = key_form(n)
        if k in keyed:
            ambiguous.add(k)
        keyed[k] = n
    for k in ambiguous:
        keyed.pop(k, None)
    return names, exact, keyed


def build_decisions(rows, standards, alias_table):
    """根据当前报告行与限量标准生成系统侧名称裁决证据。

    本函数不包含人工状态：同源重跑时系统证据稳定，已确认/拒绝关系由
    merge_manual 合并，保证重跑不会自动新增别名或改写已确认关系。
    """
    decisions = {}
    for field in ('product', 'analyte'):
        names, exact, keyed = _index(standards, field)
        raws = {}
        for r in rows:
            raws.setdefault(str(r.get(field, '')), []).append(r)
        table = alias_table.get(field, {})
        for raw, affected in raws.items():
            d = AliasDecision(field=field, raw_name=raw)
            d.affected_lines = sorted({r['_line'] for r in affected})
            d.affected_ids = sorted({r['id'] for r in affected})
            canon = canonical_form(raw)
            # 1) 报告名与标准名逐字一致
            if raw in names:
                d.status, d.reason, d.canonical_name = 'AUTO', 'EXACT', raw
                d.evidence = '报告名称与限量标准名称逐字一致'
            # 2) NFKC 规整（全角/半角、兼容字符）后唯一命中：确定性自动确认
            elif canon != raw and canon in exact:
                d.status, d.reason, d.canonical_name = 'AUTO', 'NFKC_FULLWIDTH', exact[canon]
                d.evidence = '全角/半角或兼容字符 NFKC 规整后与标准名唯一一致'
            # 3) 再去空白、统一大小写后唯一命中：仍为无歧义字符规整
            elif key_form(raw) in keyed:
                d.status, d.reason, d.canonical_name = 'AUTO', 'KEY_NORMALIZE', keyed[key_form(raw)]
                d.evidence = 'NFKC 规整并去除空白、统一大小写后与标准名唯一一致'
            # 4) 院内名称登记（简称/旧称）：给出登记目标，但必须人工确认
            elif raw in table and table[raw] in names:
                target = table[raw]
                d.reason = 'ALIAS_TABLE'
                d.evidence = '院内名称登记（简称/旧称）%s → %s，须人工确认后方可采信限量' % (raw, target)
                d.candidates = [{'name': target, 'score': 1.0}]
            # 5) 仅有相似名称：编号/品种相近，一律暂缓
            if d.status == 'PENDING':
                if not d.candidates:
                    scored = sorted(((similarity(raw, n), n) for n in names),
                                    key=lambda x: (-x[0], x[1]))
                    d.candidates = [{'name': n, 'score': s} for s, n in scored if s >= 0.4][:5]
                if not d.reason:
                    d.reason = 'SIMILAR_CODE' if field == 'analyte' else 'SIMILAR_NAME'
                    d.evidence = '名称与标准库仅相似，存在品种/项目编号混淆风险，暂缓待人工裁决'
            decisions[d.key()] = d
    return decisions


def merge_manual(system_decisions, saved):
    """合并持久化的人工裁决。

    同源重跑：已 CONFIRMED/REJECTED 的关系保持不变；新名称只进入 PENDING，
    不会自动改写既有关系。当前批次不再出现的历史关系冻结保留，裁决历史不丢失。
    """
    out = dict(system_decisions)
    for entry in saved:
        key = (entry['field'], entry['raw_name'])
        if key in out:
            cur = out[key]
            if entry['status'] in ('CONFIRMED', 'REJECTED'):
                cur.status = entry['status']
                cur.canonical_name = entry.get('canonical_name', '') if entry['status'] == 'CONFIRMED' else ''
                cur.reason = entry.get('reason', cur.reason)
                cur.evidence = entry.get('evidence', cur.evidence)
        else:
            out[key] = AliasDecision(
                field=entry['field'], raw_name=entry['raw_name'],
                canonical_name=entry.get('canonical_name', ''),
                reason=entry.get('reason', ''), status=entry['status'],
                evidence=entry.get('evidence', '') + '（历史裁决，当前批次未出现）',
            )
    return out


def resolve_name(field, raw_name, decisions):
    """返回 (标准名, 裁决状态)；只有 AUTO/CONFIRMED 能给出标准名。"""
    d = decisions.get((field, str(raw_name)))
    if d and d.status in ('AUTO', 'CONFIRMED') and d.canonical_name:
        return d.canonical_name, d.status
    return '', d.status if d else 'PENDING'
