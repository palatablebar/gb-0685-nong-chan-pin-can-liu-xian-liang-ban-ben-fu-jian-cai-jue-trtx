import hashlib, json, time
from datetime import datetime, timezone
from app.config import RULE_VERSION


def identity(content, parameters, alias_snapshot=None):
    # 名称裁决关系参与运行指纹：关系变化产生新 run_id，同源重跑（关系不变）仍幂等。
    alias_raw = json.dumps(
        sorted(
            (a.get('field', ''), a.get('raw_name', ''), a.get('status', ''),
             a.get('canonical_name', ''))
            for a in (alias_snapshot or [])
        ), ensure_ascii=False, sort_keys=True)
    raw = (content
           + json.dumps(parameters, sort_keys=True, ensure_ascii=False).encode()
           + RULE_VERSION.encode()
           + alias_raw.encode())
    return hashlib.sha256(raw).hexdigest()[:20]


def manifest(content, parameters, elapsed):
    return {'sha256': hashlib.sha256(content).hexdigest(), 'rule_version': RULE_VERSION,
            'parameters': parameters, 'elapsed_ms': round(elapsed * 1000),
            'generated_at': datetime.now(timezone.utc).isoformat(), 'timezone': 'Asia/Shanghai'}
