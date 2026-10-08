"""Memory-only refresh of explicitly enumerated benchmark configurations.

Never imports results.py, evo or SLAM. Defaults to dry run. Existing CSV row
identities, ordering and non-memory cell text are preserved. PeakReservedGB is
a legacy compatibility column: ONLY the hash-bound metadata certifies its
peak_reserved/GiB meaning. CPU RSS is never written into that reserved column.
Typed run records and Table 2 expose value_gib, memory_type and display markers.
"""
import argparse
import csv
import hashlib
import io
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean

from memory_gib import read_memory

ROOT = Path(__file__).resolve().parent
RAW = Path('/home/yuan/data2tb/experiments')
COLUMN = 'PeakReservedGB'
# Exact retained configuration routes; no directory discovery or comment toggles.
CONFIGS = [
    ('DPVO::mono', 'DPVO/mono_metrics.csv', 'DPVO/results/airsim/{sequence}/{run}/metrics.txt'),
    ('DROID-SLAM::mono', 'DROID-SLAM/mono_metrics.csv', 'DROID-SLAM/results/airsim/{sequence}/mono/{run}/metrics.txt'),
    ('DROID-SLAM::rgbd', 'DROID-SLAM/rgbd_metrics.csv', 'DROID-SLAM/results/airsim/{sequence}/rgbd/{run}/metrics.txt'),
    ('DSO::mono', 'DSO/mono_metrics.csv', 'DSO/experiments/airsim/{sequence}/mono/{run}/metric.txt'),
    ('ElasticFusion::rgbd', 'ElasticFusion/rgbd_metrics.csv', 'ElasticFusion/experiments/{sequence}/{run}/RunStats.txt'),
    ('MASt3R-SLAM::mono_calib', 'MASt3R-SLAM/calib_metrics.csv', 'MASt3R-SLAM/logs/airsim/calib/{sequence}/{run}/metrics.txt'),
    ('MASt3R-SLAM::mono_nocalib', 'MASt3R-SLAM/nocalib_metrics.csv', 'MASt3R-SLAM/logs/airsim/nocalib/{sequence}/{run}/metrics.txt'),
    ('MongGS::mono', 'MongGS/mono_metrics.csv', 'MongGS/results/airsim/{sequence}/mono/{run}/metric.txt'),
    ('ORB-SLAM2::mono', 'ORB-SLAM2/mono_metrics.csv', 'ORB-SLAM2/experiments/airsim/{sequence}/mono/{run}/RunStats.txt'),
    ('ORB-SLAM2::rgbd', 'ORB-SLAM2/rgbd_metrics.csv', 'ORB-SLAM2/experiments/airsim/{sequence}/rgbd/{run}/RunStats.txt'),
    ('ORB-SLAM3::mono', 'ORB-SLAM3/mono_metrics.csv', 'ORB_SLAM3/results/{sequence}/mono/{run}/TimingResults.txt'),
    ('ORB-SLAM3::rgbd', 'ORB-SLAM3/rgbd_metrics.csv', 'ORB_SLAM3/results/{sequence}/RGBD/{run}/TimingResults.txt'),
    ('Photo-slam::mono', 'Photo-slam/mono_metrics.csv', 'Photo-SLAM/results/airsim/mono/{sequence}/{run}/GpuPeakUsageMB.txt'),
    ('Photo-slam::rgbd', 'Photo-slam/rgbd_metrics.csv', 'Photo-SLAM/results/airsim/rgbd/{sequence}/{run}/GpuPeakUsageMB.txt'),
    ('SGS-SLAM::semantic', 'SGS-SLAM/semantic_metrics.csv', 'SGS-SLAM/experiments/Airsim_semantic/{sequence}/{run}/metrics.txt'),
    ('SLAM3R::mono', 'SLAM3R/mono_metrics.csv', 'SLAM3R/experiments/airsim/{sequence}/mono/{run}/metric.txt'),
    ('SVO::mono', 'SVO/mono_metrics.csv', 'svo_pro_universal/experiments/airsim/mono/{sequence}/{run}/metric.txt'),
    ('SplaTAM::rgbd', 'SplaTAM/rgbd_metrics.csv', 'SplaTAM/experiments/airsim/{sequence}/{run}/metric.txt'),
    ('TartanVO::mono', 'TartanVO/mono_metrics.csv', 'tartanvo/experiments/airsim/{sequence}/mono/{run}/airsim_tartanvo_1914_metric.txt'),
    ('VGGT-LONG::mono', 'VGGT-LONG/mono_metrics.csv', 'VGGT-LONG/airsim/{sequence}/{run}/runtime_stats.txt'),
    ('VGGT-SLAM::mono', 'VGGT-SLAM/mono_metrics.csv', 'VGGT-SLAM/logs/airsim/{sequence}/{run}/stats.txt'),
    ('hierslam::rgbd_500', 'hierslam/rgbd_metrics_500frames.csv', 'hierslam/experiments/Airsim_no_semantic/{sequence}/500frames/{run}/metric.txt'),
    ('hierslam::rgbd_whole', 'hierslam/rgbd_whole_trajectory/rgbd_metrics.csv', 'hierslam/experiments/Airsim_no_semantic/{sequence}/complete/{run}/metric.txt'),
    ('hierslam::semantic_500', 'hierslam/semantic_metrics_500frames.csv', 'hierslam/experiments/Airsim_semantic/{sequence}/500frames/{run}/gpu_peak_memory.txt'),
]
CPU_METHODS = {'DSO', 'ElasticFusion', 'ORB-SLAM2', 'ORB-SLAM3', 'SVO'}
RUN_FILE = 'memory_gib_run_records.csv'
FOOTNOTE_ZH = '* 表示 CPU 峰值常驻内存（peak RSS）；未标 * 的数值表示 GPU peak_reserved。二者属于不同内存类型，不进行跨类型排名。'
FOOTNOTE_EN = '* CPU peak RSS; unmarked values indicate GPU peak-reserved memory. CPU and GPU memory statistics represent different measurement types and are not directly ranked across types.'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def encode_csv(rows, fields, newline='\n'):
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator=newline)
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()


def numeric(text):
    try:
        x = float(text)
        return x if math.isfinite(x) else None
    except (ValueError, TypeError):
        return None


def table2_memory_rows(configuration_id, csv_path, metadata_path=None):
    """Reject stale, unapproved or mismatched input; never fall back to old data."""
    metadata_path = metadata_path or ROOT / 'memory_gib_metadata.json'
    metadata = json.loads(Path(metadata_path).read_text())
    if metadata.get('schema_version') != 2:
        raise ValueError('Table 2 requires typed memory metadata schema 2')
    if not metadata.get('applied'):
        raise ValueError('Dry-run metadata cannot approve Table 2 inputs')
    matches = [x for x in metadata['configurations'] if x['configuration_id'] == configuration_id]
    if len(matches) != 1:
        raise ValueError('Table 2 configuration certificate is absent or ambiguous')
    row = matches[0]
    path = Path(csv_path).resolve()
    if str(path) != row['csv_absolute_path'] or sha(path.read_bytes()) != row['after_sha256']:
        raise ValueError('Table 2 source path/SHA mismatch; memory certificate is stale')
    expected = {'GPU_RESERVED': ('peak_reserved', ''), 'CPU_RSS': ('peak_rss', '*')}
    if (not row['table2_memory_eligible'] or row['unit'] != 'GiB'
            or (row['statistic'], row['table_display_marker']) != expected.get(row['memory_type'])):
        raise ValueError('No approved typed memory source for this Table 2 row')
    # Source CSV binds retained identities, NOT CPU values in its old named column.
    # Typed values bind the exact audited raw metric and its hash per run.
    run_path = Path(metadata['run_records_path'])
    if sha(run_path.read_bytes()) != metadata['run_records_sha256']:
        raise ValueError('Typed memory records changed; certificate is stale')
    with run_path.open(newline='') as handle:
        records = [r for r in csv.DictReader(handle) if r['configuration_id'] == configuration_id]
    with path.open(newline='') as handle:
        identities = [r['dataset'] for r in csv.DictReader(handle)]
    if [r['dataset'] for r in records] != identities:
        raise ValueError('Typed memory/source identity mismatch')
    if any(r['memory_type'] != row['memory_type'] or r['table_display_marker'] != row['table_display_marker'] for r in records):
        raise ValueError('Typed memory measurement/marker mismatch')
    return records


def collect():
    plans, cells, summaries, sources = [], [], [], {}
    for cid, rel, route in CONFIGS:
        path = ROOT / rel
        original = path.read_bytes()
        reader = csv.DictReader(io.StringIO(original.decode(), newline=''))
        rows = list(reader)
        fields = reader.fieldnames
        if not fields or len(fields) != len(set(fields)) or COLUMN not in fields or 'dataset' not in fields:
            raise ValueError(f'{rel}: missing/duplicate required fields')
        ids = [r['dataset'] for r in rows]
        if len(ids) != len(set(ids)) or len(rows) != 144:
            raise ValueError(f'{rel}: unexpected retained run set (expected 144 unique rows)')
        updated = [dict(r) for r in rows]
        method = cid.split('::')[0]
        memory_type = 'CPU_RSS' if method in CPU_METHODS else 'GPU_RESERVED'
        marker = '*' if memory_type == 'CPU_RSS' else ''
        statistic = 'peak_rss' if memory_type == 'CPU_RSS' else 'peak_reserved'
        status_counts = Counter()
        by_sequence = defaultdict(list)
        seen_sequences = set()
        retained_by_sequence = defaultdict(set)
        changed_cells = 0
        for old, new in zip(rows, updated):
            match = re.fullmatch(r'([A-Za-z0-9_]+)_([1-6])', old['dataset'])
            if not match:
                raise ValueError(f'{cid}: unrecognized run identity {old["dataset"]}')
            sequence, run = match.groups()
            expected_runs = '456' if cid in {'hierslam::rgbd_500', 'hierslam::semantic_500'} else '123'
            if run not in expected_runs:
                raise ValueError(f'{cid}: wrong mode/run {old["dataset"]}')
            retained_by_sequence[sequence].add(run)
            evidence = read_memory(RAW / route.format(sequence=sequence, run=run), method)
            if evidence['memory_type'] != memory_type or evidence['table_display_marker'] != marker:
                raise ValueError(f'{cid}: inconsistent memory type/marker')
            status_counts[evidence['status']] += 1
            if evidence.get('source_sha256'):
                sources[evidence['source_path']] = evidence['source_sha256']
            if evidence['status'] in {'ambiguous_field', 'route_mismatch', 'unit_conflict'}:
                raise ValueError(f'{cid}/{old["dataset"]}: {evidence}')
            value = evidence['value_gib']
            if evidence['status'] not in {'ok', 'missing_file', 'missing_field', 'invalid_value', 'path_not_directory'}:
                raise ValueError(f'{cid}: unexpected unresolved status {evidence}')
            # Preserve the old reserved compatibility column for CPU configurations.
            # Their verified RSS measurements live only in the typed outputs.
            if memory_type == 'GPU_RESERVED':
                prior = numeric(old[COLUMN])
                if value is not None:
                    new[COLUMN] = old[COLUMN] if prior is not None and math.isclose(prior, value, rel_tol=1e-14, abs_tol=1e-14) else repr(value)
                else:
                    new[COLUMN] = 'NA'
            changed = old[COLUMN] != new[COLUMN]
            changed_cells += changed
            condition = sequence.rsplit('_', 2)[-2:]
            if len(condition) == 2 and all(x in {'low', 'medium', 'high'} for x in condition):
                seen_sequences.add(sequence)
                if value is not None:
                    by_sequence[sequence].append(value)
            cells.append(dict(configuration_id=cid, dataset=old['dataset'], sequence=sequence, run_id=run,
                              old_csv_value=old[COLUMN], resulting_csv_value=new[COLUMN], cell_changed=changed,
                              configuration_verified=True, **evidence))
        if len(seen_sequences) != 44:
            raise ValueError(f'{cid}: unexpected condition set')
        if len(retained_by_sequence) != 48 or any(v != set(expected_runs) for v in retained_by_sequence.values()):
            raise ValueError(f'{cid}: unexpected per-sequence retained run membership')
        replacement = encode_csv(updated, fields, '\r\n' if b'\r\n' in original else '\n') if changed_cells else original
        if [{k: v for k, v in r.items() if k != COLUMN} for r in rows] != [{k: v for k, v in r.items() if k != COLUMN} for r in updated]:
            raise AssertionError('Non-memory cells changed')
        entry = dict(configuration_id=cid, csv_relative_path=rel, csv_absolute_path=str(path),
                     source_route=str(RAW / route), retained_runs=len(rows),
                     before_sha256=sha(original), after_sha256=sha(replacement),
                     csv_modified=bool(changed_cells), changed_memory_cells=changed_cells,
                     non_memory_cells_and_order_unchanged=True, legacy_column=COLUMN,
                     legacy_column_certified=memory_type == 'GPU_RESERVED',
                     statistic=statistic, memory_type=memory_type, table_display_marker=marker,
                     value_gib=mean([mean(v) for v in by_sequence.values()]) if by_sequence else None,
                     value_scope='condition_labelled; equal_weight_sequence_means',
                     unit='GiB', memory_available=bool(by_sequence),
                     table2_memory_eligible=bool(by_sequence) and method != 'SGS-SLAM',
                     paper_eligible=method != 'SGS-SLAM',
                     memory_verified=True, status_counts=dict(status_counts),
                     color_ranking_enabled=False,
                     reason=('SGS 的内存已核实；独立的 Accuracy 论文排除规则仍生效' if method == 'SGS-SLAM'
                             else '现有保留测量为 CPU peak RSS，带 * 展示；不推断算法是否使用 GPU' if memory_type == 'CPU_RSS'
                             else 'GPU peak_reserved 来源与单位已核实；个别缺失记录仍不可用'))
        plans.append((path, original, replacement, entry))
        summaries.append(dict(configuration_id=cid, subset='condition_labelled', statistic=statistic, unit='GiB',
                              value_gib=entry['value_gib'], memory_type=memory_type, table_display_marker=marker,
                              table_display_value=(f"{entry['value_gib']:.4f}{marker}" if entry['table2_memory_eligible'] else '--'),
                              table_metric_name='Peak Memory (GiB)', color_ranking_enabled=False,
                              PeakReservedGiB=(entry['value_gib'] if memory_type == 'GPU_RESERVED' and entry['table2_memory_eligible'] else ''),
                              finite_runs=sum(map(len, by_sequence.values())), retained_runs=132,
                              finite_sequences=len(by_sequence), observed_sequences=44,
                              aggregation='序列内有限内存记录均值，再对序列等权；不按 RMSE/SR 筛选',
                              memory_available=bool(by_sequence), paper_eligible=entry['paper_eligible'],
                              status=('available' if entry['table2_memory_eligible'] else 'excluded_from_paper' if not entry['paper_eligible'] else 'unavailable'), reason=entry['reason'],
                              footnote=FOOTNOTE_ZH,
                              source_csv=rel, source_sha256=entry['after_sha256']))
    return plans, cells, summaries, sources


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='Write memory-only corrections after all validation')
    parser.add_argument('--audit-dir', type=Path, required=True, help='New directory for backup and evidence (must not exist)')
    args = parser.parse_args()
    if args.audit_dir.exists():
        parser.error('audit directory already exists; existing evidence is never overwritten')
    plans, cells, summaries, sources = collect()
    # Recheck exact small source files and CSVs before any source CSV mutation.
    for name, digest in sources.items():
        if sha(Path(name).read_bytes()) != digest:
            raise RuntimeError(f'Raw source changed during audit: {name}')
    for path, original, _, _ in plans:
        if path.read_bytes() != original:
            raise RuntimeError(f'CSV edited concurrently: {path}')
    audit = args.audit_dir.resolve()
    audit.mkdir(parents=True)
    cell_fields = list(dict.fromkeys(key for cell in cells for key in cell))
    (audit / 'memory_cell_audit.csv').write_bytes(encode_csv(cells, cell_fields))
    typed_fields = ['configuration_id', 'dataset', 'sequence', 'run_id', 'value_gib', 'memory_type',
                    'table_display_marker', 'status', 'source_path', 'source_sha256', 'source_field',
                    'native_unit', 'raw_value', 'conversion', 'source_line']
    typed_rows = [{k: cell.get(k, '') for k in typed_fields} for cell in cells]
    typed_data = encode_csv(typed_rows, typed_fields)
    metadata = dict(schema_version=2, compatibility_column=COLUMN, display_field='value_gib',
                    table_metric_name='Peak Memory (GiB)',
                    footnote_zh=FOOTNOTE_ZH, footnote_en=FOOTNOTE_EN,
                    color_ranking_enabled=False, cross_type_ranking_allowed=False,
                    run_records_path=str(ROOT / RUN_FILE), run_records_sha256=sha(typed_data),
                    note='GPU_RESERVED 与 CPU_RSS 分开记录，CPU 单元格带 *；旧列名不证明内存类型。原逐次 CSV 的 CPU 列不改名为 peak_reserved，现行 Table 2 只读取本次有类型及来源哈希的记录。历史表图保留。',
                    applied=args.apply, audit_directory=str(audit), configurations=[p[3] for p in plans])
    (audit / 'csv_updates.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + '\n')
    (audit / RUN_FILE).write_bytes(typed_data)
    (audit / 'memory_gib_table2.csv').write_bytes(encode_csv(summaries, list(summaries[0])))
    if args.apply:
        for path, old, new, _ in plans:
            if old != new:
                backup = audit / 'backups' / path.relative_to(ROOT)
                backup.parent.mkdir(parents=True, exist_ok=True)
                backup.write_bytes(old)
        for fn in ['memory_gib_metadata.json', 'memory_gib_table2.csv', RUN_FILE]:
            if (ROOT / fn).exists():
                backup = audit / 'backups' / fn
                backup.parent.mkdir(parents=True, exist_ok=True)
                backup.write_bytes((ROOT / fn).read_bytes())
        for path, old, new, _ in plans:
            if old != new:
                path.write_bytes(new)
        (ROOT / 'memory_gib_metadata.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + '\n')
        (ROOT / RUN_FILE).write_bytes(typed_data)
        (ROOT / 'memory_gib_table2.csv').write_bytes(encode_csv(summaries, list(summaries[0])))
        for path, _, new, _ in plans:
            if path.read_bytes() != new:
                raise RuntimeError(f'Post-write mismatch: {path}')
    print(json.dumps(dict(applied=args.apply, configurations=len(plans),
                          verified=sum(p[3]['memory_verified'] for p in plans),
                          csvs_changed=sum(p[3]['csv_modified'] for p in plans),
                          changed_cells=sum(p[3]['changed_memory_cells'] for p in plans),
                          audit_dir=str(audit)), indent=2))


if __name__ == '__main__':
    main()
