#!/usr/bin/env python3
"""Step 5 only: independently aggregate DPVO CSV and compare three frozen targets.

No research script is imported or executed. Source paths are fixed and read-only.
Only the six named step-5 artifacts can be written; default is exclusive creation.
"""

import argparse
from collections import Counter, defaultdict
import csv
from decimal import Decimal
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import shlex
import statistics
import sys
from unittest.mock import patch

import pandas as pd

# Reviewed local, side-effect-free helpers. Its main() is not called.
from audit_metric_protocol import parse_identifier, numeric_state, diagnose

WORKSPACE = Path('/home/yuan/SLAM/codex_review/benchmark_analysis')
BENCHMARK = Path('/home/yuan/SLAM/AirSim-Visual-SLAM-Research-Toolkit/Benchmark')
INPUT_ROOT = BENCHMARK / 'experiment_data'
MATRIX = WORKSPACE / 'reports/04_input_protocol_matrix.csv'
SOURCE = 'DPVO/mono_metrics.csv'
TARGETS = {
    'scene': 'DPVO/summary_metrics_by_scene_mono.csv',
    'altitude': 'DPVO/summary_metrics_by_altitude.csv',
    'speed': 'DPVO/summary_metrics_by_speed.csv',
}
CODE = (
    'experiment_data/DPVO/analyze_by_dataset.py',
    'statistics/summary_metrics_by_altitude.py',
    'statistics/summary_metrics_by_speed.py',
)
OUTPUTS = {
    'records': 'derived_data/05_dpvo_pilot/run_records.csv',
    'scene': 'tables/05_dpvo_pilot/scene_recomputed.csv',
    'altitude': 'tables/05_dpvo_pilot/altitude_recomputed.csv',
    'speed': 'tables/05_dpvo_pilot/speed_recomputed.csv',
    'comparison': 'reports/05_dpvo_comparison.csv',
    'report': 'reports/05_dpvo_pilot.md',
}
METRICS = ('FPS', 'runtime', 'PeakReservedGB', 'rmse')
FIELDS = ['SR'] + [f'{m}_{stat}' for m in METRICS for stat in ('mean', 'std')]
SCENES = ('building', 'houses', 'pool', 'road', 'roundabout', 'overall')
SPEED = {'low': 2, 'medium': 4, 'high': 8}
ALTITUDE = {'low': 10, 'medium': 20, 'high': 30}
ATOL = RTOL = 1e-12
MARKER = '<!-- generated-by: scripts/run_dpvo_pilot.py; step-5-only -->'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def json_text(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True)


def no_symlinks(path):
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError(f'Symlink path rejected: {path}')


def read_bytes(path):
    no_symlinks(path)
    with path.open('rb') as f:
        raw = f.read(10 * 1024 * 1024 + 1)
    if len(raw) > 10 * 1024 * 1024:
        raise ValueError(f'File exceeds reviewed size boundary: {path}')
    return raw


def decode_csv(raw):
    """Keep cell strings; reject ragged/blank records, never silently drop them."""
    rows = list(csv.reader(io.StringIO(raw.decode('utf-8-sig'), newline=''), strict=True))
    if not rows or not rows[0]:
        raise ValueError('Missing CSV header')
    header, cells = rows[0], rows[1:]
    for i, row in enumerate(cells, 1):
        if len(row) != len(header) or not any(row):
            raise ValueError(f'Ragged or entirely empty record {i}')
    return header, cells


def records_from_cells(header, cells):
    if len(header) != len(set(header)):
        raise ValueError('Duplicate run-record header')
    return [dict(zip(header, row)) for row in cells]


def parse_record(row, index, digest):
    parsed = parse_identifier(row['dataset'])
    labelled = parsed.get('speed_mps') is not None and parsed.get('altitude_m') is not None
    # Invert already-parsed values, without maintaining another suffix parser.
    speed_level = next((k for k, v in SPEED.items() if v == parsed.get('speed_mps')), '')
    altitude_level = next((k for k, v in ALTITUDE.items() if v == parsed.get('altitude_m')), '')
    extra = {
        'source_relative_path': SOURCE, 'source_sha256': digest,
        'source_record_index': index, 'method': 'DPVO', 'configuration': 'mono',
        'sequence_raw': parsed.get('sequence_raw'), 'run_id_raw': parsed.get('run_id_raw'),
        'identifier_parse_status': parsed['parse_status'], 'scene': parsed.get('scene'),
        'speed_level': speed_level, 'altitude_level': altitude_level,
        'speed_mps': parsed.get('speed_mps'), 'altitude_m': parsed.get('altitude_m'),
        'condition_label_status': 'two_tokens' if labelled else 'missing_condition_labels',
        **{f'{m}_parse_status': numeric_state(row[m]) for m in METRICS},
    }
    if set(row) & set(extra):
        raise ValueError('Derived column conflicts with raw field')
    return {**row, **extra}


def scene_float(raw):
    """Legacy scene parser: convertible, not necessarily finite."""
    if raw is None or str(raw).strip() == '' or str(raw).strip().upper() == 'NA':
        return None
    try:
        return float(str(raw).strip())
    except (ValueError, TypeError, OverflowError):
        return None


def condition_values(rows, metric):
    # Match shared pandas numeric conversion; float() would accept extra forms,
    # e.g. underscores, which pd.to_numeric rejects. Raw strings remain separate.
    s = pd.to_numeric(pd.Series([r.get(metric) for r in rows], dtype=object), errors='coerce')
    return s[s.map(lambda v: pd.notna(v) and math.isfinite(float(v)))].astype(float)


def aggregate_group(rows, branch, label):
    """Return unrounded legacy statistics and independently recorded cohorts."""
    if branch == 'scene':
        eligible = [r for r in rows if scene_float(r.get('rmse')) is not None]
        numerator = len(eligible)
    else:
        eligible = rows
        numerator = len(condition_values(rows, 'rmse'))
    n = len(rows)
    result = {branch: label, 'SR': numerator / n if n else 0.0}
    counts = {'n_records': n, 'sr_numerator': numerator, 'sr_denominator': n}
    for m in METRICS:
        if branch == 'scene':
            values = [v for r in eligible if (v := scene_float(r.get(m))) is not None]
            # Deliberately propagate legacy pstdev errors for NaN/Inf at n>1.
            mean = sum(values) / len(values) if values else 'NA'
            std = statistics.pstdev(values) if len(values) > 1 else 0.0 if values else 'NA'
        else:
            values = condition_values(rows, m)
            mean = float(values.mean()) if len(values) else float('nan')
            std = float(values.std(ddof=1)) if len(values) > 1 else 0.0 if len(values) else float('nan')
        result[f'{m}_mean'], result[f'{m}_std'] = mean, std
        counts[f'n_used_{m}'] = len(values)
    return result, counts


def aggregate(records, branch):
    """No target values enter grouping, aggregation or label construction."""
    groups = []
    if branch == 'scene':
        groups = [(k, [r for r in records if k == 'overall' or r.get('scene') == k]) for k in SCENES]
    else:
        field, values, unit = ('altitude_m', (10, 20, 30), 'm') if branch == 'altitude' else ('speed_mps', (2, 4, 8), 'm/s')
        for value in values:
            members = [r for r in records if r.get(field) == value and r['condition_label_status'] == 'two_tokens']
            if members:  # Legacy shared branch does not emit empty condition groups.
                groups.append((f'DPVO_{value}{unit}_mono', members))
    output, counts = [], {}
    for label, members in groups:
        row, group_counts = aggregate_group(members, branch, label)
        group_counts['member_source_record_indices'] = [r['source_record_index'] for r in members]
        output.append(row)
        counts[label] = group_counts
    return output, counts


def serialize(value, branch):
    """Legacy CSV serialization, used only after calculation."""
    if isinstance(value, str):
        return value
    if pd.isna(value):
        return '' if branch != 'scene' else str(value)
    return str(value) if branch == 'scene' else '%.6f' % value


def value_state(raw):
    # Missing spellings are intentionally not collapsed to one bucket.
    if raw == '':
        return 'empty', None
    if raw.strip() == '':
        return 'whitespace', None
    if raw.strip().upper() in {'NA', 'N/A', 'NONE', 'NULL'}:
        return 'marker:' + raw.strip().upper(), None
    try:
        v = float(raw)
    except (ValueError, TypeError):
        return 'unparseable:' + raw, None
    if math.isnan(v):
        return 'nan', None
    if math.isinf(v):
        return 'positive_inf' if v > 0 else 'negative_inf', None
    return 'finite', v


def compare_value(old_raw, new_value, branch):
    new_full = str(new_value)
    legacy_text = serialize(new_value, branch)
    old_state, old_number = value_state(old_raw)
    # Compare missingness in the branch's actual on-disk representation.
    new_state, _ = value_state(legacy_text)
    _, new_number = value_state(new_full)
    base = {'old_value_raw': old_raw, 'recomputed_value_unrounded': new_full,
            'recomputed_legacy_text': legacy_text, 'old_state': old_state,
            'recomputed_state': new_state, 'absolute_difference': ''}
    if old_state != 'finite' or new_state != 'finite':
        same = old_state == new_state and not old_state.startswith('unparseable')
        return {**base, 'comparison_rule': 'exact missing/nonfinite state after legacy serialization',
                'status': 'missingness_match' if same else 'missingness_mismatch'}
    diff = abs(old_number - new_number)
    if diff <= ATOL + RTOL * abs(old_number):
        status, rule = 'numeric_match', 'abs(diff) <= 1e-12 + 1e-12*abs(old)'
    elif branch != 'scene' and Decimal(old_raw.strip()) == Decimal(legacy_text):
        status, rule = 'rounding_match', 'numeric equality after %.6f legacy serialization'
    else:
        status, rule = 'value_mismatch', 'strict tolerance failed; scene has no decimal-rounding allowance' if branch == 'scene' else 'strict tolerance and %.6f serialization both failed'
    return {**base, 'absolute_difference': repr(diff), 'comparison_rule': rule, 'status': status}


def compare_tables(branch, old_header, old_cells, new_rows, counts):
    """Outer comparison of group and schema unions; never first-row/inner join."""
    new_header = [branch, *FIELDS]
    output = []

    def emit(label, field, detail, **values):
        c = counts.get(label, {})
        metric = field.rsplit('_', 1)[0] if field != 'SR' else 'rmse'
        output.append({
            'branch': branch, 'legacy_branch': 'scene_rmse_gate_ddof0' if branch == 'scene' else 'shared_condition_independent_finite_ddof1',
            'target_relative_path': TARGETS[branch], 'group_key': label,
            'old_group_label': label if label in old_groups else '',
            'recomputed_group_label': label if label in new_groups else '',
            'field': field, 'n_records': c.get('n_records', ''),
            'n_used': c.get('sr_numerator', '') if field == 'SR' else c.get(f'n_used_{metric}', ''),
            'sr_numerator': c.get('sr_numerator', ''), 'sr_denominator': c.get('sr_denominator', ''),
            **{f'n_used_{m}': c.get(f'n_used_{m}', '') for m in METRICS},
            'member_source_record_indices': json_text(c.get('member_source_record_indices', [])),
            'old_value_raw': '', 'recomputed_value_unrounded': '', 'recomputed_legacy_text': '',
            'old_state': '', 'recomputed_state': '', 'absolute_difference': '',
            'comparison_rule': '', 'status': '', 'detail': detail, **values,
        })

    old_groups, new_groups = defaultdict(list), defaultdict(list)
    for row in new_rows:
        new_groups[row[branch]].append(row)
    if old_header.count(branch) == 1:
        key_index = old_header.index(branch)
        for row in old_cells:
            old_groups[row[key_index]].append(row)
    else:
        emit('', branch, 'missing or duplicate target group column; cannot align target rows',
             status='schema_mismatch', old_value_raw=json_text(old_cells))
    fields = list(dict.fromkeys([*new_header, *old_header]))
    bad_fields = {f for f in fields if old_header.count(f) != 1 or new_header.count(f) != 1}
    for f in sorted(bad_fields):
        emit('', f, f'column occurrence counts: old={old_header.count(f)}, recomputed={new_header.count(f)}', status='schema_mismatch')
    for label in sorted(set(old_groups) | set(new_groups)):
        old, new = old_groups[label], new_groups[label]
        if len(old) != 1 or len(new) != 1:
            emit(label, '__group__', f'group occurrence counts: old={len(old)}, recomputed={len(new)}; no arbitrary alignment',
                 status='group_mismatch', old_value_raw=json_text(old), recomputed_value_unrounded=json_text(new))
            continue
        for f in fields:
            if f == branch:
                continue
            if f in bad_fields:
                emit(label, f, 'field is absent or repeated; no inferred value', status='schema_mismatch',
                     old_value_raw=json_text([old[0][i] for i, name in enumerate(old_header) if name == f]),
                     recomputed_value_unrounded=str(new[0].get(f, '')))
            else:
                emit(label, f, '', **compare_value(old[0][old_header.index(f)], new[0][f], branch))
    return output


def check_output(path, overwrite):
    if not path.is_absolute() or path not in {WORKSPACE / p for p in OUTPUTS.values()}:
        raise ValueError(f'Not an allowed step-5 output: {path}')
    no_symlinks(path)
    if not path.resolve().is_relative_to(WORKSPACE.resolve()):
        raise ValueError('Output escapes workspace')
    if path.exists():
        if not overwrite:
            raise FileExistsError(f'Refusing overwrite: {path}')
        if not path.is_file() or path.stat().st_nlink != 1:
            raise ValueError(f'Output is not an ordinary unlinked file: {path}')


def write_output(path, content, overwrite):
    check_output(path, overwrite)
    path.parent.mkdir(parents=True, exist_ok=True)
    check_output(path, overwrite)
    flags = os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW | (os.O_TRUNC if overwrite else os.O_EXCL)
    with os.fdopen(os.open(path, flags, 0o666), 'w', encoding='utf-8', newline='') as f:
        f.write(content)


def csv_text(rows, fields):
    buffer = io.StringIO(newline='')
    writer = csv.DictWriter(buffer, fieldnames=fields, lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def self_test():
    """All synthetic data stays in memory; no source reads or output writes."""
    passed = []

    def sample(run, rmse, fps='10', runtime='20', memory='2', std='999', dataset=None):
        return parse_record({'dataset': dataset or f'cross_building_low_high_{run}',
                             'rmse': rmse, 'FPS': fps, 'runtime': runtime,
                             'PeakReservedGB': memory, 'std': std}, run, 'virtual')

    p = sample(2, '1', dataset='roundabout_square25fps_2')
    assert p['sequence_raw'] == 'roundabout_square25fps' and p['run_id_raw'] == '2'
    assert p['speed_mps'] is None and p['altitude_m'] is None and p['scene'] == 'roundabout'
    p = sample(1, '1')
    assert (p['sequence_raw'], p['speed_mps'], p['altitude_m']) == ('cross_building_low_high', 2, 30)
    assert parse_identifier('cross_building_low_high')['parse_status'] == 'unresolved'
    passed.append('含下划线名称、末尾编号、无条件标签与缺少编号：通过')

    pair = [sample(1, '1'), sample(2, '3')]
    scene, _ = aggregate_group(pair, 'scene', 'building')
    cond, _ = aggregate_group(pair, 'altitude', 'DPVO_30m_mono')
    assert scene['rmse_mean'] == cond['rmse_mean'] == 2
    assert scene['rmse_std'] == 1 and math.isclose(cond['rmse_std'], math.sqrt(2))
    assert scene['rmse_mean'] != math.sqrt(5)
    passed.append('逐次算术均值、ddof=0/1 与非 RMS-of-RMSE：通过')

    pair = [sample(1, '1', fps='10'), sample(2, 'NA', fps='30')]
    s, ns = aggregate_group(pair, 'scene', 'building')
    c, nc = aggregate_group(pair, 'speed', 'DPVO_2m/s_mono')
    assert s['FPS_mean'] == 10 and c['FPS_mean'] == 20 and s['SR'] == c['SR'] == 0.5
    assert ns['n_used_FPS'] == 1 and nc['n_used_FPS'] == 2
    assert ns['sr_denominator'] == nc['sr_denominator'] == 2
    passed.append('RMSE=NA 但 FPS 有效：scene 门控/条件独立集合及 SR 分子分母：通过')

    pair = [sample(1, '1', fps='NA'), sample(2, '3', runtime='NA')]
    for branch in TARGETS:
        _, n = aggregate_group(pair, branch, 'test')
        assert (n['n_used_rmse'], n['n_used_FPS'], n['n_used_runtime'], n['n_used_PeakReservedGB']) == (2, 1, 1, 2)
    passed.append('RMSE 有效但不同效率列缺失，各指标 n_used 独立：通过')

    for branch in TARGETS:
        one, n = aggregate_group([sample(1, '1', fps='NA')], branch, 'test')
        assert one['rmse_std'] == 0 and n['n_used_FPS'] == 0
        assert serialize(one['FPS_std'], branch) == ('NA' if branch == 'scene' else '')
    empty, _ = aggregate([], 'scene')
    assert len(empty) == 6 and all(r['SR'] == 0 and r['FPS_mean'] == 'NA' for r in empty)
    assert aggregate([], 'altitude')[0] == aggregate([], 'speed')[0] == []
    assert len(aggregate([sample(1, 'NA')], 'altitude')[0]) == 1
    passed.append('单值 std=0、空指标 NA/空单元格、scene 空组写出、条件空组跳过：通过')

    a = aggregate_group([sample(1, '1', std='0'), sample(2, '3', std='0')], 'scene', 'building')[0]
    b = aggregate_group([sample(1, '1', std='1e9'), sample(2, '3', std='-999')], 'scene', 'building')[0]
    assert a == b and a['rmse_std'] == 1
    _, ct = aggregate([sample(1, '1'), sample(2, '2', dataset='mystery25fps_2')], 'scene')
    assert ct['overall']['n_records'] == 2 and ct['building']['n_records'] == 1
    passed.append('原始单行 std 不参与 rmse_std；未知场景仍纳入 pooled overall：通过')

    for token in ('nan', 'inf', '-inf'):
        assert scene_float(token) is not None
        assert len(condition_values([sample(1, token)], 'rmse')) == 0
        try:
            aggregate_group([sample(1, token), sample(2, '1')], 'scene', 'building')
        except (AttributeError, ValueError, OverflowError, statistics.StatisticsError):
            pass
        else:
            raise AssertionError('Expected current Python legacy pstdev nonfinite failure')
    assert len(condition_values([sample(1, '0'), sample(2, '-2')], 'rmse')) == 2
    assert scene_float('1_000') == 1000 and len(condition_values([sample(1, '1_000')], 'rmse')) == 0
    passed.append('可转 float 与有限数不同；NaN/Inf 的旧 pstdev 报错边界、0/负数、pandas 解析边界：通过')

    for old, new, branch, status in [
        ('1.0', 1.0 + 1e-13, 'scene', 'numeric_match'),
        ('1.234568', 1.2345678, 'altitude', 'rounding_match'),
        ('1.234568', 1.2345678, 'scene', 'value_mismatch'),
        ('1.0', 1.01, 'scene', 'value_mismatch'),
        ('NA', 'NA', 'scene', 'missingness_match'),
        ('', float('nan'), 'speed', 'missingness_match'),
        ('NA', float('nan'), 'speed', 'missingness_mismatch'),
        ('NaN', 'NA', 'scene', 'missingness_mismatch'),
        ('', 0.0, 'scene', 'missingness_mismatch'),
    ]:
        assert compare_value(old, new, branch)['status'] == status
    passed.append('比较器严格容差、六位舍入、真实差异、NA/空/NaN/0 状态区分：通过')

    new, counts = aggregate([sample(1, '1')], 'scene')
    header = ['scene', *FIELDS]
    cells = [[serialize(row[f], 'scene') for f in header] for row in new]
    assert any(r['status'] == 'group_mismatch' for r in compare_tables('scene', header, cells[:-1], new, counts))
    assert any(r['status'] == 'group_mismatch' for r in compare_tables('scene', header, cells + [cells[0]], new, counts))
    extra = [list(cells[0])]; extra[0][0] = 'unexpected_scene'
    assert any(r['group_key'] == 'unexpected_scene' for r in compare_tables('scene', header, cells + extra, new, counts))
    assert any(r['status'] == 'schema_mismatch' for r in compare_tables('scene', header[:-1], [r[:-1] for r in cells], new, counts))
    assert any(r['status'] == 'schema_mismatch' for r in compare_tables('scene', header + ['extra'], [r + ['42'] for r in cells], new, counts))
    assert any(r['status'] == 'schema_mismatch' for r in compare_tables('scene', header + ['SR'], [r + ['1'] for r in cells], new, counts))
    passed.append('比较器分组和字段并集、缺失/额外/重复组、缺失/额外/重复列：通过')

    for bad in [INPUT_ROOT / SOURCE, WORKSPACE / 'README.md']:
        try:
            check_output(bad, True)
        except ValueError:
            pass
        else:
            raise AssertionError('Output allowlist bypass')
    with patch.object(Path, 'is_symlink', return_value=True):
        try:
            check_output(WORKSPACE / OUTPUTS['records'], True)
        except ValueError:
            pass
        else:
            raise AssertionError('Symlink guard bypass')
    with patch.object(Path, 'is_symlink', return_value=False), patch.object(Path, 'exists', return_value=True):
        try:
            check_output(WORKSPACE / OUTPUTS['records'], False)
        except FileExistsError:
            pass
        else:
            raise AssertionError('Default overwrite guard bypass')
    passed.append('输出白名单、拒绝源/历史文件、符号链接与默认覆盖（内存模拟）：通过')
    return passed


def report_text(snapshot, sources, code_info, tests, diagnostics, checks, counts, comparisons, command):
    lines = [MARKER, '# 第 5 步：DPVO 单方法试跑与三张 summary 核对', '',
             '只核对现有 CSV 的聚合一致性；不重新评估轨迹，不证明物理单位、历史生成版本或完整轨迹成功。',
             '规则背景见 [README](../README.md) 与 [第 4 步报告](04_metric_protocol_audit.md)。', '',
             '## 输入快照与实际执行', '', f'工作区：`{WORKSPACE}`。输入根：`{INPUT_ROOT}`。',
             '四份 CSV 先核对第 4 步矩阵 SHA-256，再解析；目标数值在独立计算完成后才进入比较器。',
             '本轮只读取以下四份源 CSV，没有重新盘点其它方法。', '',
             '| 实际路径 | bytes | 第 4 步/执行前 SHA-256 | 执行后 SHA-256 | 读取状态 |', '|---|---:|---|---|---|']
    for name, info in sources.items():
        lines.append(f"| `{INPUT_ROOT/name}` | {info['size']} | `{info['expected']}` | `{info['after']}` | {info['status']} |")
    lines += ['', '仅静态读取三份获准源码；没有执行、导入或复制后运行。', '',
              '| Benchmark 相对路径 | 第 4 步及执行前后 SHA-256 | 关键规则位置 |', '|---|---|---|']
    refs = ['45–54、75–118、121–153：转换/门控/pooled/std/CSV 直接写数值',
            '127–179、264–325、439：条件/有限值/独立集合/ddof=1/%.6f',
            '158–217、283–376、504–510：同上速度分支']
    for name, ref in zip(CODE, refs):
        lines.append(f"| `{name}` | `{code_info[name]['before']}`；前后相同={code_info[name]['unchanged']} | {ref} |")
    lines += ['', '执行命令（固定解释器，禁用字节码；无环境安装/重新检查）：', '', '```bash',
              f'/home/yuan/anaconda3/bin/python3 -B {WORKSPACE}/scripts/run_dpvo_pilot.py --self-test', command, '```', '',
              '默认拒绝覆盖已有文件。仅在审阅本轮派生输出后，复跑命令可加 `--overwrite`；',
              '覆盖仍限六个明确产物，拒绝软链接和硬链接输出，不触及 README、状态、旧快照或源目录。', '',
              '## 原始记录与解析复核', '',
              'run_records.csv 保留原始 11 字段及每个单元格文本；只增加来源、记录序号、配置、解析列和四核心列状态。',
              'source_record_index 从 1 起、不含表头。原始 std 保留，但不进入跨记录 rmse_std 计算。',
              '仅使用已审阅的工作区 audit_metric_protocol.py 中纯 parse_identifier / numeric_state / diagnose；不改第 4 步脚本。', '',
              '| 快照项目 | 本轮观察 | 第 4 步核对 |', '|---|---|---|']
    for field in ('record_count', 'sequence_count', 'run_id_set_distribution_json', 'condition_labelled_records',
                  'duplicate_full_identifier_groups', 'unresolved_identifier_count'):
        lines.append(f'| {field} | `{diagnostics[field]}` | {checks[field]} |')
    lines += [f"| 无条件标签序列 | `{diagnostics['condition_unlabelled_sequences_json']}` | {checks['condition_unlabelled_sequences_json']} |",
              f"| 每序列编号和计数逐项 | 见试跑记录表（未补行或删行） | {checks['sequence_run_records_json']} |", '',
              '144 条记录、48 个完整 sequence、各编号 1/2/3；132 条双条件标签，12 条来自四个 25fps sequence。',
              '这些数量来自实际解析及逐项快照比较，没有硬编码生成记录。四核心指标均为 144 个有限正值。',
              '编号不代表成功或共享随机种子；未确认的单位保持原值，不进行统一换算。', '',
              '## Legacy 分支、标签映射与样本数', '',
              '- scene：五类前缀映射不合并原始 sequence；包含可归类的无条件标签路线。RMSE 可转 float 后门控所有指标，再各自排缺失；ddof=0。overall 合并全部现存记录，不平均场景统计。',
              '- altitude/speed：双条件标签才纳入；每项各用自身有限集合，无 RMSE 效率门控；ddof=1，没有 overall。',
              '- SR 分母均为该组现存记录；scene 分子为 RMSE 可转 float，条件分子为有限 RMSE。均不称作已验证完整轨迹成功率。',
              '- 所有均值为参与逐次值的算术均值，无 sequence 预平均、帧数/sse/runtime 加权或 RMS-of-RMSE。',
              '- scene 空组仍写 SR=0、指标 NA；条件无记录组不写，存在记录但某指标空则写空单元格。两分支单值 std=0 仅为 legacy 对照；单次保留实验的重复运行 std 仍不可估计。',
              '- scene CSV 直接写 Python 浮点文本，不使用终端显示的六位格式。高度/速度 CSV 按 `%.6f` 写出；比较清单始终保留未舍入的重算值。展示舍入不反向参与计算。',
              '- 内部分组键与旧显示标签显式映射见下表；scene 键原样，高度 10/20/30 → DPVO_{值}m_mono，速度 2/4/8 → DPVO_{值}m/s_mono。', '',
              '| 分支 | 内部分组键 → 旧标签 | n_records | SR 分子/分母 | FPS n_used | runtime n_used | 内存 n_used | rmse n_used |',
              '|---|---|---:|---|---:|---:|---:|---:|']
    for branch, groups in counts.items():
        for label, c in groups.items():
            key = label if branch == 'scene' else label.removeprefix('DPVO_').removesuffix('_mono')
            lines.append(f"| {branch} | `{key}` → `{label}` | {c['n_records']} | {c['sr_numerator']}/{c['sr_denominator']} | " + ' | '.join(str(c[f'n_used_{m}']) for m in METRICS) + ' |')
    lines += ['', '每个比较单元还记录参与记录的 source_record_index 列表，便于定位分组成员。', '',
              '## 真实计算前的内存测试', '', *['- ' + item for item in tests], '',
              '所有虚拟行仅在内存，没有写入真实记录表或研究结果。特别覆盖 DPVO 实际数据没有出现的缺失、非有限值和空组。',
              '兼容边界：scene 的 float 转换接受 NaN/Inf，当前 Python statistics.pstdev 对包含它们的多值组报错；',
              '试跑脚本保留这一行为并显式捕获阶段错误，不偷偷改成有限值过滤。单值仍按旧规则 std=0。', '',
              '## 比较规则与结果', '',
              '按分组标签和字段并集对照，不按行号、不 inner join；每表比较 SR 与四指标 mean/std，共 9 数值列。',
              '严格规则：abs(new-old) ≤ 1e-12 + 1e-12×abs(old)。严格不符时，仅高度/速度允许',
              '将未舍入重算值用 `%.6f` 序列化，再用 Decimal 比较数值相等；未使用默认宽松容差或事后调参。',
              '场景无小数位容差；1.0 不导出 ±0.05。NA、空、NaN、Inf 状态分开，缺失不补零；',
              '相同缺失状态另记 missingness_match（本轮真实结果不需要），不能把不可解析文本一概视为相同。', '',
              '| 目标 | 比较项数 | numeric_match | rounding_match | 不匹配 | 最大有限绝对差 |', '|---|---:|---:|---:|---:|---:|']
    mismatches = []
    for branch in TARGETS:
        comp = [r for r in comparisons if r['branch'] == branch]
        counter = Counter(r['status'] for r in comp)
        bad = [r for r in comp if r['status'].endswith('mismatch')]
        mismatches.extend(bad)
        maximum = max((float(r['absolute_difference']) for r in comp if r['absolute_difference'] != ''), default=0)
        lines.append(f"| {branch} | {len(comp)} | {counter['numeric_match']} | {counter['rounding_match']} | {len(bad)} | {maximum:.17g} |")
    lines += ['', '完整逐单元格结果：[05_dpvo_comparison.csv](05_dpvo_comparison.csv)。', '',
              '状态总计：`' + json_text(Counter(r['status'] for r in comparisons)) + '`。', '',
              '没有把原始 max/min/mean/median/sse/std 作为本轮旧表指标；三份目标不提供这些字段。',
              '分组列作为键核对；其余字段都参与 schema 并集检查，没有被静默略过。', '',
              '### 所有未匹配项及诊断', '']
    if mismatches:
        lines += ['| 分支 | 组 | 字段 | 旧值 | 重算未舍入值 | 状态/原因 |', '|---|---|---|---|---|---|']
        for r in mismatches:
            lines.append(f"| {r['branch']} | {r['group_key']} | {r['field']} | {r['old_value_raw']} | {r['recomputed_value_unrounded']} | {r['status']}；{r['detail'] or 'unresolved；需限定诊断'} |")
    else:
        lines += ['无 value_mismatch、missingness_mismatch、group_mismatch 或 schema_mismatch。',
                  '高度/速度中严格不符项均由已确认的六位小数写出解释；不存在需放宽容差的残余差异。']
    lines += ['', '## 确认范围、限制与下一阶段', '',
              '本轮确认：这些固定字节版本的 DPVO CSV，在已核验且事先确定的分支规则下的解析、分组、样本集合、聚合和目标比较。',
              '本轮未确认：底层轨迹评估、实际速度/高度与数值物理单位、历史生成源码版本、完整轨迹成功、效率底层测量；不作跨方法结论。',
              '分组 std 混合跨序列差异与重复波动，不是单独的重复实验稳定性；没有显著性检验、排名、联合条件分析或科研图。',
              ('可进入第 6 步，但尚未开始，等待用户任务。可复用原始值保留、末尾编号解析、显式配置/条件、来源哈希、分组成员及并集比较。'
               if not mismatches else '存在上述差异；第 6 步前须保留其原因/限制，不宣称三张旧表全部吻合。'),
              '第 6 步不能把两类 legacy 口径提前合一；其它方法的缺失、不同配置范围、运行次数和来源边界继续按 README/第 4 步记录处理。', '',
              '## 文件与保护检查', '',
              *['- `' + p + '`' for p in OUTPUTS.values()], '',
              '新增可复跑脚本：`scripts/run_dpvo_pilot.py`。本报告由脚本生成，不手工编辑派生 CSV 数值。',
              '执行前后四份源 CSV、三份获准源码哈希一致；第 3/4 步快照与脚本、AGENTS 未改。',
              'figures/ 无本轮输出；未访问轨迹/日志、其它方法逐次文件，未安装、修改环境/权限、运行研究脚本、操作 Git 或上传。',
              '普通执行器出现 mountinfo path is not absolute；仅通过工具允许的限定审批机制运行本工作区检查。', '',
              '第 5 步试跑与对照已完成；是否旧表吻合以以上逐项判定为准。完成后停止，不自动开始第 6 步。', '']
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--self-test', action='store_true', help='memory-only tests; no real CSV read')
    parser.add_argument('--overwrite', action='store_true', help='refresh only the six reviewed step-5 artifacts')
    args = parser.parse_args()
    tests = self_test()
    print(json_text({'self_tests': len(tests), 'result': 'passed'}))
    if args.self_test:
        for test in tests:
            print(test)
        return
    for relative in OUTPUTS.values():
        check_output(WORKSPACE / relative, args.overwrite)
    if args.overwrite and any((WORKSPACE / p).exists() for p in OUTPUTS.values()):
        prior_report = WORKSPACE / OUTPUTS['report']
        if not prior_report.is_file() or not prior_report.read_text(encoding='utf-8').startswith(MARKER):
            raise ValueError('Existing artifacts lack this pilot report marker; review before overwriting')
    header, cells = decode_csv(read_bytes(MATRIX))
    matrix = records_from_cells(header, cells)
    candidates = [r for r in matrix if r['source_relative_path'] == SOURCE]
    if len(candidates) != 1:
        raise ValueError('DPVO snapshot row must be unique')
    snapshot = candidates[0]
    refs = {r['current_path']: r['sha256'] for r in json.loads(snapshot['related_summaries_json'])}
    refs[SOURCE] = snapshot['sha256']
    sources, raw_inputs = {}, {}
    for relative in [SOURCE, *TARGETS.values()]:
        raw = read_bytes(INPUT_ROOT / relative)
        digest = sha(raw)
        sources[relative] = {'expected': refs[relative], 'before': digest, 'size': len(raw),
                             'status': 'hash_matched; pending_parse'}
        raw_inputs[relative] = raw
    changed = [p for p, v in sources.items() if v['before'] != v['expected']]
    if changed:
        message = MARKER + '\n# 第 5 步暂停：输入快照已变化\n\n' + json_text(sources) + '\n\n未解析或采用变化文件；未生成派生数值。\n'
        write_output(WORKSPACE / OUTPUTS['report'], message, args.overwrite)
        raise ValueError(f'Changed inputs; comparison paused: {changed}')
    code_refs = {r['path']: r['sha256'] for r in json.loads(snapshot['aggregation_code_evidence_json'])}
    code_info = {}
    for relative in CODE:
        digest = sha(read_bytes(BENCHMARK / relative))
        if digest != code_refs[str(BENCHMARK / relative)]:
            raise ValueError(f'Reviewed aggregation source changed: {relative}')
        code_info[relative] = {'before': digest}
    raw_header, cells = decode_csv(raw_inputs[SOURCE])
    raw_rows = records_from_cells(raw_header, cells)
    required = {'dataset', *METRICS, 'max', 'min', 'mean', 'median', 'sse', 'std'}
    if not required.issubset(raw_header):
        raise ValueError('Missing required DPVO input fields')
    records = [parse_record(row, i, sources[SOURCE]['before']) for i, row in enumerate(raw_rows, 1)]
    diagnostics = diagnose(raw_rows, raw_header)
    check_fields = ('record_count', 'sequence_count', 'run_id_set_distribution_json', 'condition_labelled_records',
                    'duplicate_full_identifier_groups', 'unresolved_identifier_count', 'sequence_run_records_json',
                    'condition_unlabelled_sequences_json', 'scene_record_counts_json', 'numeric_states_json', 'raw_columns_json')
    checks = {key: str(diagnostics[key]) == snapshot[key] for key in check_fields}
    # The reused strict suffix parser and shared first-two-token regex need not
    # agree on arbitrary names. Check every real name, without substituting rules.
    for record in records:
        tokens = re.findall(r'(?<![A-Za-z0-9])(high|medium|low)(?![A-Za-z0-9])', record['dataset'].lower())
        levels = (tokens[0], tokens[1]) if len(tokens) >= 2 else ('', '')
        if levels != (record['speed_level'], record['altitude_level']):
            raise ValueError(f'Condition parser ambiguity: {record["dataset"]}')
    if not all(checks.values()):
        raise ValueError('Structure differs from step-4 snapshot: ' + json_text(checks))
    recomputed, counts = {}, {}
    for branch in TARGETS:
        recomputed[branch], counts[branch] = aggregate(records, branch)
    # Only now decode target cells; nothing above consulted their numerical values.
    comparisons = []
    for branch, relative in TARGETS.items():
        target_header, target_cells = decode_csv(raw_inputs[relative])
        comparisons.extend(compare_tables(branch, target_header, target_cells, recomputed[branch], counts[branch]))
    for relative, info in sources.items():
        info['after'] = sha(read_bytes(INPUT_ROOT / relative))
        info['status'] = 'hash_matched; read_and_parsed; unchanged' if info['after'] == info['before'] else 'CHANGED_DURING_RUN'
        if info['after'] != info['before']:
            raise ValueError(f'Input changed during run: {relative}')
    for relative, info in code_info.items():
        info['unchanged'] = sha(read_bytes(BENCHMARK / relative)) == info['before']
        if not info['unchanged']:
            raise ValueError(f'Source changed during run: {relative}')
    command = shlex.join(['/home/yuan/anaconda3/bin/python3', '-B', str(Path(__file__).absolute()), *sys.argv[1:]])
    outputs = {'records': csv_text(records, list(records[0]))}
    for branch in TARGETS:
        rows = [{key: value if key == branch else serialize(value, branch) for key, value in row.items()} for row in recomputed[branch]]
        outputs[branch] = csv_text(rows, [branch, *FIELDS])
    outputs['comparison'] = csv_text(comparisons, list(comparisons[0]))
    outputs['report'] = report_text(snapshot, sources, code_info, tests, diagnostics, checks, counts, comparisons, command)
    for key, content in outputs.items():
        write_output(WORKSPACE / OUTPUTS[key], content, args.overwrite)
    print(json_text({'records': len(records), 'sequences': diagnostics['sequence_count'],
                     'comparison_counts': {b: dict(Counter(r['status'] for r in comparisons if r['branch'] == b)) for b in TARGETS},
                     'outputs': list(OUTPUTS.values())}))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, KeyError, AttributeError, statistics.StatisticsError) as error:
        print(f'STOP: {error}', file=sys.stderr)
        sys.exit(1)
