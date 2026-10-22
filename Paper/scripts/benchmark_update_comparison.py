"""Compare backed-up and staged benchmark artifacts without recalculating statistics.

This helper reads only the analysis workspace.  It does not read source experiment
files, execute a prior stage, infer run identity from equal labels, or publish the
staging tree.  The refresh orchestrator calls it after the dependency build ends.
"""
from collections import Counter
import csv
import hashlib
import io
import json
import math
import os
from pathlib import Path


W = Path('/home/yuan/SLAM/codex_review/benchmark_analysis')
UPDATED = frozenset(('hierslam::rgbd_500', 'hierslam::semantic_500',
                     'hierslam::rgbd_whole', 'SplaTAM::rgbd'))
TOLERANCE = {'relative': 1e-12, 'absolute': 1e-12}
OUTPUTS = ('sequence_changes.csv', 'changed_results.csv', 'changed_claims.csv', 'update_report.md')
MARKER = '<!-- generated-by: scripts/benchmark_update_comparison.py -->'
csv.field_size_limit(100 * 1024 * 1024)


def js(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _update_path(value):
    p = Path(value).absolute()
    if p.parent != W / 'updates' or not p.is_dir():
        raise ValueError('Expected one existing update directory directly below workspace/updates')
    if any(x.is_symlink() for x in (p, *p.parents)):
        raise ValueError('Symlink update directory rejected')
    return p


def _read(path):
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('Symlink input rejected: ' + str(path))
    if not path.resolve().is_relative_to(W.resolve()) or not path.is_file():
        raise ValueError('Missing or external comparison input: ' + str(path))
    return path.read_bytes()


def _csv(path):
    return list(csv.DictReader(io.StringIO(_read(path).decode('utf-8-sig'))))


def _number(value):
    if value in ('', None) or isinstance(value, bool):
        return None
    try:
        n = float(value)
    except (ValueError, TypeError):
        return None
    return n if math.isfinite(n) else None


def _equal(a, b):
    if a == b:
        return True
    x, y = _number(a), _number(b)
    return x is not None and y is not None and math.isclose(x, y, rel_tol=1e-12, abs_tol=1e-12)


def _index(rows, keys, table):
    out = {}
    for row in rows:
        key = tuple(row[k] for k in keys)
        if key in out:
            raise ValueError(f'Duplicate comparison key in {table}: {key!r}')
        out[key] = row
    return out


COUNTS = ('n_retained_records', 'n_observed_sequences', 'n_finite_records',
          'n_sequences_with_finite', 'n_sequences_without_finite', 'finite_fraction',
          'n_sequences_repeat_sd_estimable', 'n_sequences_single_retained_run',
          'n_sequences_multiple_retained_insufficient_finite', 'n_values_used')
DESCRIPTIVE = ('mean', 'median', 'q25', 'q75', 'p90', 'min', 'max', 'sample_sd')
SEQ_NUMBERS = ('n_retained_runs', 'n_finite_runs', 'finite_fraction', 'mean', 'median',
               'min', 'max', 'repeat_sd', 'finite_range')
SUPPORT_FIELDS = ('n_reference_blocks', 'n_R', 'n_F', 'n_C', 'low_n_blocks', 'high_n_blocks',
                  'low_n_scenes', 'high_n_scenes', 'low_n_retained', 'high_n_retained',
                  'low_n_finite', 'high_n_finite', 'n_blocks', 'scene_weight')
PATTERN_NUMBERS = ('n_observed_sequences', 'n_finite_sequences', 'n_retained_runs', 'n_finite_runs',
                   'finite_fraction', 'rmse_sequence_mean', 'rmse_sequence_median',
                   'rmse_sequence_p90', 'rmse_sequence_max', 'all_nonfinite_cells', 'no_record_cells',
                   'n_speed_reversal_scenes', 'repeat_sd_estimable', 'repeat_sd_undefined',
                   'sequences_identical_rmse_repeats', 'sequences_identical_provided_error_fields',
                   'sequences_mean_median_numeric_difference', 'sequence_drop_range_nonzero',
                   'condition_baselines_computed', 'condition_baselines_unavailable',
                   'condition_problems_any_direction_change', 'condition_trials_unavailable',
                   'fps_overall_rho', 'runtime_overall_rho', 'memory_overall_rho',
                   'constant_correlation_views', 'n_efficiency_metrics_with_A_B_exclusion') + tuple(
    f'{axis}_{suffix}' for axis in ('speed', 'altitude') for suffix in
    ('endpoint_positive', 'endpoint_negative', 'endpoint_numerical_zero', 'endpoint_unavailable',
     'triple_nondecreasing', 'triple_nonincreasing', 'triple_numerically_flat', 'triple_nonmonotonic',
     'triple_unavailable', 'F_blocks', 'C_blocks', 'V1', 'view_direction_changes', 'loso_direction_changes'))


# Keys and existing output fields only: none of the stage formulas is reimplemented.
SPECS = {
    'tables/07_eda/sequence_metrics.csv': {
        'keys': ('configuration_id', 'sequence_raw', 'metric'), 'numeric': SEQ_NUMBERS,
        'status': ('repeat_sd_status',),
        'members': ('retained_run_ids_json', 'finite_run_ids_json', 'finite_values_json',
                    'source_record_indices_json', 'finite_source_record_indices_json')},
    'tables/07_eda/descriptive_summary.csv': {
        'keys': ('configuration_id', 'subset', 'scene', 'metric', 'aggregation_level'),
        'numeric': COUNTS + DESCRIPTIVE},
    'tables/07_eda/efficiency_cohort_comparison.csv': {
        'keys': ('configuration_id', 'subset', 'metric'),
        'numeric': ('n_retained_records', 'n_A', 'n_B', 'n_A_not_B', 'A_mean', 'A_median', 'B_mean', 'B_median', 'B_minus_A_mean'),
        'members': ('A_record_indices_json', 'B_record_indices_json', 'A_not_B_record_indices_json', 'A_not_B_datasets_json')},
    'tables/08_conditions/joint_metrics.csv': {
        'keys': ('configuration_id', 'scene', 'altitude_m', 'speed_mps', 'metric', 'aggregation_level'),
        'numeric': COUNTS + ('mean', 'median', 'min', 'max', 'sample_sd'), 'status': ('cell_state',),
        'members': ('sequences_json', 'finite_sequences_json', 'source_record_indices_json', 'finite_source_record_indices_json')},
    'tables/08_conditions/conditional_contrasts.csv': {
        'keys': ('configuration_id', 'scene', 'metric', 'aggregation_level', 'contrast_kind', 'direction', 'fixed_axis', 'fixed_value'),
        'numeric': ('difference', 'finite_fraction_difference_pp'),
        'status': ('status', 'unavailable_reason', 'coverage_or_validity_counts_changed', 'retained_sequence_sets_differ', 'finite_sequence_sets_differ')},
    'tables/08_conditions/efficiency_cohort_cells.csv': {
        'keys': ('configuration_id', 'scene', 'altitude_m', 'speed_mps', 'metric', 'aggregation_level'),
        'numeric': ('n_retained_records', 'n_A', 'n_B', 'n_A_not_B', 'A_mean', 'B_mean', 'A_median', 'B_median', 'B_minus_A_mean'),
        'status': ('status', 'A_cell_state', 'B_cell_state'),
        'members': ('A_record_indices_json', 'B_record_indices_json', 'A_not_B_record_indices_json', 'A_not_B_datasets_json')},
    'tables/09_robustness/repeat_value_audit.csv': {
        'keys': ('configuration_id', 'sequence_raw'),
        'numeric': ('n_retained', 'n_finite_rmse', 'n_distinct_finite_raw_rmse', 'n_distinct_finite_rmse_value', 'n_equal_comparable_aux_fields', 'rmse_repeat_sd'),
        'status': ('finite_rmse_identical', 'finite_rmse_text_identical', 'all_provided_error_fields_identical', 'all_efficiency_fields_identical')},
    'tables/09_robustness/support_blocks.csv': {
        'keys': ('configuration_id', 'block_id'),
        'numeric': ('low_n_retained', 'low_n_finite', 'low_n_sequences', 'low_mean', 'low_median', 'low_finite_fraction',
                    'high_n_retained', 'high_n_finite', 'high_n_sequences', 'high_mean', 'high_median', 'high_finite_fraction'),
        'status': ('in_R', 'in_F', 'in_C', 'low_state', 'high_state', 'matching_status')},
    'tables/09_robustness/sensitivity_estimates.csv': {
        'keys': ('estimate_id',), 'numeric': SUPPORT_FIELDS + ('baseline_value', 'delta_from_baseline', 'endpoint_low', 'endpoint_high', 'value',
            'repeat_sd', 'original_n_retained', 'original_n_finite', 'original_finite_fraction', 'trial_n_used', 'trial_repeat_sd',
            'range_min', 'range_max', 'n_variants', 'n_computed_variants', 'n_unavailable_variants', 'n_direction_changes'),
        'status': ('status', 'direction', 'direction_changed'),
        'members': ('low_block_ids_json', 'high_block_ids_json', 'no_record_block_ids_json', 'variant_ids_json')},
    'tables/09_robustness/efficiency_decomposition.csv': {
        'keys': ('row_id',), 'numeric': ('n_A', 'n_B', 'n_E', 'mean_A', 'mean_B', 'mean_E', 'overall_B_minus_A',
        'contribution', 'identity_rhs', 'identity_residual', 'record_contribution_sum', 'excluded_value', 'n_excluded_in_group'),
        'status': ('status',)},
    'tables/10_relationships/comparison_scope.csv': {
        'keys': ('pair_id',), 'numeric': (), 'status': ('processing_status',),
        'metadata': ('scope_A', 'scope_B', 'scope_evidence_A', 'scope_evidence_B', 'modality_A', 'modality_B', 'semantic_A', 'semantic_B')},
    'tables/10_relationships/pairwise_patterns.csv': {
        'keys': ('row_id',), 'numeric': ('rho', 'n_sequences', 'n_unique_A', 'n_unique_B', 'n_tied_observations_A', 'n_tied_observations_B',
            'n_scenes', 'A_n_retained', 'A_n_finite', 'B_n_retained', 'B_n_finite', 'n_U', 'n_P', 'n_F', 'n_C',
            'baseline_rho', 'delta_from_baseline', 'q75_A', 'q75_B', 'n_T_A', 'n_T_B', 'n_intersection', 'n_union', 'jaccard'),
        'status': ('status', 'constant_A', 'constant_B', 'direction_changed'),
        'members': ('members_json', 'U_members_json', 'P_members_json', 'F_members_json', 'C_members_json', 'T_A_json', 'T_B_json', 'intersection_json', 'union_json')},
    'tables/10_relationships/pairwise_availability.csv': {
        'keys': ('pair_id',), 'numeric': ('n_U', 'n_P', 'all_nonfinite_jaccard', 'both_finite_n', 'both_finite_fraction_P',
            'only_A_finite_n', 'only_A_finite_fraction_P', 'only_B_finite_n', 'only_B_finite_fraction_P', 'neither_finite_n', 'neither_finite_fraction_P',
            'A_n_retained_P', 'A_n_finite_P', 'A_run_finite_fraction_P', 'A_any_finite_sequences_P',
            'B_n_retained_P', 'B_n_finite_P', 'B_run_finite_fraction_P', 'B_any_finite_sequences_P'),
        'status': ('all_nonfinite_jaccard_status',),
        'members': ('P_members_json', 'both_finite_members_json', 'only_A_finite_members_json', 'only_B_finite_members_json', 'neither_finite_members_json')},
    'tables/10_relationships/within_configuration_tradeoffs.csv': {
        'keys': ('row_id',), 'numeric': ('n_retained', 'n_finite_rmse', 'n_finite_efficiency', 'n_joint_finite', 'rmse_joint_mean', 'efficiency_joint_mean',
            'rho', 'n_sequences', 'n_unique_A', 'n_unique_B', 'n_tied_observations_A', 'n_tied_observations_B', 'n_observed_sequences', 'n_scenes'),
        'status': ('status', 'constant_A', 'constant_B'),
        'members': ('used_sequence_row_ids_json', 'unavailable_sequence_row_ids_json', 'members_json')},
    'tables/11b_review/configuration_patterns.csv': {
        'keys': ('configuration_id',), 'numeric': PATTERN_NUMBERS,
        'status': ('speed_opposing_scene_contributions', 'altitude_opposing_scene_contributions', 'fps_scene_relation',
                   'runtime_scene_relation', 'memory_scene_relation', 'co_worsening_all_three_overall', 'co_worsening_all_scenes_and_three'),
        'members': ('speed_direction_reversal_scenes_json', 'speed_missing_loso_scenes_json', 'altitude_missing_loso_scenes_json',
                    'fps_opposite_scenes_json', 'runtime_opposite_scenes_json', 'memory_opposite_scenes_json')},
    'tables/11b_review/condition_sensitivity.csv': {
        'keys': ('estimate_id',), 'numeric': ('baseline_value', 'delta_from_baseline', 'value', 'range_min', 'range_max',
            'n_variants', 'n_computed_variants', 'n_unavailable_variants', 'n_direction_changes'),
        'status': ('status', 'direction', 'direction_changed'), 'members': ('variant_ids_json',)},
    'tables/11b_review/claim_applicability.csv': {
        'keys': ('claim_id', 'configuration_id'), 'numeric': (),
        'status': ('literal_scope_status', 'applicability_category', 'support_level')},
    'tables/11b_review/selection_rationale.csv': {
        'keys': ('configuration_id',), 'numeric': (),
        'status': ('selection_recommendation',), 'members': ('candidate_roles_json',)},
    'tables/11c_overview/speed_response_matrix.csv': {
        'keys': ('configuration_id', 'scene', 'fixed_axis', 'fixed_value'),
        'numeric': ('endpoint_difference', 'finite_fraction_difference_pp'),
        'status': ('endpoint_direction', 'display_status', 'triple_shape'), 'members': ('three_level_values_json', 'endpoint_counts_json')},
    'tables/11c_overview/altitude_response_matrix.csv': {
        'keys': ('configuration_id', 'scene', 'fixed_axis', 'fixed_value'),
        'numeric': ('endpoint_difference', 'finite_fraction_difference_pp'),
        'status': ('endpoint_direction', 'display_status', 'triple_shape'), 'members': ('three_level_values_json', 'endpoint_counts_json')},
    'tables/11c_overview/finite_coverage_matrix.csv': {
        'keys': ('configuration_id', 'scene', 'altitude_m', 'speed_mps'),
        'numeric': ('n_finite_records', 'n_retained_records', 'n_finite_sequences', 'n_observed_sequences', 'finite_fraction'),
        'status': ('cell_state',), 'members': ('sequence_members_json', 'finite_sequences_json')},
    'tables/11c_overview/precision_efficiency_matrix.csv': {
        'keys': ('configuration_id', 'efficiency_metric', 'scene'),
        'numeric': ('rho', 'n_sequences', 'n_joint_finite', 'n_observed_sequences', 'n_unique_A', 'n_unique_B'),
        'status': ('status', 'constant_A', 'constant_B'), 'members': ('sequence_members_json',)},
}


class Comparison:
    def __init__(self, update_dir):
        self.u = _update_path(update_dir)
        from refresh_benchmark_results import load_update_policy, configuration_delta_name, is_sgs_policy
        self.policy = load_update_policy(self.u)
        self.full_field_comparison = is_sgs_policy(self.policy)
        # Keep legacy policies and their historical comparison projection intact.
        self.specs = {table: dict(spec) for table, spec in SPECS.items()}
        if self.full_field_comparison:
            self.specs.update({
                'tables/07_eda/flagged_cases.csv': {'keys': ('case_id',)},
                'tables/10_relationships/pair_sequence_evidence.csv': {'keys': ('evidence_id',)},
                'tables/11c_overview/distribution_summary.csv': {'keys': ('configuration_id',)},
                'tables/11c_overview/family_pattern_candidates.csv': {'keys': ('candidate_id',)},
                'tables/11c_overview/case_selection_review.csv': {'keys': ('case_review_id',)},
            })
        self.configuration_delta_path = self.u / configuration_delta_name(self.policy)
        self.updated = frozenset(self.policy['authorized_changed_configurations']) if self.policy else UPDATED
        self.cache = {}
        self.hashes = {}
        self.indexes = {}
        if self.policy:
            self.hashes['update_policy.json'] = sha(_read(self.u/'update_policy.json'))

    def rows(self, version, table):
        key = (version, table)
        if key not in self.cache:
            path = self.u / version / table
            raw = _read(path)
            self.hashes[str(path.relative_to(self.u))] = sha(raw)
            self.cache[key] = list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))))
        return self.cache[key]

    def index(self, version, table, keys):
        key = (version, table, tuple(keys))
        if key not in self.indexes:
            self.indexes[key] = _index(self.rows(version, table), keys, table)
        return self.indexes[key]

    def reference(self, version, table, key):
        fields = tuple(sorted(key))
        return self.index(version, table, fields).get(tuple(str(key[k]) for k in fields))

    def unchanged_inputs(self):
        return all(sha(_read(self.u / path)) == value for path, value in self.hashes.items())


def _state(retained, finite):
    if not retained:
        return 'no_retained_records'
    return 'observed_all_nonfinite' if not finite else 'observed_all_finite' if finite == retained else 'observed_partial_finite'


def _sequence_changes(c):
    table = 'tables/07_eda/sequence_metrics.csv'
    keys = ('configuration_id', 'sequence_raw', 'metric')
    old, new = (c.index(v, table, keys) for v in ('backup', 'staging'))
    out = []
    for key in sorted(set(old) | set(new)):
        if key[2] != 'rmse':
            continue
        a, b = old.get(key), new.get(key)
        item = {'configuration_id': key[0], 'sequence_raw': key[1], 'metric': 'rmse',
                'subset': (b or a)['subset'], 'source_update_authorized': key[0] in c.updated,
                'evidence_table': table, 'evidence_key_json': js(dict(zip(keys, key))),
                'record_correspondence_limit': 'Compare exported sequence summaries; equal run IDs are not verified experiment identity or a renumber mapping.'}
        for prefix, row in [('old', a), ('new', b)]:
            n, k = (int(row['n_retained_runs']), int(row['n_finite_runs'])) if row else (0, 0)
            item[prefix + '_state'] = _state(n, k)
            for field in ('n_retained_runs', 'n_finite_runs', 'finite_fraction', 'mean', 'median', 'repeat_sd', 'repeat_sd_status',
                          'finite_range', 'retained_run_ids_json', 'finite_run_ids_json', 'finite_values_json',
                          'source_relative_path', 'source_sha256', 'source_record_indices_json', 'finite_source_record_indices_json'):
                item[prefix + '_' + field] = row.get(field, '') if row else ''
        item['state_changed'] = item['old_state'] != item['new_state']
        item['sequence_added_to_export'] = a is None and b is not None
        item['sequence_removed_from_export'] = a is not None and b is None
        item['finite_count_changed'] = a is not None and b is not None and not _equal(item['old_n_finite_runs'], item['new_n_finite_runs'])
        item['mean_changed'] = not _equal(item['old_mean'], item['new_mean'])
        item['repeat_sd_changed'] = not _equal(item['old_repeat_sd'], item['new_repeat_sd'])
        item['newly_finite_sequence'] = item['old_state'] in ('no_retained_records', 'observed_all_nonfinite') and item['new_state'] not in ('no_retained_records', 'observed_all_nonfinite')
        item['lost_all_finite_results'] = item['new_state'] == 'observed_all_nonfinite' and item['old_state'] not in ('no_retained_records', 'observed_all_nonfinite')
        out.append(item)
    return out


def _compact(value):
    """Large evidence is addressed by exact table key + field, not silently dropped."""
    if value is None or len(str(value)) <= 6000:
        return value
    return js({'full_value_sha256': sha(str(value).encode()), 'characters': len(str(value)),
               'storage': 'See the exact old/new evidence table, key and field recorded on this row.'})


def _member_delta(a, b):
    try:
        x, y = json.loads(a), json.loads(b)
        if isinstance(x, list) and isinstance(y, list):
            sx, sy = {js(v) for v in x}, {js(v) for v in y}
            return js({'old_length': len(x), 'new_length': len(y),
                       'removed': [json.loads(v) for v in sorted(sx - sy)],
                       'added': [json.loads(v) for v in sorted(sy - sx)]})
    except (ValueError, TypeError):
        pass
    return ''


def _change(table, key, a, b, field, kind):
    av, bv = a.get(field, '') if a else '', b.get(field, '') if b else ''
    x, y = _number(av), _number(bv)
    row = b or a or {}
    return {'table': table, 'evidence_key_json': js(key), 'configuration_id': row.get('configuration_id', ''),
            'pair_id': row.get('pair_id', ''), 'configuration_A': row.get('configuration_A', ''),
            'configuration_B': row.get('configuration_B', ''), 'field': field, 'change_kind': kind,
            'old_value': _compact(av), 'new_value': _compact(bv),
            'numeric_delta': y - x if x is not None and y is not None else '',
            'old_row_present': a is not None, 'new_row_present': b is not None,
            'members_delta_json': _compact(_member_delta(av, bv)) if kind == 'support_membership_change' else '',
            'old_evidence': 'backup/' + table, 'new_evidence': 'staging/' + table,
            'interpretation': 'Observed version difference, not causal attribution to one newly retained run.'}


def _field_change_kind(field, old_value, new_value):
    """Classify saved-field differences only; never infer a new metric or effect."""
    if (field.endswith(('sha256', '_path')) or field in {
            'source_relative_path', 'source_absolute_path', 'source_record_index',
            'evidence_key_json', 'evidence_keys', 'original_evidence_rows_json',
            'source_evidence_reference', 'targeted_review_record'}):
        return 'source_provenance_change'
    if (field in {'input_version', 'current_version', 'evaluation_scope',
                  'base_modality', 'semantic_usage', 'display_input_group',
                  'algorithm_family', 'row_order', 'metadata_evidence_json'} or
            any(part in field for part in ('measurement_limit', 'efficiency_limit', 'rmse_limit',
                                          'unit_status', 'alignment_status', 'protocol'))):
        return 'measurement_metadata_change'
    if (_number(old_value) is not None or _number(new_value) is not None):
        return 'numerical_result_change'
    if (field.endswith(('_status', '_state', '_reason')) or
            field in {'status', 'direction', 'display_status', 'triple_shape',
                      'source_triple_classification', 'in_U', 'in_P', 'in_F', 'in_C'} or
            old_value in ('True', 'False', 'true', 'false') or new_value in ('True', 'False', 'true', 'false')):
        return 'status_change'
    if field.endswith('_json') or field in {'current_facts', 'alternative_facts'}:
        if any(part in field for part in ('member', 'indices', 'datasets', 'run_ids', 'record')):
            return 'support_membership_change'
        # endpoints/weights/views/repeat details contain real numeric evidence;
        # retain their exact existing payload instead of treating it as prose.
        return 'structured_evidence_change'
    if field.endswith(('configs', 'configurations', 'methods', 'distribution')):
        return 'support_membership_change'
    return 'wording_change'


def _all_table_changes(c):
    out, table_counts = [], {}
    for table, spec in c.specs.items():
        old, new = (c.index(v, table, spec['keys']) for v in ('backup', 'staging'))
        before = len(out)
        for key_tuple in sorted(set(old) | set(new)):
            a, b = old.get(key_tuple), new.get(key_tuple)
            key = dict(zip(spec['keys'], key_tuple))
            if a is None or b is None:
                out.append(_change(table, key, a, b, '', 'evidence_row_added' if a is None else 'evidence_row_removed'))
            registered = set(spec['keys'])
            for category, kind in [('numeric', 'numerical_result_change'), ('status', 'status_change'),
                                   ('members', 'support_membership_change'), ('metadata', 'metadata_only_change')]:
                registered.update(spec.get(category, ()))
                for field in spec.get(category, ()):
                    av, bv = a.get(field, '') if a else '', b.get(field, '') if b else ''
                    if not _equal(av, bv):
                        out.append(_change(table, key, a, b, field, kind))
            if c.full_field_comparison:
                for field in sorted((set(a or {}) | set(b or {})) - registered):
                    av, bv = (a or {}).get(field, ''), (b or {}).get(field, '')
                    if not _equal(av, bv):
                        out.append(_change(table, key, a, b, field, _field_change_kind(field, av, bv)))
        table_counts[table] = {'old_rows': len(old), 'new_rows': len(new), 'changed_fields': len(out) - before}
    if c.full_field_comparison:
        for row in out:
            row['change_type'] = row['change_kind']
            row['comparison_scope'] = 'all saved non-key fields, including structured evidence; no metric recalculation'
    return out, table_counts


def _pair_snapshots(c):
    scope_table = 'tables/10_relationships/comparison_scope.csv'
    pattern_table = 'tables/10_relationships/pairwise_patterns.csv'
    scopes = {v: c.index(v, scope_table, ('pair_id',)) for v in ('backup', 'staging')}
    if set(scopes['backup']) != set(scopes['staging']) or len(scopes['staging']) != 276:
        raise ValueError('All 276 unordered configuration pairs must remain explicitly registered')
    patterns = {v: c.index(v, pattern_table, ('row_id',)) for v in ('backup', 'staging')}
    out = []
    for key in sorted(scopes['staging']):
        pair = key[0]
        snapshots = {}
        for version in ('backup', 'staging'):
            r = scopes[version][key]
            d = {'processing_status': r['processing_status'], 'scope_A': r['scope_A'], 'scope_B': r['scope_B']}
            for view in ('F_mean', 'C_mean', 'F_median'):
                p = patterns[version].get((pair + '|' + view + '|__all_scenes__',))
                d[view] = {f: p.get(f, '') for f in ('rho', 'status', 'n_sequences', 'n_U', 'n_P', 'n_F', 'n_C', 'members_json', 'F_members_json', 'C_members_json')} if p else {'status': 'not_computed_due_to_scope'}
            snapshots[version] = d
        row = _change(scope_table, {'pair_id': pair}, scopes['backup'][key], scopes['staging'][key], 'all_pair_review', 'all_pair_review_snapshot')
        row['old_value'], row['new_value'] = js(snapshots['backup']), js(snapshots['staging'])
        row['numeric_delta'] = ''
        row['interpretation'] = 'Complete pair registry: processing status and F/C/rho/members compared; scope confirmation is separate from numerical change.'
        out.append(row)
    return out


def _verify_unchanged(c):
    deltas = _csv(c.configuration_delta_path)
    unaffected = {r['configuration_id'] for r in deltas if r['old_sha256'] == r['new_sha256']}
    if unaffected != {r['configuration_id'] for r in deltas} - c.updated:
        raise ValueError('Source-difference authorization set differs from the confirmed source updates')
    failures, counts = [], Counter()
    for table, spec in c.specs.items():
        # Applicability and relative case roles may change when other configurations change.
        if table.endswith(('claim_applicability.csv', 'selection_rationale.csv')) or (
                c.full_field_comparison and table.endswith(('case_selection_review.csv', 'family_pattern_candidates.csv'))):
            continue
        old, new = (c.index(v, table, spec['keys']) for v in ('backup', 'staging'))
        for key in sorted(set(old) | set(new)):
            a, b = old.get(key), new.get(key)
            row = b or a
            config = row.get('configuration_id', '')
            is_unaffected = config in unaffected or (row.get('configuration_A') in unaffected and row.get('configuration_B') in unaffected)
            if not is_unaffected:
                continue
            if a is None or b is None:
                failures.append({'table': table, 'key': dict(zip(spec['keys'], key)), 'issue': 'row_membership_changed'})
                continue
            # The initial update confirmed scope. A DSO-only correction must also
            # preserve all unaffected processing states and exact support members.
            fields = spec.get('numeric', ()) + tuple(f for f in spec.get('status', ()) if c.policy or f != 'processing_status')
            if c.policy:
                fields += spec.get('members', ())
            if c.full_field_comparison:
                # Cross-configuration narrative/selection tables were excluded
                # explicitly above. Per-configuration facts and provenance must
                # remain unchanged for every other configuration.
                fields = tuple(sorted((set(a) | set(b)) - {'input_version', 'current_version'}))
            for field in fields:
                counts[table] += 1
                if not _equal(a.get(field, ''), b.get(field, '')):
                    failures.append({'table': table, 'key': dict(zip(spec['keys'], key)), 'field': field,
                                     'old': a.get(field, ''), 'new': b.get(field, '')})
    unaffected_pairs = set()
    if c.policy:
        # Audit every untouched pair, not merely the previously highlighted pairs.
        # Include the per-sequence source members and three-state cross-membership
        # fields omitted from the original update's compact comparison projection.
        pair_tables = {'comparison_scope.csv':'pair_id', 'pair_sequence_evidence.csv':'evidence_id',
                       'pairwise_patterns.csv':'row_id', 'pairwise_availability.csv':'pair_id'}
        for name, identity in pair_tables.items():
            table = 'tables/10_relationships/'+name
            old, new = (c.index(v, table, (identity,)) for v in ('backup','staging'))
            for key in sorted(set(old)|set(new)):
                a, b = old.get(key), new.get(key)
                row = b or a
                if not {row['configuration_A'],row['configuration_B']}.issubset(unaffected):
                    continue
                unaffected_pairs.add(row['pair_id'])
                if a is None or b is None:
                    failures.append({'table':table,'key':{identity:key[0]},'issue':'untouched_pair_row_membership_changed'})
                    continue
                for field in sorted(set(a)|set(b)):
                    # No current pair table has a version column; this exemption
                    # explicitly separates a future global version tag from facts.
                    if field in {'input_version','current_version'}:
                        continue
                    counts['all_pair_fields:'+table] += 1
                    if not _equal(a.get(field,''),b.get(field,'')):
                        failures.append({'table':table,'key':{identity:key[0]},'field':field,
                                         'old':a.get(field,''),'new':b.get(field,'')})
    return {'passed': not failures, 'configuration_ids': sorted(unaffected), 'n_configurations': len(unaffected),
            **({'untouched_pair_count':len(unaffected_pairs),'untouched_pair_ids':sorted(unaffected_pairs)} if c.policy else {}),
            'tolerance': TOLERANCE, 'compared_fields_by_table': dict(counts), 'differences': failures,
            **({'full_field_comparison': True,
                'context_tables_excluded_from_local_invariance': [
                    'tables/11b_review/claim_applicability.csv', 'tables/11b_review/selection_rationale.csv',
                    'tables/11c_overview/case_selection_review.csv', 'tables/11c_overview/family_pattern_candidates.csv'],
                'context_change_policy': 'All changes remain in changed_results; global applicability/case/family context is not mislabelled as numerical drift in an unchanged configuration.'}
               if c.full_field_comparison else {}),
            'scope': ('Numeric results, statistical states and support members for unchanged-source configurations and pairs; metadata and cross-configuration selection roles are separate.'
                      if c.policy else 'Numeric results and statistical states for unchanged-source configurations; metadata and cross-configuration selection roles are separate.')}


def verify_unchanged_configurations(update_dir):
    """Read-only numerical-drift gate; returns every unexpected difference."""
    return _verify_unchanged(Comparison(update_dir))


def _claim_changes(c):
    old_claims = c.rows('backup', 'reports/11_claim_registry.csv')
    new_claims = {r['claim_id']: r for r in c.rows('staging', 'reports/11_claim_registry.csv')}
    rows = []
    for old in old_claims:
        new = new_claims.get(old['claim_id'])
        numeric, statuses, membership, missing, refs = [], [], [], [], []
        def addresses(claim):
            return {js({'table':r['table'],'key':r['key']}):{'table':r['table'],'key':r['key']}
                    for r in json.loads(claim['evidence_rows_json'])} if claim else {}
        old_refs, new_refs = addresses(old), addresses(new)
        added_refs = [new_refs[k] for k in sorted(set(new_refs)-set(old_refs))]
        retired_refs = [old_refs[k] for k in sorted(set(old_refs)-set(new_refs))]
        if added_refs or retired_refs:
            membership.append({'table':'reports/11_claim_registry.csv','key':{'claim_id':old['claim_id']},
                'field':'cited_evidence_keys','old':_compact(js(list(old_refs.values()))),
                'new':_compact(js(list(new_refs.values()))),
                'added_keys':added_refs,'retired_keys':retired_refs,
                'interpretation':'Evidence registration membership changed; compare the underlying union rows before treating a statement change as wording-only.'})
        for identity in sorted(set(old_refs)|set(new_refs)):
            address = new_refs.get(identity) or old_refs[identity]
            table, key = address['table'], address['key']
            a, b = (c.reference(v, table, key) for v in ('backup', 'staging'))
            refs.append(address)
            missing_versions = [v for v, row, cited in [('backup',a,identity in old_refs),
                                 ('staging',b,identity in new_refs)] if cited and row is None]
            if missing_versions:
                missing.append({**address,'missing_cited_versions':missing_versions})
            if a is None or b is None:
                # A newly cited row may be new; a retired key need not exist now.
                # Those membership changes are recorded above, not invented as
                # missing currently cited evidence or fictitious zero-value rows.
                continue
            # Existing evidence numeric fields; no new effect or inferential calculation.
            for field in sorted(set(a) | set(b)):
                av, bv = a.get(field, ''), b.get(field, '')
                if _equal(av, bv):
                    continue
                entry = {**address, 'field': field, 'old': _compact(av), 'new': _compact(bv)}
                if _number(av) is not None or _number(bv) is not None:
                    numeric.append(entry)
                elif field in ('status', 'direction', 'direction_changed', 'cell_state', 'repeat_sd_status'):
                    statuses.append(entry)
                elif field.endswith('_json') and any(x in field for x in ('member', 'sequence', 'indices', 'values', 'run_ids')):
                    membership.append(entry)
        statement_changed = new is not None and old['statement'] != new['statement']
        if missing or new is None:
            state = 'needs_reassessment'
        elif statement_changed and not numeric and not statuses and not membership:
            state = 'metadata_or_wording_change_only'
        elif statuses or statement_changed:
            state = 'claim_changed'
        elif numeric or membership:
            state = 'needs_reassessment'
        else:
            state = 'retained_values_unchanged_metadata_updated'
        rows.append({'record_type': 'stage11_claim', 'claim_id': old['claim_id'],
            'configuration_id': (new or old)['configurations_json'], 'case_review_id': '',
            'old_status': old['release_status'], 'new_status': new['release_status'] if new else 'missing',
            'update_assessment': state, 'old_statement_or_role': old['statement'],
            'new_statement_or_role': new['statement'] if new else '',
            'changed_numeric_fields': len(numeric), 'changed_status_fields': len(statuses),
            'changed_membership_fields': len(membership), 'unresolved_evidence_keys': len(missing),
            'evidence_changes_json': js({'numeric': numeric, 'status': statuses, 'membership': membership, 'missing': missing,
                'evidence_registration':{'old_key_count':len(old_refs),'new_key_count':len(new_refs),
                    'added':added_refs,'retired':retired_refs,'comparison_scope':'union of old and current cited evidence keys'},
                'configuration_membership':{'old':json.loads(old['configurations_json']),
                    'new':json.loads(new['configurations_json']) if new else []}}),
            'evidence_keys_json': js(refs),
            'interpretation': 'Changed evidence requires factual/role review; numerical change alone is not proof that the scientific direction reversed. No new paper-line selection.'})
    case_table = 'tables/11c_overview/case_selection_review.csv'
    old, new = (c.index(v, case_table, ('case_review_id',)) for v in ('backup', 'staging'))
    for key in sorted(set(old) | set(new)):
        a, b = old.get(key), new.get(key)
        fields = ('current_example_role', 'current_example_relation_to_predicate', 'keep_replace_supplement_candidate',
                  'supporting_configs', 'counterexample_configs', 'insufficient_configs', 'candidate_status')
        changes = [{'field': f, 'old': a.get(f, '') if a else '', 'new': b.get(f, '') if b else ''}
                   for f in fields if (a.get(f, '') if a else '') != (b.get(f, '') if b else '')]
        row = b or a
        rows.append({'record_type': 'stage11c_case_role', 'claim_id': row['claim_id'],
            'configuration_id': row['current_example_configuration_id'], 'case_review_id': key[0],
            'old_status': a.get('candidate_status', '') if a else 'absent',
            'new_status': b.get('candidate_status', '') if b else 'absent',
            'update_assessment': 'claim_changed' if changes else 'candidate_role_unchanged',
            'old_statement_or_role': a.get('current_example_role', '') if a else '',
            'new_statement_or_role': b.get('current_example_role', '') if b else '',
            'changed_numeric_fields': 0, 'changed_status_fields': len(changes), 'changed_membership_fields': 0,
            'unresolved_evidence_keys': 0, 'evidence_changes_json': js(changes),
            'evidence_keys_json': js({'table': case_table, 'key': {'case_review_id': key[0]},
                'old_current_facts': a.get('current_facts', '') if a else '', 'new_current_facts': b.get('current_facts', '') if b else ''}),
            'interpretation': 'Review every existing case role; retain candidate status, do not automatically replace or finalize manuscript examples.'})
    return rows


def _fmt(value):
    n = _number(value)
    return '未定义' if n is None else f'{n:.6g}'


def _report(c, sequences, results, claims, verify, table_counts):
    delta = _csv(c.configuration_delta_path)
    by_config = {r['configuration_id']: r for r in delta}
    correction_facts = []
    reviewed_note = []
    splatam = bool(c.policy and c.policy.get('reason') == 'audited_splatam_accuracy_protocol_migration')
    sgs = bool(c.policy and c.policy.get('reason') == 'audited_sgs_new_run_batch_protocol_refresh')
    if c.policy:
        build_raw = _read(c.u/'rebuild_manifest.json')
        c.hashes['rebuild_manifest.json'] = sha(build_raw)
        publication = json.loads(build_raw)
        correction_facts.append(f"本轮发布状态：`{publication['status']}`；发布时刻：`{publication.get('published_at', '尚未发布')}`。现行入口及逐文件哈希见 `rebuild_manifest.json`。")
    if splatam:
        context = publication['current_input_manifest']
        d = by_config['SplaTAM::rgbd']
        correction_facts += [
            f"当前全量{context['total_record_count']}条＝带条件{context['condition_labelled_records']}条＋无标签{context['condition_unlabelled_records']}条；24个配置身份与原运行集合均保留。",
            f"仅SplaTAM的Accuracy来源由`{d['old_sha256']}`迁入`{d['new_sha256']}`；采用已审计的外部evo Sim(3) translation APE RMSE(m)。旧原生日志值仍保存在备份，不通过改标签冒充新数值。",
            '逐次来源校验限定于相同run标识、顺序和RMSE有限mask；FPS、runtime、PeakReservedGB原文保持不变。其它23配置使用上一已发布版本的冻结CSV，不顺带纳入后来独立的内存修订。',
            'SR沿用author_protocol_v3_dso_extension的3456条冻结运行；本轮只建立稳定运行键与来源版本对应，不改变成功标签、覆盖、阈值或分母。', '']
        pattern_path = 'tables/11b_review/configuration_patterns.csv'
        before = next(r for r in c.rows('backup', pattern_path) if r['configuration_id'] == 'SplaTAM::rgbd')
        after = next(r for r in c.rows('staging', pattern_path) if r['configuration_id'] == 'SplaTAM::rgbd')
        correction_facts += ['以下为相同带条件子集、序列均值等权下的材料版本差异；旧值来自旧原生评估链，新值为米制外部Sim(3) APE RMSE。**不能将这种协议修订解释为算法性能改善。**', '',
            '| 统计量 | 旧版本 | 本版 |', '|---|---:|---:|']
        for label, field in [('均值','rmse_sequence_mean'), ('中位数','rmse_sequence_median'), ('p90','rmse_sequence_p90'), ('最大序列均值','rmse_sequence_max')]:
            correction_facts.append(f"| {label} | {_fmt(before[field])} | {_fmt(after[field])} |")
        correction_facts += ['', '精确来源：`tables/11b_review/configuration_patterns.csv`，`configuration_id=SplaTAM::rgbd`。', '']
        review_path = c.u / 'claim_review/decisions.csv'
        if review_path.is_file():
            raw_review = _read(review_path)
            c.hashes['claim_review/decisions.csv'] = sha(raw_review)
            decisions = list(csv.DictReader(io.StringIO(raw_review.decode('utf-8-sig'))))
            reviewed = sum(r.get('review_status') == 'reviewed' for r in decisions)
            reviewed_note = [f'**实际解释性复核：{reviewed}/{len(decisions)}项已登记**，见[主张与案例决议](claim_review/decisions.csv)及[措辞修订](claim_review/wording_changes.md)。上表为自动差异标签，不作为未处理待办；不直接清除历史差异日志。C11_COV的覆盖主张保留，变化的是其所引用行中的分布数值；CASE04/10为比较背景更新，CASE09仍为coverage_limited_case。原发布限制保留，未自动批准投稿。', '']
    elif sgs:
        context = publication['current_input_manifest']
        d = by_config['SGS-SLAM::semantic']
        correction_facts += [
            f"当前全量{context['total_record_count']}条＝带条件{context['condition_labelled_records']}条＋无标签{context['condition_unlabelled_records']}条；17方法、24配置身份保留。",
            f"仅SGS输入由`{d['old_sha256']}`替换为`{d['new_sha256']}`；新run 4/5/6替换旧run 1/2/3，保持实际编号，不把六条混合为重复，不宣称旧新物理实验配对。",
            '旧指标为W2C矩阵平移列、Horn刚体R+t且无尺度校正的native mean；新指标为已保存C2W全帧轨迹的外部evo Sim(3)平移APE RMSE（m），frame_index精确关联max_diff=0。协议与实际运行批次同时改变，不能将差值或比值归因为定位精度提升。',
            '其它23配置复用上一发布版冻结CSV；新SGS的FPS、runtime和memory只使用本次来源，不从旧批次填补。运行级字段差异见`input_delta.csv`，配置级来源摘要见`configuration_input_delta.csv`。',
            '历史author_protocol_v3及DSO增量保持原样；新SGS的native完成信号与有类型内存须另按本轮组件核验，不能继承旧run 1/2/3标签，也不虚构SR@80/90/95。当前论文、论文图表及工程包尚未同步。', '']
        pattern_path = 'tables/11b_review/configuration_patterns.csv'
        before = next(r for r in c.rows('backup', pattern_path) if r['configuration_id'] == 'SGS-SLAM::semantic')
        after = next(r for r in c.rows('staging', pattern_path) if r['configuration_id'] == 'SGS-SLAM::semantic')
        correction_facts += ['以下按原有带条件子集及序列均值等权规则并列旧新描述量；两列误差定义和运行批次不同，**不计算净改善率**。', '',
            '| 统计量 | 旧native版本 | 新APE RMSE版本 |', '|---|---:|---:|']
        for label, field in [('均值','rmse_sequence_mean'), ('中位数','rmse_sequence_median'), ('p90','rmse_sequence_p90'), ('最大序列均值','rmse_sequence_max')]:
            correction_facts.append(f"| {label} | {_fmt(before[field])} | {_fmt(after[field])} |")
        correction_facts += ['', '精确来源：`tables/11b_review/configuration_patterns.csv`，`configuration_id=SGS-SLAM::semantic`；数学定义见本轮`audit/sgs_accuracy_protocol.md`。', '']
    elif c.policy:
        preflight_raw = _read(c.u/'input_preflight.json')
        c.hashes['input_preflight.json'] = sha(preflight_raw)
        preflight = json.loads(preflight_raw)
        all_runs, labelled = preflight['all_configurations'], preflight['all_condition_labelled']
        dso_all, dso_labelled = preflight['DSO_all'], preflight['DSO_condition_labelled']
        sr = preflight['sr_compatibility']
        sensitivity = 'tables/09_robustness/sensitivity_estimates.csv'
        v1_key = {'estimate_id':'DSO::mono|speed8_minus2|support_view|V1'}
        v2_key = {'estimate_id':'DSO::mono|speed8_minus2|support_view|V2'}
        old_v1 = c.reference('backup',sensitivity,v1_key)
        v1, v2 = c.reference('staging',sensitivity,v1_key), c.reference('staging',sensitivity,v2_key)
        availability = 'tables/10_relationships/pairwise_availability.csv'
        complementary = {}
        for version in ('backup','staging'):
            complementary[version] = {r['pair_id'] for r in c.rows(version,availability)
                if int(r['only_A_finite_n'])>0 and int(r['only_B_finite_n'])>0}
        added_pairs = sorted(complementary['staging']-complementary['backup'])
        correction_facts += [
            f"当前全量{all_runs['records']}条＝带条件{labelled['records']}条＋无标签{preflight['all_condition_unlabelled_records']}条；RMSE有限分别为全量{all_runs['finite_metric_records']['rmse']}、条件子集{labelled['finite_metric_records']['rmse']}条。",
            f"DSO全量{dso_all['records']}运行/{dso_all['configuration_sequences']}序列、条件子集{dso_labelled['records']}运行/{dso_labelled['configuration_sequences']}序列；有限RMSE分别{dso_all['finite_metric_records']['rmse']}、{dso_labelled['finite_metric_records']['rmse']}条。新增五序列的全部指标文本均NA这一检查为{preflight['all_added_metric_cells_NA']}（input_preflight.json）；这是缺失指标事实，不是SR失败标签。",
            f"DSO速度权重敏感性仍为V1={float(v1['value']):+.6g}、V2={float(v2['value']):+.6g}；R从{old_v1['n_R']}增至{v1['n_R']}，F={v1['n_F']}、C={v1['n_C']}。有限块集合未扩大，原方向差仍保留；不能将已恢复全非有限序列当作可用RMSE填入。",
            f"双向数值可用性互补由{len(complementary['backup'])}对变为{len(complementary['staging'])}对；新增{len(added_pairs)}对为{js(added_pairs)}。C11_AVAIL当前证据名单相应更新；这不是融合收益。",
            f"SR只读对应：旧v3 {sr['frozen_SR_rows']}条中{sr['matched_current_rows']}条稳定逻辑运行键仍对应；原DSO {sr['frozen_SR_DSO_rows']}条保留历史标签，新增{len(sr['not_in_this_SR_version'])}条尚未纳入该SR版本。未运行SR入口或改变历史分母，当前DSO全量SR不能直接沿用旧摘要。", '']
    lines = [MARKER, '# 受控数据版本更新：结果差异与追溯', '',
        '## 实质变化与未改变的边界', '',
        ('本报告将已核验的SplaTAM修订Accuracy接入标准化记录及第7～11C派生表图，复用原阶段公式并定点更新描述。实验保持completed；没有重新运行SLAM/evo、改动源CSV、重算SR或扩大研究范围。'
         if splatam else '本报告接收作者已完成的SGS新批次，复用第6～11C既有统计公式并定点刷新；本报告是机器差异入口，逐项科学解释由claim_impact.csv另行裁定。实验保持completed，本轮未运行SLAM/evo，未修改源CSV、历史SR或现行论文。'
         if sgs else '本报告比较旧备份与新暂存产物，复用原阶段统计公式。五条DSO序列的既有实验被导出代码错误跳过，本次接收用户修正的CSV；原因登记为user_confirmed_export_omission_corrected。实验仍completed，这是分析输入修正，不是新增实验、补跑或新增配置。'
         if c.policy else '本报告比较旧备份与新暂存产物；数值沿用原阶段结果，不重新定义统计。新增、替换和文件登记迁移共同构成新输入版本，不能把全部差异归因于某一次补跑。'), '',
        *correction_facts,
        '| 配置 | 保留记录旧→新 | RMSE有限记录旧→新 | 有限序列旧→新 | 可估repeat_sd序列旧→新 | 当前编号分布 |',
        '|---|---:|---:|---:|---:|---|']
    for config in sorted(c.updated):
        group = [s for s in sequences if s['configuration_id'] == config]
        d = by_config[config]
        totals = {}
        for prefix in ('old', 'new'):
            totals[prefix] = {'n': sum(int(s[prefix + '_n_retained_runs'] or 0) for s in group),
                'f': sum(int(s[prefix + '_n_finite_runs'] or 0) for s in group),
                'seq': sum(int(s[prefix + '_n_finite_runs'] or 0) > 0 for s in group),
                'sd': sum(_number(s[prefix + '_repeat_sd']) is not None for s in group)}
        a, b = totals['old'], totals['new']
        lines.append(f"| `{config}` | {a['n']}→{b['n']} | {a['f']}→{b['f']} | {a['seq']}→{b['seq']} / {len(group)} | {a['sd']}→{b['sd']} | `{d['new_run_distribution']}` |")
    lines += ['', '上表包含带条件与无条件标签序列；后面的方向、共同集合和11C图使用既有 condition_labelled 主子集。三次保留不等于三次有限，也不证明轨迹完成或重复独立。', '']
    for config in sorted(c.updated):
        group = [s for s in sequences if s['configuration_id'] == config]
        newly = [s['sequence_raw'] for s in group if s['newly_finite_sequence']]
        lost = [s['sequence_raw'] for s in group if s['lost_all_finite_results']]
        states = [f"{s['sequence_raw']}:{s['old_state']}→{s['new_state']}" for s in group if s['state_changed']]
        sd = [_number(s['new_repeat_sd']) for s in group if _number(s['new_repeat_sd']) is not None]
        d = by_config[config]
        changed_labels = json.loads(d['same_identifier_changed_raw'])
        shared = [s for s in group if s['old_state']!='no_retained_records' and s['new_state']!='no_retained_records']
        newly_observed = [s for s in group if s['sequence_added_to_export']]
        lines += [f'### {config}', '',
            f"- 当前路径：`{d['new_path']}`；当前 `{d['new_sequence_count']}` 序列，非三条记录序列：`{d['non_three_sequences']}`。",
            f'- 先前全非有限／未观测而本版有有限结果：{js(newly)}；本版失去全部有限结果：{js(lost)}。',
            f"- 两版均有记录的{len(shared)}条序列中，有限数量改变{sum(s['finite_count_changed'] for s in shared)}条；新增到导出清单{len(newly_observed)}条序列，其中{sum(s['new_state']=='observed_all_nonfinite' for s in newly_observed)}条为有记录但RMSE全非有限。无记录→零有限不是原有限值改变。序列均值改变{sum(s['mean_changed'] for s in group)}/{len(group)}；repeat_sd数值或定义状态改变{sum(s['repeat_sd_changed'] for s in group)}/{len(group)}。",
            f"- 当前可估repeat_sd范围：{_fmt(min(sd)) if sd else '未定义'}～{_fmt(max(sd)) if sd else '未定义'}；有限值不足2的序列数 {len(group)-len(sd)}。",
            f'- 同一导出标识下原文字段改变 {len(changed_labels)} 条；这不是已证明的实验身份匹配。完整字段差异见 `input_delta.csv`。',
            f'- 覆盖状态变化：{js(states) if states else "无"}。', '']
    patterns = {v: c.index(v, 'tables/11b_review/configuration_patterns.csv', ('configuration_id',)) for v in ('backup', 'staging')}
    lines += ['## 条件方向、非单调性与有限覆盖', '',
        '| 配置 | 速度正/负/不可算旧→新 | 速度三档非单调旧→新 | 高度正/负/不可算旧→新 | 高度三档非单调旧→新 | 主子集有限/保留运行旧→新 |',
        '|---|---|---:|---|---:|---|']
    for config in sorted(c.updated):
        a, b = (patterns[v][(config,)] for v in ('backup', 'staging'))
        def direction(r, axis):
            return '/'.join(r[f'{axis}_endpoint_{f}'] for f in ('positive', 'negative', 'unavailable'))
        lines.append(f"| `{config}` | {direction(a,'speed')}→{direction(b,'speed')} | {a['speed_triple_nonmonotonic']}→{b['speed_triple_nonmonotonic']} | {direction(a,'altitude')}→{direction(b,'altitude')} | {a['altitude_triple_nonmonotonic']}→{b['altitude_triple_nonmonotonic']} | {a['n_finite_runs']}/{a['n_retained_runs']}→{b['n_finite_runs']}/{b['n_retained_runs']} |")
    direction_changes = [r for r in results if r['table'].endswith(('/speed_response_matrix.csv', '/altitude_response_matrix.csv')) and r['field'] in ('endpoint_direction', 'triple_shape', 'display_status')]
    lines += ['', f'精确到配置×场景×固定条件的方向／三档形状／可算状态变动共 {len(direction_changes)} 项，完整旧新键和值见 `changed_results.csv`；端点方向与三档单调性保持独立。', '',
              '## 方法对共同集合与相关性', '']
    pair_rows = [r for r in results if r['change_kind'] == 'all_pair_review_snapshot']
    numerical_pairs = {r['pair_id'] for r in results if r['table'] in ('tables/10_relationships/pairwise_patterns.csv', 'tables/10_relationships/pairwise_availability.csv') and r['change_kind'] in ('numerical_result_change', 'status_change', 'support_membership_change')}
    rho_changes = [r for r in results if r['table'] == 'tables/10_relationships/pairwise_patterns.csv' and r['field'] == 'rho']
    member_pairs = {r['pair_id'] for r in results if r['table'] == 'tables/10_relationships/pairwise_patterns.csv' and r['field'] in ('F_members_json', 'C_members_json')}
    lines += [f'- 276个无序配置对全部登记并比较，实际快照行 {len(pair_rows)}；没有只复核原六对。',
              f'- 至少一个数值／支持成员／统计状态变化的配置对：{len(numerical_pairs)}/276；F或C成员改变的配置对：{len(member_pairs)}/276；rho变动视图 {len(rho_changes)} 个。',
              '- 全部变动pair_id：' + js(sorted(numerical_pairs)) + '。',
              '- 范围、模态、语义确认造成的处理说明更新与数值变化分开；相同范围不表示单位、对齐和效率协议一致。', '',
              '| 原重点对 | F mean rho旧→新 | F序列数旧→新 | C mean rho旧→新 | C序列数旧→新 |', '|---|---:|---:|---:|---:|']
    old_scope = c.rows('backup', 'tables/10_relationships/comparison_scope.csv')
    focus = {r['pair_id'] for r in old_scope if r['prespecified_focus'] == 'True'}
    for r in pair_rows:
        if r['pair_id'] not in focus:
            continue
        a, b = json.loads(r['old_value']), json.loads(r['new_value'])
        lines.append(f"| `{r['pair_id']}` | {_fmt(a['F_mean'].get('rho'))}→{_fmt(b['F_mean'].get('rho'))} | {a['F_mean'].get('n_sequences','')}→{b['F_mean'].get('n_sequences','')} | {_fmt(a['C_mean'].get('rho'))}→{_fmt(b['C_mean'].get('rho'))} | {a['C_mean'].get('n_sequences','')}→{b['C_mean'].get('n_sequences','')} |")
    lines += ['', '## 旧主张与案例角色', '',
        '| 主张／案例 | 更新评估 | 数值／状态／成员变动字段数 |', '|---|---|---:|']
    for row in claims:
        if row['record_type'] == 'stage11_claim' or row['update_assessment'] == 'claim_changed':
            label = row['claim_id'] if row['record_type'] == 'stage11_claim' else row['case_review_id']
            lines.append(f"| `{label}` | {row['update_assessment']} | {row['changed_numeric_fields']}/{row['changed_status_fields']}/{row['changed_membership_fields']} |")
    wording_only = [r['claim_id'] for r in claims if r['update_assessment'] == 'metadata_or_wording_change_only']
    lines += ['', '`needs_reassessment`表示旧证据数值／成员改变或证据缺失，需要审核措辞与角色，不自动断言方向反转；`claim_changed`记录统计状态、同时伴随证据变化的措辞或案例分类已有改变。`metadata_or_wording_change_only`只表示文字／元数据更新，数值、统计状态、成员和证据完整性均未变。全部原18项主张及既有案例都在 `changed_claims.csv`，未自行确定新的论文主线。',
        '仅文字／元数据更新的主张：' + (', '.join(wording_only) or '无') + '。',
        *(['C11_P5 的相关系数、支持成员及统计状态没有变化；更新的是 MASt3R 当前输入模态说明，仍保留上游标定细节未核实的限制。'] if 'C11_P5' in wording_only else []), '',
        *reviewed_note,
        '## 未变来源一致性与纯元数据迁移', '',
        f"- {verify['n_configurations']}个未变来源配置的数值、统计状态"+('及支持成员' if c.policy else '')+f"核对：{'通过' if verify['passed'] else '未通过，停止受影响结果发布'}；数值容差为相对/绝对1e-12。未解释差异 {len(verify['differences'])} 项。",
        ('- `metadata_changes.csv`保存实际元数据变动；空表表示本次没有改变模态、范围或配置定义。Hier/SplaTAM三次保留及当前输入组声明继续沿用。'
         if c.policy else '- `metadata_changes.csv`单独登记当前范围、语义与输入声明；旧unknown和旧重复计划仅作为历史审计保留。文件名迁移没有增加或拆分configuration_id。'),
        ('- SplaTAM运行集合及RMSE有限状态保持不变；仅修订Accuracy值及其派生关系，不以有限RMSE推断SR，不按成功标签删原误差记录。'
         if splatam else '- SGS新批次保留实际run 4/5/6及逐指标有限状态；旧run 1/2/3不混入本版，不以有限RMSE推断完成信号，不按SR筛除误差或效率。'
         if sgs else '- 恢复的DSO运行保留实际原始字段和逐指标有限状态；不以有限RMSE推断SR，不把历史漏导解释为未运行或失败。'
         if c.policy else '- 若新增保留运行的RMSE均非有限，序列均值可以不变，而运行级有限比例分母会增加；repeat_sd仍可能不可估。序列级1/1不会因此替换为3/3。'),
        ('- SplaTAM Accuracy已按现行来源闭合，runtime全部为秒；其它尚未核实的对齐、计时范围和重复独立性分别保留。旧图内存保持历史快照，不能作为当前Table 2有类型内存入口；没有新的显著性、family推断或因果解释。'
         if splatam else '- SGS新Accuracy协议按本版来源核验；这不自动统一其余23配置。runtime秒单位继续有效，计时范围、重复独立性和不同类型内存的比较边界保持；没有新的显著性、family推断、因果解释或统一排行榜。'
         if sgs else '- 未解决的单位、历史对齐、计时、内存类型及重复独立性保持限制；没有新的显著性、family推断或因果解释。'), '',
        *(['## SR输入边界', '',
           ('现行author_protocol_v3_dso_extension的3456条运行、规则和判定保持完成并冻结；本轮源SHA变更通过configuration_id、sequence及run_id追溯。不将新Accuracy来源哈希当作新增实验或重算SR依据。'
            if splatam else '新SGS批次与旧原生SR运行身份不同：仅本轮SGS组件可按已经批准的native完成规则读取现成信号；不得把旧标签、有限误差或新轨迹存在直接当作本批成功证据。其它23配置及历史SR文件保持不变。具体完成数、未知项和组件路径以本轮独立核验及交接为准；本比较器不执行SR计算。'
            if sgs else 'SR规则及v3既有运行判定保持完成和冻结；本轮仅只读对照稳定逻辑运行键，结果见`sr_input_compatibility.csv`。新版指标清单新增的DSO运行若尚无SR标签，当前DSO全量SR尚不能直接沿用v3的129运行摘要。新运行未纳入该SR版本不表示失败；没有重算SR或改动v3分母。'), '']
          if c.policy else ['## 发布前重新冻结的经过', '',
           '本轮首次冻结后，发布前源哈希校验发现两份 Hier-SLAM 500 帧逐次文件仍在更新；初版没有发布。用户确认源文件已更新完成后，重新冻结当前来源并重建依赖产物。',
           '首次暂存、比较和审阅记录保存在 `superseded_prepublication/initial_freeze/`，供追溯而不作为现行结果。初版出现的 Hier 500 帧重复SD不可估、共同C集合为0等结论已被新冻结版本替代，不能与本报告当前结果混用。', '']),
        '## 执行与追溯', '',
        f'- 更新目录：`{c.u}`。旧文件内容位于 `backup/`，当前构建位于 `staging/`；旧第3～5步证据不改写。',
        '- 本模块不读取源实验CSV或运行研究脚本；仅比较已经生成的标准化/分析表。源输入差异见 `input_delta.csv`，实际命令及发布状态见 `rebuild_manifest.json`。',
        '- 数值/成员证据每行给出旧新表路径、精确键及字段；极大字段以内容哈希和精确位置引用，完整证据仍在对应CSV。',
        '- 图像实际审阅及发布验收由更新入口单独登记；本报告不以脚本返回0替代看图。', '',
        '以下列出本轮阶段构建/已登记审阅命令及最终验证命令。阶段构建写入本更新目录的 `staging/`；逐次执行状态、日志和输入输出哈希以 `rebuild_manifest.json` 为准。`--verify`为最终复核入口，其实际完成状态以verification记录为准。', '',
        '```bash',
        *[f'/home/yuan/anaconda3/bin/python3 -B scripts/refresh_benchmark_results.py --update-dir updates/{c.u.name} --build {stage} --overwrite'
          for stage in ('06', '07', '08', '09', '10', '11')],
        *([] if c.policy else [f'/home/yuan/anaconda3/bin/python3 -B scripts/refresh_benchmark_results.py --update-dir updates/{c.u.name} --record-reviews 11']),
        f'/home/yuan/anaconda3/bin/python3 -B scripts/refresh_benchmark_results.py --update-dir updates/{c.u.name} --build 11B --overwrite',
        f'/home/yuan/anaconda3/bin/python3 -B scripts/refresh_benchmark_results.py --update-dir updates/{c.u.name} --record-reviews 11B',
        f'/home/yuan/anaconda3/bin/python3 -B scripts/refresh_benchmark_results.py --update-dir updates/{c.u.name} --build 11C --overwrite',
        f'/home/yuan/anaconda3/bin/python3 -B scripts/refresh_benchmark_results.py --update-dir updates/{c.u.name} --record-reviews 11C',
        f'/home/yuan/anaconda3/bin/python3 -B scripts/refresh_benchmark_results.py --update-dir updates/{c.u.name} --verify',
        '```', '',
        *(['第11步及11B/11C是否需要重新登记取决于本次实际图像哈希；相同SHA可继承既有实际审阅回执，变化图必须重新查看。最终状态以verification及visual_reviews为准，不由本比较报告预设完成。', ''] if splatam or sgs else
          ['本次未执行`--record-reviews 11`：第11步三张PNG与已审阅版本哈希一致，沿用原有效视觉回执。11B/11C的新增或变化PNG已按当前哈希单独审阅并登记；未将旧图哈希回执用于变化图。', ''] if c.policy else []),
        '`--record-reviews`依据逐张实际看图且绑定最终PNG哈希的回执登记；它不把仅生成文件当成视觉审阅。', '',
        '发布必须在验证通过后单独执行下面的命令；本比较模块没有执行发布。是否已执行及发布是否完成，应查看 `rebuild_manifest.json` 的实际状态，不能由报告生成推断。', '',
        '```bash',
        f'/home/yuan/anaconda3/bin/python3 -B scripts/refresh_benchmark_results.py --update-dir updates/{c.u.name} --publish --overwrite',
        '```', '',
        '比较表范围及行数：', '', '| 表 | 旧行数 | 新行数 | 变动字段 |', '|---|---:|---:|---:|']
    for table, d in table_counts.items():
        lines.append(f"| `{table}` | {d['old_rows']} | {d['new_rows']} | {d['changed_fields']} |")
    if not verify['passed']:
        lines += ['', '未解释的数值差异：', '', '```json', js(verify['differences']), '```']
    return '\n'.join(lines) + '\n'


def _csv_bytes(rows):
    if not rows:
        raise ValueError('Expected nonempty comparison output')
    fields = list(dict.fromkeys(k for row in rows for k in row))
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()


def build_update_comparison(update_dir, overwrite=False):
    """Write comparison artifacts; explicit refresh requires the prior saved hashes."""
    c = Comparison(update_dir)
    previous_hashes = {}
    verification_path = c.u / 'comparison_verification.json'
    verification_hash = None
    if overwrite:
        verification_raw = _read(verification_path)
        verification_hash = sha(verification_raw)
        previous_hashes = json.loads(verification_raw)['output_sha256']
        if set(previous_hashes) != set(OUTPUTS):
            raise ValueError('Prior comparison verification must register exactly the four generated outputs')
    for name in OUTPUTS:
        path = c.u / name
        if path.exists() and not overwrite:
            raise FileExistsError('Refusing to replace an existing update comparison: ' + name)
        if overwrite:
            if not path.is_file() or path.stat().st_nlink != 1 or sha(_read(path)) != previous_hashes[name]:
                raise ValueError('Explicit comparison refresh rejected: unregistered or edited output ' + name)
    sequences = _sequence_changes(c)
    results, counts = _all_table_changes(c)
    pair_snapshots = _pair_snapshots(c)
    if c.full_field_comparison:
        for row in pair_snapshots:
            row['change_type'] = 'all_pair_review_snapshot'
            row['comparison_scope'] = 'existing complete 276-pair registry; no recomputation'
    results.extend(pair_snapshots)
    if c.full_field_comparison:
        for row in results:
            # Stage is provenance only; preserve the existing result key and values.
            row['stage'] = row['table'].split('/')[1].split('_')[0].upper()
    claims = _claim_changes(c)
    verification = _verify_unchanged(c)
    report = _report(c, sequences, results, claims, verification, counts)
    if not c.unchanged_inputs():
        raise ValueError('An input artifact changed while comparing versions')
    blobs = {'sequence_changes.csv': _csv_bytes(sequences), 'changed_results.csv': _csv_bytes(results),
             'changed_claims.csv': _csv_bytes(claims), 'update_report.md': report.encode()}
    if overwrite:
        if sha(_read(verification_path)) != verification_hash:
            raise ValueError('Comparison verification changed during explicit refresh')
        for name in OUTPUTS:
            if sha(_read(c.u / name)) != previous_hashes[name]:
                raise ValueError('Comparison output changed during explicit refresh: ' + name)
    for name, raw in blobs.items():
        path = c.u / name
        flags = os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW | (os.O_TRUNC if overwrite else os.O_EXCL)
        with os.fdopen(os.open(path, flags, 0o666), 'wb') as stream:
            stream.write(raw)
    return {'sequence_rows': len(sequences), 'changed_result_rows': len(results),
            'claim_rows': len(claims), 'all_pair_snapshots': 276, 'unchanged_configurations': verification,
            'input_sha256': c.hashes,
            'output_sha256': {name: sha(raw) for name, raw in blobs.items()},
            'explicit_refresh': overwrite, 'previous_output_sha256': previous_hashes,
            'previous_verification_sha256': verification_hash,
            'status': 'comparison_complete' if verification['passed'] else 'blocked_unexplained_numeric_drift'}
