#!/usr/bin/env python3
"""Step 7 only: descriptive exploration of the fixed step-6 standardized input."""
import argparse
from collections import Counter, defaultdict
import hashlib
import io
import json
import math
import os
from pathlib import Path
import shlex
import sys
import tempfile
import textwrap
from unittest.mock import patch

import numpy as np

# Pure I/O helpers only; no previous stage's main() is executed.
from build_analysis_dataset import read_bytes, decode_csv, csv_text, reject_links
from version_support import workspace as controlled_workspace, current_version

WORKSPACE = controlled_workspace('/home/yuan/SLAM/codex_review/benchmark_analysis')
INPUT_CONTEXT = current_version(WORKSPACE)
INPUTS = {
    'records': 'derived_data/06_standardized/run_records.csv',
    'manifest': 'derived_data/06_standardized/source_manifest.csv',
    'schema': 'derived_data/06_standardized/schema.json',
    'quality': 'reports/06_data_quality.md',
    'coverage': 'reports/06_sequence_coverage.csv',
}
OUTPUTS = {
    'spec': 'reports/07_exploration_spec.json',
    'sequence': 'tables/07_eda/sequence_metrics.csv',
    'summary': 'tables/07_eda/descriptive_summary.csv',
    'efficiency': 'tables/07_eda/efficiency_cohort_comparison.csv',
    'cases': 'tables/07_eda/flagged_cases.csv',
    'report': 'reports/07_exploratory_analysis.md',
    'questions': 'reports/07_research_questions.csv',
}
FIGURES = ('01_rmse_distribution', '02_scene_rmse', '03_repeat_rmse',
           '04_finite_rmse_fraction', '05_efficiency_cohorts')
for figure in FIGURES:
    for extension in ('png', 'svg'):
        OUTPUTS[figure + '.' + extension] = f'figures/07_eda/{figure}.{extension}'
METRICS = ('rmse', 'fps', 'runtime', 'memory')
SUBSETS = ('condition_labelled', 'unlabelled', 'all_retained')
LEVELS = ('pooled_retained_runs', 'equal_weight_sequence_means')
SCENES = ('building', 'houses', 'pool', 'road', 'roundabout')
MARKER = '<!-- generated-by: scripts/explore_benchmark.py; exploration-step-7 -->'
META = ('method_directory', 'configuration', 'configuration_id', 'evaluation_scope')
SEQ_META = ('sequence_raw', 'scene', 'condition_label_status', 'speed_level', 'altitude_level', 'speed_mps', 'altitude_m')


def js(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, allow_nan=False)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def parse_bool(text):
    if text not in ('True', 'False'):
        raise ValueError('Invalid boolean text: ' + repr(text))
    return text == 'True'


def fraction(numerator, denominator):
    return numerator / denominator if denominator else None


def describe(values):
    n = len(values)
    names = ('mean', 'median', 'q25', 'q75', 'p90', 'min', 'max', 'sample_sd')
    if n == 0:
        return {name: None for name in names}
    x = np.asarray(values, dtype=float)
    if not np.isfinite(x).all():
        raise ValueError('Nonfinite input to descriptive statistics')
    q25, median, q75, p90 = np.quantile(x, [.25, .5, .75, .9], method='linear')
    return dict(mean=float(np.mean(x)), median=float(median), q25=float(q25), q75=float(q75),
                p90=float(p90), min=float(np.min(x)), max=float(np.max(x)),
                sample_sd=float(np.std(x, ddof=1)) if n >= 2 else None)


def finite_values(rows, metric):
    return [r[metric + '_value'] for r in rows if r[metric + '_is_finite']]


def subset_rows(rows, subset):
    if subset == 'all_retained':
        return rows
    labelled = subset == 'condition_labelled'
    return [r for r in rows if (r['condition_label_status'] == 'two_tokens') == labelled]


def subset_of(row):
    return 'condition_labelled' if row['condition_label_status'] == 'two_tokens' else 'unlabelled'


def unit_limit(source, metric):
    if metric == 'rmse':
        return source['rmse_unit_status'] + '; ' + source['alignment_status']
    protocol = json.loads(source['efficiency_protocol_json'])
    key = {'fps': 'fps_unit_status', 'runtime': 'runtime_unit_status', 'memory': 'memory_conversion_and_kind'}[metric]
    return protocol[key] + '; ' + protocol['evidence_status']


def provenance(rows):
    first = rows[0]
    return {'source_relative_path': first['source_relative_path'], 'source_sha256': first['source_sha256'],
            'source_record_indices_json': js([r['source_record_index'] for r in rows]),
            'retained_run_ids_json': js([r['run_id_raw'] for r in rows]),
            'raw_datasets_json': js([r['raw_dataset'] for r in rows])}


def sequence_table(rows, sources):
    groups = defaultdict(list)
    for row in rows:
        groups[row['configuration_id'], row['sequence_raw']].append(row)
    result = []
    for key, group in sorted(groups.items()):
        group = sorted(group, key=lambda r: r['source_record_index'])
        first = group[0]
        for metric in METRICS:
            used = [r for r in group if r[metric + '_is_finite']]
            values = finite_values(group, metric)
            stat = describe(values)
            result.append({
                **{k: first[k] for k in META + SEQ_META}, 'subset': subset_of(first), 'metric': metric,
                **provenance(group), 'n_retained_runs': len(group), 'n_finite_runs': len(used),
                'finite_run_ids_json': js([r['run_id_raw'] for r in used]),
                'finite_source_record_indices_json': js([r['source_record_index'] for r in used]),
                'finite_values_json': js(values), 'finite_fraction': fraction(len(used), len(group)),
                **{k: stat[k] for k in ('mean', 'median', 'min', 'max')},
                'repeat_sd': stat['sample_sd'],
                'repeat_sd_status': 'estimated_from_finite_repeats' if len(used) >= 2 else 'undefined_fewer_than_two_finite',
                'finite_range': stat['max'] - stat['min'] if used else None,
                'measurement_limit': unit_limit(sources[key[0]], metric),
                'source_manifest_reference': INPUTS['manifest'] + '#configuration_id=' + key[0],
            })
    return result


def summary_group(rows, config, subset, scene, metric, source):
    groups = defaultdict(list)
    for row in rows:
        groups[row['sequence_raw']].append(row)
    values = finite_values(rows, metric)
    means = [describe(x)['mean'] for group in groups.values() if (x := finite_values(group, metric))]
    common = {**{k: source[k] for k in META}, 'subset': subset, 'group_type': 'configuration' if scene == '__all__' else 'scene',
              'scene': scene, 'metric': metric, 'n_retained_records': len(rows), 'n_observed_sequences': len(groups),
              'n_finite_records': len(values), 'n_sequences_with_finite': len(means),
              'n_sequences_without_finite': len(groups) - len(means),
              'finite_fraction': fraction(len(values), len(rows)),
              'n_sequences_repeat_sd_estimable': sum(len(finite_values(g, metric)) >= 2 for g in groups.values()),
              'n_sequences_single_retained_run': sum(len(g) == 1 for g in groups.values()),
              'n_sequences_multiple_retained_insufficient_finite': sum(len(g) > 1 and len(finite_values(g, metric)) < 2 for g in groups.values()),
              'finite_fraction_numerator': len(values), 'finite_fraction_denominator': len(rows),
              'measurement_limit': unit_limit(source, metric),
              'source_manifest_reference': INPUTS['manifest'] + '#configuration_id=' + config}
    return [{**common, 'aggregation_level': level, 'n_values_used': len(v),
             'n_values_unit': 'retained_run_records' if level == LEVELS[0] else 'sequence_means', **describe(v)}
            for level, v in zip(LEVELS, (values, means))]


def descriptive_table(rows, sources):
    result = []
    for config, source in sorted(sources.items()):
        all_rows = [r for r in rows if r['configuration_id'] == config]
        for subset in SUBSETS:
            group = subset_rows(all_rows, subset)
            for metric in METRICS:
                result.extend(summary_group(group, config, subset, '__all__', metric, source))
        main = subset_rows(all_rows, 'condition_labelled')
        for scene in SCENES:
            group = [r for r in main if r['scene'] == scene]
            for metric in METRICS:
                result.extend(summary_group(group, config, 'condition_labelled', scene, metric, source))
    return result


def efficiency_table(rows, sources):
    result = []
    for config, source in sorted(sources.items()):
        for subset in ('all_retained', 'condition_labelled'):
            group = subset_rows([r for r in rows if r['configuration_id'] == config], subset)
            for metric in METRICS[1:]:
                a = [r for r in group if r[metric + '_is_finite']]
                b = [r for r in a if r['rmse_is_finite']]
                excluded = [r for r in a if not r['rmse_is_finite']]
                sa, sb = describe(finite_values(a, metric)), describe(finite_values(b, metric))
                result.append({**{k: source[k] for k in META}, 'subset': subset, 'metric': metric,
                               'n_retained_records': len(group), 'n_A': len(a), 'n_B': len(b), 'n_A_not_B': len(excluded),
                               'A_mean': sa['mean'], 'A_median': sa['median'], 'B_mean': sb['mean'], 'B_median': sb['median'],
                               'B_minus_A_mean': sb['mean'] - sa['mean'] if a and b else None,
                               'source_relative_path': source['source_relative_path'], 'source_sha256': source['source_sha256'],
                               'A_record_indices_json': js([r['source_record_index'] for r in a]),
                               'B_record_indices_json': js([r['source_record_index'] for r in b]),
                               'A_not_B_record_indices_json': js([r['source_record_index'] for r in excluded]),
                               'A_not_B_datasets_json': js([r['raw_dataset'] for r in excluded]),
                               'measurement_limit': unit_limit(source, metric)})
    return result


def flagged_cases(rows, sequences):
    lookup = {(r['configuration_id'], r['sequence_raw'], r['metric']): r for r in sequences}
    result = {}
    def add(seq, reason, record=None):
        kind = 'sequence_descriptor' if record is None else 'retained_run_record'
        identity = [kind, seq['configuration_id'], seq['sequence_raw'], seq['metric'], None if record is None else record['source_record_index']]
        case_id = sha(js(identity).encode())[:20]
        if case_id not in result:
            result[case_id] = {'case_id': case_id, 'case_kind': kind, **{k: seq[k] for k in META + SEQ_META},
                              'subset': seq['subset'], 'metric': seq['metric'], 'source_relative_path': seq['source_relative_path'],
                              'source_sha256': seq['source_sha256'], 'source_record_indices_json': seq['source_record_indices_json'] if record is None else js([record['source_record_index']]),
                              'raw_datasets_json': seq['raw_datasets_json'] if record is None else js([record['raw_dataset']]),
                              'run_ids_json': seq['retained_run_ids_json'] if record is None else js([record['run_id_raw']]),
                              'n_retained': seq['n_retained_runs'], 'n_finite': seq['n_finite_runs'],
                              'finite_source_record_indices_json': seq['finite_source_record_indices_json'],
                              'sequence_mean': seq['mean'], 'repeat_sd': seq['repeat_sd'], 'finite_range': seq['finite_range'],
                              'record_value': None if record is None else record[seq['metric'] + '_value'],
                              'finite_repeat_values_json': seq['finite_values_json'], 'reasons': []}
        result[case_id]['reasons'].append(reason)
    for config in sorted({r['configuration_id'] for r in rows}):
        seqs = [s for s in sequences if s['configuration_id'] == config and s['subset'] == 'condition_labelled' and s['metric'] == 'rmse']
        for field, reason in [('mean', 'top_3_sequence_mean_rmse'), ('repeat_sd', 'top_3_estimable_rmse_repeat_sd')]:
            selected = sorted([s for s in seqs if s[field] is not None], key=lambda s: (-s[field], s['sequence_raw'], s['source_record_indices_json']))[:3]
            for seq in selected: add(seq, reason)
        for metric in METRICS[1:]:
            available = [r for r in subset_rows(rows, 'condition_labelled') if r['configuration_id'] == config and r[metric + '_is_finite']]
            for sign, reason in [(1, 'finite_minimum_record'), (-1, 'finite_maximum_record')]:
                ordered = sorted(available, key=lambda r: (sign * r[metric + '_value'], r['sequence_raw'], r['source_record_index']))
                if ordered:
                    r = ordered[0]
                    add(lookup[config, r['sequence_raw'], metric], reason, r)
    output = []
    for r in sorted(result.values(), key=lambda r: (r['configuration_id'], r['metric'], r['sequence_raw'], r['case_id'])):
        reasons = r.pop('reasons')
        output.append({**r, 'selection_reasons_json': js(reasons), 'interpretation': 'case_to_check_not_confirmed_error_or_failure'})
    return output


def check_output(path, overwrite=False):
    if path not in {WORKSPACE / p for p in OUTPUTS.values()}:
        raise ValueError(f'Outside step-7 output allowlist: {path}')
    reject_links(path)
    if not path.resolve().is_relative_to(WORKSPACE.resolve()):
        raise ValueError('Output escapes workspace')
    if path.exists():
        if not overwrite:
            raise FileExistsError(f'Refusing overwrite: {path}')
        if not path.is_file() or path.stat().st_nlink != 1:
            raise ValueError('Symlink/hardlink/nonregular output rejected: ' + str(path))


def write_output(key, content, overwrite):
    p = WORKSPACE / OUTPUTS[key]
    check_output(p, overwrite)
    p.parent.mkdir(parents=True, exist_ok=True)
    check_output(p, overwrite)
    flags = os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW | (os.O_TRUNC if overwrite else os.O_EXCL)
    with os.fdopen(os.open(p, flags, 0o666), 'wb') as f:
        f.write(content.encode('utf-8') if isinstance(content, str) else content)


def validate_inputs(raw_inputs):
    schema = json.loads(raw_inputs['schema'])
    if schema.get('dataset_status') != 'complete_validated' or schema.get('schema_version') != '1.0.0':
        raise ValueError('Expected reviewed complete schema version 1.0.0')
    header, strings = decode_csv(raw_inputs['records'])
    mh, manifest = decode_csv(raw_inputs['manifest'])
    if header != list(schema['files']['records']['columns']) or mh != list(schema['files']['manifest']['columns']):
        raise ValueError('CSV fields disagree with schema')
    source_by_key = {(m['source_relative_path'], m['source_sha256']): m for m in manifest}
    sources = {m['configuration_id']: m for m in manifest}
    if len(source_by_key) != len(manifest) or len(sources) != len(manifest):
        raise ValueError('Source metadata join is not many-to-one or configuration identity is ambiguous')
    if len(strings) != sum(int(m['output_record_count']) for m in manifest):
        raise ValueError('Record count differs from manifest')
    snapshot = schema.get('validated_snapshot')
    if snapshot:
        for key in ('records', 'manifest', 'coverage'):
            expected = snapshot['files'][key]
            if expected['path'] != INPUTS[key] or sha(raw_inputs[key]) != expected['sha256']:
                raise ValueError('Standardized frozen snapshot hash mismatch: ' + key)
        expected_count = snapshot['total_record_count']
        expected_sources = snapshot['source_count']
    else:
        expected_count, expected_sources = 3153, 24
    if len(strings) != expected_count or len(sources) != expected_sources or len(sources) != 24:
        raise ValueError('Record/configuration count differs from the accepted frozen version')
    keys, source_counts, seq_meta = set(), Counter(), {}
    rows = []
    for original in strings:
        r = dict(original)  # raw_ cells stay untouched; numeric columns get explicit types.
        key = (r['source_relative_path'], r['source_sha256'])
        source = source_by_key[key]
        for field in META + ('modality_declared', 'semantic_usage'):
            if r[field] != source[field]:
                raise ValueError('Metadata association conflict: ' + repr(key))
        index = int(r['source_record_index'])
        if (key, index) in keys:
            raise ValueError('Duplicate source row key')
        keys.add((key, index)); source_counts[key] += 1
        r['source_record_index'] = index
        if r['condition_label_status'] not in ('two_tokens', 'missing_condition_labels'):
            raise ValueError('Unknown condition subset')
        if r['scene'] not in SCENES or not r['sequence_raw']:
            raise ValueError('Unresolved sequence/scene in current standardized input')
        for field in ('speed_mps', 'altitude_m'):
            r[field] = int(r[field]) if r[field] else None
        if (r['condition_label_status'] == 'two_tokens') != (r['speed_mps'] is not None and r['altitude_m'] is not None):
            raise ValueError('Condition fields and status disagree')
        for metric in METRICS:
            finite = parse_bool(r[metric + '_is_finite'])
            state, text = r[metric + '_state'], r[metric + '_value']
            allowed = schema['files']['records']['columns'][metric + '_state']['allowed_values']
            if state not in allowed or finite != (state in ('finite_positive', 'finite_zero', 'finite_negative')):
                raise ValueError('Finite state and flag disagree')
            value = float(text) if text else None
            if finite:
                if value is None or not math.isfinite(value): raise ValueError('Finite value missing/nonfinite')
                sign = 'finite_negative' if value < 0 else 'finite_zero' if value == 0 else 'finite_positive'
                if sign != state: raise ValueError('Finite sign state disagrees')
            elif text != '':
                raise ValueError('Nonfinite metric has a numeric view')
            r[metric + '_is_finite'], r[metric + '_value'] = finite, value
        sq = (r['configuration_id'], r['sequence_raw'])
        metadata = tuple(r[k] for k in SEQ_META)
        if sq in seq_meta and seq_meta[sq] != metadata:
            raise ValueError('Sequence condition/scene metadata conflict')
        seq_meta[sq] = metadata
        rows.append(r)
    for key, source in source_by_key.items():
        if source_counts[key] != int(source['output_record_count']) or source_counts[key] != int(source['source_record_count']):
            raise ValueError('Per-source count mismatch')
    # Coverage is context only, never the source of zero-run observations.
    _, coverage = decode_csv(raw_inputs['coverage'])
    coverage_n = sum(int(r['n_records']) for r in coverage)
    if coverage_n != len(rows): raise ValueError('Coverage count disagrees')
    if snapshot:
        if len(subset_rows(rows, 'condition_labelled')) != snapshot['condition_labelled_records'] or len(subset_rows(rows, 'unlabelled')) != snapshot['condition_unlabelled_records']:
            raise ValueError('Condition subset counts disagree with the accepted frozen version')
    return rows, sources, schema, {'schema_and_fields': True, 'many_to_one_metadata': True,
        'source_row_keys_unique': True, 'per_source_counts': True, 'finite_columns_consistent': True,
        'rows': len(rows), 'configurations': len(sources), 'sequences_per_configuration_total': len(seq_meta),
        'condition_labelled_records': len(subset_rows(rows, 'condition_labelled')),
        'unlabelled_records': len(subset_rows(rows, 'unlabelled'))}


def make_spec(raw_inputs, schema, command):
    return {
        'generated_by': 'scripts/explore_benchmark.py', 'spec_version': '1.0.0',
        'protocol_wording_template': {'path':'scripts/review_all_configurations_narrative.py',
                                      'sha256':sha(Path(__file__).with_name('review_all_configurations_narrative.py').read_bytes())},
        'purpose': 'Exploratory computation parameters, not preregistration and not a change to legacy statistics.',
        'schema_version': schema['schema_version'], 'command': command,
        'validated_input_version': schema.get('validated_snapshot', {}).get('input_version', 'historical_step04_snapshot'),
        'input_snapshot_origin': 'Actual step-7 byte snapshot; no nonexistent historical digest claimed.',
        'inputs': {key: {'path': INPUTS[key], 'sha256': sha(raw),
                        'role': 'only_performance_values' if key == 'records' else 'metadata_or_context'} for key, raw in raw_inputs.items()},
        'subsets': {'condition_labelled': 'condition_label_status == two_tokens; primary',
                    'unlabelled': 'condition_label_status == missing_condition_labels; separate',
                    'all_retained': 'union of the above, supplementary; never add all three counts'},
        'sequence_grouping': ['configuration_id', 'sequence_raw', 'metric'],
        'summary_grouping': 'configuration x subset x metric x aggregation_level; primary subset also by five existing scene keys',
        'aggregation_levels': {'pooled_retained_runs': 'Arithmetic distribution of finite retained run values; not independent samples.',
                               'equal_weight_sequence_means': 'Arithmetic distribution of per-sequence finite-run arithmetic means, equal sequence weights. All-invalid sequences excluded from values but retained in counts.'},
        'numeric_validity': 'Use existing value/state/is_finite; strict True/False string parsing. Independent metric finite sets. Do not parse raw_ into new values.',
        'finite_fraction': 'n_finite retained records / n_retained records; empty denominator undefined, all-invalid nonempty group 0; no historical/unperformed runs.',
        'means': 'Arithmetic; no frame/runtime/sse weighting, RMS-of-RMSE, trimming or imputation.',
        'standard_deviations': {'repeat_sd': 'Within sequence, finite runs, ddof=1, undefined if n<2; never use raw_std.',
                                'sample_sd': 'Distribution at declared summary level, ddof=1, undefined if n_values_used<2; not repeat_sd.'},
        'quantiles': 'NumPy quantile(method=linear), sorted position (n-1)*q; q=.25,.5,.75,.9.',
        'missing_output': 'Empty CSV cells / JSON null for undefined numeric statistics; no zero substitution.',
        'efficiency_cohorts': {'A': 'efficiency metric finite', 'B': 'efficiency metric finite AND rmse finite',
                               'subsets': ['all_retained', 'condition_labelled'], 'comparison': 'within configuration and metric only; B minus A mean; retain excluded record keys'},
        'case_rules': {'primary_subset_only': True, 'high_rmse': 'up to 3 largest finite sequence means per configuration',
                       'repeat': 'up to 3 largest estimable RMSE repeat_sd per configuration',
                       'efficiency': 'one finite minimum and maximum retained record per metric/configuration',
                       'ties': 'sequence_raw then source_record_index; no random selection',
                       'overlap': 'merge reasons for the same case identity; case rows are not new experiments'},
        'figure_selection': {
            'maximum_main_figures': 5, 'scope': 'One configuration per numeric axis; do not compare measurement types across methods.',
            FIGURES[0]: 'Primary RMSE equal-sequence view: >=10 finite sequences, positive mean; largest positive (mean-median)/abs(mean). Ties configuration_id. Plot full ECDF, mean and median.',
            FIGURES[1]: 'Primary RMSE: at least 2 finite sequences in each of 5 scenes, positive overall sequence mean; largest (max scene mean-min scene mean)/abs(overall sequence mean). Plot all sequence means and scene mean/median.',
            FIGURES[2]: 'Primary RMSE sequence with >=2 finite runs and positive mean: largest finite range/abs(mean), ties configuration then sequence; show that configuration top 3 estimable repeat_sd sequences with actual finite runs.',
            FIGURES[3]: 'Primary RMSE: largest fraction of observed sequences with no finite result, ties configuration_id; plot per-scene finite records numerator/denominator and finite sequence counts.',
            FIGURES[4]: 'Primary efficiency comparison with n_A_not_B>0, n_B>0, nonzero A_mean: largest abs(B-A)/abs(A_mean), ties configuration_id then metric. Display A/B mean and median with n.',
            'ratio_boundary': 'Ratios used only as unitless exploratory selection heuristics for positive nonzero means, never as method rankings or causality. Full absolute differences remain in tables/report.',
            'no_candidates': 'Skip category and report reason; never fabricate cases.',
            'rendering': 'Matplotlib Agg, English labels, PNG+SVG, linear axes with full finite range, no CI/stars or hidden outliers.',
            'visual_review': 'Open each PNG after rendering; report remains pending until actual inspection is documented.'},
        'outputs': list(OUTPUTS.values()),
        'interpretation_limits': ['descriptive/exploratory only', 'no whole-trajectory success claim', 'no cross-method pooled mean/rank/score',
            '500-frame versus whole-trajectory separate; unknown scope stays unknown', 'unit/alignment/efficiency history remain qualified in manifest',
            'no mechanism attribution, ANOVA/regression/bootstrap/clustering/SHAP or significance',
            'no systematic height x speed x scene table, paired test, scene-removal validation or cross-method correlation matrix'],
    }


def select_figures(sequences, summary, efficiency):
    overall = {r['configuration_id']: r for r in summary if r['subset'] == 'condition_labelled' and r['scene'] == '__all__' and r['metric'] == 'rmse' and r['aggregation_level'] == LEVELS[1]}
    primary = [s for s in sequences if s['subset'] == 'condition_labelled' and s['metric'] == 'rmse']
    def choose(items, score, tie):
        return sorted(items, key=lambda r: (-score(r), tie(r)))[0] if items else None
    tail = choose([r for r in overall.values() if r['n_sequences_with_finite'] >= 10 and r['mean'] is not None and r['mean'] > 0 and r['mean'] > r['median']],
                  lambda r: (r['mean'] - r['median']) / abs(r['mean']), lambda r: r['configuration_id'])
    scene_candidates = []
    for config, all_row in overall.items():
        parts = [r for r in summary if r['configuration_id'] == config and r['subset'] == 'condition_labelled' and r['scene'] in SCENES and r['metric'] == 'rmse' and r['aggregation_level'] == LEVELS[1]]
        if len(parts) == 5 and all(r['n_values_used'] >= 2 for r in parts) and all_row['mean'] is not None and all_row['mean'] > 0:
            scene_candidates.append({'configuration_id': config, 'parts': parts, 'overall': all_row,
                                     'score': (max(r['mean'] for r in parts) - min(r['mean'] for r in parts)) / abs(all_row['mean'])})
    scene = choose(scene_candidates, lambda r: r['score'], lambda r: r['configuration_id'])
    repeat = choose([s for s in primary if s['n_finite_runs'] >= 2 and s['mean'] > 0],
                    lambda s: s['finite_range'] / abs(s['mean']), lambda s: (s['configuration_id'], s['sequence_raw']))
    missing = choose([r for r in overall.values() if r['n_observed_sequences'] > 0],
                     lambda r: r['n_sequences_without_finite'] / r['n_observed_sequences'], lambda r: r['configuration_id'])
    cohort = choose([r for r in efficiency if r['subset'] == 'condition_labelled' and r['n_A_not_B'] > 0 and r['n_B'] > 0 and r['A_mean'] is not None and r['A_mean'] > 0],
                    lambda r: abs(r['B_minus_A_mean']) / abs(r['A_mean']), lambda r: (r['configuration_id'], r['metric']))
    return {'tail': tail, 'scene': scene, 'repeat': repeat, 'missing': missing, 'cohort': cohort}


def retain_original_questions(schema, sequences, summary, efficiency, candidates):
    """Re-evaluate existing questions, recording changed automatic candidates separately."""
    snapshot = schema.get('validated_snapshot', {})
    frozen = snapshot.get('frozen_stage07_questions')
    if not frozen:
        return candidates, None, []
    rel = Path(frozen['path'])
    if rel.is_absolute() or '..' in rel.parts:
        raise ValueError('Frozen question path must remain inside the analysis workspace')
    raw = read_bytes(WORKSPACE / rel)
    if sha(raw) != frozen['sha256']:
        raise ValueError('Historical question snapshot hash mismatch')
    _, original = decode_csv(raw)
    question_by_id = {q['question_id']: q for q in original}
    mapping = dict(zip(('Q1', 'Q2', 'Q3', 'Q4', 'Q5'), ('tail', 'scene', 'repeat', 'missing', 'cohort')))
    if set(question_by_id) != set(mapping) or len(original) != len(mapping):
        raise ValueError('Expected the five frozen stage-7 questions exactly once')
    selected, comparisons = {}, []
    for qid, category in mapping.items():
        question = question_by_id[qid]
        config = question['configuration_id']
        seq = [r for r in sequences if r['configuration_id'] == config]
        desc = [r for r in summary if r['configuration_id'] == config]
        eff = [r for r in efficiency if r['configuration_id'] == config]
        if category == 'cohort':
            metric = question['supporting_table_key'].rsplit('/', 1)[-1]
            selected[category] = next(r for r in eff if r['subset'] == 'condition_labelled' and r['metric'] == metric)
        else:
            selected[category] = select_figures(seq, desc, eff)[category]
        if selected[category] is None:
            raise ValueError('Original case has insufficient current data for its existing plot: ' + qid)
        candidate = candidates[category]
        comparisons.append({'question_id': qid, 'category': category, 'retained_configuration_id': config,
                            'current_rule_candidate_configuration_id': candidate['configuration_id'] if candidate else None,
                            'retained_metric': selected[category].get('metric'),
                            'current_rule_candidate_metric': candidate.get('metric') if candidate else None,
                            'selection_changed': candidate is None or candidate['configuration_id'] != config
                              or (category == 'cohort' and candidate.get('metric') != selected[category].get('metric'))})
    return selected, {'policy': 'Keep the five historical question/configuration anchors during this controlled input update; recompute all observations, not a new case selection.',
                      'source': frozen, 'candidate_comparison': comparisons}, original


def restore_question_anchors(questions, original, sequences):
    if not original:
        return questions
    by_id = {q['question_id']: q for q in original}
    for q in questions:
        old = by_id[q['question_id']]
        if q['configuration_id'] != old['configuration_id']:
            raise ValueError('Historical question configuration changed')
        q['current_observed_sequence_names_json'] = q['sequence_names_json']
        q['historical_question_anchor_names_json'] = old['sequence_names_json']
        names = json.loads(old['sequence_names_json'])
        by_name = {s['sequence_raw']: s for s in sequences if s['configuration_id'] == q['configuration_id'] and s['metric'] == 'rmse'}
        if any(name not in by_name for name in names):
            raise ValueError('An original question anchor is absent in the current data')
        q['sequence_names_json'] = old['sequence_names_json']
        q['source_evidence_json'] = js([{'sequence': name, 'scene': by_name[name]['scene'],
           'source_relative_path': by_name[name]['source_relative_path'], 'source_sha256': by_name[name]['source_sha256'],
           'record_indices': json.loads(by_name[name]['source_record_indices_json']),
           'finite_record_indices': json.loads(by_name[name]['finite_source_record_indices_json'])} for name in names])
        for field in ('next_question', 'alternative_explanation', 'refuting_result', 'suggested_stage'):
            q[field] = old[field]
        q['question_role'] = 'historical_question_reassessed_on_current_frozen_input'
    return questions


def fmt(value):
    return '未定义' if value is None else format(value, '.6g')


def chart_rows(sequences, config):
    return [s for s in sequences if s['configuration_id'] == config and s['subset'] == 'condition_labelled' and s['metric'] == 'rmse']


def repeat_examples(sequences, config):
    return sorted([s for s in chart_rows(sequences, config) if s['repeat_sd'] is not None],
                  key=lambda s: (-s['repeat_sd'], s['sequence_raw']))[:3]


def draw_figures(selected, sequences, summary, sources, overwrite):
    # Matplotlib is imported only after directing its cache to a task-owned folder.
    temp_root = WORKSPACE / 'reports/.07_exploration_tmp'
    reject_links(temp_root)
    created_root = not temp_root.exists()
    temp_root.mkdir(exist_ok=True)
    saved_env = {k: os.environ.get(k) for k in ('MPLCONFIGDIR', 'XDG_CACHE_HOME', 'TMPDIR')}
    figures = []
    try:
        with tempfile.TemporaryDirectory(prefix='run_', dir=temp_root) as tmp:
            for k in saved_env: os.environ[k] = tmp
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10, 'axes.titlesize': 12,
                                 'svg.hashsalt': 'benchmark-step7', 'axes.spines.top': False, 'axes.spines.right': False})
            def save(fig, name, config, question, unit, n_note):
                scope = sources[config]['evaluation_scope']
                footer = f'{config} | condition_labelled | scope={scope}\n{n_note}\n{unit}; source-reported values, no unit conversion; upstream protocol/history unverified.'
                fig.text(.02, .015, footer, va='bottom', fontsize=8)
                fig.subplots_adjust(bottom=.25, top=.78 if name == FIGURES[2] else .86, left=.10, right=.97)
                fig.suptitle(question + '\n' + config, fontsize=14, y=.98)
                hashes = {}
                for ext in ('png', 'svg'):
                    buffer = io.BytesIO()
                    metadata = {'Software': 'benchmark step-7 exploration'} if ext == 'png' else {'Date': None, 'Creator': 'benchmark step-7 exploration'}
                    fig.savefig(buffer, format=ext, dpi=160, bbox_inches='tight', metadata=metadata)
                    raw = buffer.getvalue(); hashes[ext] = sha(raw)
                    write_output(name + '.' + ext, raw, overwrite)
                plt.close(fig)
                figures.append({'name': name, 'configuration_id': config, 'subset': 'condition_labelled',
                                'question': question, 'caption': footer, 'sha256': hashes})
            r = selected['tail']
            if r:
                config = r['configuration_id']; seq = chart_rows(sequences, config)
                values = sorted(s['mean'] for s in seq if s['mean'] is not None)
                fig, ax = plt.subplots(figsize=(9, 5.7))
                ax.step(values, np.arange(1, len(values) + 1) / len(values), where='post', color='#2166ac', label='Finite sequence means')
                ax.scatter(values, np.arange(1, len(values) + 1) / len(values), s=15, color='#2166ac')
                ax.axvline(r['mean'], color='#b2182b', label=f'Mean = {fmt(r["mean"])}')
                ax.axvline(r['median'], color='#1b7837', linestyle='--', label=f'Median = {fmt(r["median"])}')
                ax.set(xlabel='Sequence-mean RMSE (source units)', ylabel='Empirical cumulative fraction', ylim=(0, 1.04))
                ax.legend(loc='lower right'); ax.grid(alpha=.18)
                save(fig, FIGURES[0], config, 'Does the mean describe most finite sequences?', 'Unit: RMSE source units',
                     f'Unit of distribution: sequence mean; finite sequences {len(values)}/{len(seq)}; finite runs {r["n_finite_records"]}/{r["n_retained_records"]}')
            r = selected['scene']
            if r:
                config = r['configuration_id']; fig, ax = plt.subplots(figsize=(9.5, 6.1))
                seq = chart_rows(sequences, config); labels = []
                for i, scene in enumerate(SCENES):
                    s = next(p for p in r['parts'] if p['scene'] == scene)
                    values = [p['mean'] for p in seq if p['scene'] == scene and p['mean'] is not None]
                    ax.scatter(i + np.linspace(-.13, .13, len(values)), values, color='#2166ac', s=25, alpha=.75, label='Sequence means' if i == 0 else None)
                    if values:
                        ax.scatter(i, s['mean'], color='#b2182b', marker='D', s=65, label='Scene mean' if i == 0 else None)
                        ax.scatter(i, s['median'], color='#1b7837', marker='_', s=240, linewidths=2, label='Scene median' if i == 0 else None)
                    labels.append(f'{scene}\nseq {s["n_sequences_with_finite"]}/{s["n_observed_sequences"]}\nruns {s["n_finite_records"]}/{s["n_retained_records"]}')
                ax.set_xticks(range(5), labels); ax.set_ylabel('Sequence-mean RMSE (source units)'); ax.grid(axis='y', alpha=.18)
                ax.legend(loc='upper left')
                save(fig, FIGURES[1], config, 'How do finite sequence means differ by scene?', 'Unit: RMSE source units',
                     f'Each dot is one sequence mean; labels give finite/retained sequences and finite/retained runs; {len(seq)} observed sequences')
            r = selected['repeat']
            if r:
                config = r['configuration_id']; examples = repeat_examples(sequences, config)
                fig, axes = plt.subplots(1, len(examples), figsize=(11, 6.2), squeeze=False, sharey=True)
                for ax, s in zip(axes[0], examples):
                    values = json.loads(s['finite_values_json']); runs = json.loads(s['finite_run_ids_json'])
                    ax.scatter(range(len(values)), values, s=55, color='#2166ac')
                    ax.axhline(s['mean'], linestyle=':', color='#b2182b')
                    ax.set_xticks(range(len(values)), runs); ax.set_xlabel('Retained run ID (identifier)')
                    title = '\n'.join(textwrap.wrap(s['sequence_raw'], 26))
                    ax.set_title(title + f'\nfinite/retained={s["n_finite_runs"]}/{s["n_retained_runs"]}\nrepeat_sd={fmt(s["repeat_sd"])}', fontsize=9)
                    for i, value in enumerate(values): ax.annotate(format(value, '.4g'), (i, value), xytext=(0, 7), textcoords='offset points', ha='center', fontsize=8)
                    ax.margins(x=.3, y=.2); ax.grid(axis='y', alpha=.18)
                axes[0][0].set_ylabel('Run RMSE (source units)')
                save(fig, FIGURES[2], config, 'How far apart are retained finite repeat values?', 'Unit: RMSE source units',
                     'Each dot: finite run; dotted line: sequence mean; top 3 estimable repeat_sd sequences; ddof=1, no confidence intervals')
            r = selected['missing']
            if r:
                config = r['configuration_id']; fig, ax = plt.subplots(figsize=(9.5, 5.8))
                parts = [s for s in summary if s['configuration_id'] == config and s['subset'] == 'condition_labelled' and s['scene'] in SCENES and s['metric'] == 'rmse' and s['aggregation_level'] == LEVELS[1]]
                for i, scene in enumerate(SCENES):
                    s = next(p for p in parts if p['scene'] == scene)
                    value = s['finite_fraction']
                    if value is not None: ax.bar(i, value, color='#4c78a8', width=.6)
                    label = f'{s["n_finite_records"]}/{s["n_retained_records"]}' + (' undefined' if value is None else '')
                    ax.text(i, (value if value is not None else 0) + .035, label, ha='center')
                ax.set_xticks(range(5), [f'{p["scene"]}\nfinite sequences {p["n_sequences_with_finite"]}/{p["n_observed_sequences"]}' for p in parts])
                ax.set(ylim=(0, 1.18), ylabel='Finite RMSE records / retained records'); ax.grid(axis='y', alpha=.18)
                save(fig, FIGURES[3], config, 'Finite RMSE records are not trajectory success', 'Unit: dimensionless record fraction',
                     f'Numerators/denominators shown above bars; total finite runs {r["n_finite_records"]}/{r["n_retained_records"]}; no absent runs added')
            r = selected['cohort']
            if r:
                config = r['configuration_id']; fig, ax = plt.subplots(figsize=(9, 5.6))
                for stat, marker, color, dx in [('mean', 'D', '#b2182b', -.07), ('median', 'o', '#2166ac', .07)]:
                    values = [r['A_' + stat], r['B_' + stat]]
                    ax.scatter(np.array([0, 1]) + dx, values, marker=marker, color=color, s=75, label=stat)
                    for i, v in enumerate(values): ax.annotate(format(v, '.6g'), (i + dx, v), xytext=(0, 10 if stat == 'mean' else -17), textcoords='offset points', ha='center')
                ax.set_xticks([0, 1], [f'A: efficiency finite\nn={r["n_A"]}', f'B: efficiency + RMSE finite\nn={r["n_B"]}'])
                ax.set_xlim(-.4, 1.4); ax.set_ylabel(r['metric'] + ' (source units)')
                all_values = [r[k] for k in ('A_mean', 'A_median', 'B_mean', 'B_median')]
                ax.set_ylim(min(0, min(all_values)), max(all_values) * 1.25 if max(all_values) > 0 else 1)
                ax.legend(); ax.grid(axis='y', alpha=.18)
                save(fig, FIGURES[4], config, 'Does RMSE filtering change this efficiency summary?', 'Unit: ' + r['metric'] + ' source units',
                     f'Statistical unit: finite retained run; removed {r["n_A_not_B"]}; B-A mean={fmt(r["B_minus_A_mean"])}; descriptive subset change only')
    finally:
        for key, value in saved_env.items():
            if value is None: os.environ.pop(key, None)
            else: os.environ[key] = value
        if created_root and temp_root.exists() and not any(temp_root.iterdir()): temp_root.rmdir()
    return figures


def finding_records(selected, sequences, summary, efficiency, sources):
    findings, questions = [], []
    def add(fid, title, config, observation, sequence_list, figure, table_key, limits, question, alternative, falsifier, stage='8'):
        evidence = [{'sequence': s['sequence_raw'], 'scene': s['scene'], 'source_relative_path': s['source_relative_path'],
                     'source_sha256': s['source_sha256'], 'record_indices': json.loads(s['source_record_indices_json']),
                     'finite_record_indices': json.loads(s['finite_source_record_indices_json'])} for s in sequence_list]
        findings.append({'id': fid, 'title': title, 'configuration_id': config, 'observation': observation,
                         'table_key': table_key, 'figure': figure, 'source_evidence': evidence,
                         'limits': limits, 'unverified_explanations': alternative, 'next_check': question,
                         'refutation': falsifier, 'measurement_limit': unit_limit(sources[config], 'rmse' if fid != 'F5' else selected['cohort']['metric'])})
        questions.append({'question_id': 'Q' + fid[1:], 'observation': observation, 'configuration_id': config,
                          'sequence_names_json': js([s['sequence_raw'] for s in sequence_list]),
                          'source_evidence_json': js(evidence), 'next_question': question,
                          'alternative_explanation': alternative, 'refuting_result': falsifier,
                          'required_data': 'Existing step-6 records and manifest for stage 8; mechanism attribution would require separately authorized logs/collection or evaluation metadata.',
                          'suggested_stage': stage, 'supporting_table_key': table_key, 'supporting_figure': figure})
    r = selected['tail']
    if r:
        config = r['configuration_id']; seqs = chart_rows(sequences, config)
        top = sorted([s for s in seqs if s['mean'] is not None], key=lambda s: (-s['mean'], s['sequence_raw']))[:3]
        pooled = next(p for p in summary if p['configuration_id'] == config and p['subset'] == 'condition_labelled' and p['scene'] == '__all__' and p['metric'] == 'rmse' and p['aggregation_level'] == LEVELS[0])
        finite_means = [s['mean'] for s in seqs if s['mean'] is not None]
        share = sum(s['mean'] for s in top) / sum(finite_means) if finite_means and min(finite_means) >= 0 and sum(finite_means) > 0 else None
        details = '；'.join(f"{s['sequence_raw']}（{s['scene']}，均值 {fmt(s['mean'])}，有限/保留 {s['n_finite_runs']}/{s['n_retained_runs']}）" for s in top)
        observation = (f"condition_labelled、序列均值等权：mean={fmt(r['mean'])}，median={fmt(r['median'])}，绝对差={fmt(abs(r['mean']-r['median']))}，"
                       f"p90={fmt(r['p90'])}，max={fmt(r['max'])}；有效序列 {r['n_sequences_with_finite']}/{r['n_observed_sequences']}，有限记录 {r['n_finite_records']}/{r['n_retained_records']}。"
                       f"逐次 pooled mean={fmt(pooled['mean'])}，与序列等权均值绝对差={fmt(abs(pooled['mean']-r['mean']))}。最高三条为 {details}。"
                       + (f"这三条的均值之和占全部有限序列均值之和 {share:.2%}（仅为描述性集中程度）。" if share is not None else '均值和占比不适用。'))
        add('F1', '序列均值的尾部使平均值偏离多数序列', config, observation, top, FIGURES[0],
            f"descriptive_summary: {config}/condition_labelled/__all__/rmse/{LEVELS[1]}; sequence_metrics: top three named sequences/rmse",
            '只描述现有有限结果；序列均值会受有限重复次数影响，均值和占比不是误差能量或总体失败比例。',
            '在这些高误差序列所属场景内，名义高度×速度条件是否集中出现较大序列均值，还是跨多个条件分散出现？',
            '场景和路线组成、少量偏离运行、有限结果选择均可能解释尾部；运动或算法机制未证实。',
            '第 8 步若高值跨名义条件分散、由单次重复主导，或有效覆盖差异足以解释表象，则不支持稳定的条件集中模式。')
    r = selected['scene']
    if r:
        config = r['configuration_id']; parts = sorted(r['parts'], key=lambda p: (-p['mean'], p['scene']))
        high, low = parts[0], parts[-1]
        seqs = sorted([s for s in chart_rows(sequences, config) if s['scene'] == high['scene'] and s['mean'] is not None], key=lambda s: (-s['mean'], s['sequence_raw']))[:3]
        observation = (f"condition_labelled、序列均值等权：{high['scene']} mean={fmt(high['mean'])}、median={fmt(high['median'])}；"
                       f"{low['scene']} mean={fmt(low['mean'])}、median={fmt(low['median'])}；两场景均值绝对差={fmt(high['mean']-low['mean'])}。"
                       f"前者有效序列 {high['n_sequences_with_finite']}/{high['n_observed_sequences']}、有限记录 {high['n_finite_records']}/{high['n_retained_records']}；"
                       f"后者为 {low['n_sequences_with_finite']}/{low['n_observed_sequences']}、{low['n_finite_records']}/{low['n_retained_records']}。")
        add('F2', '同一配置内部的场景差异值得进一步拆分', config, observation, seqs, FIGURES[1],
            f"descriptive_summary: {config}/condition_labelled/[{high['scene']},{low['scene']}]/rmse/{LEVELS[1]}",
            '场景包含不同路线与条件组成，不是场景的因果效应，也不表示该场景对所有方法最难。',
            f"优先在 {config} 的 {high['scene']} 场景查看高度×速度联合分布，并与该配置其它场景的条件覆盖说明并列检查，差异是否由少数组合主导？",
            '少数路线、条件组成、重复运行数值和缺失选择均可能产生场景边际差异；场景复杂度或运动机制未证实。',
            '若该场景各可观察条件均类似、原差异主要是路线或重复波动，而非集中组合，则不支持特定高度×速度模式。')
    r = selected['repeat']
    if r:
        config = r['configuration_id']; examples = repeat_examples(sequences, config); s = examples[0]
        descriptor = next(p for p in summary if p['configuration_id'] == config and p['subset'] == 'condition_labelled' and p['scene'] == '__all__' and p['metric'] == 'rmse' and p['aggregation_level'] == LEVELS[1])
        observations = list(zip(json.loads(s['finite_run_ids_json']), json.loads(s['finite_values_json']), json.loads(s['finite_source_record_indices_json'])))
        observation = (f"condition_labelled 中 {s['sequence_raw']} 的现有有限重复值（run_id, rmse, 来源索引）={js(observations)}；"
                       f"极差={fmt(s['finite_range'])}，repeat_sd={fmt(s['repeat_sd'])}，有限/保留次数={s['n_finite_runs']}/{s['n_retained_runs']}。"
                       f"该配置主子集可估计 RMSE repeat_sd 的序列数为 {descriptor['n_sequences_repeat_sd_estimable']}/{descriptor['n_observed_sequences']}；"
                       f"只保留一次 {descriptor['n_sequences_single_retained_run']} 条，多次保留但有限值不足两次 {descriptor['n_sequences_multiple_retained_insufficient_finite']} 条。")
        add('F3', '部分序列的重复值差距不能由一个均值概括', config, observation, examples, FIGURES[2],
            f"sequence_metrics: {config}/[{','.join(s['sequence_raw'] for s in examples)}]/rmse",
            'repeat_sd 仅描述当前有限的少量重复，不是模型不确定性或置信区间；同编号跨方法不作配对。',
            f"第 8 步在 {config} 的这些序列所属场景中，较大重复极差与较大序列平均 RMSE 是否出现在相同的名义高度×速度位置？",
            '单次偏离、有限重复过少、未确认的执行差异都可能造成表象；不归因于初始化、关键帧或模糊。',
            '若大极差不在条件上重复出现、与均值高值位置不一致，则不支持稳定的条件相关波动模式。')
    r = selected['missing']
    if r:
        config = r['configuration_id']; bad = [s for s in chart_rows(sequences, config) if s['n_finite_runs'] == 0]
        observation = (f"condition_labelled 的有限 RMSE 记录比例={r['n_finite_records']}/{r['n_retained_records']}={fmt(r['finite_fraction'])}；"
                       f"有效序列 {r['n_sequences_with_finite']}/{r['n_observed_sequences']}，其中 {r['n_sequences_without_finite']} 条序列没有有限 RMSE。"
                       f"有限序列等权 mean={fmt(r['mean'])}、median={fmt(r['median'])}，这些数值排除了上述全无效序列；不能据此称更鲁棒。")
        add('F4', '平均误差必须与有限记录覆盖共同阅读', config, observation, bad, FIGURES[3],
            f"descriptive_summary: {config}/condition_labelled/__all__/rmse/{LEVELS[1]}; sequence_metrics n_finite_runs=0",
            '有限比例不是完整轨迹成功率；缺失原因须按逐运行证据区分，不能从NA自动推断失败。本阶段分母采用实际保留记录，不替代独立SR专题的运行集合及作者确认。',
            f"第 8 步在 {config} 中，全无效或部分无效序列是否在特定场景的名义高度×速度组合集中？先展示存在性和有限数量，再解释误差。",
            '未保留/导出状态、不同路线或条件组成可能影响可用性；当前数据不能区分缺失机制。',
            '若无效结果在场景和条件中分散，或覆盖信息不足，则不能支持某个飞行条件导致不可用的解释。')
    r = selected['cohort']
    if r:
        config = r['configuration_id']; indices = set(json.loads(r['A_not_B_record_indices_json']))
        involved = [s for s in chart_rows(sequences, config) if indices.intersection(json.loads(s['source_record_indices_json']))]
        observation = (f"{r['subset']}、{r['metric']}：A（该效率有限）n={r['n_A']}，mean={fmt(r['A_mean'])}、median={fmt(r['A_median'])}；"
                       f"B（效率与 RMSE 均有限）n={r['n_B']}，mean={fmt(r['B_mean'])}、median={fmt(r['B_median'])}；"
                       f"B-A 均值差={fmt(r['B_minus_A_mean'])}，排除 {r['n_A_not_B']} 条来源记录 {r['A_not_B_record_indices_json']}。")
        add('F5', 'RMSE 筛选会改变同一配置的效率描述', config, observation, involved, FIGURES[4],
            f"efficiency_cohort_comparison: {config}/condition_labelled/{r['metric']}",
            '仅是更换记录集合后的描述变化，不证明 A/B 哪个更正确，不表示 RMSE 导致效率变化。',
            f"第 8 步在 {config} 中检查被 RMSE 筛选排除的这些现有记录属于哪些场景和条件，效率集合变化是否集中于少数组合？",
            '被排除记录的执行时长/测量阶段或保留方式可能不同；原因需要另行授权的上游材料，不能从本轮断定。',
            '若排除记录没有条件集中或 A/B 差异由单条记录决定，则不支持普遍的条件相关效率变化。')
    return findings, questions


def exploration_report(findings, figures, sequences, summary, efficiency, sources, spec, checks, tests, command):
    from review_all_configurations_narrative import protocol_note
    lines = [MARKER, '# 第 7 步：第一轮探索分析', '',
             protocol_note({'accuracy_protocol_by_configuration':sources}), '', '本轮发现', '']
    for finding in findings:
        lines += [f"## {finding['id']}．{finding['title']}（{finding['configuration_id']}）", '', finding['observation'], '',
                  f"图：[{finding['figure']}.png](../figures/07_eda/{finding['figure']}.png)。表格键：`{finding['table_key']}`。", '',
                  '来源索引：`' + js(finding['source_evidence']) + '`。', '',
                  '**限制：**' + finding['limits'] + ' 单位/测量边界：' + finding['measurement_limit'] + '。',
                  '**尚未证实的解释：**' + finding['unverified_explanations'],
                  '**下一步验证／反驳：**' + finding['next_check'] + ' ' + finding['refutation'], '']
    lines += ['## 全配置主子集的误差、权重与重复描述', '',
              '下表均为 condition_labelled、RMSE；P 为有限逐次 pooled 均值，S 为序列均值等权。',
              '不同配置逐行独立描述，不作排名，不统一物理单位。全部三子集、四指标与两层级见完整 CSV。', '',
              '| 配置 | 有限记录/保留 | 有效序列/观测 | P mean | S mean | S median | S p90 | abs(P-S) | abs(S mean-median) | 可估 repeat_sd/仅保留一次/多次但有限不足 |',
              '|---|---|---|---:|---:|---:|---:|---:|---:|---|']
    for config in sorted(sources):
        group = [r for r in summary if r['configuration_id'] == config and r['subset'] == 'condition_labelled' and r['scene'] == '__all__' and r['metric'] == 'rmse']
        p = next(r for r in group if r['aggregation_level'] == LEVELS[0]); s = next(r for r in group if r['aggregation_level'] == LEVELS[1])
        diff = abs(p['mean']-s['mean']) if p['mean'] is not None and s['mean'] is not None else None
        gap = abs(s['mean']-s['median']) if s['mean'] is not None else None
        lines.append(f"| `{config}` | {s['n_finite_records']}/{s['n_retained_records']} | {s['n_sequences_with_finite']}/{s['n_observed_sequences']} | " + ' | '.join(fmt(v) for v in [p['mean'], s['mean'], s['median'], s['p90'], diff, gap]) + f" | {s['n_sequences_repeat_sd_estimable']}/{s['n_sequences_single_retained_run']}/{s['n_sequences_multiple_retained_insufficient_finite']} |")
    singleton = [r for r in summary if r['subset']=='condition_labelled' and r['scene']=='__all__' and r['metric']=='rmse' and r['aggregation_level']==LEVELS[1] and r['n_sequences_single_retained_run']]
    lines += ['', '仅一次保留的配置：' + ('；'.join(f"{r['configuration_id']} 有 {r['n_sequences_single_retained_run']} 条主子集序列仅保留一次，RMSE repeat_sd 可估条数 {r['n_sequences_repeat_sd_estimable']}" for r in singleton) or '当前主子集没有仅一次保留的配置') + '。有限值不足两次时标准差仍未定义，不是零波动。', '',
              '## 效率集合敏感性与无标签补充', '',
              'A 为效率自身有限，B 再要求 RMSE 有限；下表仅列集合发生变化的项，其余配置也在完整表中保留 A/B 结果。', '',
              '| 配置 | 子集 | 指标 | A/B n | A mean | B mean | B-A | 排除来源索引 |', '|---|---|---|---|---:|---:|---:|---|']
    for r in efficiency:
        if r['n_A_not_B']:
            lines.append(f"| `{r['configuration_id']}` | {r['subset']} | {r['metric']} | {r['n_A']}/{r['n_B']} | {fmt(r['A_mean'])} | {fmt(r['B_mean'])} | {fmt(r['B_minus_A_mean'])} | `{r['A_not_B_record_indices_json']}` |")
    excluded = {subset: {(r['source_relative_path'], r['source_sha256'], i) for r in efficiency if r['subset']==subset for i in json.loads(r['A_not_B_record_indices_json'])} for subset in ('all_retained','condition_labelled')}
    lines += ['', f"按来源键去重后的相关记录：all_retained={len(excluded['all_retained'])}，condition_labelled={len(excluded['condition_labelled'])}；无标签部分={len(excluded['all_retained']-excluded['condition_labelled'])}。这是记录集合计数，不把三个效率指标重复计为三次实验。", '',
              '无标签与 all_retained 的四指标两层级结果均保存在 descriptive_summary.csv；主场景图仅用 condition_labelled。',
              '三子集不得相加：condition_labelled 与 unlabelled 构成 all_retained。25fps 不解释为飞行条件或数据年代。', '',
              '## 图表选择与图注', '',
              '选择规则在读取性能值后的描述计算之前写入 spec；属于探索性选图，不是预注册或跨方法排名。',
              '使用配置内的无量纲差异作为选图线索，报告绝对差与原来源单位；未展示的配置不能据此视为没有问题。', '']
    for figure in figures:
        lines += [f"- **{figure['name']}**：{figure['question']}。配置 `{figure['configuration_id']}`。", '  图注：' + figure['caption'].replace('\n', '；'),
                  '  对应规则：' + spec['figure_selection'][figure['name']], '  PNG SHA-256：`' + figure['sha256']['png'] + '`。']
    lines += ['', '每图同时保存 PNG 和 SVG，独立配置的数值轴不与其它方法共享；无 CI、显著性星号或隐藏尾部。', '',
              '<!-- VISUAL_REVIEW_START -->', 'PNG 实际打开检查：待完成；文件成功写出不等于视觉检查通过。', '<!-- VISUAL_REVIEW_END -->', '',
              '## 计算规则、数据限制与可复跑性', '',
              '逐序列表是一条配置×实际序列×指标的描述，不是新实验。所有全无效序列仍有 n_retained/n_finite，数值为空。',
              '逐次值与序列均值等权两层级均为算术均值；分位数 linear，位置 (n-1)q；sample_sd/repeat_sd 均 ddof=1，少于两个有限值未定义。',
              'source_record_index 和原始 run_id 保留；原始 raw_std 不参与重复标准差。缺失指标不删除整条记录，效率各自取有限集合。',
              '序列等权无法消除缺失选择；有限比例不等于完整轨迹成功率。当前 500 帧与完整轨迹分开，未知 scope 不改名。',
              '这些是新的 exploration 规则，不是复现旧 scene summary；不通过调整门控、ddof 或权重追求旧表一致。',
              '未做高度×速度×场景系统汇总、配对检验、逐场景剔除、跨方法相关矩阵或推断；替代解释只列为待验证问题。', '',
              '输入快照为本轮实际读取字节，没有虚构与未保存的第 6 步派生哈希一致。', '',
              '| 输入 | SHA-256（执行前后相同） | 角色 |', '|---|---|---|']
    for item in spec['inputs'].values(): lines.append(f"| `{item['path']}` | `{item['sha256']}` | {item['role']} |")
    lines += ['', '入口及结果检查：`' + js(checks) + '`。', '', '真实计算前的内存测试：', '', *['- ' + t for t in tests], '',
              '缓存只在 reports/.07_exploration_tmp/ 本轮创建的子目录中，已清理本轮内容；未修改 HOME 或永久配置。',
              '普通执行器 mountinfo 错误通过工具允许的限定审批处理。没有访问 experiment_data 或重新执行第 3～6 步。', '',
              '实际运行命令：', '', '```bash', f'/home/yuan/anaconda3/bin/python3 -B {WORKSPACE}/scripts/explore_benchmark.py --self-test', command, '```', '',
              '审阅后可加 `--overwrite` 复跑，仅刷新本轮固定输出；之后须重新实际查看 PNG。默认拒绝覆盖，不跟随输出软/硬链接。', '',
              '实际输出：', '', *['- `' + p + '`' for p in OUTPUTS.values()], '',
              '新增脚本：`scripts/explore_benchmark.py`；现有 AGENTS 与第 1～6 步产物保持只读。', '',
              '## 下一阶段候选', '',
              '具体可验证问题见 [07_research_questions.csv](07_research_questions.csv)。优先从 F1/F2/F3 涉及的配置和场景开展第 8 步条件联合描述；',
              '同时记录 F4 覆盖与 F5 效率筛选敏感性，先展示各单元实际次数和有限数量，再解释误差。',
              ('机制解释仍需额外证据；本轮为已授权数据版本更新，现有问题由同版本依赖流程继续核验，不自动引入新问题。'
               if spec.get('frozen_question_selection') else '机制解释仍需额外证据；本轮完成后停止，不自动开始第 8、9、10 步。'), '']
    if spec.get('frozen_question_selection'):
        lines += ['## 本次版本更新的选例约束', '',
                  '保留原第7步五个问题及配置锚点，观察值和来源成员按当前数据重新计算。原极端选图规则仍单独重算候选，候选变化不自动更换问题或论文主线。', '',
                  '| 问题 | 保留配置 | 当前原规则候选 | 配置或指标候选改变 |', '|---|---|---|---|']
        for item in spec['frozen_question_selection']['candidate_comparison']:
            lines.append(f"| {item['question_id']} | {item['retained_configuration_id']} / {item['retained_metric']} | {item['current_rule_candidate_configuration_id']} / {item['current_rule_candidate_metric']} | {item['selection_changed']} |")
    return '\n'.join(lines)


def self_test():
    tests = []
    def source(config):
        return {'configuration_id': config, 'method_directory': 'virtual', 'configuration': config.split('::')[-1],
                'evaluation_scope': '500_frames' if '500' in config else 'whole_trajectory',
                'rmse_unit_status': 'virtual unit', 'alignment_status': 'virtual',
                'source_relative_path': config + '.csv', 'source_sha256': 'virtual',
                'efficiency_protocol_json': js(dict(fps_unit_status='virtual', runtime_unit_status='virtual', memory_conversion_and_kind='virtual', evidence_status='virtual'))}
    def row(seq, run, value, config='virtual::mono', fps=10, labelled=True):
        s = source(config)
        r = {**{k:s[k] for k in META}, 'sequence_raw': seq, 'run_id_raw': str(run), 'scene': 'building',
             'condition_label_status': 'two_tokens' if labelled else 'missing_condition_labels',
             'speed_level': 'low' if labelled else '', 'altitude_level': 'high' if labelled else '',
             'speed_mps': 2 if labelled else None, 'altitude_m': 30 if labelled else None,
             'source_relative_path': config + '.csv', 'source_sha256': 'virtual', 'source_record_index': run,
             'raw_dataset': seq + '_' + str(run), 'raw_std': '999999', 'raw_rmse': 'NA' if value is None else str(value)}
        for metric, v in [('rmse', value), ('fps', fps), ('runtime', 20), ('memory', 2)]:
            r[metric+'_value'] = v; r[metric+'_is_finite'] = v is not None
        return r
    rows = [row('s1',1,1),row('s1',2,1),row('s1',3,1),row('s2',4,9)]
    p, s = summary_group(rows, 'virtual::mono', 'condition_labelled', '__all__', 'rmse', source('virtual::mono'))
    assert p['mean']==3 and s['mean']==5 and p['n_values_used']==4 and s['n_values_used']==2
    tests.append('不等有效重复次数时，逐次 mean=3 与序列等权 mean=5 正确区分：通过')
    for values, expected_sd in [([None],None),([2],None),([1,3],math.sqrt(2))]:
        group = [row('s1',i+1,v) for i,v in enumerate(values)]
        seq = sequence_table(group, {'virtual::mono':source('virtual::mono')})[0]
        assert seq['n_finite_runs']==sum(v is not None for v in values)
        assert seq['repeat_sd']==expected_sd or expected_sd is not None and math.isclose(seq['repeat_sd'],expected_sd)
        if not seq['n_finite_runs']: assert seq['mean'] is None and seq['finite_fraction']==0
    assert fraction(0,0) is None and fraction(0,2)==0
    empty = summary_group([], 'virtual::mono','condition_labelled','building','rmse',source('virtual::mono'))
    assert all(r['mean'] is None and r['sample_sd'] is None and r['finite_fraction'] is None for r in empty)
    tests.append('n_finite=0/1/2、repeat_sd 未定义、无记录与全无效比例不同：通过')
    r = describe([1,3]);assert r['mean']==2 and r['median']==2 and r['q25']==1.5 and r['q75']==2.5 and r['p90']==2.8 and math.isclose(r['sample_sd'],math.sqrt(2))
    assert describe([2])['sample_sd'] is None
    tests.append('可手算 mean/median/linear quantile 与 ddof=1；单值 sample_sd 不填零：通过')
    group = [row('s1',1,1,fps=10),row('s1',2,None,fps=30)]
    e = next(r for r in efficiency_table(group,{'virtual::mono':source('virtual::mono')}) if r['subset']=='all_retained' and r['metric']=='fps')
    assert (e['n_A'],e['n_B'],e['A_mean'],e['B_mean'],e['B_minus_A_mean'])==(2,1,20,10,-10)
    assert json.loads(e['A_not_B_record_indices_json'])==[2]
    tests.append('逐指标有限集合与 RMSE 门控集合，A/B 数值及排除索引：通过')
    assert parse_bool('False') is False and parse_bool('True') is True
    try: parse_bool('NA')
    except ValueError: pass
    else: raise AssertionError('Invalid boolean accepted')
    for v in (float('nan'),float('inf')):
        try: describe([v])
        except ValueError: pass
        else: raise AssertionError('Nonfinite value accepted')
    assert group[1]['raw_rmse']=='NA' and finite_values([group[1]],'rmse')==[]
    tests.append('True/False 明确解析，NA/NaN 不补零，非有限统计输入拒绝：通过')
    both = [row('same',4,2,'virtual::rgbd_500'),row('same',1,3,'virtual::rgbd_whole'),row('unlabelled',2,4,labelled=False)]
    sources={r['configuration_id']:source(r['configuration_id']) for r in both}
    seq=sequence_table(both,sources)
    assert len(seq)==12 and len({r['configuration_id'] for r in seq})==3
    assert len(subset_rows(both,'condition_labelled'))==2 and len(subset_rows(both,'unlabelled'))==1
    tests.append('500 帧与完整轨迹不合并，无标签不进入主子集，run=4 不改号：通过')
    original=[row('s1',1,1),row('s1',2,3)]
    a=sequence_table(original,{'virtual::mono':source('virtual::mono')})
    altered=[{**r,'raw_std':'0'} for r in original]
    assert a==sequence_table(altered,{'virtual::mono':source('virtual::mono')})
    tests.append('原始 raw_std 不参与 RMSE repeat_sd：通过')
    for bad in [WORKSPACE/'README.md',WORKSPACE/'derived_data/06_standardized/run_records.csv',Path('/tmp/07_bad.csv')]:
        try:check_output(bad,True)
        except ValueError:pass
        else:raise AssertionError('Output boundary bypass')
    with patch.object(Path,'is_symlink',return_value=True):
        try:check_output(WORKSPACE/OUTPUTS['sequence'],True)
        except ValueError:pass
        else:raise AssertionError('Symlink accepted')
    with patch.object(Path,'is_symlink',return_value=False),patch.object(Path,'exists',return_value=True):
        try:check_output(WORKSPACE/OUTPUTS['sequence'])
        except FileExistsError:pass
        else:raise AssertionError('Overwrite accepted')
    tests.append('错误输出、历史文件、软链接及默认覆盖保护（内存模拟）：通过')
    return tests


def validate_results(rows, sequences, summary, efficiency, sources):
    groups = {(r['configuration_id'],r['sequence_raw']) for r in rows}
    assert len(sequences)==len(groups)*len(METRICS)
    assert len({(s['configuration_id'],s['sequence_raw'],s['metric']) for s in sequences})==len(sequences)
    assert all((s['repeat_sd'] is None)==(s['n_finite_runs']<2) for s in sequences)
    assert all(s['mean'] is None for s in sequences if s['n_finite_runs']==0)
    assert {r['configuration_id'] for r in sequences}==set(sources)
    for config in sources:
        for metric in METRICS:
            totals=[r for r in summary if r['configuration_id']==config and r['metric']==metric and r['scene']=='__all__' and r['aggregation_level']==LEVELS[0]]
            counts={r['subset']:r for r in totals}
            assert counts['condition_labelled']['n_retained_records']+counts['unlabelled']['n_retained_records']==counts['all_retained']['n_retained_records']
            assert counts['condition_labelled']['n_finite_records']+counts['unlabelled']['n_finite_records']==counts['all_retained']['n_finite_records']
    for r in summary:
        assert r['n_sequences_with_finite']+r['n_sequences_without_finite']==r['n_observed_sequences']
        assert (r['sample_sd'] is None)==(r['n_values_used']<2)
        assert r['n_values_used']==r['n_finite_records' if r['aggregation_level']==LEVELS[0] else 'n_sequences_with_finite']
    for r in efficiency:
        a,b,excluded=map(lambda k:set(json.loads(r[k])),('A_record_indices_json','B_record_indices_json','A_not_B_record_indices_json'))
        assert b.issubset(a) and a-b==excluded and len(a)==r['n_A'] and len(b)==r['n_B']
    return {'all_configurations_described':True,'all_invalid_sequences_retained_in_counts':True,
            'undefined_repeat_sd_not_zero':True,'subsets_partition_counts':True,'aggregation_units_and_counts':True,
            'efficiency_cohort_indices':True,'sequence_descriptor_rows':len(sequences),'summary_rows':len(summary),'efficiency_rows':len(efficiency)}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--self-test',action='store_true')
    parser.add_argument('--overwrite',action='store_true')
    args=parser.parse_args()
    tests=self_test()
    print(js({'memory_tests_passed':len(tests)}))
    if args.self_test:
        for test in tests:print(test)
        return
    for p in OUTPUTS.values():check_output(WORKSPACE/p,args.overwrite)
    if args.overwrite and any((WORKSPACE/p).exists() for p in OUTPUTS.values()):
        previous=WORKSPACE/OUTPUTS['spec']
        if not previous.is_file() or json.loads(previous.read_text()).get('generated_by')!='scripts/explore_benchmark.py':
            raise ValueError('Existing output ownership unconfirmed; review before overwrite')
    raw={key:read_bytes(WORKSPACE/path) for key,path in INPUTS.items()}
    rows,sources,schema,checks=validate_inputs(raw)
    command=shlex.join(['/home/yuan/anaconda3/bin/python3','-B',str(Path(__file__).absolute()),*sys.argv[1:]])
    spec=make_spec(raw,schema,command)
    frozen = schema.get('validated_snapshot', {}).get('frozen_stage07_questions')
    if frozen:
        spec['frozen_question_selection'] = {'source': frozen, 'policy': 'Retain historical question/configuration anchors; evaluate current observations and record new automatic candidates separately.', 'candidate_comparison': []}
        spec['historical_figure_selection_rules'] = {name: spec['figure_selection'][name] for name in FIGURES}
        for name in FIGURES:
            spec['figure_selection'][name] = 'Controlled update: preserve the historical question/configuration anchor; recompute its current values. Original automatic diagnostic rule: ' + spec['figure_selection'][name]
    # Persist the rules and byte snapshot BEFORE computing real descriptive statistics.
    write_output('spec',json.dumps(spec,ensure_ascii=False,indent=2)+'\n',args.overwrite)
    print('SPEC WRITTEN: real descriptive calculations start now.')
    seq=sequence_table(rows,sources)
    summary=descriptive_table(rows,sources)
    efficiency=efficiency_table(rows,sources)
    cases=flagged_cases(rows,seq)
    checks.update(validate_results(rows,seq,summary,efficiency,sources))
    candidates=select_figures(seq,summary,efficiency)
    selected,selection_context,original_questions=retain_original_questions(schema,seq,summary,efficiency,candidates)
    if selection_context:
        spec['frozen_question_selection'] = selection_context
    findings,questions=finding_records(selected,seq,summary,efficiency,sources)
    questions=restore_question_anchors(questions,original_questions,seq)
    figures=draw_figures(selected,seq,summary,sources,args.overwrite)
    for key,path in INPUTS.items():
        if sha(read_bytes(WORKSPACE/path))!=spec['inputs'][key]['sha256']:
            raise ValueError('Input changed during exploration: '+path)
    if frozen and sha(read_bytes(WORKSPACE/frozen['path'])) != frozen['sha256']:
        raise ValueError('Historical question snapshot changed during exploration')
    checks.update(inputs_unchanged=True,flagged_cases=len(cases),major_findings=len(findings),main_figures=len(figures),visual_review='pending_actual_open')
    for key,data in [('sequence',seq),('summary',summary),('efficiency',efficiency),('cases',cases),('questions',questions)]:
        write_output(key,csv_text(data,list(data[0])),args.overwrite)
    report=exploration_report(findings,figures,seq,summary,efficiency,sources,spec,checks,tests,command)
    # Only enrich this invocation's already-written spec with observed candidate changes.
    write_output('spec',json.dumps(spec,ensure_ascii=False,indent=2)+'\n',True)
    write_output('report',report,args.overwrite)
    print(js({'checks':checks,'selected':{k:None if v is None else {'configuration_id':v['configuration_id'],'sequence':v.get('sequence_raw'),'metric':v.get('metric')} for k,v in selected.items()},'findings':findings,'figures':figures}))


if __name__=='__main__':
    try:main()
    except (OSError,ValueError,KeyError,AssertionError,StopIteration) as error:
        print('STOP: '+str(error),file=sys.stderr)
        sys.exit(1)
