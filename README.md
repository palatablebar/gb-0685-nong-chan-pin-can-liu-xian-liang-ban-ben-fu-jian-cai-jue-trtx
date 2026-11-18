# 农产品残留限量版本与复检裁决

面向农产品检测站复核员，处理采信、判定、核算、复核与归档。

## 启动

```bash
docker compose up --build -d
```

访问 http://localhost:18254 。初次启动自动运行脏样例，可切换 clean.csv、legacy.csv 与 aliases.csv。顶部“运行批次”会重新计算，同源输入复用批次。

## 名称裁决

检测报告中的产品与残留项目可能使用全角字符、简称或院内旧称。在“项目映射”页（`/m2_mapping`）裁决名称关系：

- 全角/半角等 NFKC 规整后与标准名唯一一致的，系统自动确认（AUTO），可直接判级；
- 院内简称/旧称登记在 `sample_data/alias_registry.csv`，但必须人工确认（CONFIRMED）后才采信限量；
- 编号或品种相近的名称只给候选证据，默认暂缓（PENDING），不套限量；拒绝归并（REJECTED）按 ALIAS 隔离。

裁决清单展示报告原名称、归并依据、采用限量与复检结论。关系独立持久化：同源重跑不新增别名、不改写已确认关系；关系变化只重算受影响项目；补齐依据失败时旧版结果保留，原始名称与隔离数据不丢失。

## 业务模块

- 报告采信：`/m1_ingest`、`/api/m1_ingest`
- 项目映射：`/m2_mapping`、`/api/m2_mapping`
- 限量选版：`/m3_versions`、`/api/m3_versions`
- 检出量换算：`/m4_segments`、`/api/m4_segments`
- 复检裁决：`/m5_calculate`、`/api/m5_calculate`
- 批次判级：`/m6_reconcile`、`/api/m6_reconcile`
- 报告归档：`/m7_archive`、`/api/m7_archive`

## 核心规则

按采样日期选择有效限量，低于检出限保留区间；复检不得越过样本关联与方法适用范围。完整数值、边界和异常定义见 `docs/DATA-DICTIONARY.md`。

## 验证

```bash
docker compose exec -T app pytest -q
docker compose config --quiet
```

原始样例在 `sample_data/`。测试在 `tests/`。封存文件是单份CSV，含运行清单、计算证据、隔离原因与对账。复核需提交当前版本，陈旧复核返回409。

## 数据与限制

SQLite保存在records命名卷，普通重启与构建不会清除。确认可丢弃本项目数据后，运行 `docker compose down -v` 再启动可重置。单文件上限2MB；不接入外部业务系统；历史规则由本项目样例定义，不代表实际行业标准。
