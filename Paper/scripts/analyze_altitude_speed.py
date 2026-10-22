#!/usr/bin/env python3
"""Step 8 only: descriptive altitude x speed x scene analysis of step-6 records."""
import argparse
from collections import Counter, defaultdict
import io
import itertools
import json
import math
import os
from pathlib import Path
import shlex
import sys
import tempfile
from unittest.mock import patch
import numpy as np
# Pure functions only: never invoke an earlier stage's main().
from explore_benchmark import (describe, sequence_table, summary_group, finite_values,
                               validate_inputs, js, sha, fmt, META, METRICS, LEVELS, SCENES, unit_limit)
from build_analysis_dataset import read_bytes, decode_csv, csv_text, reject_links
from version_support import workspace as controlled_workspace, current_version

W = controlled_workspace('/home/yuan/SLAM/codex_review/benchmark_analysis')
INPUT_CONTEXT = current_version(W)
HEIGHTS = (10, 20, 30)
SPEEDS = (2, 4, 8)
ALL = '__all_scenes__'
INPUTS = {
    'records': 'derived_data/06_standardized/run_records.csv',
    'manifest': 'derived_data/06_standardized/source_manifest.csv',
    'schema': 'derived_data/06_standardized/schema.json',
    'coverage': 'reports/06_sequence_coverage.csv',
    'previous_spec': 'reports/07_exploration_spec.json',
    'previous_report': 'reports/07_exploratory_analysis.md',
    'questions': 'reports/07_research_questions.csv',
    'previous_summary': 'tables/07_eda/descriptive_summary.csv',
    'previous_sequence': 'tables/07_eda/sequence_metrics.csv',
}
OUTPUTS = {
    'spec': 'reports/08_condition_analysis_spec.json',
    'joint': 'tables/08_conditions/joint_metrics.csv',
    'contrasts': 'tables/08_conditions/conditional_contrasts.csv',
    'efficiency': 'tables/08_conditions/efficiency_cohort_cells.csv',
    'questions': 'reports/08_question_assessment.csv',
    'report': 'reports/08_altitude_speed_analysis.md',
}
FIGURES = {
    '01_orb2_condition_rmse': 'Q1: road/building 3x3 RMSE with common within-configuration scale; test tail concentration.',
    '02_orb2_speed_curves': 'Q1: road/building speed curves at real 2,4,8 coordinates; missing cells break lines.',
    '03_droid_pool_conditions': 'Q2: pool 3x3 and speed curves; whether a few conditions dominate the scene mean.',
    '04_orb3_condition_rmse': 'Q3: road/building 3x3 means with coverage; place repeat cases within surrounding cells.',
    '05_orb3_retained_repeats': 'Q3: the three sequence names in the existing question; retain every run ID and missing label.',
    '06_vggt_coverage_rmse': 'Q4: pool/roundabout coverage beside RMSE; distinguish no records and all-nonfinite.',
    '07_hier_runtime_cohorts': 'Q5: houses/pool runtime A/B in all nine cells, including unaffected backgrounds; other efficiency metrics in table.',
}
for name in FIGURES:
    for ext in ('png', 'svg'):
        OUTPUTS[name+'.'+ext] = 'figures/08_conditions/'+name+'.'+ext

def check_output(path, overwrite=False):
    if path not in {W / p for p in OUTPUTS.values()}:
        raise ValueError('Outside step-8 output allowlist: '+str(path))
    reject_links(path)
    if not path.resolve().is_relative_to(W.resolve()):
        raise ValueError('Output escapes workspace')
    if path.exists():
        if not overwrite: raise FileExistsError('Refusing overwrite: '+str(path))
        if not path.is_file() or path.stat().st_nlink != 1:
            raise ValueError('Linked/nonregular output rejected: '+str(path))

def write(key, content, overwrite):
    p=W/OUTPUTS[key]
    check_output(p, overwrite); p.parent.mkdir(parents=True, exist_ok=True);check_output(p,overwrite)
    flags=os.O_WRONLY|os.O_CREAT|os.O_NOFOLLOW|(os.O_TRUNC if overwrite else os.O_EXCL)
    with os.fdopen(os.open(p, flags, 0o666), 'wb') as f:
        f.write(content.encode() if isinstance(content,str) else content)

def cell_state(n, k):
    if n==0: return 'no_retained_records'
    if k==0: return 'observed_all_nonfinite'
    return 'observed_all_finite' if n==k else 'observed_partial_finite'

def index_rows(rows):
    grouped=defaultdict(list)
    for r in rows:
        key=(r['configuration_id'],r['scene'],r['altitude_m'],r['speed_mps'])
        grouped[key].append(r)
        grouped[(key[0],ALL,key[2],key[3])].append(r)
    return grouped

def cell_key(config,scene,h,v,metric='rmse',level=LEVELS[1]):
    return (config,scene,h,v,metric,level)

def sequence_details(rows, metric):
    groups=defaultdict(list)
    for r in rows:groups[r['sequence_raw']].append(r)
    result=[]
    for name, group in sorted(groups.items()):
        vals=finite_values(group,metric);s=describe(vals)
        result.append({
            'sequence':name, 'scene':group[0]['scene'],
            'n_retained':len(group),'n_finite':len(vals),
            'mean':s['mean'],'median':s['median'],
            'repeat_sd':s['sample_sd'],'finite_range':max(vals)-min(vals) if vals else None,
            'retained_runs':[{'run_id':r['run_id_raw'],'source_record_index':r['source_record_index'],
                              'raw_dataset':r['raw_dataset'],'value':r[metric+'_value'],
                              'state':r[metric+'_state']} for r in group],
        })
    return result

def joint_cell(rows, source, scene, h, v, metric):
    # Reuse audited stage-7 aggregation and metric-specific finite sets.
    stats=summary_group(rows,source['configuration_id'],'condition_labelled',scene,metric,source)
    details=sequence_details(rows,metric)
    used=[r for r in rows if r[metric+'_is_finite']]
    finite_sequences=sorted({r['sequence_raw'] for r in used})
    contribution={}
    for sc in SCENES:
        group=[d for d in details if d['scene']==sc]
        n=sum(d['n_finite']>0 for d in group)
        contribution[sc]={'n_records':sum(d['n_retained'] for d in group),
                          'n_finite_records':sum(d['n_finite'] for d in group),
                          'n_observed_sequences':len(group),'n_finite_sequences':n,
                          'sequence_mean_weight':n/len(finite_sequences) if finite_sequences else None}
    common={
        'scene':scene,'altitude_m':h,'speed_mps':v,
        'cell_state':cell_state(len(rows),len(used)),
        'sequences_json':js([d['sequence'] for d in details]),
        'finite_sequences_json':js(finite_sequences),
        'source_relative_path':source['source_relative_path'],'source_sha256':source['source_sha256'],
        'source_record_indices_json':js([r['source_record_index'] for r in rows]),
        'finite_source_record_indices_json':js([r['source_record_index'] for r in used]),
        'sequence_descriptors_json':js(details),
        'retained_scenes_json':js([s for s in SCENES if contribution[s]['n_records']]),
        'finite_scenes_json':js([s for s in SCENES if contribution[s]['n_finite_records']]),
        'scene_contributions_json':js(contribution),
        'display_grid_only':True,
    }
    return [{**{k:v for k,v in s.items() if k not in ('q25','q75','p90')},
             **common,'group_type':'all_scenes_condition' if scene==ALL else 'scene_condition'} for s in stats]

def joint_table(rows,sources):
    groups=index_rows(rows);result=[]
    for config,source in sorted(sources.items()):
        for scene,h,v,metric in itertools.product((*SCENES,ALL),HEIGHTS,SPEEDS,METRICS):
            result.extend(joint_cell(groups[(config,scene,h,v)],source,scene,h,v,metric))
    return result

ENDPOINT_FIELDS=('altitude_m','speed_mps','cell_state','mean','median','n_retained_records',
    'n_finite_records','n_observed_sequences','n_sequences_with_finite','n_sequences_without_finite',
    'finite_fraction','n_values_used','sequences_json','finite_sequences_json',
    'source_record_indices_json','finite_source_record_indices_json','scene_contributions_json')

def endpoint(row):
    return {k[:-5] if k.endswith('_json') else k:json.loads(row[k]) if k.endswith('_json') else row[k] for k in ENDPOINT_FIELDS}

def contrast_value(endpoints, coefficients):
    if any(e['mean'] is None for e in endpoints):
        return None,'unavailable','; '.join(f"H={e['altitude_m']},V={e['speed_mps']}:{e['cell_state']}" for e in endpoints if e['mean'] is None)
    return sum(c*e['mean'] for c,e in zip(coefficients,endpoints)),'computed',''

def make_contrast(cells,kind,direction,axis,fixed_value,coefficients):
    a=cells[0];ep=[endpoint(c) for c in cells]
    delta,status,reason=contrast_value(ep,coefficients)
    coverage_fields=('n_retained_records','n_observed_sequences','n_finite_records','n_sequences_with_finite','finite_fraction','cell_state')
    changed=any(any(c[k]!=a[k] for k in coverage_fields) for c in cells[1:])
    fractions=[c['finite_fraction'] for c in cells]
    frac_delta=sum(c*x for c,x in zip(coefficients,fractions))*100 if all(x is not None for x in fractions) else None
    return {
        **{k:a[k] for k in META},'scene':a['scene'],'subset':'condition_labelled',
        'metric':a['metric'],'aggregation_level':a['aggregation_level'],
        'contrast_kind':kind,'direction':direction,'fixed_axis':axis,'fixed_value':fixed_value,
        'coefficients_json':js(coefficients),'endpoints_json':js(ep),'difference':delta,
        'difference_unit':a['metric']+' source units','finite_fraction_difference_pp':frac_delta,
        'status':status,'unavailable_reason':reason,'coverage_or_validity_counts_changed':changed,
        'retained_sequence_sets_differ':any(c['sequences_json']!=a['sequences_json'] for c in cells[1:]),
        'finite_sequence_sets_differ':any(c['finite_sequences_json']!=a['finite_sequences_json'] for c in cells[1:]),
        'members_note':'Condition-specific sequence names; differing sets do not establish route matching or a causal confound.',
        'source_relative_path':a['source_relative_path'],'source_sha256':a['source_sha256'],
        'measurement_limit':a['measurement_limit'],
        'interpretation':'descriptive difference of cell means; no run-ID pairing; not a slope, causal effect or significance test',
    }

def contrast_table(joint,sources):
    lookup={cell_key(r['configuration_id'],r['scene'],r['altitude_m'],r['speed_mps'],r['metric'],r['aggregation_level']):r for r in joint}
    result=[]
    for config,scene in itertools.product(sorted(sources),SCENES):
        for metric,level in itertools.product(METRICS,LEVELS):
            get=lambda h,v:lookup[cell_key(config,scene,h,v,metric,level)]
            for h,(lo,hi) in itertools.product(HEIGHTS,((2,4),(4,8),(2,8))):
                result.append(make_contrast([get(h,lo),get(h,hi)],'speed_difference',f'{hi} - {lo}','altitude_m',h,[-1,1]))
            for v,(lo,hi) in itertools.product(SPEEDS,((10,20),(20,30),(10,30))):
                result.append(make_contrast([get(lo,v),get(hi,v)],'altitude_difference',f'{hi} - {lo}','speed_mps',v,[-1,1]))
        corners=[lookup[cell_key(config,scene,h,v)] for h,v in ((30,8),(30,2),(10,8),(10,2))]
        result.append(make_contrast(corners,'rmse_four_corner','(H30V8-H30V2)-(H10V8-H10V2)','none',None,[1,-1,-1,1]))
    return result

def efficiency_cells(rows,sources):
    affected=sorted({r['configuration_id'] for r in rows if not r['rmse_is_finite'] and any(r[m+'_is_finite'] for m in METRICS[1:])})
    groups=index_rows(rows);result=[]
    for config,scene,h,v,metric in itertools.product(affected,(*SCENES,ALL),HEIGHTS,SPEEDS,METRICS[1:]):
        group=groups[(config,scene,h,v)]
        a=[r for r in group if r[metric+'_is_finite']]
        b=[r for r in a if r['rmse_is_finite']]
        excluded=[r for r in a if not r['rmse_is_finite']]
        sa,sb=describe(finite_values(a,metric)),describe(finite_values(b,metric))
        result.append({
            **{k:sources[config][k] for k in META},'scene':scene,'altitude_m':h,'speed_mps':v,
            'subset':'condition_labelled','metric':metric,'aggregation_level':'pooled_retained_runs',
            'n_retained_records':len(group),'n_A':len(a),'n_B':len(b),'n_A_not_B':len(excluded),
            'A_mean':sa['mean'],'B_mean':sb['mean'],'A_median':sa['median'],'B_median':sb['median'],
            'B_minus_A_mean':sb['mean']-sa['mean'] if a and b else None,
            'status':'computed' if a and b else 'unavailable',
            'A_cell_state':cell_state(len(group),len(a)),'B_cell_state':cell_state(len(group),len(b)),
            'source_relative_path':sources[config]['source_relative_path'],'source_sha256':sources[config]['source_sha256'],
            'sequences_json':js(sorted({r['sequence_raw'] for r in group})),
            'A_record_indices_json':js([r['source_record_index'] for r in a]),
            'B_record_indices_json':js([r['source_record_index'] for r in b]),
            'A_not_B_record_indices_json':js([r['source_record_index'] for r in excluded]),
            'A_not_B_datasets_json':js([r['raw_dataset'] for r in excluded]),
            'measurement_limit':unit_limit(sources[config],metric),
        })
    return result

def make_spec(raw,schema,command):
    return {
        'generated_by':'scripts/analyze_altitude_speed.py','spec_version':'1.0.0','schema_version':schema['schema_version'],
        'protocol_wording_template':{'path':'scripts/review_all_configurations_narrative.py','sha256':sha(Path(__file__).with_name('review_all_configurations_narrative.py').read_bytes())},
        'purpose':'Exploratory descriptive conventions; not preregistration or legacy table reconstruction.',
        'command':command,'inputs':{k:{'path':INPUTS[k],'sha256':sha(v),'role':'only_run_performance_input' if k=='records' else 'context_or_crosscheck'} for k,v in raw.items()},
        'previous_hash_check':'records/manifest/schema must equal step-7 spec; stop on change',
        'main_subset':'condition_label_status == two_tokens; use existing numeric conditions, no name parser',
        'display_grid':{'altitude_m':HEIGHTS,'speed_mps':SPEEDS,'scenes':SCENES,'all_scenes_label':ALL,
                        'meaning':'summary display grid, not attempted/expected runs; no rows added to records'},
        'grouping':['configuration x observed sequence x metric (memory only; embedded repeat descriptors)',
                    'configuration x scene x altitude x speed x metric x aggregation_level',
                    'configuration x all current scenes x altitude x speed x metric x aggregation_level'],
        'levels':dict(zip(LEVELS,['finite retained runs','equal weight per-sequence finite-run means'])),
        'statistics':'mean/median/min/max/sample_sd ddof=1; n<2 sd undefined; independent metric finite sets; no unit conversion, trimming, filling or weighting by frames/runtime/sse',
        'repeat_sd':'within observed sequence, finite values ddof=1; separate from sequence-mean sample_sd; raw_std unused',
        'denominator':'actual retained records only; finite_fraction=finite/retained, n=0 undefined; all-nonfinite n>0 fraction 0',
        'states':['no_retained_records','observed_all_nonfinite','observed_partial_finite','observed_all_finite'],
        'provenance':'row source path+sha256+index arrays; endpoint and sequence descriptors retain actual members',
        'scene_weights':'number of finite sequences in scene / number of finite sequences across scenes, undefined if no finite sequences',
        'contrasts':{'scope':'five scenes within each configuration; all-scene cells remain composition-qualified supplements',
                     'speed':['4-2','8-4','8-2'],'altitude':['20-10','30-20','30-10'],
                     'formula':'high-condition cell mean minus low-condition cell mean, separately for two levels; no run pairing, no percent ratios, no equal-step slopes',
                     'missing':'keep unavailable and endpoint reason if either mean absent',
                     'finite_fraction_difference':'100*(endpoint high fraction - endpoint low fraction), percentage points',
                     'four_corner':'RMSE equal-sequence only: (H30V8-H30V2)-(H10V8-H10V2); all four required, not causal DID'},
        'efficiency':'for every configuration with any A-not-B record, all nine cells in all five scenes and all_scenes; A=efficiency finite, B=also RMSE finite; include unaffected cells',
        'figure_selection':FIGURES,'max_figures':len(FIGURES),
        'selection_reason':'Fixed follow-ups to existing Q1-Q5 and user named cases, not representative sampling or performance ranking; no extra selection by favorable outcomes.',
        'question_assessment':'Link existing question_id; statuses are descriptive support/limits, not significance. Evidence and caveats derived from actual cells.',
        'outputs':list(OUTPUTS.values()),
        'bounds':['no experiment_data access','no changes to stages 1-7','no inference/regression/bootstrap/CI',
                  'no scene-removal or forced common-support analysis','no causal attribution or cross-method ranking',
                  'same scene does not verify same route; finite RMSE does not prove complete trajectory',
                  '500 frames, whole trajectory and unknown scopes stay separate; measurement history remains qualified'],
    }

def lookup_joint(joint):
    return {cell_key(r['configuration_id'],r['scene'],r['altitude_m'],r['speed_mps'],r['metric'],r['aggregation_level']):r for r in joint}

def compact_cell(r):
    return f"H{r['altitude_m']} V{r['speed_mps']}: {fmt(r['mean'])} ({r['n_finite_records']}/{r['n_retained_records']}, seq {r['n_sequences_with_finite']}/{r['n_observed_sequences']})"

def assess_questions(questions,joint,efficiency,sequences):
    lookup=lookup_joint(joint);out=[]
    def grid(c,sc):
        return [lookup[cell_key(c,sc,h,v)] for h,v in itertools.product(HEIGHTS,SPEEDS)]
    for q in questions:
        c=q['configuration_id'];sq=[s for s in sequences if s['configuration_id']==c and s['metric']=='rmse']
        names=json.loads(q['sequence_names_json'])
        anchors=[s for s in sq if s['sequence_raw'] in names]
        allvalid=[s for s in sq if s['mean'] is not None]
        evidence=[];status='unresolved';limit='名义条件，路线一致性与实际采集差异未独立核实；仅描述当前有限结果。'
        if c=='ORB-SLAM2::mono':
            selected=sorted(allvalid,key=lambda s:(-s['mean'],s['sequence_raw']))[:3]
            top_sum=sum(s['mean'] for s in selected);total=sum(s['mean'] for s in allvalid)
            support=bool(selected) and all(s['altitude_m']==30 for s in selected)
            status='descriptive_support' if support else 'not_supported_by_current_description'
            evidence=[*grid(c,'road'),*grid(c,'building')]
            road=grid(c,'road')
            vals='；'.join(compact_cell(lookup[cell_key(c,'road',30,v)]) for v in SPEEDS)
            obs=f"实际最高三条序列的高度为 {[s['altitude_m'] for s in selected]} m、速度 {[s['speed_mps'] for s in selected]} m/s；均值和占全部有限序列均值和 {top_sum/total:.2%}。road 30m：{vals}。"
            changes=[]
            for sc in ('road','building'):
                for h in (10,30):
                    a,b=lookup[cell_key(c,sc,h,2)],lookup[cell_key(c,sc,h,8)]
                    changes.append(f"{sc} H{h}: V2→V8 {fmt(a['mean'])}→{fmt(b['mean'])}, 差={fmt(b['mean']-a['mean']) if a['mean'] is not None and b['mean'] is not None else '未定义'}, 覆盖 {a['n_finite_records']}/{a['n_retained_records']}→{b['n_finite_records']}/{b['n_retained_records']}")
            obs+=' 相反方向的条件变化：'+'；'.join(changes)+'。最高三序列的有限重复最小值分别为 '+js([s['min'] for s in selected])+'；这些锚点的高均值有多个有限重复支持，而不是仅一个高值。'
            limitation=limit+'最高三条的集中不等于所有30m条件均较差；10m与30m速度变化方向相反，不能声称普遍随高度或速度增加退化。'
            nextq='第9步核查高值是否由单次重复主导，以及组成和有限结果选择对该局部集中结论的影响；不推广成高度因果效应。'
        elif c=='DROID-SLAM::rgbd':
            evidence=grid(c,'pool');finite=sorted([r for r in evidence if r['mean'] is not None],key=lambda r:(-r['mean'],r['altitude_m'],r['speed_mps']))
            share=sum(r['mean'] for r in finite[:3])/sum(r['mean'] for r in finite)
            status='descriptive_support' if len(finite)==9 and share>.5 else 'not_supported_by_current_description'
            obs=f"pool 有 {len(finite)}/9 个均值可计算格；最高三格均值之和占九格有限均值和 {share:.2%}（格内序列数另见表）；最高三格："+'；'.join(compact_cell(r) for r in finite[:3])+'；最低格：'+compact_cell(finite[-1])+'。'
            poolseq=[s for s in sq if s['scene']=='pool']
            identical=sum(s['n_finite_runs']>=2 and s['finite_range']==0 for s in poolseq)
            differences=[lookup[cell_key(c,'pool',h,8)]['mean']-lookup[cell_key(c,'pool',h,2)]['mean'] for h in HEIGHTS]
            height_differences=[lookup[cell_key(c,'pool',30,v)]['mean']-lookup[cell_key(c,'pool',10,v)]['mean'] for v in SPEEDS]
            obs+=f" 各高度10/20/30m的V8−V2分别为 {js(differences)}；各速度2/4/8m/s的H30−H10分别为 {js(height_differences)}。{identical}/{len(poolseq)} 条pool序列的已保留有限重复值完全相同。"
            limitation=limit+'“前三格超过50%”仅为集中程度描述，不是显著性或通用异常阈值；本轮没有确认相同重复数值的生成原因，不能据此证明独立实验的稳定性；场景差异不是场景因果效应。'
            nextq='第9步优先核查pool条件集中是否对保留重复值与有限集合敏感，区分场景边际组成和具体条件差异。'
        elif c=='ORB-SLAM3::rgbd':
            evidence=[*grid(c,'road'),*grid(c,'building')]
            parts=[]
            for name in names:
                s=next(s for s in anchors if s['sequence_raw']==name)
                parts.append(f"{name} (H{s['altitude_m']},V{s['speed_mps']}): mean={fmt(s['mean'])}, finite={s['n_finite_runs']}/{s['n_retained_runs']}, values={s['finite_values_json']}, range={fmt(s['finite_range'])}, repeat_sd={fmt(s['repeat_sd'])}")
            obs='；'.join(parts)+'。这些差异发生于各自固定名义条件的重复之间，不能由高度或速度改变直接解释。'
            nearby=next(s for s in sq if s['scene']=='road' and s['altitude_m']==20 and s['speed_mps']==4)
            obs+=f" 邻近road H20,V4：mean={fmt(nearby['mean'])}, values={nearby['finite_values_json']}, repeat_sd={fmt(nearby['repeat_sd'])}, finite={nearby['n_finite_runs']}/{nearby['n_retained_runs']}；因此高均值不能全部解释为单次偏离。"
            status='repeat_limited'
            limitation=limit+'部分单元只有两个有限值；三个案例分布在不同高度/速度，不能据此确立统一条件相关波动模式。'
            nextq='第9步评估具体重复值对高均值结论的敏感性，以及条件趋势是否稳定；不把同条件波动当条件效应。'
        elif c=='VGGT-SLAM::mono':
            evidence=[*grid(c,'pool'),*grid(c,'roundabout')]
            fragments=[]
            for sc in ('pool','roundabout'):
                g=grid(c,sc);counts=Counter(r['cell_state'] for r in g)
                invalid=[f"H{r['altitude_m']}V{r['speed_mps']}" for r in g if r['cell_state']=='observed_all_nonfinite']
                available=[r for r in g if r['mean'] is not None]
                low=min(available,key=lambda r:r['mean'])
                fragments.append(f"{sc} 状态={dict(counts)}；全无效位置={invalid}；最低有限均值格 {compact_cell(low)}")
            obs='；'.join(fragments)+'。'
            status='coverage_limited';limitation=limit+'可用均值只覆盖有限结果；缺失原因未知，低均值不能称为鲁棒性改善。'
            nextq='第9步先评估覆盖与有限结果选择对条件描述的影响，再决定哪些条件误差可合理比较。'
        elif c=='hierslam::rgbd_whole':
            changed=[r for r in efficiency if r['configuration_id']==c and r['scene']!=ALL and r['metric']=='runtime' and r['n_A_not_B']]
            evidence=[*grid(c,'houses'),*grid(c,'pool')]
            support=bool(changed) and all(r['speed_mps']==8 for r in changed)
            status='descriptive_support' if support else 'not_supported_by_current_description'
            obs='runtime 集合变化位置：'+'；'.join(f"{r['scene']} H{r['altitude_m']} V{r['speed_mps']}, A/B={r['n_A']}/{r['n_B']}, Amean={fmt(r['A_mean'])}, Bmean={fmt(r['B_mean'])}, B-A={fmt(r['B_minus_A_mean'])}, excluded={r['A_not_B_record_indices_json']}" for r in changed)+'。'
            positive=[r for r in changed if r['B_minus_A_mean']>0]
            negative=[r for r in changed if r['B_minus_A_mean']<0]
            obs+=f" 受影响单元中，B−A为正 {len(positive)} 个、为负 {len(negative)} 个；不能将整体均值下降推广到所有条件。"
            limitation=limit+'只说明筛除位置集中；不同条件B−A方向不同，未证明高速导致缺失或B更正确。完整轨迹为配置范围，不是每次完成判定。'
            nextq='第9步检查整体效率集合差异对当前实际排除记录及条件/场景权重的敏感性，保持FPS、runtime和内存定义独立。'
        else: raise ValueError('Unhandled existing research question: '+q['question_id'])
        out.append({
            'question_id':q['question_id'],'configuration_id':c,'status':status,
            'original_question':q['next_question'],'observation':obs,'limitations':limitation,'next_step_question':nextq,
            'involved_conditions_json':js([{'scene':r['scene'],'altitude_m':r['altitude_m'],'speed_mps':r['speed_mps'],'cell_state':r['cell_state']} for r in evidence]),
            'joint_table_keys_json':js([list(cell_key(c,r['scene'],r['altitude_m'],r['speed_mps'])) for r in evidence]),
            'source_relative_path':anchors[0]['source_relative_path'],'source_sha256':anchors[0]['source_sha256'],
            'anchor_sequence_names_json':js(names),
            'anchor_source_indices_json':js({s['sequence_raw']:json.loads(s['source_record_indices_json']) for s in anchors}),
            'evidence_tables':'joint_metrics.csv; conditional_contrasts.csv'+('; efficiency_cohort_cells.csv' if c=='hierslam::rgbd_whole' else ''),
            'interpretation':'descriptive assessment, not a significance label',
        })
    return out

def draw_figures(joint,efficiency,questions,sources,overwrite):
    root=W/'reports/.08_conditions_tmp';reject_links(root)
    created=not root.exists();root.mkdir(exist_ok=True)
    old={k:os.environ.get(k) for k in ('MPLCONFIGDIR','XDG_CACHE_HOME','TMPDIR')}
    lookup=lookup_joint(joint);figures=[]
    qlookup={q['configuration_id']:q for q in questions}
    try:
        with tempfile.TemporaryDirectory(prefix='run_',dir=root) as tmp:
            for k in old:os.environ[k]=tmp
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            from matplotlib.colors import Normalize, TwoSlopeNorm
            from matplotlib.patches import Rectangle
            plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.titlesize':11,'svg.hashsalt':'benchmark-step8'})
            def get(c,sc,h,v):return lookup[cell_key(c,sc,h,v)]
            def save(fig,name,c,title,note):
                fig.suptitle(title+'\n'+c,fontsize=14,y=.98)
                caption=f"{c} | condition_labelled | scope={sources[c]['evaluation_scope']}\n{note}"
                fig.text(.015,.015,caption,fontsize=8,va='bottom')
                hashes={}
                for ext in ('png','svg'):
                    buffer=io.BytesIO()
                    meta={'Software':'benchmark step-8 exploration'} if ext=='png' else {'Date':None,'Creator':'benchmark step-8 exploration'}
                    fig.savefig(buffer,format=ext,dpi=130,bbox_inches='tight',metadata=meta)
                    data=buffer.getvalue();write(name+'.'+ext,data,overwrite);hashes[ext]=sha(data)
                plt.close(fig);figures.append({'name':name,'configuration_id':c,'caption':caption,'sha256':hashes})
            def heat(ax,c,sc,fraction=False,norm=None):
                rows=[get(c,sc,h,v) for h,v in itertools.product(HEIGHTS,SPEEDS)]
                vals=np.array([r['finite_fraction'] if fraction else r['mean'] for r in rows],dtype=float).reshape(3,3)
                cmap=plt.get_cmap('YlGnBu').copy();cmap.set_bad('#eeeeee')
                im=ax.imshow(np.ma.masked_invalid(vals),cmap=cmap,norm=norm or Normalize(0,1),origin='upper',aspect='auto')
                for i,h in enumerate(HEIGHTS):
                    for j,v in enumerate(SPEEDS):
                        r=get(c,sc,h,v);state=r['cell_state'];val=r['finite_fraction'] if fraction else r['mean']
                        if state=='no_retained_records':label='NO RECORDS\nn=0';ax.add_patch(Rectangle((j-.5,i-.5),1,1,fill=False,hatch='///',edgecolor='#bbbbbb'))
                        elif state=='observed_all_nonfinite':label=f"ALL NONFINITE\n0/{r['n_retained_records']}"
                        else:
                            label=f"{val:.3g}\n{r['n_finite_records']}/{r['n_retained_records']}"
                        label+=f"\nseq {r['n_sequences_with_finite']}/{r['n_observed_sequences']}"
                        color='white' if val is not None and math.isfinite(val) and im.norm(val)>.58 else 'black'
                        ax.text(j,i,label,ha='center',va='center',fontsize=9,color=color)
                ax.set_xticks(range(3),SPEEDS);ax.set_yticks(range(3),HEIGHTS)
                ax.set_xlabel('Nominal speed (m/s)');ax.set_ylabel('Nominal altitude (m)')
                ax.set_title(sc+(' | finite fraction' if fraction else ' | RMSE'))
                return im
            def norm_for(c,scenes):
                vals=[get(c,sc,h,v)['mean'] for sc,h,v in itertools.product(scenes,HEIGHTS,SPEEDS)]
                vals=[v for v in vals if v is not None]
                return Normalize(min(0,min(vals)),max(vals) if max(vals)>0 else 1)
            def count_note(c, scenes):
                selected=[get(c,sc,h,v) for sc,h,v in itertools.product(scenes,HEIGHTS,SPEEDS)]
                ratios=sorted({(r['n_finite_records'],r['n_retained_records']) for r in selected})
                sizes=sorted({(r['n_sequences_with_finite'],r['n_observed_sequences']) for r in selected})
                return f"Per-cell finite/retained runs: {ratios}; finite/observed sequences: {sizes}."
            def curves(ax,c,sc,ylim=None):
                for h,color in zip(HEIGHTS,('#2166ac','#b2182b','#1b7837')):
                    cells=[get(c,sc,h,v) for v in SPEEDS]
                    y=[np.nan if r['mean'] is None else r['mean'] for r in cells]
                    ax.plot(SPEEDS,y,marker='o',color=color,label=f'H={h} m')
                    if cells[0]['mean'] is not None and cells[1]['mean'] is None and cells[2]['mean'] is not None:
                        ax.text(.02,.94-(HEIGHTS.index(h)*.06),f'H={h}: middle missing',transform=ax.transAxes,fontsize=8,color=color)
                ax.set_xticks(SPEEDS);ax.set_xlabel('Nominal speed (m/s), unequal intervals')
                ax.set_ylabel('Sequence-mean RMSE (source units)');ax.set_title(sc);ax.grid(alpha=.18);ax.legend(fontsize=8)
                ax.margins(x=.1,y=.25)
                if ylim:ax.set_ylim(*ylim)
            # Figures are fixed question follow-ups, not selected from favorable outcomes.
            c='ORB-SLAM2::mono'
            fig,axes=plt.subplots(1,2,figsize=(11,6))
            fig.subplots_adjust(top=.81,bottom=.22,left=.08,right=.88,wspace=.30)
            norm=norm_for(c,('road','building'))
            for ax,sc in zip(axes,('road','building')):im=heat(ax,c,sc,norm=norm)
            fig.colorbar(im,cax=fig.add_axes([.90,.25,.02,.51]),label='RMSE (source units)')
            save(fig,'01_orb2_condition_rmse',c,'Where are the larger RMSE cell means?',
                 'Equal-weight sequence means; cells: mean, finite/retained runs, finite/observed sequences.\nCommon scale across these two scenes; NO RECORDS differs from ALL NONFINITE.')
            fig,axes=plt.subplots(1,2,figsize=(12,6.2))
            fig.subplots_adjust(top=.81,bottom=.22,left=.07,right=.97,wspace=.22)
            for ax,sc in zip(axes,('road','building')):curves(ax,c,sc,(-.05*norm.vmax,1.23*norm.vmax))
            save(fig,'02_orb2_speed_curves',c,'Does increasing speed change RMSE similarly at each height?',
                 'Equal-weight sequence means; '+count_note(c,('road','building'))+'\nActual 2,4,8 coordinates; missing values break lines. Cell values and counts also shown in figure 01.')
            c='DROID-SLAM::rgbd';fig,axes=plt.subplots(1,2,figsize=(11,6.4))
            fig.subplots_adjust(top=.81,bottom=.23,left=.07,right=.88,wspace=.30)
            im=heat(axes[0],c,'pool',norm=norm_for(c,('pool',)))
            curves(axes[1],c,'pool')
            fig.colorbar(im,cax=fig.add_axes([.90,.27,.02,.49]),label='RMSE (source units)')
            save(fig,'03_droid_pool_conditions',c,'Is the pool scene mean spread across all conditions?',
                 'Equal-weight sequence means; '+count_note(c,('pool',))+'\nHeatmap contains numeric labels; curves use actual speeds; source RMSE units.')
            c='ORB-SLAM3::rgbd';fig,axes=plt.subplots(1,2,figsize=(11,6))
            fig.subplots_adjust(top=.81,bottom=.22,left=.08,right=.88,wspace=.30)
            for ax,sc in zip(axes,('road','building')):im=heat(ax,c,sc,norm=norm_for(c,('road','building')))
            fig.colorbar(im,cax=fig.add_axes([.90,.25,.02,.51]),label='RMSE (source units)')
            save(fig,'04_orb3_condition_rmse',c,'Where do the repeat cases sit among nearby conditions?',
                 'Equal-weight sequence means; cells: mean, finite/retained runs, finite/observed sequences.\nCommon scale across these two scenes; finite means can conceal strongly different repeats.')
            names=json.loads(qlookup[c]['sequence_names_json']);fig,axes=plt.subplots(1,len(names),figsize=(12.5,6.7),sharey=True)
            fig.subplots_adjust(top=.72,bottom=.29,left=.07,right=.98,wspace=.20)
            for ax,name in zip(axes,names):
                cell=next(r for r in joint if r['configuration_id']==c and r['scene']!=ALL and r['metric']=='rmse' and r['aggregation_level']==LEVELS[1] and name in json.loads(r['sequences_json']))
                d=next(x for x in json.loads(cell['sequence_descriptors_json']) if x['sequence']==name)
                runs=d['retained_runs'];x=list(range(len(runs)))
                vals=[r['value'] for r in runs]
                ax.scatter([i for i,v in enumerate(vals) if v is not None],[v for v in vals if v is not None],s=40)
                if d['mean'] is not None:ax.axhline(d['mean'],color='#b2182b',linestyle=':')
                for i,v in enumerate(vals):
                    if v is None:ax.text(i,-.29,'RMSE\nmissing',transform=ax.get_xaxis_transform(),ha='center',color='#a00000',fontsize=9)
                    else:ax.annotate(f'{v:.4g}',(i,v),xytext=(0,8),textcoords='offset points',ha='center',fontsize=8)
                ax.set_xticks(x,[r['run_id'] for r in runs]);ax.set_xlim(-.4,len(x)-.6)
                ax.set_title(f"{name}\n{cell['scene']} H={cell['altitude_m']}m V={cell['speed_mps']}m/s\nfinite/retained={d['n_finite']}/{d['n_retained']}; repeat_sd={fmt(d['repeat_sd'])}",fontsize=9)
                ax.set_xlabel('Retained run ID');ax.grid(axis='y',alpha=.2);ax.margins(y=.22)
            axes[0].set_ylabel('Run RMSE (source units)')
            save(fig,'05_orb3_retained_repeats',c,'Do high cell means describe every retained repeat?',
                 'Statistical unit: retained run within each named sequence; dotted line: finite-run mean.\nAll run IDs retained; missing labels outside numeric axis; repeat_sd is not a confidence interval.')
            c='VGGT-SLAM::mono';fig,axes=plt.subplots(2,2,figsize=(12,10))
            fig.subplots_adjust(top=.87,bottom=.17,left=.07,right=.85,wspace=.35,hspace=.38)
            norm=norm_for(c,('pool','roundabout'))
            for i,sc in enumerate(('pool','roundabout')):
                im1=heat(axes[i,0],c,sc,norm=norm);im2=heat(axes[i,1],c,sc,fraction=True,norm=Normalize(0,1))
            fig.colorbar(im1,cax=fig.add_axes([.89,.57,.018,.23]),label='RMSE (source units)')
            fig.colorbar(im2,cax=fig.add_axes([.89,.25,.018,.23]),label='Finite fraction (0 to 1)')
            save(fig,'06_vggt_coverage_rmse',c,'Which conditional means are supported by finite records?',
                 'Left: equal-weight sequence RMSE; right: finite/retained record fraction; labels include sequence counts.\nNO RECORDS (hatched, n=0) and ALL NONFINITE (0/n) remain distinct; no missing value is zero error.')
            c='hierslam::rgbd_whole';fig,axes=plt.subplots(1,2,figsize=(12,6.6))
            fig.subplots_adjust(top=.80,bottom=.23,left=.07,right=.88,wspace=.25)
            cells=[r for r in efficiency if r['configuration_id']==c and r['metric']=='runtime' and r['scene'] in ('houses','pool')]
            delta=[abs(r['B_minus_A_mean']) for r in cells if r['B_minus_A_mean'] is not None];bound=max(delta) or 1
            norm=TwoSlopeNorm(0,-bound,bound)
            for ax,sc in zip(axes,('houses','pool')):
                entries={(r['altitude_m'],r['speed_mps']):r for r in cells if r['scene']==sc}
                array=np.array([entries[h,v]['B_minus_A_mean'] for h,v in itertools.product(HEIGHTS,SPEEDS)],dtype=float).reshape(3,3)
                im=ax.imshow(np.ma.masked_invalid(array),cmap='RdBu_r',norm=norm,aspect='auto')
                for i,h in enumerate(HEIGHTS):
                    for j,v in enumerate(SPEEDS):
                        r=entries[h,v]
                        label=(f"A {r['A_mean']:.4g}\nB {r['B_mean']:.4g}\nB-A {r['B_minus_A_mean']:.3g}" if r['status']=='computed' else 'UNAVAILABLE')
                        label+=f"\nnA/nB {r['n_A']}/{r['n_B']}"
                        color='white' if r['B_minus_A_mean'] is not None and abs(r['B_minus_A_mean'])>.6*bound else 'black'
                        ax.text(j,i,label,ha='center',va='center',fontsize=9,color=color)
                ax.set_xticks(range(3),SPEEDS);ax.set_yticks(range(3),HEIGHTS)
                ax.set_xlabel('Nominal speed (m/s)');ax.set_ylabel('Nominal altitude (m)');ax.set_title(sc)
            fig.colorbar(im,cax=fig.add_axes([.90,.27,.02,.48]),label='B-A runtime (source units)')
            save(fig,'07_hier_runtime_cohorts',c,'Where does RMSE filtering change the runtime mean?',
                 'Finite-run arithmetic means: A=runtime finite; B=runtime and RMSE finite; nA/nB labels every cell.\nCommon difference scale; all nine conditions include unaffected backgrounds; this is a subset change.')
    finally:
        for k,v in old.items():
            if v is None:os.environ.pop(k,None)
            else:os.environ[k]=v
        if created and root.exists() and not any(root.iterdir()):root.rmdir()
    return figures

def report_text(assessments,joint,contrasts,efficiency,sequences,sources,figures,checks,spec,tests):
    from review_all_configurations_narrative import protocol_note
    lines=['<!-- generated-by: scripts/analyze_altitude_speed.py; exploration-step-8 -->',
           '# 第 8 步：高度 × 速度 × 场景联合描述','',
           protocol_note({'accuracy_protocol_by_configuration':sources}),'',
           '本轮发现均为当前保留记录的描述，不是显著性、因果效应或全方法排名。H 为名义高度 m，V 为名义速度 m/s；性能单位按各配置当前source_manifest及页首协议分别解释，不假定全体同口径。',
           'k/n 表示有限／保留记录；seq a/b 表示有限／观测序列。主均值为序列均值等权，repeat_sd 与跨序列 sample_sd 分开。','']
    lookup=lookup_joint(joint)
    for a in assessments:
        lines += [f"## {a['question_id']}：{a['configuration_id']}（{a['status']}）",'',a['observation'],'',
                  '**限制与修正：**'+a['limitations'],'','**第 9 步候选：**'+a['next_step_question'],'']
    lines+=['## 重点单元、重复值与条件差值','',
            '以下格子对应 joint_metrics.csv 的 configuration_id/scene/H/V/rmse/equal_weight_sequence_means。未观察的展示格不表示尝试过的实验。','']
    focuses={'ORB-SLAM2::mono':('road','building'),'DROID-SLAM::rgbd':('pool',),
             'ORB-SLAM3::rgbd':('road','building'),'VGGT-SLAM::mono':('pool','roundabout')}
    for c,scenes in focuses.items():
        for scene in scenes:
            lines += [f"### {c} / {scene}",'', '| H / V | 2 m/s | 4 m/s | 8 m/s |','|---|---|---|---|']
            for h in HEIGHTS:
                values=[]
                for v in SPEEDS:
                    r=lookup[cell_key(c,scene,h,v)]
                    text=fmt(r['mean'])
                    if r['cell_state']=='no_retained_records':text='无记录；比例未定义'
                    elif r['cell_state']=='observed_all_nonfinite':text='全部非有限'
                    values.append(f"{text}；{r['n_finite_records']}/{r['n_retained_records']}；seq {r['n_sequences_with_finite']}/{r['n_observed_sequences']}")
                lines.append(f"| {h} m | "+' | '.join(values)+' |')
            relevant=[r for r in contrasts if r['configuration_id']==c and r['scene']==scene and r['metric']=='rmse' and r['aggregation_level']==LEVELS[1] and (r['direction'] in ('8 - 2','30 - 10') or r['contrast_kind']=='rmse_four_corner')]
            lines+=['','条件端点均值的描述差（不是同名 run 配对；速度间隔不同，不称为斜率）：','',
                    '| 对照 | 固定条件 | 差值 | 状态／原因 | 覆盖或有限数量变化 |','|---|---|---:|---|---|']
            for r in relevant:
                lines.append(f"| {r['direction']} | {r['fixed_axis']}={r['fixed_value']} | {fmt(r['difference'])} | {r['status']} {r['unavailable_reason']} | {r['coverage_or_validity_counts_changed']} |")
            lines+=['']
    lines+=['### Q1–Q3 锚点的实际有限重复值','',
            '| 配置 / sequence | H,V | run_id：有限值（来源索引） | 有限/保留 | mean / median | repeat_sd / range |',
            '|---|---|---|---|---|---|']
    for a in assessments[:3]:
        for name in json.loads(a['anchor_sequence_names_json']):
            s=next(s for s in sequences if s['configuration_id']==a['configuration_id'] and s['sequence_raw']==name and s['metric']=='rmse')
            tuples=list(zip(json.loads(s['finite_run_ids_json']),json.loads(s['finite_values_json']),json.loads(s['finite_source_record_indices_json'])))
            lines.append(f"| {s['configuration_id']} / {name} | {s['altitude_m']},{s['speed_mps']} | {js(tuples)} | {s['n_finite_runs']}/{s['n_retained_runs']} | {fmt(s['mean'])} / {fmt(s['median'])} | {fmt(s['repeat_sd'])} / {fmt(s['finite_range'])} |")
    lines+=['','全部保留 run_id 及非有限状态见 sequence_descriptors_json；图 05 保留缺失 run 的位置。RMSE 单位和历史对齐限制按 manifest 保留。','',
            '### Hier-SLAM 完整轨迹：条件内效率 A/B','',
            'A 为效率自身有限，B 另要求 RMSE 有限。列出 houses/pool 的所有受影响效率格，'
            '每个场景、指标另保留一个有数值的未受影响背景格（H、V 升序固定选取）。完整表保留受影响配置的全部九格。','',
            '| scene / H,V | 指标 | nA/nB | A mean / median | B mean / median | B-A | 排除来源索引 |',
            '|---|---|---|---|---|---:|---|']
    hc=[r for r in efficiency if r['configuration_id']=='hierslam::rgbd_whole' and r['scene'] in ('houses','pool')]
    selected=[r for r in hc if r['n_A_not_B']]
    for sc,m in itertools.product(('houses','pool'),METRICS[1:]):
        choices=[r for r in hc if r['scene']==sc and r['metric']==m and not r['n_A_not_B'] and r['status']=='computed']
        if choices:selected.append(min(choices,key=lambda r:(r['altitude_m'],r['speed_mps'])))
    for r in sorted(selected,key=lambda r:(r['scene'],r['altitude_m'],r['speed_mps'],r['metric'])):
        lines.append(f"| {r['scene']} / {r['altitude_m']},{r['speed_mps']} | {r['metric']} | {r['n_A']}/{r['n_B']} | {fmt(r['A_mean'])} / {fmt(r['A_median'])} | {fmt(r['B_mean'])} / {fmt(r['B_median'])} | {fmt(r['B_minus_A_mean'])} | {r['A_not_B_record_indices_json']} |")
    lines+=['','同一条来源记录同时改变三个效率指标的集合，不计为三次实验。','',
            '## 全部 24 配置的条件结果简述','',
            '每段仅描述配置内部。正/负差数为固定 H 的 V8−V2、固定 V 的 H30−H10，不是独立效应样本或显著性投票。'
            '45 个展示格不代表已尝试45条序列。权重与均值/中位数差用于提醒解释边界，不构成排名。','']
    for c,source in sorted(sources.items()):
        g=[r for r in joint if r['configuration_id']==c and r['scene']!=ALL and r['metric']=='rmse' and r['aggregation_level']==LEVELS[1]]
        finite=[r for r in g if r['mean'] is not None];counts=Counter(r['cell_state'] for r in g)
        lo=min(finite,key=lambda r:(r['mean'],r['scene'],r['altitude_m'],r['speed_mps']))
        hi=max(finite,key=lambda r:(r['mean'],r['scene'],r['altitude_m'],r['speed_mps']))
        def directions(kind,direction):
            values=[r['difference'] for r in contrasts if r['configuration_id']==c and r['metric']=='rmse' and r['aggregation_level']==LEVELS[1] and r['contrast_kind']==kind and r['direction']==direction and r['status']=='computed']
            return f"正/负/零={sum(v>0 for v in values)}/{sum(v<0 for v in values)}/{sum(v==0 for v in values)}，可算 {len(values)}/15"
        allcells=[lookup[cell_key(c,ALL,h,v)] for h,v in itertools.product(HEIGHTS,SPEEDS)]
        candidates=[r for r in allcells if r['mean'] is not None]
        difference=lambda r:abs(r['mean']-lookup[cell_key(c,ALL,r['altitude_m'],r['speed_mps'],'rmse',LEVELS[0])]['mean'])
        wd=max(candidates,key=difference);md=max(candidates,key=lambda r:abs(r['mean']-r['median']))
        seq=[s for s in sequences if s['configuration_id']==c and s['metric']=='rmse']
        once=sum(s['n_retained_runs']==1 for s in seq);estimable=sum(s['repeat_sd'] is not None for s in seq)
        lines += [f"**{c}**（scope={source['evaluation_scope']}）。45 个场景展示格：无记录 {counts['no_retained_records']}、"
                  f"全非有限 {counts['observed_all_nonfinite']}、部分有限 {counts['observed_partial_finite']}、全部有限 {counts['observed_all_finite']}。"
                  f"RMSE {sum(r['n_finite_records'] for r in g)}/{sum(r['n_retained_records'] for r in g)} 条有限；"
                  f"最低均值格 {lo['scene']} {compact_cell(lo)}，最高 {hi['scene']} {compact_cell(hi)}。"
                  f"V8−V2：{directions('speed_difference','8 - 2')}；H30−H10：{directions('altitude_difference','30 - 10')}。"
                  f"全场景最大 abs(序列等权−pooled)={fmt(difference(wd))}（H{wd['altitude_m']}V{wd['speed_mps']}）；"
                  f"最大 abs(序列层 mean−median)={fmt(abs(md['mean']-md['median']))}（H{md['altitude_m']}V{md['speed_mps']}）。"
                  f"repeat_sd 可估 {estimable}/{len(seq)} 序列，仅保留一次 {once}；"
                  +('只有一次保留结果，无法判断重复稳定性。' if once else '少量有限重复只能描述现有波动。'),'']
    g=[r for r in joint if r['scene']!=ALL and r['metric']=='rmse' and r['aggregation_level']==LEVELS[0]]
    shared=[]
    for sc,h,v in itertools.product(SCENES,HEIGHTS,SPEEDS):
        if all(lookup[cell_key(c,sc,h,v)]['n_retained_records']==0 for c in sources):shared.append([sc,h,v])
    dso=[r for r in g if r['configuration_id']=='DSO::mono' and not r['n_retained_records']]
    changing=[]
    for c in sources:
        cells=[lookup[cell_key(c,ALL,h,v)] for h,v in itertools.product(HEIGHTS,SPEEDS)]
        signatures={r['finite_scenes_json']+r['scene_contributions_json'] for r in cells}
        if len(signatures)>1:changing.append(c)
    lines += ['## 覆盖、场景组成与权重','',
              f"互斥场景×H×V 的记录数（仅 RMSE pooled 一份）合计 {sum(r['n_retained_records'] for r in g)}，恢复主子集。"
              f"全部配置共同无记录的格实际为 {js(shared)}，不解释成失败或本应已运行。",
              f"DSO 当前无记录显示格：{js([[r['scene'],r['altitude_m'],r['speed_mps']] for r in dso])}；" +
              ('DSO五条旧导出漏项已按真实CSV恢复；下列有记录但全非有限格与共同无记录空格分开，不补造数值。'
               f"DSO有记录但无有限RMSE格：{js([[r['scene'],r['altitude_m'],r['speed_mps']] for r in g if r['configuration_id']=='DSO::mono' and r['n_retained_records'] and not r['n_finite_records']])}。"
               if INPUT_CONTEXT and INPUT_CONTEXT.get('update_policy', {}).get('reason') == 'user_confirmed_export_omission_corrected'
               else '共同空格与 DSO 额外缺项分别保留，不加入分母。'),'',
              '全场景格记录 retained_scenes_json、finite_scenes_json 和 scene_contributions_json；场景权重为其有限序列数/单元全部有限序列数。'
              f'当前 {len(changing)}/24 配置的至少两个条件格在场景组成、贡献数量或记录数上不同。'
              '因此整体曲线不能直接解释成纯条件作用。本轮没有删数据凑共同支持集。','',
              '恢复 pooled mean 用 n_finite_records 加权，恢复序列等权 mean 用 n_sequences_with_finite 加权；'
              '中位数从原有限值/序列均值直接重算，不平均单元中位数。','',
              '## 规则、追溯与图表','',
              '约定见 [08_condition_analysis_spec.json](08_condition_analysis_spec.json)。四指标分别筛选有限值；std ddof=1，n<2未定义。'
              '单序列三次运行是一个序列均值，sample_sd 未定义，repeat_sd 单独描述。展示网格不新增实验，500帧、完整轨迹及unknown分开。','',
              '来源键=source_relative_path + source_sha256 + source_record_indices_json；finite_source_record_indices_json 保存实际指标参与者，'
              'sequence_descriptors_json 保留各序列 run_id、数值、状态与 repeat_sd。差值 endpoints_json 保留具体条件、成员、覆盖；比例差单位为百分点。'
              '端点成员名称不同不意味着路线已匹配或已证明混杂。','',
              '四角量只为RMSE序列等权均值的差值之差；缺一角均值即 unavailable，不是因果DID、显著交互、置信区间或机制。','']
    for f in figures:
        lines += [f"- [{f['name']}.png](../figures/08_conditions/{f['name']}.png) / [SVG](../figures/08_conditions/{f['name']}.svg)：{FIGURES[f['name']]}",
                  '  图注：'+f['caption'].replace('\n','；'),'  PNG SHA-256：'+f['sha256']['png']+'。']
    lines += ['','<!-- VISUAL_REVIEW_START -->','七张 PNG 的实际查看：待完成，成功写出不等于视觉验收。',
              '<!-- VISUAL_REVIEW_END -->','','## 验证、输入快照与复跑','',
              '真实计算前的内存测试：','']+['- '+t for t in tests]
    lines+=['','实际结果核对：'+js(checks)+'。','',
            '| 输入 | SHA-256（运行前后相同） |','|---|---|']
    for i in spec['inputs'].values():lines.append(f"| {i['path']} | {i['sha256']} |")
    lines+=['','普通执行器 mountinfo 错误仅通过允许的限定审批处理；未关闭沙箱或改权限。'
            '缓存仅 reports/.08_conditions_tmp/ 本轮子目录，结束时清理本轮内容。','',
            '实际运行命令：','',chr(96)*3+'bash',spec['command'],chr(96)*3,'',
            '默认拒绝覆盖，审阅后 --overwrite 只刷新本轮固定输出；复跑后须重新查看PNG。三个标准化输入必须与第7步spec哈希一致。','',
            '实际输出：','']+['- '+p for p in OUTPUTS.values()]
    lines+=['','新增 scripts/analyze_altitude_speed.py。README 与 PROJECT_STATUS 只更新阶段，AGENTS 和第1～7步产物保留。','',
            '## 第 9 步候选与停止点','',
            '优先核验Q1高值集中对有限重复与覆盖的敏感性、Q2的pool条件差异、Q3高均值对单次偏离的依赖；'
            'Q4先核对覆盖可比性，Q5检查四条筛除记录与条件组成。这些是待授权问题。'
            '本轮未做统计推断、共同支持集/逐场景剔除、底层日志追查或因果归因；完成后停止。','']
    return '\n'.join(lines)

def validate_results(rows,sources,joint,sequences,contrasts,efficiency,raw):
    lookup=lookup_joint(joint)
    assert len(lookup)==len(joint)==len(sources)*6*9*4*2
    assert len(contrasts)==len(sources)*5*(18*4*2+1)
    for c in sources:
        actual=sorted(r['source_record_index'] for r in rows if r['configuration_id']==c)
        cells=[lookup[cell_key(c,sc,h,v,'rmse',LEVELS[0])] for sc,h,v in itertools.product(SCENES,HEIGHTS,SPEEDS)]
        assert sorted(i for r in cells for i in json.loads(r['source_record_indices_json']))==actual
        for m in METRICS:
            for sc,h,v in itertools.product((*SCENES,ALL),HEIGHTS,SPEEDS):
                a=lookup[cell_key(c,sc,h,v,m)]
                assert a['n_finite_records']==len(json.loads(a['finite_source_record_indices_json']))
                assert a['n_retained_records']==len(json.loads(a['source_record_indices_json']))
                assert a['cell_state']==cell_state(a['n_retained_records'],a['n_finite_records'])
                if a['n_values_used']<2:assert a['sample_sd'] is None
                if a['mean'] is not None and sc==ALL:
                    weights=json.loads(a['scene_contributions_json'])
                    assert math.isclose(sum(x['sequence_mean_weight'] for x in weights.values()),1)
    _,previous=decode_csv(raw['previous_summary']);checks=0
    for old in previous:
        if old['subset']!='condition_labelled':continue
        c=old['configuration_id'];m=old['metric'];level=old['aggregation_level'];sc=ALL if old['scene']=='__all__' else old['scene']
        group=[lookup[cell_key(c,sc,h,v,m,level)] for h,v in itertools.product(HEIGHTS,SPEEDS)]
        for field in ('n_retained_records','n_finite_records','n_observed_sequences','n_sequences_with_finite','n_sequences_without_finite'):
            assert sum(r[field] for r in group)==int(old[field]);checks+=1
        denom=sum(r['n_values_used'] for r in group)
        mean=sum(r['mean']*r['n_values_used'] for r in group if r['mean'] is not None)/denom if denom else None
        assert (mean is None and old['mean']=='') or (mean is not None and math.isclose(mean,float(old['mean']),rel_tol=1e-12,abs_tol=1e-12));checks+=1
    _,previous_seq=decode_csv(raw['previous_sequence'])
    previous_seq={(r['configuration_id'],r['sequence_raw'],r['metric']):r for r in previous_seq if r['subset']=='condition_labelled'}
    assert len(previous_seq)==len(sequences)
    for s in sequences:
        old=previous_seq[s['configuration_id'],s['sequence_raw'],s['metric']]
        for k in ('mean','median','repeat_sd','finite_range'):
            assert (s[k] is None and old[k]=='') or (s[k] is not None and math.isclose(s[k],float(old[k]),rel_tol=1e-12,abs_tol=1e-12))
        for k in ('source_record_indices_json','finite_source_record_indices_json','retained_run_ids_json'):
            assert json.loads(s[k])==json.loads(old[k])
    unique_excluded={(r['source_relative_path'],i) for r in efficiency if r['scene']!=ALL for i in json.loads(r['A_not_B_record_indices_json'])}
    return {'all_24_configurations':True,'joint_rows':len(joint),'contrast_rows':len(contrasts),
            'efficiency_cell_rows':len(efficiency),'affected_efficiency_configurations':len({r['configuration_id'] for r in efficiency}),
            'primary_records_recovered':len(rows),'stage7_count_and_weighted_mean_checks':checks,
            'stage7_primary_sequence_metric_rows_matched':len(sequences),'members_and_counts_consistent':True,
            'independent_efficiency_excluded_records':len(unique_excluded),
            'four_corner_computed':sum(r['contrast_kind']=='rmse_four_corner' and r['status']=='computed' for r in contrasts),
            'visual_review':'pending_actual_open'}

def self_test():
    tests=[]
    def source(c='virtual::mono'):
        return dict(configuration_id=c,configuration=c.split('::')[-1],method_directory='virtual',evaluation_scope='unknown',
                    source_relative_path='virtual/test.csv',source_sha256='virtual',rmse_unit_status='source units',alignment_status='unverified',
                    efficiency_protocol_json=js(dict(fps_unit_status='source units',runtime_unit_status='source units',
                                                    memory_conversion_and_kind='source units',evidence_status='virtual')))
    def row(seq='s',index=1,value=1,h=10,v=2,c='virtual::mono',fps=10):
        r={**source(c),'sequence_raw':seq,'scene':'pool','altitude_m':h,'speed_mps':v,
           'condition_label_status':'two_tokens','speed_level':'low','altitude_level':'low','source_record_index':index,
           'run_id_raw':str(index),'raw_dataset':seq+'_'+str(index),'raw_std':'999'}
        for m in METRICS:
            x=value if m=='rmse' else fps
            r.update({m+'_value':x,m+'_is_finite':x is not None,m+'_state':'missing_token' if x is None else 'finite_positive'})
        return r
    assert index_rows([row(h=30,v=4)])[('virtual::mono','pool',30,4)][0]['altitude_m']==30
    assert not index_rows([row(h=30,v=4)])[('virtual::mono','pool',4,30)]
    tests.append('高度/速度不互换：H30,V4只落入对应键')
    empty=joint_cell([],source(),'pool',10,2,'rmse')[1]
    bad=joint_cell([row(value=None)],source(),'pool',10,2,'rmse')[1]
    assert empty['cell_state']=='no_retained_records' and empty['finite_fraction'] is None
    assert bad['cell_state']=='observed_all_nonfinite' and bad['finite_fraction']==0 and bad['mean'] is None
    tests.append('无记录与全非有限：均值均未定义，比例分别未定义/0')
    triple=[row(index=i,value=i) for i in (1,2,3)]
    c=joint_cell(triple,source(),'pool',10,2,'rmse')[1]
    assert (c['n_retained_records'],c['n_observed_sequences'],c['n_values_used'],c['sample_sd'])==(3,1,1,None)
    d=json.loads(c['sequence_descriptors_json'])[0];assert d['repeat_sd']==1
    assert sequence_table([row()],{'virtual::mono':source()})[0]['repeat_sd'] is None
    tests.append('三次运行只是一条序列；单有限重复的repeat_sd未定义')
    uneven=[row('a',1,1),row('a',2,1),row('a',3,1),row('b',4,9)]
    p,s=joint_cell(uneven,source(),'pool',10,2,'rmse')
    assert p['mean']==3 and s['mean']==5
    tests.append('不等有限重复次数：pooled=3，序列等权=5；raw_std未参与')
    er=efficiency_cells([row(index=1,value=1,fps=10),row(index=2,value=None,fps=30)],{'virtual::mono':source()})
    r=next(r for r in er if r['scene']=='pool' and r['altitude_m']==10 and r['speed_mps']==2 and r['metric']=='fps')
    assert (r['n_A'],r['n_B'],r['A_mean'],r['B_mean'],r['B_minus_A_mean'])==(2,1,20,10,-10)
    assert json.loads(r['A_not_B_record_indices_json'])==[2]
    tests.append('RMSE缺失而效率有限：A/B集合、差值和来源索引正确')
    x={**endpoint(c),'altitude_m':10,'speed_mps':2};y={**x,'mean':None,'cell_state':'observed_all_nonfinite','speed_mps':8}
    assert contrast_value([x,y],[-1,1])[1]=='unavailable'
    assert contrast_value([x,x,x,y],[1,-1,-1,1])[1]=='unavailable'
    assert contrast_value([{**x,'mean':v} for v in (8,2,4,1)],[1,-1,-1,1])[0]==3
    tests.append('任一端点缺失不填零；四角缺一不计算，完整四角按指定符号')
    means=[{**x,'mean':2*v,'speed_mps':v} for v in SPEEDS]
    assert contrast_value(means[:2],[-1,1])[0]==4 and contrast_value(means[1:],[-1,1])[0]==8
    tests.append('2到4与4到8差值保留4和8，不冒充相同速度增量的斜率')
    assert json.loads(c['source_record_indices_json'])==[1,2,3]
    assert [a['run_id'] for a in d['retained_runs']]==['1','2','3']
    for badpath in (W/'README.md',W/'tables/07_eda/sequence_metrics.csv',Path('/tmp/out.csv')):
        try:check_output(badpath,True)
        except ValueError:pass
        else:raise AssertionError('Output boundary bypass')
    with patch.object(Path,'is_symlink',return_value=True):
        try:check_output(W/OUTPUTS['joint'],True)
        except ValueError:pass
        else:raise AssertionError('Symlink accepted')
    with patch.object(Path,'is_symlink',return_value=False),patch.object(Path,'exists',return_value=True):
        try:check_output(W/OUTPUTS['joint'])
        except FileExistsError:pass
        else:raise AssertionError('Overwrite accepted')
    with patch.object(Path,'is_symlink',return_value=False),patch.object(Path,'exists',return_value=True),patch.object(Path,'is_file',return_value=True),patch.object(Path,'stat') as stat:
        stat.return_value.st_nlink=2
        try:check_output(W/OUTPUTS['joint'],True)
        except ValueError:pass
        else:raise AssertionError('Hardlink accepted')
    tests.append('来源编号追溯、输出白名单、默认拒绝覆盖、软/硬链接保护')
    return tests

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--self-test',action='store_true');parser.add_argument('--overwrite',action='store_true')
    args=parser.parse_args()
    tests=self_test();print(js({'memory_tests_passed':len(tests)}))
    if args.self_test:
        for t in tests:print(t)
        return
    for p in OUTPUTS.values():check_output(W/p,args.overwrite)
    if args.overwrite and any((W/p).exists() for p in OUTPUTS.values()):
        p=W/OUTPUTS['spec']
        if not p.is_file() or json.loads(p.read_text()).get('generated_by')!='scripts/analyze_altitude_speed.py':
            raise ValueError('Existing output ownership unconfirmed')
    raw={k:read_bytes(W/p) for k,p in INPUTS.items()}
    previous=json.loads(raw['previous_spec'])
    for key in ('records','manifest','schema'):
        expected=previous['inputs'][key]
        if expected['path']!=INPUTS[key] or expected['sha256']!=sha(raw[key]):
            raise ValueError(f'Step-7 snapshot mismatch for {key}: expected {expected}, actual {sha(raw[key])}')
    allrows,sources,schema,checks=validate_inputs(raw)
    rows=[r for r in allrows if r['condition_label_status']=='two_tokens']
    if len(rows) != checks['condition_labelled_records']:
        raise ValueError('Primary subset differs from the validated current snapshot')
    if any(r['altitude_m'] not in HEIGHTS or r['speed_mps'] not in SPEEDS for r in rows):
        raise ValueError('Unexpected nominal condition outside display grid')
    _,questions=decode_csv(raw['questions'])
    if len({q['question_id'] for q in questions})!=len(questions):raise ValueError('Duplicate prior question ID')
    command=shlex.join(['/home/yuan/anaconda3/bin/python3','-B',str(Path(__file__).absolute()),*sys.argv[1:]])
    spec=make_spec(raw,schema,command)
    spec['assessment_markers']={'Q1':'support if actual top-three finite sequence means all have H30; no causal implication',
       'Q2':'support concentration if all 9 cells usable and top-three cell mean sum > half of total; descriptive threshold only',
       'Q3':'repeat_limited: inspect anchor values and conditions; no reproducible conditional instability claim from few repeats',
       'Q4':'coverage_limited for RMSE comparisons; describe actual missing locations',
       'Q5':'support concentration if all actual excluded runtime rows fall at V8; not a missingness cause'}
    write('spec',json.dumps(spec,ensure_ascii=False,indent=2)+'\n',args.overwrite)
    print('SPEC WRITTEN: real joint descriptive calculations start now.',flush=True)
    seq=sequence_table(rows,sources);joint=joint_table(rows,sources)
    contrasts=contrast_table(joint,sources);efficiency=efficiency_cells(rows,sources)
    checks.update(validate_results(rows,sources,joint,seq,contrasts,efficiency,raw))
    assessment=assess_questions(questions,joint,efficiency,seq)
    for key,data in [('joint',joint),('contrasts',contrasts),('efficiency',efficiency),('questions',assessment)]:
        if not data:raise ValueError('Unexpected empty output '+key)
        write(key,csv_text(data,list(data[0])),args.overwrite)
    figs=draw_figures(joint,efficiency,questions,sources,args.overwrite)
    for key,path in INPUTS.items():
        if read_bytes(W/path)!=raw[key]:raise ValueError('Input changed while running '+path)
    checks.update(inputs_unchanged=True,main_figures=len(figs),question_assessments=len(assessment))
    write('report',report_text(assessment,joint,contrasts,efficiency,seq,sources,figs,checks,spec,tests),args.overwrite)
    print(js({'checks':checks,'assessments':[{k:r[k] for k in ('question_id','configuration_id','status','observation')} for r in assessment],'figures':figs}))

if __name__=='__main__':
    try:main()
    except (ValueError,FileExistsError,AssertionError,KeyError) as e:
        print('STOP: '+str(e),file=sys.stderr);sys.exit(1)
