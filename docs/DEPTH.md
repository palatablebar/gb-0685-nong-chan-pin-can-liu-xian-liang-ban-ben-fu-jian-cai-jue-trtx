# 深度登记 农产品残留限量版本与复检裁决

规模：中型。核心规则：按采样日期选择有效限量，低于检出限保留区间；复检不得越过样本关联与方法适用范围。

## 功能模块

| 模块 | 使用者动作 | 入口 | 核心文件 | 测试 |
|---|---|---|---|---|
| M1 报告采信 | 查看并复算报告采信 | `/api/m1_ingest` | `app/modules/m1_ingest/reader.py` | `tests/test_ingest.py` |
| M2 项目映射 | 裁决名称关系并复算项目映射 | `/api/m2_mapping`、`/api/m2_mapping/aliases` | `app/modules/m2_mapping/rules.py`、`app/modules/m2_mapping/matching.py` | `tests/test_mapping.py`、`tests/test_name_adjudication.py`、`tests/test_alias_api.py` |
| M3 限量选版 | 查看并复算限量选版 | `/api/m3_versions` | `app/modules/m3_versions/rules.py` | `tests/test_versions.py` |
| M4 检出量换算 | 查看并复算检出量换算 | `/api/m4_segments` | `app/modules/m4_segments/rules.py` | `tests/test_segments.py` |
| M5 复检裁决 | 查看并复算复检裁决 | `/api/m5_calculate` | `app/modules/m5_calculate/rules.py` | `tests/test_calculate.py` |
| M6 批次判级 | 查看并复算批次判级 | `/api/m6_reconcile` | `app/modules/m6_reconcile/compare.py` | `tests/test_reconcile.py` |
| M7 报告归档 | 查看并复算报告归档 | `/api/m7_archive` | `app/modules/m7_archive/export_out.py` | `tests/test_archive.py` |

## 陷阱登记

| TRAP | 现象 | 朴素实现 | 处理 | 处理位置 | 测试 |
|---|---|---|---|---|---|
| TRAP-01 | GB18030中文 | 固定UTF-8失败 | 按编码链回退 | `app/modules/m1_ingest/decode.py` | `tests/test_ingest.py::test_legacy_encoding` |
| TRAP-02 | 表头BOM | 首列键失配 | 去除BOM | `app/modules/m1_ingest/decode.py` | `tests/test_ingest.py::test_bom` |
| TRAP-03 | 引号内换行 | 分行误计 | csv逻辑记录 | `app/modules/m1_ingest/reader.py` | `tests/test_ingest.py::test_preserves_multiline_note` |
| TRAP-05 | 列数错位 | 静默补列 | WIDTH隔离 | `app/modules/m1_ingest/reader.py` | `tests/test_ingest.py::test_width_isolation` |
| TRAP-06 | 全角千分位 | float失败 | NFKC与Decimal | `app/modules/m2_mapping/coerce.py` | `tests/test_mapping.py::test_thousands` |
| TRAP-07 | 空值哨兵 | 空值当零 | MISSING隔离 | `app/modules/m2_mapping/coerce.py` | `tests/test_mapping.py::test_missing_numeric` |
| TRAP-08 | 前导零ID | 编码失真 | 字符串保形 | `app/modules/m2_mapping/rules.py` | `tests/test_mapping.py::test_identifier_zeroes` |
| TRAP-10 | 浮点误差 | 累计失准 | Decimal求和 | `app/modules/m2_mapping/coerce.py` | `tests/test_mapping.py::test_decimal_precision` |
| TRAP-14 | 同版冲突 | 最后覆盖 | 整组隔离 | `app/modules/m2_mapping/rules.py` | `tests/test_mapping.py::test_real_conflict_quarantine` |
| TRAP-18 | 三种空态 | 除零或伪成功 | 三个错误码 | `app/modules/m1_ingest/reader.py` | `tests/test_ingest.py::test_empty_three_states` |
| TRAP-26 | 旧版本复核 | 覆盖新结论 | 事务条件更新 | `app/store.py` | `tests/test_archive.py::test_stale_review` |
| TRAP-15 | ug/kg与mg/kg | 差1000倍 | 浓度统一mg/kg | `app/modules/m4_segments/rules.py` | `tests/test_segments.py::test_unit_conversion` |
| TRAP-25 | 标准时间边界 | 双版或错版 | 采样日半开区间选版 | `app/modules/m3_versions/standards.py` | `tests/test_versions.py::test_halfopen_effective` |
| TRAP-20 | 复检引用环 | 遍历无法结束 | 引用路径检测 | `app/modules/m5_calculate/rules.py` | `tests/test_calculate.py::test_cycle_rejected` |
| TRAP-30 | 全角项目名 | 与限量标准逐字匹配失败 | NFKC 唯一规整自动确认，原名保形 | `app/modules/m2_mapping/matching.py` | `tests/test_name_adjudication.py::test_fullwidth_analyte_auto_normalized` |
| TRAP-31 | 简称/旧称套错限量 | 相似即合并 | 登记仅作证据，必须人工 CONFIRMED | `app/modules/m2_mapping/matching.py` | `tests/test_name_adjudication.py::test_registry_alias_still_requires_manual` |
| TRAP-32 | 编号相近（P01/P010） | 相似度高自动归并 | 一律 PENDING 暂缓，候选仅展示 | `app/modules/m2_mapping/matching.py` | `tests/test_name_adjudication.py::test_similar_code_must_stay_pending` |
| TRAP-33 | 同源重跑改写关系 | 重跑重建别名表 | 关系独立持久化，重跑只合并不改写 | `app/alias_db.py`、`app/modules/m2_mapping/matching.py` | `tests/test_alias_api.py::test_rerun_with_same_relations_is_idempotent` |
| TRAP-34 | 关系变更覆盖旧结果 | 同 run_id 插入覆盖 | 关系快照纳入 run_id，失败保留旧版 | `app/manifest.py`、`app/store.py` | `tests/test_alias_api.py::test_confirm_unknown_target_rejected_and_old_result_kept` |

## 对账规则

输入行数=采纳+隔离+暂缓+空行+重复表头+完全重复；业务总数与计算证据独立求和。隔离行保留来源行、ID、原因码与原值；暂缓行与名称裁决清单随归档证据导出，原始报告名称不丢失。

## 已知不覆盖

不做多租户权限和外部服务联调。行业规则以项目数据字典为准。文件上限2MB，逐行解析后在上限内完成分组计算。
