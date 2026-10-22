#!/usr/bin/env python3
"""Step 6: matrix-indexed structural conversion only, with no metric aggregation."""

import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import io
import json
import math
import os
from pathlib import Path
import shlex
import sys
from unittest.mock import patch

# Reviewed pure workspace functions; never call that script's main().
from audit_metric_protocol import parse_identifier, numeric_state, diagnose, SPEED, ALTITUDE
from version_support import workspace as controlled_workspace, source_read_path

PROJECT_ROOT = Path('/home/yuan/SLAM/codex_review/benchmark_analysis')
WORKSPACE = controlled_workspace(PROJECT_ROOT)
INPUT_ROOT = Path('/home/yuan/SLAM/AirSim-Visual-SLAM-Research-Toolkit/Benchmark/experiment_data')
MATRIX = WORKSPACE / 'reports/04_input_protocol_matrix.csv'
MATRIX_HASH = 'ec04df2a4de15f1848c5fe77e0c044ccd94156a940b7228b30bc22191766526f'
INPUT_CONTEXT = None
PILOT = WORKSPACE / 'derived_data/05_dpvo_pilot/run_records.csv'
OUTPUTS = {
    'records': 'derived_data/06_standardized/run_records.csv',
    'manifest': 'derived_data/06_standardized/source_manifest.csv',
    'schema': 'derived_data/06_standardized/schema.json',
    'coverage': 'reports/06_sequence_coverage.csv',
    'report': 'reports/06_data_quality.md',
}
CORE = {'rmse': 'rmse', 'FPS': 'fps', 'runtime': 'runtime', 'PeakReservedGB': 'memory'}
AUXILIARY = ('max', 'min', 'mean', 'median', 'sse', 'std')
SCHEMA_VERSION = '1.0.0'
MARKER = '<!-- generated-by: scripts/build_analysis_dataset.py; step-6-only -->'
STATES = ('source_not_provided', 'empty_string', 'whitespace_only', 'text_missing_marker',
          'unparseable', 'nan', 'positive_inf', 'negative_inf',
          'finite_negative', 'finite_zero', 'finite_positive')


def js(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def reject_links(path):
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError(f'Symbolic link rejected: {path}')


def read_bytes(path):
    reject_links(path)
    with path.open('rb') as f:
        raw = f.read(10 * 1024 * 1024 + 1)
    if len(raw) > 10 * 1024 * 1024:
        raise ValueError(f'Over 10 MiB: {path}')
    return raw


def require_hash(raw, expected):
    actual = digest(raw)
    if actual != expected:
        raise ValueError(f'SHA-256 mismatch: expected={expected}; actual={actual}')
    return actual


def decode_csv(raw):
    """No NA inference, trimming, blank-record skipping, or duplicate removal."""
    reader = csv.reader(io.StringIO(raw.decode('utf-8-sig'), newline=''), strict=True)
    header = next(reader)
    if not header or len(set(header)) != len(header):
        raise ValueError('Empty or duplicate header')
    rows = []
    for index, cells in enumerate(reader, 1):
        if len(cells) != len(header) or not any(cells):
            raise ValueError(f'Ragged or entirely empty record: {index}')
        rows.append(dict(zip(header, cells)))
    return header, rows


def csv_text(rows, fields):
    out = io.StringIO(newline='')
    writer = csv.DictWriter(out, fieldnames=fields, lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue()


def numeric_view(raw, provided=True):
    if not provided:
        return '', 'source_not_provided', False
    state = numeric_state(raw)
    finite = state.startswith('finite_')
    # This float view is NOT the pandas conversion or a legacy SR predicate.
    return (float(raw.strip()) if finite else ''), state, finite


def metadata(snapshot):
    modality = snapshot['modality']
    modality = 'unknown' if modality.startswith('unknown') else modality
    semantic = snapshot['semantic_usage']
    semantic = 'yes' if semantic.startswith('yes') else 'no' if semantic == 'no' else 'unknown'
    scope = {'500 frames': '500_frames', '500_frames': '500_frames',
             'whole trajectory': 'whole_trajectory', 'whole_trajectory': 'whole_trajectory',
             'unknown': 'unknown'}[snapshot['evaluation_scope']]
    method, config = snapshot['method_directory'], snapshot['configuration']
    return {
        'method_directory': method, 'configuration': config,
        'configuration_id': method + '::' + config,
        'modality_declared': modality,
        'modality_evidence': 'unknown' if modality == 'unknown' else 'user_confirmed',
        'semantic_usage': semantic,
        'semantic_evidence': 'unknown' if semantic == 'unknown' else 'user_confirmed',
        'evaluation_scope': scope,
        'evaluation_scope_evidence': 'unknown' if scope == 'unknown' else 'user_confirmed',
    }


def load_input_snapshots(manifest_path=None, manifest_sha256=None):
    """Accept an explicit frozen version while keeping the step-4 audit immutable."""
    global INPUT_CONTEXT
    historical_raw = read_bytes(MATRIX)
    require_hash(historical_raw, MATRIX_HASH)
    _, historical = decode_csv(historical_raw)
    if bool(manifest_path) != bool(manifest_sha256):
        raise ValueError('--input-manifest and --input-manifest-sha256 must be supplied together')
    context_path = WORKSPACE / 'reports/current_input_manifest.json'
    context = None
    if context_path.exists():
        context_raw = read_bytes(context_path)
        context = json.loads(context_raw)
        declared = context['manifest']
        default_path = Path(declared['path'])
        if default_path.is_absolute() or '..' in default_path.parts:
            raise ValueError('Current manifest path must be workspace-relative')
        if manifest_path is None:
            manifest_path, manifest_sha256 = default_path, declared['sha256']
        else:
            actual = Path(manifest_path)
            if actual.is_absolute():
                actual = actual.relative_to(WORKSPACE)
            if actual != default_path or manifest_sha256 != declared['sha256']:
                raise ValueError('Explicit manifest disagrees with the current frozen version')
        context = dict(context, context_path=str(context_path.relative_to(WORKSPACE)),
                       context_sha256=digest(context_raw))
    if manifest_path is None:
        INPUT_CONTEXT = None
        return historical
    if context is None:
        raise ValueError('A versioned input requires reports/current_input_manifest.json with frozen counts and evidence')
    path = Path(manifest_path)
    path = path if path.is_absolute() else WORKSPACE / path
    if not path.resolve().is_relative_to(WORKSPACE.resolve()):
        raise ValueError('Input manifest escapes the selected workspace')
    raw = read_bytes(path)
    require_hash(raw, manifest_sha256)
    _, snapshots = decode_csv(raw)
    old_by_id = {metadata(r)['configuration_id']: r for r in historical}
    if len(snapshots) != context['source_count'] or {metadata(r)['configuration_id'] for r in snapshots} != set(old_by_id):
        raise ValueError('Current version must preserve all 24 historical configuration IDs exactly once')
    if sum(int(r['record_count']) for r in snapshots) != context['total_record_count']:
        raise ValueError('Current manifest count does not match its frozen version context')
    for r in snapshots:
        old = old_by_id[metadata(r)['configuration_id']]
        if r['historical_source_relative_path'] != old['source_relative_path'] or r['historical_source_sha256'] != old['sha256']:
            raise ValueError('Historical source audit disagrees with preserved step-4 matrix')
        json.loads(r['historical_metadata_json'])
        if not r['current_metadata_evidence'] or r['input_version'] != context['current_version']:
            raise ValueError('Current metadata requires explicit version and user-confirmation evidence')
    INPUT_CONTEXT = context
    return snapshots


def convert_source(rows, header, union, snapshot):
    """Append one converted row per source record; no merge or row eligibility."""
    meta = metadata(snapshot)
    result = []
    for index, row in enumerate(rows, 1):
        item = {f'raw_{k}': row[k] if k in header else '' for k in union}
        item.update(source_relative_path=snapshot['source_relative_path'], source_sha256=snapshot['sha256'],
                    source_record_index=index, **meta)
        parsed = parse_identifier(row['dataset'])
        item.update({k: parsed.get(k) or '' for k in ('sequence_raw', 'run_id_raw', 'scene')})
        item['identifier_parse_status'] = parsed['parse_status']
        item['speed_mps'] = parsed.get('speed_mps') if parsed.get('speed_mps') is not None else ''
        item['altitude_m'] = parsed.get('altitude_m') if parsed.get('altitude_m') is not None else ''
        item['speed_level'] = next((k for k, v in SPEED.items() if v == item['speed_mps']), '')
        item['altitude_level'] = next((k for k, v in ALTITUDE.items() if v == item['altitude_m']), '')
        item['condition_label_status'] = 'two_tokens' if item['speed_level'] and item['altitude_level'] else 'missing_condition_labels'
        for raw_name, name in CORE.items():
            value, state, finite = numeric_view(row.get(raw_name, ''), raw_name in header)
            item.update({name + '_value': value, name + '_state': state, name + '_is_finite': finite})
        for name in AUXILIARY:
            item[name + '_state'] = numeric_view(row.get(name, ''), name in header)[1]
        result.append(item)
    return result


def snapshot_check(diagnostic, snapshot):
    differences = {}
    for key, actual in diagnostic.items():
        expected = snapshot[key]
        equivalent = json.loads(actual) == json.loads(expected) if key.endswith('_json') else str(actual) == expected
        if not equivalent:
            differences[key] = {'expected': expected, 'observed': actual}
    return differences


def quality(rows):
    identifiers = Counter(r['raw_dataset'] for r in rows)
    source_keys = Counter((r['source_relative_path'], r['source_sha256'], str(r['source_record_index'])) for r in rows)
    sequences = defaultdict(list)
    for r in rows:
        if r['sequence_raw']:
            sequences[r['sequence_raw']].append(r['run_id_raw'])
    states = {name: dict(sorted(Counter(r[name + '_state'] for r in rows).items())) for name in CORE.values()}
    # Counts, never SR or metric mean/std.
    return {
        'output_record_count': len(rows), 'sequence_count': len(sequences),
        'run_ids_json': js(sorted({r['run_id_raw'] for r in rows})),
        'records_per_sequence_json': js(Counter(map(len, sequences.values()))),
        'run_id_sets_per_sequence_json': js(Counter(','.join(sorted(set(v))) for v in sequences.values())),
        'duplicate_identifiers_json': js({k: v for k, v in identifiers.items() if v > 1}),
        'duplicate_source_row_keys': sum(v - 1 for v in source_keys.values()),
        'condition_labelled_records': sum(r['condition_label_status'] == 'two_tokens' for r in rows),
        'condition_unlabelled_records': sum(r['condition_label_status'] != 'two_tokens' for r in rows),
        'core_states_json': js(states),
        'finite_counts_json': js({name: sum(r[name + '_is_finite'] for r in rows) for name in CORE.values()}),
        'finite_efficiency_with_nonfinite_rmse_json': js({name: sum(not r['rmse_is_finite'] and r[name + '_is_finite'] for r in rows) for name in ('fps', 'runtime', 'memory')}),
        'auxiliary_states_json': js({name: dict(Counter(r[name + '_state'] for r in rows)) for name in AUXILIARY}),
    }


def manifest_row(snapshot, header, diagnostic, converted, before, after):
    q = quality(converted)
    return {
        'source_relative_path': snapshot['source_relative_path'], 'source_absolute_path': str(INPUT_ROOT / snapshot['source_relative_path']),
        'source_sha256': before, 'step04_sha256': snapshot.get('historical_source_sha256', snapshot['sha256']), 'source_sha256_after': after,
        'hash_matches_snapshot': before == snapshot['sha256'], 'hash_unchanged': before == after,
        'raw_header_json': js(header), 'raw_field_mapping_json': js({k: 'raw_' + k for k in header}),
        'source_not_provided_fields_json': js([k for k in AUXILIARY if k not in header]),
        **metadata(snapshot),
        'configuration_evidence': snapshot['configuration_evidence'],
        'modality_matrix_text': snapshot['modality'], 'semantic_matrix_text': snapshot['semantic_usage'],
        'scope_matrix_text': snapshot['evaluation_scope'],
        'user_confirmed_repetitions': snapshot['user_confirmed_repetitions'],
        'future_repetition_plan': snapshot['future_repetition_plan'],
        'rmse_unit_status': snapshot['rmse_unit_status'], 'alignment_status': snapshot['alignment_status'],
        'efficiency_protocol_json': snapshot['efficiency_protocol_json'],
        'trajectory_completion_status': 'unknown', 'failure_reason': 'unknown',
        'method_specific_issues': snapshot['method_specific_issues'],
        'source_evidence_reference': ((INPUT_CONTEXT['manifest']['path'] if INPUT_CONTEXT else 'reports/04_input_protocol_matrix.csv')
                                      + '#source_relative_path=' + snapshot['source_relative_path']),
        'evidence_matrix_sha256': MATRIX_HASH,
        'unresolved': snapshot['unresolved'],
        'structure_impact': 'no blocker: fixed source and record/configuration boundaries verified',
        'comparison_impact': 'Read per-configuration rmse_unit_status/alignment_status for accuracy eligibility. Retain configuration/scope boundaries; finite RMSE does not imply SR or independent repeats. Runtime is author-confirmed seconds; efficiency_protocol_json preserves historical extraction notes, not the separate current typed Table 2 memory protocol.',
        'source_record_count': diagnostic['record_count'], 'snapshot_record_count': int(snapshot['record_count']),
        'snapshot_diagnostics_match': not snapshot_check(diagnostic, snapshot),
        'processing_status': 'included', **q,
        'raw_numeric_states_json': diagnostic['numeric_states_json'],
        'raw_missing_markers_json': diagnostic['raw_nonfinite_or_missing_markers_json'],
        'input_version': snapshot.get('input_version', 'historical_step04_snapshot'),
        'input_manifest_sha256': INPUT_CONTEXT['manifest']['sha256'] if INPUT_CONTEXT else MATRIX_HASH,
        'current_metadata_evidence': snapshot.get('current_metadata_evidence', 'reports/04_input_protocol_matrix.csv'),
        'historical_source_relative_path': snapshot.get('historical_source_relative_path', snapshot['source_relative_path']),
        'historical_source_sha256': snapshot.get('historical_source_sha256', snapshot['sha256']),
        'historical_metadata_json': snapshot.get('historical_metadata_json', js(snapshot)),
    }


def sequence_coverage(records, manifests):
    union = sorted({r['sequence_raw'] for r in records if r['sequence_raw']})
    groups = defaultdict(list)
    for row in records:
        groups[row['configuration_id'], row['sequence_raw']].append(row)
    result = []
    for source in manifests:
        for seq in union:
            group = groups[source['configuration_id'], seq]
            result.append({
                'reference_kind': 'observed_union_not_expected_manifest',
                'configuration_id': source['configuration_id'], 'method_directory': source['method_directory'],
                'configuration': source['configuration'], 'sequence_raw': seq,
                'source_relative_path': source['source_relative_path'], 'source_sha256': source['source_sha256'],
                'observed': bool(group), 'n_records': len(group),
                'run_ids_json': js(sorted({r['run_id_raw'] for r in group})),
                **{name + '_finite_count': sum(r[name + '_is_finite'] for r in group) for name in CORE.values()},
            })
    return result


def roundtrip_check(decoded, originals, manifests):
    lookup = {(r['source_relative_path'], r['source_sha256']): r for r in manifests}
    if len(lookup) != len(manifests):
        raise ValueError('Manifest join is not many-to-one')
    seen, cells = set(), 0
    for record in decoded:
        source = lookup[(record['source_relative_path'], record['source_sha256'])]
        index = int(record['source_record_index'])
        key = (source['source_relative_path'], index)
        if key in seen:
            raise ValueError(f'Duplicate source row key: {key}')
        seen.add(key)
        original = originals[source['source_relative_path']][index - 1]
        header = json.loads(source['raw_header_json'])
        for name in header:
            if record['raw_' + name] != original[name]:
                raise ValueError(f'Raw roundtrip mismatch: {key}, {name}')
            cells += 1
        if record['configuration_id'] != source['configuration_id']:
            raise ValueError('Wrong configuration metadata join')
    expected = {(rel, i) for rel, rows in originals.items() for i in range(1, len(rows) + 1)}
    if seen != expected:
        raise ValueError('Source/output records are not one-to-one')
    return {'records_checked': len(seen), 'raw_cells_checked': cells, 'passed': True}


def dpvo_check(decoded, pilot):
    new = [r for r in decoded if r['source_relative_path'] == 'DPVO/mono_metrics.csv']
    def keyed(rows):
        result = {(r['source_relative_path'], r['source_sha256'], r['source_record_index']): r for r in rows}
        if len(result) != len(rows):
            raise ValueError('Duplicate DPVO regression key')
        return result
    a, b = keyed(new), keyed(pilot)
    if set(a) != set(b):
        raise ValueError('DPVO regression key sets differ')
    fields = {f'raw_{k}': k for k in ('dataset', *CORE, *AUXILIARY)}
    fields.update({k: k for k in ('sequence_raw', 'run_id_raw', 'scene', 'speed_level', 'altitude_level',
                                 'speed_mps', 'altitude_m', 'identifier_parse_status', 'condition_label_status')})
    fields.update({name + '_state': raw + '_parse_status' for raw, name in CORE.items()})
    mismatches = []
    for key, row in a.items():
        for field, old_field in fields.items():
            if row[field] != b[key][old_field]:
                mismatches.append({'key': key, 'field': field, 'new': row[field], 'pilot': b[key][old_field]})
    if mismatches:
        raise ValueError('DPVO regression mismatch: ' + js(mismatches))
    return {'records_checked': len(new), 'cells_checked': len(new) * len(fields), 'field_mapping': fields, 'passed': True}


def check_output(path, overwrite=False):
    if path not in {WORKSPACE / p for p in OUTPUTS.values()}:
        raise ValueError(f'Output not in step-6 allowlist: {path}')
    reject_links(path)
    if not path.resolve().is_relative_to(WORKSPACE.resolve()):
        raise ValueError('Output escapes workspace')
    if path.exists():
        if not overwrite:
            raise FileExistsError(f'Refusing overwrite: {path}')
        if not path.is_file() or path.stat().st_nlink != 1:
            raise ValueError(f'Not an ordinary unlinked output file: {path}')


def write_output(key, content, overwrite):
    path = WORKSPACE / OUTPUTS[key]
    check_output(path, overwrite)
    path.parent.mkdir(parents=True, exist_ok=True)
    check_output(path, overwrite)
    flags = os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW | (os.O_TRUNC if overwrite else os.O_EXCL)
    with os.fdopen(os.open(path, flags, 0o666), 'w', encoding='utf-8', newline='') as f:
        f.write(content)


def schema_document(union, record_fields, manifest_fields, coverage_fields, regression_mapping):
    def field(kind, meaning, **more):
        return {'type': kind, 'meaning': meaning, **more}
    record = {f'raw_{k}': field('string', 'Original cell text; blank if source did not provide column (see manifest header).', source_field=k) for k in union}
    descriptions = {
        'source_relative_path': ('string', 'Exact current path relative to input root; source-level join key part 1.'),
        'source_sha256': ('string', 'SHA-256 of original source bytes; source-level join key part 2.'),
        'source_record_index': ('integer', 'One-based source data record position excluding header; never renumber run_id.'),
        'method_directory': ('string', 'Exact method directory spelling and case.'),
        'configuration': ('string', 'Specific configuration label from step-4 matrix; not proof of all sensor inputs.'),
        'configuration_id': ('string', 'method_directory + :: + configuration; unique source configuration in this snapshot.'),
        'modality_declared': ('string', 'Known input declaration or unknown; matrix detailed qualification is in manifest.'),
        'modality_evidence': ('enum', 'Evidence for modality declaration only: user_confirmed or unknown.'),
        'semantic_usage': ('enum', 'yes/no/unknown; yes does not imply depth absent.'),
        'semantic_evidence': ('enum', 'Evidence for semantic usage: user_confirmed or unknown.'),
        'evaluation_scope': ('enum', '500_frames/whole_trajectory/unknown; nominal evaluation configuration, not per-run completion.'),
        'evaluation_scope_evidence': ('enum', 'Evidence for evaluation scope: user_confirmed or unknown.'),
        'sequence_raw': ('string', 'Full sequence after removal of terminal integer run suffix; blank if unresolved.'),
        'run_id_raw': ('string', 'Original terminal integer token; identifier only, no success or shared-seed inference.'),
        'scene': ('string', 'Prefix-based scene key, not a replacement for sequence; blank if unrecognized.'),
        'identifier_parse_status': ('enum', 'terminal_integer_suffix or unresolved, from reviewed parse_identifier.'),
        'speed_mps': ('nullable integer', 'Nominal speed from first condition token: low/medium/high -> 2/4/8, not remeasured.'),
        'altitude_m': ('nullable integer', 'Nominal altitude from second condition token: low/medium/high -> 10/20/30, not remeasured.'),
        'speed_level': ('string', 'low/medium/high or blank if missing condition labels.'),
        'altitude_level': ('string', 'low/medium/high or blank if missing condition labels.'),
        'condition_label_status': ('enum', 'two_tokens or missing_condition_labels; never infer a value for 25fps sequences.'),
    }
    record.update({name: field(*info) for name, info in descriptions.items()})
    for raw, name in CORE.items():
        record[name + '_value'] = field('nullable finite float64', 'Finite float view of raw text, with no explicit rounding, rescaling or normalization.', source_field=raw)
        record[name + '_state'] = field('enum', 'Cell numeric state; independent of other metrics and experimental completion.', source_field=raw, allowed_values=list(STATES))
        record[name + '_is_finite'] = field('boolean', 'True exactly for finite_negative/finite_zero/finite_positive; never a success flag.')
    for name in AUXILIARY:
        record[name + '_state'] = field('enum', 'Auxiliary raw field presence and numeric state; no computed numeric view.', source_field=name, allowed_values=list(STATES))
    manifest = {k: v for k, v in record.items() if k in manifest_fields}
    extra = {
        'source_absolute_path': ('string', 'Fixed input root plus exact relative source path.'),
        'step04_sha256': ('string', 'Historical byte digest from the preserved step-4 matrix; not the current-version expected hash.'),
        'source_sha256_after': ('string', 'Byte digest checked after all records were converted and validated.'),
        'hash_matches_snapshot': ('boolean', 'Current pre-read source digest equals the frozen input-manifest digest for this version.'),
        'hash_unchanged': ('boolean', 'Pre/post build source byte digests equal.'),
        'raw_header_json': ('JSON array', 'Exact source header in original order; distinguishes absent fields from present empty cells.'),
        'raw_field_mapping_json': ('JSON object', 'One-to-one source-column to raw_ output-column mapping.'),
        'source_not_provided_fields_json': ('JSON array', 'Auxiliary fields absent from source schema; their raw cells are blank, state source_not_provided.'),
        'configuration_evidence': ('string', 'Source configuration evidence, retaining historical qualifications not superseded by current confirmation.'),
        'modality_matrix_text': ('string', 'Exact current modality text from the frozen input manifest; historical declarations are separate.'),
        'semantic_matrix_text': ('string', 'Exact current semantic-usage text from the frozen input manifest; no inferred sensor capability.'),
        'scope_matrix_text': ('string', 'Exact current evaluation-scope text from the frozen input manifest.'),
        'user_confirmed_repetitions': ('string', 'User-confirmed retained repeat situation, or unknown; not derived from run numbering.'),
        'future_repetition_plan': ('string', 'Previously confirmed future plan; not current data or authorization.'),
        'rmse_unit_status': ('string', 'Inherited unit declarations and unresolved upstream provenance.'),
        'alignment_status': ('string', 'Current code evidence and unresolved historical invocation, copied from matrix.'),
        'efficiency_protocol_json': ('JSON object', 'Historical matrix extraction notes; no new conversion performed. Current runtime seconds and separately audited typed memory policy supersede historical unit uncertainty; this field does not update historical memory values.'),
        'trajectory_completion_status': ('string', 'unknown: finite values do not certify full trajectory completion.'),
        'failure_reason': ('string', 'unknown: missing metrics do not establish a failure cause.'),
        'method_specific_issues': ('string', 'Matrix current-source routing/conflict caveats, not rewritten as resolved.'),
        'source_evidence_reference': ('string', 'Workspace-relative current input-manifest reference with source_relative_path selector.'),
        'evidence_matrix_sha256': ('string', 'Digest of the preserved historical step-4 audit matrix.'),
        'unresolved': ('string', 'Still-unresolved evidence; superseded historical unknowns remain in historical_metadata_json.'),
        'structure_impact': ('string', 'Whether evidence limitations block this record/configuration conversion.'),
        'comparison_impact': ('string', 'Limits on later measurement/scope/success comparisons, not an eligibility flag.'),
        'source_record_count': ('integer', 'Number of source data rows before conversion.'),
        'snapshot_record_count': ('integer', 'Expected source row count in the selected frozen input version.'),
        'snapshot_diagnostics_match': ('boolean', 'Every diagnose() field agrees with the selected frozen input version, including per-sequence and numeric-state counts.'),
        'processing_status': ('enum', 'included only after hash, structure and traceability checks pass.'),
        'input_version': ('string', 'Explicit frozen input-version ID; no change to the stable configuration ID.'),
        'input_manifest_sha256': ('string', 'SHA-256 of the frozen manifest defining the current source hashes and observations.'),
        'current_metadata_evidence': ('string', 'User-confirmation and observed-input evidence for current metadata.'),
        'historical_source_relative_path': ('string', 'Prior version source path retained for audit, not an additional input source.'),
        'historical_source_sha256': ('string', 'Historical source byte digest; does not claim that unavailable old source bytes were backed up.'),
        'historical_metadata_json': ('JSON object', 'Preserved prior-version source metadata, including superseded scope, repeat and plan statements.'),
        'output_record_count': ('integer', 'Actual converted row count for this source.'),
        'sequence_count': ('integer', 'Distinct parseable sequence count.'),
        'run_ids_json': ('JSON array', 'Observed raw run identifiers, not expected experiments or paired seeds.'),
        'records_per_sequence_json': ('JSON object', 'Observed records-per-sequence count -> number of sequences.'),
        'run_id_sets_per_sequence_json': ('JSON object', 'Observed comma-joined run-ID set -> number of sequences.'),
        'duplicate_identifiers_json': ('JSON object', 'Repeated full dataset string -> count, within this source/configuration; retained, never deduplicated.'),
        'duplicate_source_row_keys': ('integer', 'Additional occurrences of the composite source-row unique key; must be zero.'),
        'condition_labelled_records': ('integer', 'Rows with both condition tokens parsed.'),
        'condition_unlabelled_records': ('integer', 'Rows without both condition tokens; retained.'),
        'core_states_json': ('JSON object', 'Per core metric: numeric-state -> count.'),
        'finite_counts_json': ('JSON object', 'Per core metric: finite value count, not successful runs.'),
        'finite_efficiency_with_nonfinite_rmse_json': ('JSON object', 'Per efficiency metric: finite count where rmse is not finite.'),
        'auxiliary_states_json': ('JSON object', 'Per auxiliary field: numeric/presence state -> count.'),
        'raw_numeric_states_json': ('JSON object', 'Source-provided numeric fields and original step-4 diagnostic state counts.'),
        'raw_missing_markers_json': ('JSON object', 'Nonfinite/missing original text counts by source-provided field.'),
    }
    manifest.update({name: field(*info) for name, info in extra.items()})
    coverage = {k: v for k, v in {**record, **manifest}.items() if k in coverage_fields}
    coverage.update({
        'reference_kind': field('enum', 'observed_union_not_expected_manifest: union of actually parsed source sequences.'),
        'observed': field('boolean', 'At least one retained record exists for this configuration and sequence.'),
        'n_records': field('integer', 'Retained rows; zero means not observed, never a failure or SR denominator entry.'),
        **{name + '_finite_count': field('integer', 'Finite values in retained group; zero can mean no rows or all nonfinite, use n_records.') for name in CORE.values()},
    })
    for actual, definitions in [(record_fields, record), (manifest_fields, manifest), (coverage_fields, coverage)]:
        if set(actual) != set(definitions):
            raise ValueError('Undocumented schema fields: ' + repr(set(actual) ^ set(definitions)))
    return {
        'schema_version': SCHEMA_VERSION, 'dataset_status': 'complete_validated',
        'scope': 'Structural standardization of retained run-labelled rows only; no metric aggregation, normalization or harmonization.',
        'input_root': str(INPUT_ROOT), 'workspace': str(WORKSPACE),
        'evidence_matrix': {'path': str(MATRIX), 'sha256': MATRIX_HASH},
        'files': {key: {'path': OUTPUTS[key], 'columns': {k: defs[k] for k in cols}} for key, cols, defs in [
            ('records', record_fields, record), ('manifest', manifest_fields, manifest), ('coverage', coverage_fields, coverage)]},
        'primary_key': ['source_relative_path', 'source_sha256', 'source_record_index'],
        'source_join': {'record_columns': ['source_relative_path', 'source_sha256'], 'manifest_columns': ['source_relative_path', 'source_sha256'], 'cardinality': 'many-to-one; validated unique manifest keys; no row expansion'},
        'configuration_identity': 'Exact method_directory + :: + matrix configuration; one source per configuration in this snapshot, explicitly checked.',
        'raw_field_mapping': {k: 'raw_' + k for k in union},
        'numeric_conversion': {
            'implementation': 'Reviewed audit_metric_protocol.numeric_state; only state beginning finite_ gets float(raw.strip()).',
            'state_order': ['absence -> source_not_provided', 'exact empty -> empty_string', 'strip empty -> whitespace_only',
                            'upper stripped NA/N/A/NONE/NULL -> text_missing_marker', 'float parse error -> unparseable',
                            'NaN / +/-Inf -> separate nonfinite states', 'finite sign -> finite_negative/finite_zero/finite_positive'],
            'finite_representation': 'Python binary64 float, repr-compatible CSV text; no explicit decimal rounding. Exact original decimal/text remains raw_.',
            'nonfinite_representation': 'Empty numeric cell; raw text and state retained; never unknown string or zero replacement.',
            'no_transformations': 'No unit conversion (including SplaTAM /100), clipping, imputation, interpolation, log, z-score or min-max.',
            'legacy_boundary': 'A generic view, NOT a scene SR predicate or pandas shared-condition reproduction rule. float accepts inputs such as 1_000 that pandas may reject; raw text must be reused for future legacy reproduction.',
        },
        'missing_conventions': {'raw_empty': 'Use source manifest raw_header_json and field state to distinguish source_not_provided from present empty_string.',
                                'metadata_unknown': 'unknown; never upgrade to verified due to successful conversion.',
                                'nominal_condition_unknown': 'Empty speed/altitude numeric/level fields plus missing_condition_labels.',
                                'boolean_csv': 'True or False; read explicitly, not via truthiness of nonempty strings.',
                                'raw_csv_reader': 'Use csv strings or equivalent keep_default_na=False; do not infer NA values in raw_ fields.'},
        'source_not_provided_auxiliary': list(AUXILIARY),
        'coverage_zero_meaning': 'Not observed among current source records relative to observed sequence union; not an expected experiment manifest, main record, failure, or SR denominator.',
        'dpvo_regression_field_mapping': regression_mapping,
        'experiment_rules_reference': 'README.md; detailed prior evidence in reports/04_input_protocol_matrix.csv; no independent rule system created.',
    }


def self_test():
    tests = []
    def check(label, function):
        function()
        tests.append({'name': label, 'passed': True})
    def snap(path='virtual/mono_metrics.csv', config='mono'):
        return {'source_relative_path': path, 'sha256': 'virtual', 'method_directory': path.split('/')[0],
                'configuration': config, 'modality': 'unknown', 'semantic_usage': 'unknown', 'evaluation_scope': 'unknown'}
    union = ['dataset', *CORE, *AUXILIARY]
    row = {'dataset': 'cross_building_low_high_4', 'rmse': 'NA', 'FPS': '2.5000', 'runtime': ' 7 ', 'PeakReservedGB': "('NA', 'NA')"}
    converted = convert_source([row], list(row), union, snap())
    def identity():
        other = convert_source([row], list(row), union, snap('other/rgbd_metrics.csv', 'rgbd'))
        assert len(converted + other) == 2
        assert converted[0]['configuration_id'] != other[0]['configuration_id']
        assert converted[0]['run_id_raw'] == '4'
        duplicates = convert_source([row, row], list(row), union, snap())
        assert len(duplicates) == 2 and len(json.loads(quality(duplicates)['duplicate_identifiers_json'])) == 1
        assert quality(duplicates)['duplicate_source_row_keys'] == 0
    check('相同 dataset 跨配置不合并，run_id=4 原样保留，重复完整标识保留两行', identity)
    def missing():
        r = converted[0]
        assert r['rmse_value'] == '' and r['rmse_state'] == 'text_missing_marker'
        assert r['fps_value'] == 2.5 and r['runtime_value'] == 7 and r['memory_state'] == 'unparseable'
        assert r['raw_PeakReservedGB'] == "('NA', 'NA')"
        assert r['max_state'] == 'source_not_provided' and r['raw_max'] == ''
        expanded = {**row, 'max': 'NA', 'min': '', 'mean': ' '}
        r = convert_source([expanded], list(expanded), union, snap())[0]
        assert (r['max_state'], r['min_state'], r['mean_state']) == ('text_missing_marker', 'empty_string', 'whitespace_only')
    check('未提供字段与 NA/空/空白区分；RMSE 缺失仍保留有限效率与元组原文', missing)
    def states():
        tokens = ['', ' ', 'NA', 'N/A', 'None', 'null', "('NA', 'NA')", 'NaN', 'Inf', '-Inf', '-2', '0', '3']
        wanted = ['empty_string', 'whitespace_only', *(['text_missing_marker'] * 4), 'unparseable', 'nan', 'positive_inf', 'negative_inf', 'finite_negative', 'finite_zero', 'finite_positive']
        assert [numeric_view(x)[1] for x in tokens] == wanted
        for token in tokens:
            value, state, finite = numeric_view(token)
            assert (value != '') == finite
            if finite: assert math.isfinite(value)
        assert numeric_view('1_000') == (1000.0, 'finite_positive', True)
    check('全部数值状态、非有限值空数值列、有限零/负值与 float 兼容边界', states)
    def identifiers():
        p = converted[0]
        assert (p['sequence_raw'], p['speed_mps'], p['altitude_m']) == ('cross_building_low_high', 2, 30)
        r = convert_source([{**row, 'dataset': 'roundabout_square25fps_2'}], list(row), union, snap())[0]
        assert r['sequence_raw'] == 'roundabout_square25fps' and r['scene'] == 'roundabout'
        assert r['speed_mps'] == r['altitude_m'] == '' and r['condition_label_status'] == 'missing_condition_labels'
    check('完整含下划线名称、两 token 顺序及 25fps 条件缺失', identifiers)
    def roundtrip():
        textrow = {**row, 'runtime': '1,"quoted"\nvalue', 'std': ''}
        original = [row, textrow]
        header = list(textrow)
        original[0] = {**row, 'std': 'NA'}
        output = convert_source(original, header, union, snap())
        _, decoded = decode_csv(csv_text(output, list(output[0])).encode())
        manifest = [{'source_relative_path': snap()['source_relative_path'], 'source_sha256': 'virtual', 'raw_header_json': js(header), 'configuration_id': output[0]['configuration_id']}]
        result = roundtrip_check(decoded, {snap()['source_relative_path']: original}, manifest)
        assert result['records_checked'] == 2 and result['raw_cells_checked'] == 2 * len(header)
        try:
            roundtrip_check(decoded, {snap()['source_relative_path']: original}, manifest * 2)
        except ValueError: pass
        else: raise AssertionError('Nonunique metadata join accepted')
    check('原始单元格序列化往返（含引号/逗号/换行）与多对一关联保护', roundtrip)
    def hash_guard():
        assert require_hash(b'old', digest(b'old')) == digest(b'old')
        try: require_hash(b'new', digest(b'old'))
        except ValueError: pass
        else: raise AssertionError('Changed bytes accepted')
    check('输入哈希变化拒绝，不自动更新快照', hash_guard)
    def outputs():
        for path in [INPUT_ROOT / 'DPVO/mono_metrics.csv', WORKSPACE / 'README.md', WORKSPACE / 'derived_data/05_dpvo_pilot/run_records.csv']:
            try: check_output(path, True)
            except ValueError: pass
            else: raise AssertionError('Output allowlist bypass')
        with patch.object(Path, 'is_symlink', return_value=True):
            try: check_output(WORKSPACE / OUTPUTS['records'], True)
            except ValueError: pass
            else: raise AssertionError('Symlink accepted')
        with patch.object(Path, 'is_symlink', return_value=False), patch.object(Path, 'exists', return_value=True):
            try: check_output(WORKSPACE / OUTPUTS['records'])
            except FileExistsError: pass
            else: raise AssertionError('Default overwrite accepted')
    check('错误输出位置、历史输出、符号链接和默认覆盖均拒绝（内存模拟）', outputs)
    return tests


def quality_report(manifests, coverage, inputs, tests, roundtrip, regression, checks, command, errors):
    dso_corrected = bool(INPUT_CONTEXT and INPUT_CONTEXT.get('update_policy', {}).get('reason') == 'user_confirmed_export_omission_corrected')
    ready = not errors and all(checks.values())
    records = sum(m['output_record_count'] for m in manifests)
    methods = len({m['method_directory'] for m in manifests})
    configs = len({m['configuration_id'] for m in manifests})
    lines = [MARKER, '# 第 6 步：结构标准化与数据质量检查', '',
             '**' + ('结构标准化完成；质量检查通过。' if ready else '构建受阻／部分检查完成；不得视为完整数据集。') + '**', '',
             '本阶段仅整理结构与标识；没有计算 mean/std/SR、归一化、重评估、性能排名或科研图。',
             '这不是测量口径统一的证明。实验规则仍见 [README](../README.md)。', '',
             '## 实际范围与命令', '', f'- 输入根：`{INPUT_ROOT}`。', f'- 工作区：`{WORKSPACE}`。',
             f'- 固定解释器：`/home/yuan/anaconda3/bin/python3 -B`；schema 版本 `{SCHEMA_VERSION}`。',
             (f"- 当前输入版本 `{INPUT_CONTEXT['current_version']}`；冻结清单 `{INPUT_CONTEXT['manifest']['path']}`，SHA-256：`{INPUT_CONTEXT['manifest']['sha256']}`。"
              if INPUT_CONTEXT else f'- 由第 4 步历史矩阵直接索引，矩阵 SHA-256：`{MATRIX_HASH}`。'),
             f'- 本轮处理状态：{len(manifests)} 来源通过单源检查，{methods} 方法，{configs} 配置，{records} 条保留记录。',
             '- 记录总数由当前冻结来源逐行计算，不是独立样本数或全部历史尝试次数；旧版 3153 行仅保留为历史。',
             '- 未读取 58 个 summary、原始图像/深度/轨迹/日志，未重审 52 份研究源码或执行任何研究脚本。', '',
             '实际命令：', '', '```bash',
             f'/home/yuan/anaconda3/bin/python3 -B {WORKSPACE}/scripts/build_analysis_dataset.py --self-test', command, '```', '',
             '默认拒绝覆盖。审阅本轮输出后可用 `--overwrite`，仍只允许五个固定第 6 步产物；拒绝软链接/硬链接输出和历史产物。',
             '纯解析与状态诊断复用已审阅的 `audit_metric_protocol.py`，未调用其 main 或修改第 3～5 步脚本。', '',
             '## 逐来源处理、快照与前后哈希', '',
             '| 当前相对路径 | 当前冻结 SHA-256 | 执行前 SHA-256 | 执行后 SHA-256 | 状态 |', '|---|---|---|---|---|']
    for item in inputs:
        lines.append(f"| `{item['path']}` | `{item['expected']}` | `{item.get('before', 'unverified')}` | `{item.get('after', 'unverified')}` | {item['status']} |")
    lines += ['', '单源检查含原始表头、记录数、每条 sequence 的编号与记录计数、重复标识、条件标签、每列数值状态和原始缺失标记；',
              '完整诊断字段逐项比较当前冻结清单，非仅比较全局行数；第4步矩阵及旧来源元数据单独保留历史追溯。来源及详细边界见 [source_manifest.csv](../derived_data/06_standardized/source_manifest.csv)。', '',
              '| 配置 | 源/输出行数 | 序列数 | 编号集合 | 每序列行数→序列数 | 双标签/无标签 | 重复完整标识组/重复来源键 | 快照诊断一致 |',
              '|---|---:|---:|---|---|---:|---:|---|']
    for m in manifests:
        lines.append(f"| `{m['configuration_id']}` | {m['source_record_count']}/{m['output_record_count']} | {m['sequence_count']} | `{m['run_ids_json']}` | `{m['records_per_sequence_json']}` | {m['condition_labelled_records']}/{m['condition_unlabelled_records']} | {len(json.loads(m['duplicate_identifiers_json']))}/{m['duplicate_source_row_keys']} | {m['snapshot_diagnostics_match']} |")
    lines += ['', '## 逐指标状态与保留方式', '',
              '- 原始字段统一为 raw_ 前缀，保留全部单元格文本；逐指标数值列只保存有限浮点，非有限数值列留空。',
              '- 不进行任何单位转换或显式小数舍入，SplaTAM 的已导出 rmse 未再次除以 100。有限值转为 binary64 视图；原始十进制文本始终可回溯。',
              '- 每个指标独立转换，RMSE 无效不清空效率。不建立 success/analysis_eligible，不删除缺失行。',
              '- 未提供的辅助字段 raw_ 留空、state=source_not_provided，manifest 保留实际表头；与已有字段的 NA、空字符串和空白状态分开。',
              '- 数值视图采用已审阅的 float 状态分类，不替代 scene 可解析性或 pandas shared-condition 的旧聚合规则。', '',
              '| 配置 | rmse 状态计数 | FPS 状态计数 | runtime 状态计数 | 内存状态计数 |', '|---|---|---|---|---|']
    for m in manifests:
        states = json.loads(m['core_states_json'])
        lines.append(f"| `{m['configuration_id']}` | " + ' | '.join('`' + js(states[name]) + '`' for name in CORE.values()) + ' |')
    lines += ['', '下表只计数，不计算有效比例或成功率。', '',
              '| 配置 | 有限数量 rmse/FPS/runtime/内存 | RMSE 非有限但效率有限 FPS/runtime/内存 | 未提供辅助列 |', '|---|---|---|---|']
    for m in manifests:
        finite, independent = json.loads(m['finite_counts_json']), json.loads(m['finite_efficiency_with_nonfinite_rmse_json'])
        lines.append(f"| `{m['configuration_id']}` | " + '/'.join(str(finite[k]) for k in CORE.values()) + ' | ' + '/'.join(str(independent[k]) for k in ('fps', 'runtime', 'memory')) + f" | `{m['source_not_provided_fields_json']}` |")
    lines += ['', '实际非有限/缺失原文（按来源保留，不执行字符串）：', '']
    for m in manifests:
        markers = {k: v for k, v in json.loads(m['raw_missing_markers_json']).items() if v}
        if markers:
            lines.append(f"- `{m['configuration_id']}`：`{js(markers)}`。")
    lines += ['', 'VGGT-SLAM 元组文本保持完整，状态 unparseable；不 eval/exec，不拆列、不替换成普通 NA 或 0。', '',
              '## 覆盖、特殊配置和未知项影响', '',
              f'覆盖表采用实际 sequence 并集，共 {len({r["sequence_raw"] for r in coverage})} 条；覆盖诊断 {len(coverage)} 行。',
              '覆盖零行仅表示该配置当前未观察到对应 sequence。它不进入主表，不属于失败记录或 SR 分母；',
              '参照不是已验证的预期实验清单，没有构造场景×高度×速度×运行编号的虚构实验表。', '',
              '未观察到的 configuration × sequence：', '']
    zero = [r for r in coverage if not r['observed']]
    lines += [f"- `{r['configuration_id']}` → `{r['sequence_raw']}`：n_records=0，原因 unknown。" for r in zero] or ['- 无。']
    lines += ['', 'Hier-SLAM 的两种 500 帧配置与完整轨迹配置分别保留，实际 run_id 不改号；',
              'SplaTAM 与 Hier-SLAM 的当前次数以本版逐序列观察及用户确认分别登记；MASt3R calib/nocalib 不合并；SGS 只保留已确认语义配置。',
              '未来补跑不生成占位行，运行编号相同不等于共享随机种子。实际次数见逐配置表。', '',
              '| 未知/冲突 | 对本轮结构整理 | 对后续比较 |', '|---|---|---|',
              '| 当前输入、语义和评测范围 | 采用冻结清单中的逐字段用户确认；旧版本 unknown 保留在历史元数据 | 评测范围不是每次运行完成状态，family 不能反推输入 |',
              '| 历史生成版本、当前代码路径冲突、ATE 单位/对齐历史 | manifest 继承第 4 步说明，不读取外部路径，不修源脚本 | 阻止无条件声称跨方法 ATE 已完全可比 |',
              '| FPS/runtime 计时、内存 reserved/device-used/RSS 类型和 GB/GiB 未统一 | 保留原值和来源说明，不再次换算 | 限制效率比较，尤其不能把所有内存列视作同一种测量 |',
              '| 完整轨迹完成、失败原因、未保留记录历史未知 | trajectory_completion_status/failure_reason 在来源层为 unknown | 数值有限不等于成功；未观察到的运行不能补失败或加入 SR 分母 |',
              ('| DSO 五序列导出漏项已恢复：user_confirmed_export_omission_corrected | 实际记录与NA原文保留；不把恢复记录预设为有限结果 | 旧缺口不是未做实验；当前DSO全量SR不能沿用冻结v3的129运行摘要 |'
               if dso_corrected else '| DSO 当前观测 sequence 缺口原因未知；有限重复数仍可能不同 | 保存真实覆盖与次数，不补行、不下采样其它来源 | 不将覆盖差异解释为失败率；重复运行与跨序列变异须区分 |'),
              '| scene 与 shared-condition 的有效集合、ddof 等不同 | 本轮不聚合、不选一个分支作为通用成功规则 | 将来复现旧表仍分别使用原文及各 legacy 规则 |', '',
              '## 回归、原文往返与内存测试', '',
              f'- 原文往返：`{js(roundtrip)}`。',
              f'- DPVO 回归：`{js({k:v for k,v in regression.items() if k != "field_mapping"})}`。',
              '- DPVO 以来源路径/哈希/记录序号关联；比较全部原始列、sequence/run、场景、条件及数值状态，字段映射记入 schema。未重算或覆盖第 5 步结果。', '',
              *[f"- {t['name']}：{'通过' if t['passed'] else '失败'}。" for t in tests], '',
              '这些样例仅在内存，未写入真实记录表。源内容、输出位置和覆盖拒绝测试不会改动源文件。', '',
              '实际全局检查：', '', *[f"- {k}：{v}。" for k, v in checks.items()], '',
              '## 产物与阶段结论', '', *['- `' + p + '`' for p in OUTPUTS.values()],
              '- `scripts/build_analysis_dataset.py`（沿用并扩展的标准化入口）。', '']
    if errors:
        lines += ['当前阻碍：', '', *['- ' + e for e in errors], '',
                  '本次不发布主表、manifest、schema 或覆盖表。若这些文件来自上一次构建，其内容未刷新，不能作为本轮通过的结果。']
    else:
        lines += ['所有输入来源及关键检查通过后才写出五项产物，报告结论来自实际检查。',
                  '可以进入第 7 步限定的探索分析：以可追溯记录和配置/覆盖边界为依据选择问题与数值集合。',
                  '这不批准忽略上表限制做跨方法结论；未知仍为 unknown，不因产物生成升级成 verified。',
                  ('这是已授权数据版本更新中的标准化层；后续阶段由同版本依赖调度器执行，不以旧版计数填充记录。'
                   if INPUT_CONTEXT else '第 7 步尚未开始，等待用户任务；tables/、figures/ 没有本轮新增输出。')]
    lines += ['', '没有源文件改动、轨迹评估、SLAM 重跑、环境/依赖/skills 安装、权限修改、Git 写操作、外部上传或 Toolkit 重构。',
              '执行环境或权限错误以本轮更新日志为准，不将历史沙箱错误冒充当前检查结果。', '']
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--self-test', action='store_true')
    parser.add_argument('--overwrite', action='store_true', help='refresh only the five reviewed step-6 outputs')
    parser.add_argument('--input-manifest', help='workspace-relative frozen current input manifest; paired with --input-manifest-sha256')
    parser.add_argument('--input-manifest-sha256', help='expected SHA-256; defaults to the current version JSON anchor when neither option is supplied')
    args = parser.parse_args()
    tests = self_test()
    print(js({'memory_tests': len(tests), 'passed': all(t['passed'] for t in tests)}))
    if args.self_test:
        for t in tests: print(js(t))
        return
    for rel in OUTPUTS.values(): check_output(WORKSPACE / rel, args.overwrite)
    if args.overwrite and any((WORKSPACE / p).exists() for p in OUTPUTS.values()):
        prior = WORKSPACE / OUTPUTS['report']
        if not prior.is_file() or not prior.read_text().startswith(MARKER):
            raise ValueError('Existing artifacts are not identified as this step-6 build; review them first')
    snapshots = load_input_snapshots(args.input_manifest, args.input_manifest_sha256)
    if len(snapshots) != 24:
        raise ValueError('Reviewed matrix must contain exactly 24 indexed sources')
    if len({r['source_relative_path'] for r in snapshots}) != len(snapshots):
        raise ValueError('Duplicate source in manifest input')
    if len({metadata(r)['configuration_id'] for r in snapshots}) != len(snapshots):
        raise ValueError('This snapshot requires one source per configuration; ambiguous configuration mapping')
    for r in snapshots:
        relative = Path(r['source_relative_path'])
        if relative.is_absolute() or '..' in relative.parts or relative.parts[0] != r['method_directory']:
            raise ValueError('Invalid matrix source path')
        if str(INPUT_ROOT / relative) != r['source_absolute_path']:
            raise ValueError('Current absolute and relative source paths disagree')
    union = list(dict.fromkeys(k for s in snapshots for k in json.loads(s['raw_columns_json'])))
    originals, parsed, converted_by_source, inputs, errors = {}, {}, {}, [], []
    for snapshot in snapshots:
        rel = snapshot['source_relative_path']
        info = {'path': rel, 'expected': snapshot['sha256'], 'status': 'pending'}
        inputs.append(info)
        try:
            raw = read_bytes(source_read_path(WORKSPACE, rel, INPUT_CONTEXT))
            info['before'] = digest(raw)
            require_hash(raw, snapshot['sha256'])
            header, rows = decode_csv(raw)
            if 'dataset' not in header:
                raise ValueError('Missing dataset column')
            diagnostic = diagnose(rows, header)
            # Convert even repeated identifiers without deduplicating; discrepancies
            # block publication of the whole build, rather than silently dropping rows.
            converted = convert_source(rows, header, union, snapshot)
            differences = snapshot_check(diagnostic, snapshot)
            if differences:
                raise ValueError('Snapshot diagnostic differences: ' + js(differences))
            originals[rel] = rows
            parsed[rel] = (header, diagnostic)
            converted_by_source[rel] = converted
            info['status'] = 'hash_and_all_diagnostics_match'
        except (OSError, ValueError, KeyError, csv.Error, StopIteration) as error:
            info['status'] = 'blocked'
            errors.append(rel + ': ' + str(error))
    manifests = []
    for snapshot, info in zip(snapshots, inputs):
        rel = snapshot['source_relative_path']
        try:
            info['after'] = digest(read_bytes(source_read_path(WORKSPACE, rel, INPUT_CONTEXT)))
            if info.get('before') != info['after']:
                raise ValueError('Source changed during processing')
        except (OSError, ValueError) as error:
            info['status'] = 'blocked'
            errors.append(rel + ': ' + str(error))
        if info['status'] == 'hash_and_all_diagnostics_match':
            header, diagnostic = parsed[rel]
            manifests.append(manifest_row(snapshot, header, diagnostic, converted_by_source[rel], info['before'], info['after']))
    all_records = [r for s in snapshots for r in converted_by_source.get(s['source_relative_path'], [])]
    checks = {
        'all_24_sources_hash_structure_match': len(manifests) == len(snapshots) and not errors,
        'per_source_source_output_counts_equal': all(m['source_record_count'] == m['output_record_count'] == m['snapshot_record_count'] for m in manifests),
        'total_matches_matrix_sum': len(all_records) == sum(int(s['record_count']) for s in snapshots),
        'manifest_sum_matches_frozen_version_count': sum(int(s['record_count']) for s in snapshots) == (INPUT_CONTEXT['total_record_count'] if INPUT_CONTEXT else 3153),
        'source_row_keys_unique': len({(r['source_relative_path'], r['source_sha256'], r['source_record_index']) for r in all_records}) == len(all_records),
        'all_source_hashes_unchanged': all(i.get('before') == i.get('after') and 'before' in i for i in inputs),
    }
    command = shlex.join(['/home/yuan/anaconda3/bin/python3', '-B', str(Path(__file__).absolute()), *sys.argv[1:]])
    roundtrip, regression, coverage, outputs = {'passed': False}, {'passed': False}, [], {}
    if not errors and all(checks.values()):
        try:
            outputs['records'] = csv_text(all_records, list(all_records[0]))
            _, decoded = decode_csv(outputs['records'].encode())
            roundtrip = roundtrip_check(decoded, originals, manifests)
            _, pilot = decode_csv(read_bytes(PILOT))
            regression = dpvo_check(decoded, pilot)
            checks['raw_text_roundtrip_passed'] = roundtrip['passed']
            checks['dpvo_regression_passed'] = regression['passed']
            coverage = sequence_coverage(all_records, manifests)
            checks['coverage_counts_conserve_records'] = sum(r['n_records'] for r in coverage) == len(all_records)
            checks['coverage_configuration_sequence_keys_unique'] = len({(r['configuration_id'], r['sequence_raw']) for r in coverage}) == len(coverage)
            checks['finite_view_states_consistent'] = all(
                ((r[name + '_value'] != '') == r[name + '_is_finite'] == r[name + '_state'].startswith('finite_'))
                and (r[name + '_value'] == '' or math.isfinite(r[name + '_value']))
                for r in all_records for name in CORE.values())
            for m in manifests:
                states, finite, old = json.loads(m['core_states_json']), json.loads(m['finite_counts_json']), json.loads(m['raw_numeric_states_json'])
                for raw, name in CORE.items():
                    if sum(states[name].values()) != m['output_record_count'] or states[name] != old[raw]:
                        raise ValueError('Core state counts differ from source snapshot: ' + m['source_relative_path'])
                    if sum(n for k, n in states[name].items() if k.startswith('finite_')) != finite[name]:
                        raise ValueError('Finite count mismatch')
            checks['all_per_source_numeric_states_match'] = True
            outputs['manifest'] = csv_text(manifests, list(manifests[0]))
            outputs['coverage'] = csv_text(coverage, list(coverage[0]))
            schema = schema_document(union, list(all_records[0]), list(manifests[0]), list(coverage[0]), regression['field_mapping'])
            labelled = sum(r['condition_label_status'] == 'two_tokens' for r in all_records)
            if INPUT_CONTEXT and (labelled != INPUT_CONTEXT['condition_labelled_records'] or len(all_records) - labelled != INPUT_CONTEXT['condition_unlabelled_records']):
                raise ValueError('Observed subset counts disagree with the frozen current version')
            schema['validated_snapshot'] = {
                'input_version': INPUT_CONTEXT['current_version'] if INPUT_CONTEXT else 'historical_step04_snapshot',
                'input_manifest': INPUT_CONTEXT['manifest'] if INPUT_CONTEXT else {'path': str(MATRIX.relative_to(WORKSPACE)), 'sha256': MATRIX_HASH},
                'source_count': len(manifests), 'total_record_count': len(all_records),
                'condition_labelled_records': labelled, 'condition_unlabelled_records': len(all_records) - labelled,
                'files': {key: {'path': OUTPUTS[key], 'sha256': digest(outputs[key].encode())} for key in ('records', 'manifest', 'coverage')},
                'historical_matrix': {'path': str(MATRIX.relative_to(WORKSPACE)), 'sha256': MATRIX_HASH},
            }
            if INPUT_CONTEXT:
                schema['validated_snapshot']['version_context'] = {'path': INPUT_CONTEXT['context_path'], 'sha256': INPUT_CONTEXT['context_sha256']}
                if 'frozen_stage07_questions' in INPUT_CONTEXT:
                    schema['validated_snapshot']['frozen_stage07_questions'] = INPUT_CONTEXT['frozen_stage07_questions']
            outputs['schema'] = json.dumps(schema, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
            checks['schema_covers_all_csv_columns'] = True
        except (OSError, ValueError, KeyError, IndexError, csv.Error) as error:
            errors.append('Global validation: ' + str(error))
    errors += ['Check failed: ' + k for k, v in checks.items() if not v]
    # Last source-byte verification immediately before publishing any complete table.
    for item in inputs:
        try:
            latest = digest(read_bytes(source_read_path(WORKSPACE, item['path'], INPUT_CONTEXT)))
            if latest != item.get('before'):
                raise ValueError('Source changed before publication')
            item['after'] = latest
        except (OSError, ValueError) as error:
            errors.append(item['path'] + ': ' + str(error))
    checks['no_source_or_global_blocker'] = not errors
    if INPUT_CONTEXT:
        require_hash(read_bytes(WORKSPACE / INPUT_CONTEXT['manifest']['path']), INPUT_CONTEXT['manifest']['sha256'])
        require_hash(read_bytes(WORKSPACE / INPUT_CONTEXT['context_path']), INPUT_CONTEXT['context_sha256'])
    report = quality_report(manifests, coverage, inputs, tests, roundtrip, regression, checks, command, errors)
    if errors:
        write_output('report', report, args.overwrite)
        raise ValueError('Build blocked; report written, no current dataset published: ' + '; '.join(errors))
    # Validate every serialized CSV and the JSON before publishing. No source writes.
    for key in ('records', 'manifest', 'coverage'): decode_csv(outputs[key].encode())
    json.loads(outputs['schema'])
    for key in ('records', 'manifest', 'schema', 'coverage'): write_output(key, outputs[key], args.overwrite)
    write_output('report', report, args.overwrite)
    print(js({'sources': len(manifests), 'methods': len({r['method_directory'] for r in manifests}),
              'configurations': len(manifests), 'records': len(all_records), 'coverage_rows': len(coverage),
              'coverage_not_observed': sum(not r['observed'] for r in coverage),
              'roundtrip': roundtrip, 'dpvo_regression': {k: v for k, v in regression.items() if k != 'field_mapping'},
              'checks': checks, 'outputs': list(OUTPUTS.values())}))


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, csv.Error, AssertionError, StopIteration) as error:
        print('STOP: ' + str(error), file=sys.stderr)
        sys.exit(1)
