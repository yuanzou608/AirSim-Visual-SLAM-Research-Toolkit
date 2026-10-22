#!/usr/bin/env python3
"""Accept a frozen input version and schedule existing benchmark entry points.

All statistical work remains in the existing stage scripts. Source experiments
are read only. An explicit update directory and operation are required.
"""
import argparse
import ast
from collections import Counter, defaultdict
import csv
import datetime
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

from version_support import CANONICAL as W, digest, local, source_read_path
from audit_metric_protocol import diagnose, numeric_state, parse_identifier

SOURCE = Path('/home/yuan/SLAM/AirSim-Visual-SLAM-Research-Toolkit/Benchmark/experiment_data')
PYTHON = '/home/yuan/anaconda3/bin/python3'
CHANGED = {'hierslam::rgbd_500', 'hierslam::semantic_500', 'hierslam::rgbd_whole', 'SplaTAM::rgbd'}
RENAMES = {'hierslam::rgbd_500': 'hierslam/rgbd_metrics_500frames.csv',
           'hierslam::semantic_500': 'hierslam/semantic_metrics_500frames.csv'}
ENTRIES = {'06':'build_analysis_dataset.py', '07':'explore_benchmark.py',
           '08':'analyze_altitude_speed.py', '09':'check_benchmark_robustness.py',
           '10':'analyze_method_relationships.py', '11':'build_paper_materials.py',
           '11B':'review_all_configurations.py', '11C':'build_cross_configuration_overview.py'}
SPECS = {'07':'reports/07_exploration_spec.json', '08':'reports/08_condition_analysis_spec.json',
         '09':'reports/09_robustness_spec.json', '10':'reports/10_relationship_spec.json',
         '11':'paper/11_draft/artifact_manifest.json', '11B':'reports/11b_artifact_manifest.json',
         '11C':'reports/11c_artifact_manifest.json'}
csv.field_size_limit(40_000_000)


def is_splatam_policy(policy):
    return bool(policy and policy.get('reason') == 'audited_splatam_accuracy_protocol_migration')


def is_sgs_policy(policy):
    return bool(policy and policy.get('reason') == 'audited_sgs_new_run_batch_protocol_refresh')


def configuration_delta_name(policy):
    # The SGS update also carries a separate, full per-run input_delta.csv.
    return 'configuration_input_delta.csv' if is_sgs_policy(policy) else 'input_delta.csv'


def load_update_policy(u):
    """Optional, narrowly authorized single-source correction; legacy updates stay unchanged."""
    path = u/'update_policy.json'
    if not path.exists():
        return None
    if path.is_symlink() or not path.is_file():
        raise ValueError('Update policy must be a regular in-project file')
    policy = json.loads(path.read_text())
    restored = {'cross_building_medium_low', 'road2_low_high', 'road2_low_low',
                'roundabout2_low_low', 'roundabout2_low_medium'}
    dso = not (policy.get('authorized_changed_configurations') != ['DSO::mono'] or
            policy.get('reason') != 'user_confirmed_export_omission_corrected' or
            len(policy.get('restored_sequences', [])) != len(restored) or
            set(policy['restored_sequences']) != restored)
    splatam = (is_splatam_policy(policy) and
        u.name == '20261013T201849+0800_splatam_accuracy' and
        policy.get('authorized_changed_configurations') == ['SplaTAM::rgbd'] and
        policy.get('previous_version') == '20261007T173229+0800_dso_export_fix' and
        policy.get('expected_old_sha256') == '6eeeb8536a6d5820e432fa2f4fef16b99faa8fd48c63173702fd4017716679b2' and
        policy.get('expected_new_sha256') == '337a4d462b9d238681be52284017b3e3ef445130303911de1cc1601a6d9c8f7b' and
        policy.get('allowed_accuracy_fields') == ['rmse','max','min','mean','median','sse','std'] and
        policy.get('preserve_sr_directory') is True and
        policy.get('preserve_other_configuration_frozen_sources') is True)
    sgs = (is_sgs_policy(policy) and
        u.name == '20261018T010047+0800_sgs_refresh_stage1' and
        policy.get('authorized_changed_configurations') == ['SGS-SLAM::semantic'] and
        policy.get('previous_version') == '20261013T201849+0800_splatam_accuracy' and
        policy.get('expected_old_sha256') == '6498bd97b30c9e36a45a09a5e04808b2f1332f5af6570106b45389fa536ec198' and
        policy.get('expected_new_sha256') == '1958020f0083595119c105ab76c5895be4560cdbd14b7cb56f6bbdcea5e7f6ac' and
        policy.get('old_run_ids') == ['1','2','3'] and policy.get('new_run_ids') == ['4','5','6'] and
        policy.get('physical_run_relationship') == 'replacement_new_batch_not_paired' and
        policy.get('preserve_historical_sr_components') is True and
        policy.get('preserve_other_configuration_frozen_sources') is True and
        policy.get('preserve_manuscripts') is True)
    if not (dso or splatam or sgs):
        raise ValueError('Policy differs from the explicitly authorized source correction')
    rebuild = u/'rebuild_manifest.json'
    if rebuild.exists():
        binding = json.loads(rebuild.read_text()).get('update_policy')
        if not binding or binding != {'path': path.name, 'sha256': digest(path)}:
            raise ValueError('Update policy differs from the accepted version')
    return policy


def check_splatam_runs(policy, old_rows, old_header, new_rows, new_header, old_sha, new_sha):
    """Permit only the already audited accuracy replacement on identical runs."""
    if old_sha != policy['expected_old_sha256'] or new_sha != policy['expected_new_sha256']:
        raise ValueError('SplaTAM source bytes differ from the reviewed old/new versions')
    allowed = set(policy['allowed_accuracy_fields'])
    if (len(old_rows) != 144 or len(new_rows) != 144 or not set(old_header) <= set(new_header)
            or (set(new_header)-set(old_header))-allowed):
        raise ValueError('SplaTAM header/count differs from the reviewed accuracy replacement')
    seen = set()
    for old, new in zip(old_rows, new_rows):
        if old['raw_dataset'] != new['dataset'] or new['dataset'] in seen:
            raise ValueError('SplaTAM run identifiers/order changed or duplicated')
        seen.add(new['dataset'])
        for field in old_header:
            if field not in allowed and old['raw_'+field] != new[field]:
                raise ValueError('Nonaccuracy source field changed: '+field)
        if numeric_state(old['raw_rmse']).startswith('finite_') != numeric_state(new['rmse']).startswith('finite_'):
            raise ValueError('SplaTAM RMSE finite mask changed')


def check_sgs_runs(policy, old_rows, old_header, new_rows, new_header, old_sha, new_sha):
    """Validate the reviewed replacement batch; never pair old and new physical runs."""
    if old_sha != policy['expected_old_sha256'] or new_sha != policy['expected_new_sha256']:
        raise ValueError('SGS source bytes differ from the reviewed old/new versions')
    if (len(old_rows) != 144 or len(new_rows) != 144 or
            set(new_header) != {'dataset','FPS','runtime','PeakReservedGB','max','min','mean','median','rmse','sse','std'} or
            not set(old_header) <= set(new_header)):
        raise ValueError('SGS header/count differs from the reviewed new batch')
    def members(rows, field):
        groups = defaultdict(list)
        for row in rows:
            parsed = parse_identifier(row[field])
            sequence, run = parsed.get('sequence_raw'), parsed.get('run_id_raw')
            if sequence is None or run is None or run in groups[sequence]:
                raise ValueError('Unparseable or duplicate SGS run: '+repr(row[field]))
            groups[sequence].append(run)
        return groups
    old, new = members(old_rows, 'raw_dataset'), members(new_rows, 'dataset')
    if (len(old) != 48 or set(old) != set(new) or
            any(sorted(runs) != policy['old_run_ids'] for runs in old.values()) or
            any(sorted(runs) != policy['new_run_ids'] for runs in new.values()) or
            sum(numeric_state(r['rmse']).startswith('finite_') for r in new_rows) != 121):
        raise ValueError('SGS sequence/run membership or finite count differs from the reviewed batch')


def accept_splatam_editorial_ownership(u, staging, backup):
    """Bind five reviewed post-publication text amendments to exact backed-up bytes."""
    allowed = {
        '11': {'reports/11_paper_synthesis.md', 'paper/11_draft/results_discussion.md',
               'paper/11_draft/results_discussion.tex'},
        '11B': {'reports/11b_all_configuration_review.md'},
        '11C': {'reports/11c_cross_configuration_review.md'},
    }
    backed_up = {e['path']:e for e in backup_entries(u)}
    conflicts = []
    for stage, paths in allowed.items():
        manifest = json.loads(local(staging,SPECS[stage]).read_text())
        for rel, entry in manifest['outputs'].items():
            current = digest(local(staging,rel))
            if current == entry['sha256']:
                continue
            if (rel not in paths or digest(local(W,rel)) != current or
                    digest(local(backup,rel)) != current or backed_up[rel]['sha256'] != current):
                raise ValueError('Unreviewed current-output conflict; preserve original: '+rel)
            row = {'stage':stage,'path':rel,'manifest_sha':entry['sha256'],'current_sha':current,
                   'status':'reviewed_current_text_bound_to_exact_preupdate_backup',
                   'backup_path':backed_up[rel]['backup_path'],
                   'backup_manifest_sha256':digest(u/'backup_manifest.json'),
                   'reason':'post-publication Accuracy/runtime wording already reviewed; original text retained in backup',
                   'action':'staging ownership only; original manifests and backups unchanged'}
            conflicts.append(row)
            entry.update(sha256=current,bytes=local(staging,rel).stat().st_size)
            manifest.setdefault('inherited_editorial_amendments',[]).append(row)
        write_json(local(staging,SPECS[stage]),manifest)
    path=u/'preflight_conflicts.json'
    if path.exists() and json.loads(path.read_text()) != conflicts:
        raise ValueError('Existing editorial conflict record differs; preserve it')
    write_json(path,conflicts)
    return conflicts


def check_restored_runs(policy, old_rows, old_header, new_rows, new_header):
    """Validate actual logical members and raw fields, never synthesize target counts."""
    def keyed(rows, standardized=False):
        found = {}
        for row in rows:
            raw = {k:row['raw_'+k] for k in old_header} if standardized else row
            ident = parse_identifier(raw['dataset'])
            key = ident['sequence_raw'], ident['run_id_raw']
            if None in key or key in found:
                raise ValueError('Unparseable or duplicate DSO logical run: '+repr(key))
            found[key] = raw
        return found
    old, new = keyed(old_rows, True), keyed(new_rows)
    expected = {(s, run) for s in policy['restored_sequences'] for run in ('1','2','3')}
    if len(old) != 129 or old_header != new_header:
        raise ValueError('DSO historical record count/header differs from the reviewed input')
    removed = sorted(set(old)-set(new))
    changed = sorted(k for k in set(old)&set(new) if old[k] != new[k])
    added = set(new)-set(old)
    if removed or changed or added != expected:
        raise ValueError('DSO correction conflicts with authorization: '+js({
            'removed':removed, 'changed_raw_records':changed,
            'unexpected_additions':sorted(added-expected), 'missing_restorations':sorted(expected-added)}))


def js(x):
    return json.dumps(x, ensure_ascii=False, sort_keys=True, allow_nan=False)


def read_csv(path):
    with Path(path).open(newline='', encoding='utf-8-sig') as f:
        return list(csv.DictReader(f))


def write_csv(path, rows, fields=None):
    if not rows and not fields:
        raise ValueError('Empty audit table: '+str(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fields or list(rows[0]), lineterminator='\n')
        writer.writeheader(); writer.writerows(rows)


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')


def backup_entries(u):
    info = json.loads((u/'backup_manifest.json').read_text())
    for e in info['files']:
        if digest(u/e['backup_path']) != e['sha256']:
            raise ValueError('Backup bytes changed: '+e['path'])
    return info['files']


def outputs_for(stage, backup):
    if stage == '06':
        return ['derived_data/06_standardized/run_records.csv', 'derived_data/06_standardized/source_manifest.csv',
                'derived_data/06_standardized/schema.json', 'reports/06_sequence_coverage.csv', 'reports/06_data_quality.md']
    info = json.loads((backup/SPECS[stage]).read_text())
    paths = list(info['outputs'])
    if stage in {'11','11B','11C'}:
        paths.append(SPECS[stage])
    return sorted(set(paths))


def declared_inputs(script):
    tree = ast.parse(script.read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'INPUT_HASHES' for t in node.targets) and isinstance(node.value, ast.Dict):
            return list(ast.literal_eval(node.value))
    return None


def inherit_editorial_amendments(staging, backup, conflicts):
    """Register proven prior editorial changes in staging ownership only."""
    manifests = {}
    for item in conflicts:
        if item.get('status') != 'matches_authorized_prior_claim_review_no_unreviewed_manual_edit':
            raise ValueError('Unreviewed current-output conflict; preserve original: '+item['path'])
        stage = item['stage']
        if stage not in {'11','11C'}:
            raise ValueError('Unexpected stage in inherited editorial amendment')
        evidence, fragment = item['evidence'].split('#',1)
        if fragment != 'modified_current_files':
            raise ValueError('Unrecognized editorial verification section')
        evidence_path = local(W,evidence)
        proof = json.loads(evidence_path.read_text())['modified_current_files']
        matches = [r for r in proof if r['path']==item['path'] and
                   r['before_sha256']==item['manifest_sha'] and r['after_sha256']==item['current_sha']]
        if len(matches) != 1:
            raise ValueError('Prior editorial before/after proof does not bind conflict: '+item['path'])
        before_path, current_path = local(backup,item['path']), local(staging,item['path'])
        if digest(before_path) != item['current_sha'] or digest(current_path) != item['current_sha']:
            raise ValueError('Backed-up editorial output differs from verified amendment: '+item['path'])
        manifest = manifests.setdefault(stage,json.loads(local(staging,SPECS[stage]).read_text()))
        entry = manifest['outputs'][item['path']]
        if entry['sha256'] != item['manifest_sha']:
            raise ValueError('Staged ownership does not match pre-amendment hash: '+item['path'])
        entry.update(sha256=item['current_sha'],bytes=current_path.stat().st_size)
        manifest.setdefault('inherited_editorial_amendments',[]).append({**item,
            'evidence_file_sha256':digest(evidence_path),
            'action':'staging ownership registered; historical and backup manifests preserved'})
    for stage, manifest in manifests.items():
        write_json(local(staging,SPECS[stage]),manifest)


def prepare(u):
    if (u/'staging').exists() or (u/'input_delta.csv').exists() or (u/'configuration_input_delta.csv').exists():
        raise ValueError('Prepared update already exists; use --build/--verify, not repeated acceptance')
    entries = backup_entries(u); backup=u/'backup'
    policy = load_update_policy(u)
    splatam = is_splatam_policy(policy)
    sgs = is_sgs_policy(policy)
    frozen_prior = splatam or sgs
    if frozen_prior:
        prior_info = json.loads((backup/'reports/current_input_manifest.json').read_text())
        if prior_info['current_version'] != policy['previous_version']:
            raise ValueError('Single-source update must inherit the reviewed preceding version')
        prior_sources = local(W,'updates/'+policy['previous_version']+'/current_sources')
    changed = set(policy['authorized_changed_configurations']) if policy else CHANGED
    previous = ({r['method_directory']+'::'+r['configuration']:r
                 for r in read_csv(backup/'reports/current_input_manifest.csv')} if policy else {})
    old = {m['configuration_id']:m for m in read_csv(backup/'derived_data/06_standardized/source_manifest.csv')}
    matrix = {r['method_directory']+'::'+r['configuration']:r for r in read_csv(backup/'reports/04_input_protocol_matrix.csv')}
    old_runs=defaultdict(list)
    for r in read_csv(backup/'derived_data/06_standardized/run_records.csv'):
        old_runs[r['configuration_id']].append(r)
    snapshots=[]; deltas=[]; metadata=[]; total=labelled=0
    for c,m in old.items():
        rel=m['source_relative_path'] if policy else RENAMES.get(c,m['source_relative_path']); p=SOURCE/rel
        read_path = local(prior_sources,rel) if frozen_prior and c not in changed else p
        if not read_path.is_file() or read_path.is_symlink():raise ValueError('Missing or linked selected input: '+rel)
        raw=read_path.read_bytes(); sha=hashlib.sha256(raw).hexdigest()
        reader=csv.DictReader(io.StringIO(raw.decode('utf-8-sig'), newline=''), strict=True)
        header=reader.fieldnames; rows=list(reader)
        if not header or len(set(header))!=len(header) or any(None in r or any(v is None for v in r.values()) for r in rows):raise ValueError('Invalid CSV structure: '+rel)
        diag=diagnose(rows,header)
        if c not in changed and sha!=m['source_sha256']:raise ValueError('Unexplained source change: '+c)
        if re.search(r'\d+\s*frames',Path(rel).name,re.I) and '500frames' not in Path(rel).name:raise ValueError('Unconfirmed frame limit: '+rel)
        old_path=SOURCE/m['source_relative_path']
        if rel!=m['source_relative_path'] and old_path.exists():
            if digest(old_path)!=m['source_sha256']:raise ValueError('Ambiguous old/new source coexistence: '+c)
            coexist='old name matches historical frozen bytes; excluded'
        else:coexist='old name absent as expected' if rel!=m['source_relative_path'] else 'not renamed'
        snapshot=dict(previous[c] if policy else matrix[c])
        snapshot.update({k:str(v) if not isinstance(v,str) else v for k,v in diag.items()})
        if policy:
            if previous[c]['sha256'] != m['source_sha256'] or previous[c]['source_relative_path'] != rel:
                raise ValueError('Current input manifest disagrees with the backed-up standardized source: '+c)
            scope, modality = snapshot['evaluation_scope'], snapshot['modality']
            snapshot.update(source_absolute_path=str(p),sha256=sha,input_version=u.name)
            if frozen_prior:
                snapshot['matches_step03_bytes']=str(sha == snapshot['step03_sha256'])
            if c in changed:
                if sgs:
                    check_sgs_runs(policy,old_runs[c],json.loads(m['raw_header_json']),rows,header,m['source_sha256'],sha)
                    evidence=('updates/'+u.name+'/audit/sgs_accuracy_protocol.md; updates/'+u.name+
                        '/audit/sgs_accuracy_row_evidence.csv; updates/'+u.name+'/update_request.md')
                    snapshot.update(
                        rmse_extraction='external evo translation-part APE get_all_statistics()[rmse]; C2W camera-center translations; full per-frame exported poses',
                        rmse_unit_status='m; current SGS C2W GT/estimate export and saved APE statistics reviewed for this frozen source SHA',
                        alignment_status='Sim(3); align(correct_scale=True, correct_only_scale=False); association max_diff=0.00; frame_index correspondence',
                        current_metadata_evidence=snapshot['current_metadata_evidence']+'; '+evidence,
                        user_confirmed_repetitions='3',
                        future_repetition_plan='current new batch retained as run IDs 4/5/6; no further run authorized',
                        efficiency_protocol_json=js({'reported_fps':'current new-batch source only; no runtime-derived FPS',
                            'runtime_unit':'s; user_confirmed', 'memory_source':'current new-batch PeakReservedGB; independent typed-GiB component is versioned separately',
                            'fps_unit_status':'reported FPS; same new-run metrics, no inference from runtime',
                            'runtime_unit_status':'seconds (s); includes mapping/final evaluation and parameter saving, excludes later TUM export; not pure tracking latency',
                            'memory_conversion_and_kind':'GPU_RESERVED GiB; torch.cuda.max_memory_reserved()/1024**3; new run metrics only',
                            'evidence_status':'current producer code and all available new-run metric fields agree; historical execution commit not independently signed',
                            'completeness_gate':'no Accuracy or SR filtering of efficiency samples; missing metrics retained as missing',
                            'same_run_policy':'do not fill any missing field from the old run 1/2/3 batch', 'evidence':evidence}),
                        unresolved='Repeated-execution independence and efficiency timing remain limited. New run IDs 4/5/6 replace old 1/2/3 without physical-run pairing; historical SGS native SR and memory are not inherited. SGS native completion component must be bound separately; finite APE is not SR.',
                        method_specific_issues='New RGB+Depth+Semantic whole-trajectory batch; external-evo C2W Sim(3) translation APE RMSE(m) replaces historical W2C rigid-aligned native mean. Batch and metric protocol both changed: no percentage accuracy-improvement attribution; 24 configurations retained, manuscript synchronization is a later authorized stage.')
                elif splatam:
                    check_splatam_runs(policy,old_runs[c],json.loads(m['raw_header_json']),rows,header,m['source_sha256'],sha)
                    snapshot.update(
                        rmse_extraction='external evo translation-part APE get_all_statistics()[rmse]',
                        rmse_unit_status='m; user_confirmed and code_verified; current source SHA bound to 20261008 accuracy audit',
                        alignment_status='Sim(3); align(correct_scale=True, correct_only_scale=False); max_diff=0.00',
                        current_metadata_evidence=snapshot['current_metadata_evidence']+'; audits/accuracy_protocol/20261008_three_configurations/report.md; updates/'+u.name+'/update_request.md',
                        unresolved='Repeated-execution independence and efficiency timing remain limited. Current SplaTAM accuracy provenance is closed by the source-bound 20261008 audit. Finite RMSE is not SR; SR labels remain frozen and are not recomputed.',
                        method_specific_issues='Current external-evo accuracy replaces the historical native logged-ATE chain; frozen SR, efficiency raw fields, configuration identity and run set unchanged.')
                else:
                    check_restored_runs(policy,old_runs[c],json.loads(m['raw_header_json']),rows,header)
                    snapshot['current_metadata_evidence'] += '; user_confirmed_export_omission_corrected: updates/'+u.name+'/update_request.md'
                    snapshot['unresolved'] = ('Historical units/alignment/export invocation; efficiency timing and memory measurement; '
                        'independent repeats. The five DSO source omissions are author-confirmed export omissions, now restored. '
                        'SR v3 remains frozen to its prior run set; new metric members have not been assigned SR labels.')
        else:
            scope='500_frames' if '500frames' in Path(rel).name else 'whole_trajectory'
            snapshot.update(source_relative_path=rel,source_absolute_path=str(p),sha256=sha,evaluation_scope=scope,semantic_usage='yes' if c in {'SGS-SLAM::semantic','hierslam::semantic_500'} else 'no')
            modality='mono' if c.startswith('MASt3R-SLAM::') else 'RGB + Depth' if snapshot['semantic_usage']=='yes' else m['modality_declared']
            snapshot.update(modality=modality,historical_source_relative_path=m['source_relative_path'],historical_source_sha256=m['source_sha256'],historical_metadata_json=js(m),current_metadata_evidence='user_confirmed: controlled update request c667ef41; prior semantic and MASt3R confirmations retained',input_version=u.name)
            snapshot['unresolved']='Historical units/alignment/export invocation; efficiency timing and memory measurement; independent repeats; run completion; missing record causes. Historical scope uncertainty is superseded only for the confirmed current per-run sources.'
        if c in changed and not policy:
            snapshot['user_confirmed_repetitions']='3';snapshot['future_repetition_plan']='previous third-repeat plan fulfilled for this input version; no future run authorized'
        snapshots.append(snapshot); total+=len(rows);labelled+=diag['condition_labelled_records']
        old_header=json.loads(m['raw_header_json']); old_by={r['raw_dataset']:{k:r['raw_'+k] for k in old_header} for r in old_runs[c]};new_by={r['dataset']:r for r in rows}
        common=set(old_by)&set(new_by);same=[k for k in common if old_by[k]==new_by[k]];replaced=sorted(common-set(same))
        finite={k:sum(numeric_state(r.get(k,'')).startswith('finite_') for r in rows) for k in ['rmse','FPS','runtime','PeakReservedGB']}
        sequence_counts=json.loads(diag['sequence_run_records_json']); bad={s:r for s,r in sequence_counts.items() if sum(r.values())!=3} if c in changed else {}
        deltas.append({'configuration_id':c,'old_path':m['source_relative_path'],'new_path':rel,'old_sha256':m['source_sha256'],'new_sha256':sha,'old_record_count':m['source_record_count'],'new_record_count':len(rows),'old_sequence_count':m['sequence_count'],'new_sequence_count':diag['sequence_count'],'old_run_distribution':m['run_id_sets_per_sequence_json'],'new_run_distribution':diag['run_id_set_distribution_json'],'old_finite_counts':m['finite_counts_json'],'new_finite_counts':js(finite),'old_header':m['raw_header_json'],'new_header':js(header),'duplicate_identifiers':diag['duplicate_full_identifiers_json'],'added_identifiers':js(sorted(set(new_by)-set(old_by))),'removed_identifiers':js(sorted(set(old_by)-set(new_by))),'same_identifier_same_raw_count':len(same),'same_identifier_changed_raw':js(replaced),'non_three_sequences':js(bad),'processing_status':(policy['reason'] if policy else 'authorized_new_input') if c in changed else 'source_bytes_unchanged','coexisting_paths':coexist,'record_correspondence_limit':'same dataset labels compared as exported records, not proven same historical experiment; no inferred renumber mapping','old_source_bytes_backup':'not available as an old source file; old raw rows and hash preserved in standardized backup' if sha!=m['source_sha256'] else 'current source bytes match old hash'})
        for field,before,after in [('source_relative_path',m['source_relative_path'],rel),('evaluation_scope',m['evaluation_scope'],scope),('semantic_usage',m['semantic_usage'],snapshot['semantic_usage']),('modality_declared',m['modality_declared'],modality),('user_confirmed_repetitions',m['user_confirmed_repetitions'],snapshot['user_confirmed_repetitions'])]:
            if before!=after:metadata.append({'configuration_id':c,'field':field,'old_value':before,'current_value':after,'evidence':'user_confirmed','input_version':u.name,'scope_limit':'configuration metadata only, not per-run success, independence or measurement protocol'})
        if frozen_prior and c in changed:
            for field in ('rmse_extraction','rmse_unit_status','alignment_status','method_specific_issues','unresolved') + (('efficiency_protocol_json',) if sgs else ()):
                if previous[c][field] != snapshot[field]:
                    metadata.append({'configuration_id':c,'field':field,'old_value':previous[c][field],
                        'current_value':snapshot[field],
                        'evidence':('updates/'+u.name+'/audit/sgs_accuracy_protocol.md; updates/'+u.name+'/audit/sgs_accuracy_row_evidence.csv; exact accepted source SHA' if sgs else 'audits/accuracy_protocol/20261008_three_configurations/report.md; exact accepted source SHA'),
                        'input_version':u.name,'scope_limit':('SGS new batch and its measured fields only; no old/new physical pairing or inherited native SR' if sgs else 'SplaTAM current accuracy only; no SR, timing or repeat-independence claim')})
        dest=u/'current_sources'/rel;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(raw)
        if digest(read_path)!=sha:raise ValueError('Selected source changed during acceptance: '+rel)
    if frozen_prior:
        for delta in deltas:
            old_copy=local(prior_sources,delta['old_path'])
            if digest(old_copy)!=delta['old_sha256']:
                raise ValueError('Previous frozen source differs from its recorded hash: '+delta['old_path'])
            delta['old_source_bytes_backup']='available at '+str(old_copy.relative_to(W))+'; previous-version frozen bytes verified'
    if len(snapshots)!=24:raise ValueError('Configuration count changed')
    write_csv(u/configuration_delta_name(policy),deltas)
    write_csv(u/'metadata_changes.csv',metadata,fields=['configuration_id','field','old_value','current_value','evidence','input_version','scope_limit'])
    staging=u/'staging'
    for e in entries:
        dst=staging/e['path'];dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(u/e['backup_path'],dst)
    if frozen_prior:
        conflicts=accept_splatam_editorial_ownership(u,staging,backup)
    else:
        conflicts=json.loads((u/'preflight_conflicts.json').read_text())
        if policy:inherit_editorial_amendments(staging,backup,conflicts)
    # New version-only anchors are copied, never overwrite stage3-5 evidence.
    anchor='reports/update_inputs/original_07_questions.csv';p=staging/anchor;p.parent.mkdir(parents=True,exist_ok=True)
    anchor_source=backup/anchor if policy else backup/'reports/07_research_questions.csv'
    shutil.copyfile(anchor_source,p)
    manifest='reports/current_input_manifest.csv';write_csv(staging/manifest,snapshots)
    protected={e['path']:e['sha256'] for e in entries if e['path']=='AGENTS.md' or re.match(r'(reports|derived_data|tables)/(03|04|05)',e['path']) or e['path'] in {'scripts/audit_metric_protocol.py','scripts/inventory_inputs.py','scripts/run_dpvo_pilot.py'}}
    info={'current_version':u.name,'created_at':datetime.datetime.now().astimezone().isoformat(),'manifest':{'path':manifest,'sha256':digest(staging/manifest)},'source_count':len(snapshots),'total_record_count':total,'condition_labelled_records':labelled,'condition_unlabelled_records':total-labelled,'frozen_stage07_questions':{'path':anchor,'sha256':digest(staging/anchor)},'backup_manifest':{'path':str((u/'backup_manifest.json').relative_to(W)),'sha256':digest(u/'backup_manifest.json')},'protected_history':protected,'user_confirmation':'updates/'+u.name+'/update_request.md','source_input_root':str(SOURCE)}
    if policy:info['update_policy']=policy
    if frozen_prior:
        info['frozen_source_root']='updates/'+u.name+'/current_sources'
        info['live_source_gate_configurations']=policy['authorized_changed_configurations']
        info['source_storage_note']='Original source paths are provenance; this version reads immutable in-project frozen CSV bytes. Other 23 configurations retain preceding-version bytes; later independent memory updates are excluded.'
        if sgs:
            info['source_storage_note']+=' SGS uses the reviewed new run 4/5/6 batch; historical native SR and memory do not establish identity with these new runs.'
    write_json(staging/'reports/current_input_manifest.json',info)
    write_json(staging/'reports/current_build_context.json',{'current_version':u.name,'input_manifest_sha256':info['manifest']['sha256'],'stages':{}})
    plan=[{'stage':s,'entry':'scripts/'+entry,'outputs':outputs_for(s,backup),'status':'pending'} for s,entry in ENTRIES.items()]
    rebuild={'current_version':u.name,'status':'prepared_not_published','backup_manifest':'backup_manifest.json','current_input_manifest':info,'stages':plan,'generated_file_conflicts':conflicts}
    if policy:rebuild['update_policy']={'path':'update_policy.json','sha256':digest(u/'update_policy.json')}
    write_json(u/'rebuild_manifest.json',rebuild)
    print(js({'prepared':str(u),'sources':len(snapshots),'records':total,'labelled':labelled,'unlabelled':total-labelled,'changed_sources':[d['configuration_id'] for d in deltas if d['old_sha256']!=d['new_sha256']]}))


def build(u, stage, overwrite):
    load_update_policy(u)
    if not overwrite:raise ValueError('Explicit --overwrite required for staged current-output refresh')
    staging=u/'staging';m=json.loads((u/'rebuild_manifest.json').read_text());plan=next(s for s in m['stages'] if s['stage']==stage)
    earlier=list(ENTRIES)[:list(ENTRIES).index(stage)]
    if any(next(s for s in m['stages'] if s['stage']==i)['status']!='computed' for i in earlier):raise ValueError('Build predecessors first')
    for p in (W/'scripts').glob('*.py'):shutil.copyfile(p,staging/'scripts'/p.name)
    script=staging/'scripts'/ENTRIES[stage]
    keys=declared_inputs(script)
    context_path=staging/'reports/current_build_context.json';context=json.loads(context_path.read_text())
    if keys is None:
        if stage=='06':keys=['reports/current_input_manifest.csv','reports/current_input_manifest.json','reports/04_input_protocol_matrix.csv','derived_data/05_dpvo_pilot/run_records.csv']
        else:keys=[x['path'] for x in json.loads((u/'backup'/SPECS[stage]).read_text())['inputs'].values()]
    inputs={p:digest(local(staging,p)) for p in keys}
    context['stages'][stage]={'inputs':inputs,'outputs':plan['outputs']};write_json(context_path,context)
    command=[PYTHON,'-B',str(script),'--overwrite'];started=datetime.datetime.now().astimezone().isoformat()
    if 'attempts' not in plan:
        plan['attempts']=[]
        if 'exit_code' in plan:
            plan['attempts'].append({k:plan[k] for k in ('command','started_at','finished_at','exit_code','log','inputs','script_sha256','status') if k in plan})
    log=u/('build_'+stage+'_attempt'+str(len(plan['attempts'])+1)+'.log')
    with tempfile.TemporaryDirectory(prefix='.version_cache_',dir=staging/'reports') as td:
        env=dict(os.environ,BENCHMARK_ANALYSIS_WORKSPACE=str(staging),PYTHONDONTWRITEBYTECODE='1',MPLCONFIGDIR=td+'/mpl',XDG_CACHE_HOME=td+'/xdg',TMPDIR=td)
        with log.open('w') as f:result=subprocess.run(command,cwd=staging,env=env,stdout=f,stderr=subprocess.STDOUT)
    plan.update(command=command,started_at=started,finished_at=datetime.datetime.now().astimezone().isoformat(),exit_code=result.returncode,log=log.name,inputs=inputs,script_sha256=digest(script),status='computed' if result.returncode==0 else 'failed')
    plan['attempts'].append({k:plan[k] for k in ('command','started_at','finished_at','exit_code','log','inputs','script_sha256','status')})
    if m['status']=='published':
        # A replay first rebuilds staging; current paths stay on their last
        # verified publication until a separately requested publish succeeds.
        m['status']='rebuilding_staging'
    if result.returncode==0:
        plan['output_snapshot']={p:{'sha256':digest(staging/p),'bytes':(staging/p).stat().st_size} for p in plan['outputs']}
        for p,h in inputs.items():
            if digest(staging/p)!=h:raise ValueError('Input changed during stage '+stage+': '+p)
    write_json(u/'rebuild_manifest.json',m)
    print(js({'stage':stage,'status':plan['status'],'log':str(log)}))
    if result.returncode:print(log.read_text()[-14000:]);raise SystemExit(result.returncode)


def reviews(u, root):
    found={}
    for p in sorted((u/'visual_reviews').glob('*.json')):
        for r in json.loads(p.read_text()):
            if r['status']!='visually_reviewed' or digest(local(root,r['path']))!=r['sha256']:
                raise ValueError('Stale or incomplete actual-view receipt: '+r['path'])
            if r['path'] in found and found[r['path']]['sha256']!=r['sha256']:
                raise ValueError('Conflicting visual receipts')
            found[r['path']]=r
    return found


def record_reviews(u, stage):
    root=u/'staging';m=json.loads((u/'rebuild_manifest.json').read_text())
    plan=next(x for x in m['stages'] if x['stage']==stage)
    if plan['status']!='computed':raise ValueError('Generate stage before visual acceptance')
    received=reviews(u,root)
    needed=[p for p in plan['outputs'] if p.endswith('.png')]
    if any(p not in received for p in needed):raise ValueError('Not every stage PNG actually viewed')
    env=dict(os.environ,BENCHMARK_ANALYSIS_WORKSPACE=str(root),PYTHONDONTWRITEBYTECODE='1')
    if stage=='11':
        manifest=root/SPECS[stage];old=json.loads(manifest.read_text())
        for p,e in old['outputs'].items():
            if digest(root/p)!=e['sha256']:raise ValueError('Paper output manually changed: '+p)
        old['visual_review']={'status':'passed_actual_open','width_mm':180,
            'figures':{p:received[p]['sha256'] for p in needed},
            'notes':{p:received[p]['note'] for p in needed},
            'receipt_directory':str((u/'visual_reviews').relative_to(W)),
            'layout_limit':'Actual generated PNG review; no claim of compiling an unknown final paper template.'}
        write_json(manifest,old)
        build(u,'11',True)
        m=json.loads((u/'rebuild_manifest.json').read_text());plan=next(x for x in m['stages'] if x['stage']==stage)
    else:
        cmd=[PYTHON,'-B',str(root/'scripts'/ENTRIES[stage]),'--record-reviewed',*[Path(p).stem for p in needed],
             '--reviewer','root with delegated actual PNG reviewers','--review-note','Actual full PNG and required large-figure details viewed for this frozen data version; per-image reviewers, hashes and notes are in the update visual_reviews directory.']
        subprocess.run(cmd,cwd=root,env=env,check=True)
        plan['review_command']=cmd
    reviews(u,root)
    plan['visual_status']='all_PNG_actually_viewed'
    plan['post_visual_output_snapshot']={p:{'sha256':digest(root/p),'bytes':(root/p).stat().st_size} for p in plan['outputs']}
    write_json(u/'rebuild_manifest.json',m)


def verify(u, require_visual=True):
    load_update_policy(u)
    m=json.loads((u/'rebuild_manifest.json').read_text());root=W if m['status']=='published' else u/'staging'
    from version_support import current_version,check_version_history
    info=current_version(root);check_version_history(root)
    for r in read_csv(root/info['manifest']['path']):
        if digest(source_read_path(root,r['source_relative_path'],info))!=r['sha256']:
            raise ValueError('Bound source snapshot changed since freezing: '+r['source_relative_path'])
        if (info.get('frozen_source_root') and
                r['method_directory']+'::'+r['configuration'] in info.get('live_source_gate_configurations',[])
                and digest(SOURCE/r['source_relative_path'])!=r['sha256']):
            raise ValueError('Authorized live source changed since freezing: '+r['source_relative_path'])
    all_outputs=set()
    for plan in m['stages']:
        if plan['status']!='computed':raise ValueError('Incomplete stage: '+plan['stage'])
        for p,h in plan['inputs'].items():
            if digest(root/p)!=h:raise ValueError('Stale dependency for '+plan['stage']+': '+p)
        for p,e in plan.get('post_visual_output_snapshot',plan['output_snapshot']).items():
            if digest(root/p)!=e['sha256']:raise ValueError('Output changed: '+p)
        all_outputs.update(plan['outputs'])
        if digest(root/'scripts'/ENTRIES[plan['stage']])!=plan['script_sha256']:raise ValueError('Entry script differs from executed version')
    got=reviews(u,root);pngs={p for p in all_outputs if p.endswith('.png')};pending=sorted(pngs-set(got))
    if require_visual and pending:raise ValueError('PNG visual review pending: '+', '.join(pending))
    from benchmark_update_comparison import verify_unchanged_configurations
    unchanged=verify_unchanged_configurations(u)
    if not unchanged['passed']:raise ValueError('Unexplained numeric drift in unchanged configurations: '+js(unchanged)[:2000])
    result={'current_version':u.name,'root':str(root),'current_sources':24,'stages':list(ENTRIES),
            'outputs':len(all_outputs),'PNGs':len(pngs),'actually_viewed':len(pngs&set(got)),'pending':pending,
            'unchanged_configuration_check':unchanged,'source_hashes_unchanged_since_acceptance':True}
    write_json(u/'verification.json',result)
    print(js({k:v for k,v in result.items() if k!='unchanged_configuration_check'}))
    return m,all_outputs


def publish(u, overwrite):
    if not overwrite:raise ValueError('Publishing requires explicit --overwrite')
    m,outputs=verify(u)
    if m['status']=='published':raise ValueError('Version already published; use --verify')
    if not (u/'changed_results.csv').is_file() or not (u/'changed_claims.csv').is_file():raise ValueError('Compare results and claims before publishing')
    old={e['path']:e for e in backup_entries(u)}
    published=m.get('published_files',{})
    extra={'reports/current_input_manifest.csv','reports/current_input_manifest.json','reports/current_build_context.json','reports/update_inputs/original_07_questions.csv'}
    for p in sorted(outputs|extra):
        dest=local(W,p)
        if p in published:
            if digest(dest)!=published[p]:raise ValueError('Published file edited before replay; preserve it: '+p)
        elif p in old:
            if digest(dest)!=old[p]['sha256']:raise ValueError('Current file edited after backup; preserve it: '+p)
        elif dest.exists():raise ValueError('Unregistered current destination already exists: '+p)
    if published:
        m.setdefault('publication_history',[]).append({'published_at':m['published_at'],'files':published})
    m['status']='publishing';write_json(u/'rebuild_manifest.json',m)
    for p in sorted(outputs|extra):
        dest=local(W,p);dest.parent.mkdir(parents=True,exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=dest.parent,prefix='.version_publish_',delete=False) as f:
            temp=Path(f.name);f.write((u/'staging'/p).read_bytes())
        os.replace(temp,dest)
    m['status']='published';m['published_at']=datetime.datetime.now().astimezone().isoformat()
    m['published_files']={p:digest(W/p) for p in sorted(outputs|extra)}
    write_json(u/'rebuild_manifest.json',m)
    verify(u)


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--update-dir',required=True)
    action=ap.add_mutually_exclusive_group(required=True);action.add_argument('--prepare',action='store_true');action.add_argument('--build',choices=list(ENTRIES))
    action.add_argument('--record-reviews',choices=['11','11B','11C']);action.add_argument('--compare',action='store_true');action.add_argument('--verify',action='store_true');action.add_argument('--publish',action='store_true')
    ap.add_argument('--overwrite',action='store_true');a=ap.parse_args()
    u=Path(a.update_dir).resolve()
    if u.parent!=W/'updates' or not (u/'backup_manifest.json').is_file():raise ValueError('Expected an existing in-project timestamped backup')
    if a.prepare:prepare(u)
    elif a.build:build(u,a.build,a.overwrite)
    elif a.record_reviews:record_reviews(u,a.record_reviews)
    elif a.compare:
        from benchmark_update_comparison import build_update_comparison
        result=build_update_comparison(u, overwrite=a.overwrite)
        write_json(u/'comparison_verification.json',result)
        print(js(result))
    elif a.publish:publish(u,a.overwrite)
    else:verify(u)


if __name__=='__main__':main()
