"""院内名称登记表加载：简称/旧称仅作为人工裁决的证据，不自动采信。"""
import csv
from pathlib import Path


def load_alias_table():
    path = Path(__file__).resolve().parents[3] / 'sample_data' / 'alias_registry.csv'
    table = {'product': {}, 'analyte': {}}
    with path.open(encoding='utf-8-sig', newline='') as f:
        for row in csv.DictReader(f):
            field = (row.get('field') or '').strip()
            raw, target = (row.get('raw_name') or '').strip(), (row.get('canonical_name') or '').strip()
            if field in table and raw and target:
                table[field][raw] = target
    return table
