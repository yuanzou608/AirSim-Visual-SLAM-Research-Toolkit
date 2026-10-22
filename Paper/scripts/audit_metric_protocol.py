#!/usr/bin/env python3
"""Historical Step 4 snapshot diagnostics; never import or run research scripts.

This is NOT the current Table 2 eligibility source. Three Accuracy findings were
superseded on 2026-10-08; use audits/accuracy_protocol/20261008_three_configurations/
table2_accuracy_eligibility.csv and its source-hash-aware policy. In particular,
never apply the current SplaTAM external-evo definition to an old logged snapshot.
"""

import argparse
import ast
from collections import Counter, defaultdict
import csv
import hashlib
import io
import json
import math
from pathlib import Path
import re

WORKSPACE = Path('/home/yuan/SLAM/codex_review/benchmark_analysis')
INPUT_ROOT = Path('/home/yuan/SLAM/AirSim-Visual-SLAM-Research-Toolkit/Benchmark/experiment_data')
RENAMES = {'SGS-SLAM/summary_metrics_by_scene_rgbd.csv':
           'SGS-SLAM/summary_metrics_by_scene_semantic.csv'}
CORE = ('rmse', 'FPS', 'runtime', 'PeakReservedGB')
LEVELS = {'low', 'medium', 'high'}
SPEED = {'low': 2, 'medium': 4, 'high': 8}
ALTITUDE = {'low': 10, 'medium': 20, 'high': 30}


def js(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def read_csv(path):
    if path.is_symlink() or any(p.is_symlink() for p in path.parents):
        raise ValueError(f'Symlink is not allowed: {path}')
    with path.open('rb') as f:
        raw = f.read(10485761)
    if len(raw) > 10485760:
        raise ValueError(f'Content exceeds 10 MiB: {path}')
    reader = csv.reader(io.StringIO(raw.decode('utf-8-sig'), newline=''), strict=True)
    header = next(reader)
    if len(set(header)) != len(header):
        raise ValueError(f'Duplicate header: {path}')
    rows = []
    for fields in reader:
        if not fields or all(v == '' for v in fields):
            continue
        if len(fields) != len(header):
            raise ValueError(f'Ragged record at physical line {reader.line_num}: {path}')
        rows.append(dict(zip(header, fields)))
    return rows, header, hashlib.sha256(raw).hexdigest()


def parse_identifier(raw):
    """Observed suffix convention only. Never invent a run number."""
    match = re.fullmatch(r'(.+)_([0-9]+)', raw)
    if not match:
        return {'dataset_raw': raw, 'sequence_raw': None, 'run_id_raw': None,
                'parse_status': 'unresolved'}
    sequence, run_id = match.groups()
    result = {'dataset_raw': raw, 'sequence_raw': sequence, 'run_id_raw': run_id,
              'parse_status': 'terminal_integer_suffix', 'scene': None,
              'speed_mps': None, 'altitude_m': None}
    lower = sequence.lower()
    for prefixes, scene in [(('cross_building', 'building'), 'building'),
                            (('house',), 'houses'), (('pool',), 'pool'),
                            (('road',), 'road'), (('roundabout',), 'roundabout')]:
        if lower.startswith(prefixes):
            result['scene'] = scene
            break
    tokens = lower.rsplit('_', 2)
    if len(tokens) == 3 and tokens[-2] in LEVELS and tokens[-1] in LEVELS:
        result.update(speed_mps=SPEED[tokens[-2]], altitude_m=ALTITUDE[tokens[-1]])
    return result


def numeric_state(raw):
    # Preserve raw strings separately; stripping here is only a diagnostic view.
    value = raw.strip()
    if raw == '':
        return 'empty_string'
    if value == '':
        return 'whitespace_only'
    if value.upper() in {'NA', 'N/A', 'NONE', 'NULL'}:
        return 'text_missing_marker'
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 'unparseable'
    if math.isnan(number):
        return 'nan'
    if math.isinf(number):
        return 'positive_inf' if number > 0 else 'negative_inf'
    return 'finite_negative' if number < 0 else 'finite_zero' if number == 0 else 'finite_positive'


def diagnose(rows, header):
    ids = [row.get('dataset', '') for row in rows]
    parsed = [parse_identifier(raw) for raw in ids]
    runs = defaultdict(list)
    scenes = Counter()
    condition_records = 0
    unlabelled_sequences = set()
    unresolved = []
    for item in parsed:
        if item['sequence_raw'] is None:
            unresolved.append(item['dataset_raw'])
            continue
        runs[item['sequence_raw']].append(item['run_id_raw'])
        scenes[item['scene'] or 'unknown'] += 1
        if item['speed_mps'] is not None:
            condition_records += 1
        else:
            unlabelled_sequences.add(item['sequence_raw'])
    states, special = {}, {}
    for field in header:
        if field == 'dataset':
            continue
        states[field] = dict(sorted(Counter(numeric_state(row[field]) for row in rows).items()))
        special[field] = dict(sorted(Counter(
            row[field] for row in rows if not numeric_state(row[field]).startswith('finite_')
        ).items()))
    duplicates = {key: value for key, value in sorted(Counter(ids).items()) if value > 1}
    invalid_rmse_efficiency = {
        field: sum(not numeric_state(row.get('rmse', '')).startswith('finite_')
                   and numeric_state(row.get(field, '')).startswith('finite_') for row in rows)
        for field in ('FPS', 'runtime', 'PeakReservedGB')
    }
    return {
        'record_count': len(rows), 'identifier_field': 'dataset',
        'parsed_identifier_count': len(rows) - len(unresolved),
        'unresolved_identifier_count': len(unresolved),
        'sequence_count': len(runs),
        'records_per_sequence_distribution_json': js(Counter(map(len, runs.values()))),
        'run_id_set_distribution_json': js(Counter(','.join(sorted(set(v))) for v in runs.values())),
        'sequence_run_records_json': js({k: dict(sorted(Counter(v).items())) for k, v in sorted(runs.items())}),
        'duplicate_full_identifier_groups': len(duplicates),
        'duplicate_full_identifiers_json': js(duplicates),
        'raw_identifier_examples_json': js(ids[:3]),
        'unresolved_identifier_examples_json': js(unresolved[:3]),
        'scene_record_counts_json': js(scenes),
        'condition_labelled_records': condition_records,
        'condition_unlabelled_sequences_json': js(sorted(unlabelled_sequences)),
        'numeric_states_json': js(states), 'raw_nonfinite_or_missing_markers_json': js(special),
        'finite_efficiency_on_nonfinite_rmse_records_json': js(invalid_rmse_efficiency),
        'raw_columns_json': js(header),
        'unprovided_auxiliary_columns_json': js([k for k in ('max','min','mean','median','sse','std') if k not in header]),
    }


def source_info(path):
    """Read/parse AST, never eval, exec, import, or call the source."""
    raw = path.read_bytes()
    text = raw.decode('utf-8')
    tree = ast.parse(text, filename=str(path))
    assignments, lists, functions = {}, {}, {}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            functions[node.name] = [node.lineno, node.end_lineno]
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    key = target.id
                    if key in {'base','csv_path','out_csv','gt','est','runtime_path','gpu_path','ATE_RMSE_path'}:
                        assignments.setdefault(key, []).append({'line': node.lineno, 'expression': ast.unparse(node.value)})
                    if key == 'dataset_list' and isinstance(node.value, ast.List):
                        lists[key] = ast.literal_eval(node.value)
    return {'path': str(path), 'sha256': hashlib.sha256(raw).hexdigest(),
            'functions': functions, 'assignments': assignments, 'literal_lists': lists}


EFFICIENCY_EXTRACTION = {
    'DPVO': ('fps_total', 'wall_time', 'peak_reserved_GiB', 'direct; GiB stated by key; reserved-labelled'),
    'DROID-SLAM': ('fps (skips first log line)', 'runtime_sec', 'peak_gpu_reserved_mb', '/1024; MB-labelled reserved; base-10/base-2 producer unit unresolved'),
    'DSO': ('FPS', 'Runtime', 'PeakMemory', '/1024; memory kind and original unit unresolved'),
    'ElasticFusion': ('fps', 'total_time_sec', 'peak_rss_mb', '/1024; RSS-labelled process memory, not interchangeable with GPU reserved'),
    'MASt3R-SLAM': ('FPS_actual', 'Elapsed_Time_sec', 'GPU_DevicePeakUsed', 'penultimate token, no conversion; device-used label, exact unit unresolved'),
    'MongGS': ('Total_FPS', 'Total_time', 'Peak_reserved_by_process', 'direct; process-reserved label, exact unit unresolved'),
    'ORB-SLAM2': ('fps', 'runtime', 'memory', '/1024; memory kind and original unit unresolved'),
    'ORB-SLAM3': ('FPS_wall_clock', 'TotalWallClockTime_s', 'Peak reserved (MB)', '/1024; current source points to Photo-SLAM; actual CSV producer unresolved'),
    'Photo-slam': ('FPS', 'total_runtime (s)', 'memory_vpeak_MB', '/1024; vpeak label; current source points to ORB-SLAM2; actual CSV producer unresolved'),
    'SGS-SLAM': ('FPS', 'Runtime', 'PeakReservedGB', 'direct; GB/reserved declared by key, producer unverified'),
    'SLAM3R': ('fps', 'runtime_sec', 'gpu_peak_reserved_mb', '/1024; GPU-reserved label, producer unit unresolved'),
    'SVO': ('fps', 'runtime_sec', 'peak_mem_mb', '/1024; memory kind and original unit unresolved'),
    'SplaTAM': ('FPS', 'SLAM wall time', 'Peak GPU reserved', '/1024; GPU-reserved label, original unit inferred by variable only'),
    'TartanVO': ('fps', 'total_time_sec', 'peak_gpu_mem_reserved', 'penultimate token, no conversion; exact unit unresolved'),
    'VGGT-LONG': ('fps', 'total_time_sec', 'peak_gpu_gb', 'direct; GPU/GB label, reserved vs allocated vs device-used unresolved'),
    'VGGT-SLAM': ('FPS', 'Runtime', 'Peak device used', 'penultimate token, no conversion; device-used, not established as reserved'),
    'hierslam': ('FPS', 'Total Runtime', 'GPU Peak Memory', '/1024; GPU-peak label, reserved vs allocated unresolved'),
}


def protocol(snapshot):
    rel = snapshot['source_relative_path']
    method, name = snapshot['method_directory'], Path(rel).name
    mode = {'mono_metrics.csv': 'mono', 'rgbd_metrics.csv': 'rgbd',
            'semantic_metrics.csv': 'semantic', 'calib_metrics.csv': 'mono_calib',
            'nocalib_metrics.csv': 'mono_nocalib'}[name]
    scope, semantic = snapshot['evaluation_scope'], snapshot['semantic_usage']
    modality = snapshot['modality']
    evidence = 'user_confirmed naming; data_observed identifiers; code_verified current routing'
    confirmed_repeats, plan = 'unknown', 'unknown'
    if method == 'hierslam':
        if 'rgbd_whole_trajectory/' in rel:
            mode, confirmed_repeats, plan = 'rgbd_whole', 'two experiments', 'third experiment planned, not yet run'
        else:
            mode += '_500'
            confirmed_repeats, plan = 'one retained experiment; historical run count unknown', 'additional repetitions planned'
    elif method == 'SplaTAM':
        confirmed_repeats, plan = 'two experiments', 'additional repetitions planned'
    if method == 'SGS-SLAM':
        semantic = 'yes (user_confirmed); depth usage not excluded'
    if method == 'MASt3R-SLAM':
        modality = 'unknown upstream inputs; code_verified aggregation label mono_calib/mono_nocalib'
    direct_log = method in {'MongGS','SGS-SLAM','SplaTAM'}
    if direct_log:
        extraction = {'MongGS':'RMSE_ATE from metric.txt; underlying evaluator unresolved',
                      'SGS-SLAM':'ATE_RMSE_m from metrics.txt; underlying evaluator unresolved',
                      'SplaTAM':'eval/ATE.txt last token / 100; cm-to-m convention in current exporter'}[method]
        alignment = 'unknown: active code extracts logged ATE; unused/commented evo function is not evidence'
    else:
        extraction = 'current exporter calls evo APE translation_part get_all_statistics; historical CSV provenance unresolved'
        alignment = 'current code: associate max_diff=0.00; align correct_scale=True, correct_only_scale=False (Sim(3)); historical invocation unknown'
    units = 'position unit inherited from trajectory; report labels m, upstream unit not verified'
    if method == 'SGS-SLAM': units = 'm declared by log key ATE_RMSE_m; producer unverified'
    if method == 'SplaTAM': units = 'm after /100 of assumed cm; producer unverified'
    if method == 'MongGS': units = 'unknown at extractor; RMSE_ATE has no explicit unit'
    if direct_log:
        historical = 'historical_step04_snapshot_only; superseded by audits/accuracy_protocol/20261008_three_configurations/report.md: '
        extraction = historical + extraction
        alignment = historical + alignment
        units = historical + units
    fps_key, runtime_key, memory_key, memory_rule = EFFICIENCY_EXTRACTION[method]
    efficiency = {'evidence_status':'code_verified extraction; unresolved underlying measurement and historical invocation',
                  'fps_log_key':fps_key, 'fps_unit_status':'FPS label; frame numerator and time interval unresolved',
                  'runtime_log_key':runtime_key, 'runtime_unit_status':'s; user_confirmed 2026-10-08 across all configurations; missing suffix is metadata only; timing scope remains a separate issue',
                  'memory_log_key':memory_key, 'memory_conversion_and_kind':memory_rule,
                  'completeness_gate':'none in this extraction layer; upstream partial-run handling unresolved'}
    if method=='MASt3R-SLAM':
        evidence='code_verified calib/nocalib-to-mono-label routing; data_observed files; upstream inputs unresolved'
    issues = {
        'DPVO':'Current results.py writes rgbd_metrics.csv although retained input is mono; history unresolved.',
        'DSO':'43 observed sequences match current active export list; why five names were commented is unresolved; do not infer failures.',
        'MASt3R-SLAM':'Only nocalib export/log-copy route is visible; calib origin and exact sensor/calibration model unresolved; scene output name conflicts.',
        'ORB-SLAM3':'Current exporter base points to Photo-SLAM; do not assign its logging protocol to historical CSV as proven.',
        'Photo-slam':'Current exporter base points to ORB-SLAM2, mono trajectory branch but rgbd output; historical producer unresolved.',
        'SGS-SLAM':'All experiments semantic is user_confirmed; depth usage unresolved. Scene rename completed; results.py external rgbd output unchanged and not followed.',
        'SplaTAM':'Two runs user_confirmed and observed; external ATE evaluation producer/alignment unresolved; extra repetitions only planned.',
        'VGGT-SLAM':'45 PeakReservedGB cells contain tuple text (NA, NA); retained verbatim, not numeric or automatically zero.',
        'hierslam':'Outer 500-frame configurations retain run 4 only; whole trajectory retains runs 1,2. Current outer exporter no-semantic base/semantic output conflicts; whole-trajectory historical exporter unknown.',
    }.get(method,'Current exporter/default scene output may use rgbd names despite other retained configuration; see path evidence and report. Historical invocation unresolved.')
    return dict(configuration=mode, modality=modality, semantic_usage=semantic,
                method_specific_issues=issues,
                efficiency_protocol_json=js(efficiency),
                evaluation_scope=scope, configuration_evidence=evidence,
                user_confirmed_repetitions=confirmed_repeats, future_repetition_plan=plan,
                record_grain='one exported run-labelled record; no repeat averaging in current exporter; historical provenance unresolved',
                grain_evidence='data_observed + code_verified; user_confirmed for Hier-SLAM and SplaTAM',
                rmse_extraction=extraction, rmse_unit_status=units, alignment_status=alignment,
                trajectory_completion_status='unknown: numeric RMSE does not prove complete trajectory',
                std_levels='row std: within-trajectory distribution if provided; scene/local condition: pooled records ddof=0; shared condition: pooled records ddof=1; per-sequence repeat std is separate',
                scene_aggregation_rule='numeric conversion of RMSE gates all metrics; denominator all stored rows in group; metric-specific missing values removed; pooled overall; population std; legacy singleton=0',
                shared_condition_rule='two level tokens; finite RMSE numerator / stored labelled rows; each efficiency metric uses its own finite records without RMSE gate; sample std; legacy singleton=0; no overall',
                missingness_recommendation='retain raw marker; diagnose finite/negative/zero separately; absent records not failures; singleton repeat std undefined; no uniform rule silently substituted',
                next_stage_recommendation='DPVO: ready for isolated CSV trial and legacy-summary comparison' if method=='DPVO' else 'retain separately; not yet a cross-method performance comparison input')


def self_test():
    x = parse_identifier('cross_building_low_high_4')
    assert (x['sequence_raw'],x['run_id_raw'],x['speed_mps'],x['altitude_m']) == ('cross_building_low_high','4',2,30)
    assert parse_identifier('roundabout_square25fps_2')['sequence_raw']=='roundabout_square25fps'
    assert parse_identifier('building25fps_1')['altitude_m'] is None
    assert parse_identifier('houses_low_high')['run_id_raw'] is None
    assert parse_identifier('road2_low_high_run_1')['altitude_m'] is None
    assert [numeric_state(x) for x in ['', 'NA','N/A','None','nan','inf','-inf','-2','0','3','bad']] == [
        'empty_string','text_missing_marker','text_missing_marker','text_missing_marker','nan',
        'positive_inf','negative_inf','finite_negative','finite_zero','finite_positive','unparseable']
    rows=[{'dataset':'cross_building_low_high_4','rmse':'0','FPS':'NA'},
          {'dataset':'cross_building_low_high_4','rmse':'NA','FPS':'2'},
          {'dataset':'road25fps','rmse':'nan','FPS':'3'}]
    d=diagnose(rows,['dataset','rmse','FPS'])
    assert d['record_count']==3 and d['duplicate_full_identifier_groups']==1
    assert d['unresolved_identifier_count']==1 and d['sequence_count']==1
    assert json.loads(d['finite_efficiency_on_nonfinite_rmse_records_json'])['FPS']==2
    print('PASS: in-memory identifier, raw numeric states, duplicates, missing suffix and count diagnostics')


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--self-test', action='store_true')
    ap.add_argument('--input-root', type=Path)
    ap.add_argument('--inventory', type=Path)
    ap.add_argument('--output-dir', type=Path)
    args=ap.parse_args()
    if args.self_test:
        self_test(); return
    if args.input_root != INPUT_ROOT or args.inventory != WORKSPACE/'reports/03_input_inventory.csv':
        ap.error('Use the fixed source root and preserved step-3 inventory')
    if (args.output_dir is None or not args.output_dir.is_dir()
            or not args.output_dir.resolve().is_relative_to(WORKSPACE.resolve())):
        ap.error('Output must be inside benchmark_analysis')
    for path in [args.input_root, args.inventory, args.output_dir]:
        if any(p.is_symlink() for p in [path,*path.parents]):
            ap.error('Symlink paths are not allowed')
    output=args.output_dir/'04_input_protocol_matrix.csv'
    if output.exists() or output.is_symlink():
        ap.error('Review existing matrix first; this script will not overwrite it')
    inventory, _, _=read_csv(args.inventory)
    snapshots=[r for r in inventory if r['file_role']=='run_metrics_candidate']
    if len(snapshots)!=24:
        ap.error('The reviewed snapshot should contain 24 candidate sources; inspect changes')
    # Directly indexed files only: no filesystem discovery or recursive scan.
    current={}
    for item in inventory:
        rel=item['source_relative_path']; actual=RENAMES.get(rel,rel)
        rows,header,digest=read_csv(args.input_root/actual)
        current[rel]={'current_path':actual,'rows':rows,'header':header,'sha256':digest,
                      'snapshot_sha256':item['sha256'], 'matches_step03':digest==item['sha256']}
    result=[]
    shared=[source_info(args.input_root.parent/'statistics'/f'summary_metrics_by_{axis}.py') for axis in ['altitude','speed']]
    for snap in snapshots:
        rel=snap['source_relative_path']; obj=current[rel]; method=snap['method_directory']
        entry={'step03_source_relative_path':rel,'source_relative_path':obj['current_path'],
               'source_absolute_path':str(args.input_root/obj['current_path']),
               'sha256':obj['sha256'],'step03_sha256':snap['sha256'],
               'matches_step03_bytes':obj['matches_step03'],'method_directory':method}
        entry.update(protocol(snap)); entry.update(diagnose(obj['rows'],obj['header']))
        export=source_info(args.input_root/method/'results.py')
        scene=source_info(args.input_root/method/'analyze_by_dataset.py')
        sequences=set(json.loads(entry['sequence_run_records_json']))
        configured=set(export['literal_lists'].get('dataset_list',[]))
        entry['current_export_list_relation_json']=js({
            'configured_sequence_count':len(configured),
            'configured_but_not_in_csv':sorted(configured-sequences),
            'in_csv_but_not_configured':sorted(sequences-configured),
            'evidence':'code_verified + data_observed; not a historical experiment manifest'})
        entry['export_code_evidence_json']=js(export)
        aggregators=[scene,*shared]
        local=args.input_root/method/'analyze_by_speed_height.py'
        if local.is_file(): aggregators.append(source_info(local))
        entry['aggregation_code_evidence_json']=js(aggregators)
        summary_refs=[]
        for item in inventory:
            if item['method_directory']!=method or item['file_role']!='aggregate_summary': continue
            original=item['source_relative_path']; data=current[original]; name=Path(original).name
            if 'by_scene_' in name:
                expected=Path(rel).with_name('summary_metrics_by_scene_'+Path(rel).name.removesuffix('_metrics.csv')+'.csv').as_posix()
                if data['current_path']!=expected: continue
            labels=[r[data['header'][0]] for r in data['rows']]
            if 'by_altitude' in name or 'by_speed' in name:
                labels=[s for s in labels if s.startswith(method+'_') and s.endswith('_'+entry['configuration'])]
            summary_refs.append({'step03_path':original,'current_path':data['current_path'],
                                 'sha256':data['sha256'],'matches_step03_bytes':data['matches_step03'],
                                 'group_column':data['header'][0],'labels':labels})
        entry['related_summaries_json']=js(summary_refs)
        entry['unresolved']=('Historical export invocation/version; upstream units and efficiency measurement definitions; '
                             'scope except user-confirmed Hier-SLAM; missing record causes; original completeness criterion. '
                             'See report for method-specific path/configuration conflicts; no source repaired beyond SGS rename.')
        result.append(entry)
    with output.open('x',encoding='utf-8',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(result[0]));writer.writeheader();writer.writerows(result)
    print(js({'output':str(output),'candidate_sources':len(result),'snapshot_byte_changes':[
        {'snapshot_path':p,'current_path':v['current_path']} for p,v in current.items() if not v['matches_step03']]}))
    for r in result:
        print(js({k:r[k] for k in ['source_relative_path','record_count','sequence_count',
                                 'records_per_sequence_distribution_json','run_id_set_distribution_json',
                                 'duplicate_full_identifier_groups','unresolved_identifier_count',
                                 'condition_labelled_records','numeric_states_json',
                                 'finite_efficiency_on_nonfinite_rmse_records_json','current_export_list_relation_json']}))


if __name__=='__main__':
    main()
