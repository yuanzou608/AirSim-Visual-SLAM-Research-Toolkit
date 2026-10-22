#!/usr/bin/env python3
"""Step 9: deterministic robustness checks, not inferential testing."""
import argparse
from collections import Counter, defaultdict
import csv
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
from explore_benchmark import describe, finite_values, parse_bool, unit_limit, META, METRICS, SCENES, fmt, sha
from build_analysis_dataset import decode_csv, csv_text, reject_links
from analyze_altitude_speed import cell_state

from version_support import workspace
W=workspace(Path('/home/yuan/SLAM/codex_review/benchmark_analysis'))
ZERO_ATOL=1e-12
INPUTS={
 'records':'derived_data/06_standardized/run_records.csv',
 'manifest':'derived_data/06_standardized/source_manifest.csv',
 'schema':'derived_data/06_standardized/schema.json',
 'report7':'reports/07_exploratory_analysis.md',
 'questions7':'reports/07_research_questions.csv',
 'spec8':'reports/08_condition_analysis_spec.json',
 'report8':'reports/08_altitude_speed_analysis.md',
 'questions8':'reports/08_question_assessment.csv',
 'joint8':'tables/08_conditions/joint_metrics.csv',
 'contrasts8':'tables/08_conditions/conditional_contrasts.csv',
 'efficiency8':'tables/08_conditions/efficiency_cohort_cells.csv',
}
OUTPUTS={'spec':'reports/09_robustness_spec.json',
 'repeat':'tables/09_robustness/repeat_value_audit.csv',
 'support':'tables/09_robustness/support_blocks.csv',
 'estimates':'tables/09_robustness/sensitivity_estimates.csv',
 'efficiency':'tables/09_robustness/efficiency_decomposition.csv',
 'claims':'reports/09_claim_assessment.csv',
 'report':'reports/09_robustness_analysis.md'}
FIGURES={
 '01_dpvo_scene_cancellation':'DPVO speed V1/V2 leave-one-scene-out and signed scene contributions; all scenes, fixed F.',
 '02_orb2_local_sensitivity':'ORB-SLAM2 road/building speed endpoints at H10/H30 and four-corner quantities; baseline, median and one-record-removal ranges.',
 '03_orb3_repeat_influence':'ORB-SLAM3 three existing repeat cases plus road H20V4; baseline means and every finite single-removal variant.',
 '04_vggt_support_views':'VGGT-SLAM V0-V4 for speed and height, with R/F/C counts and R validity; no unavailable value plotted as zero.',
 '05_hier_runtime_decomposition':'Hier-SLAM whole-trajectory runtime: actual excluded-record algebraic terms and total; no causal interpretation.',
}
for name in FIGURES:
 for ext in ('png','svg'):OUTPUTS[name+'.'+ext]='figures/09_robustness/'+name+'.'+ext
RAW_FIELDS={'rmse':'raw_rmse','fps':'raw_FPS','runtime':'raw_runtime','memory':'raw_PeakReservedGB',
            **{k:'raw_'+k for k in ('max','min','mean','median','sse','std')}}
ERROR_FIELDS=('max','min','mean','median','rmse','sse','std')
COMPARISONS={'speed8_minus2':('speed_mps',2,8,'altitude_m'),
             'altitude30_minus10':('altitude_m',10,30,'speed_mps')}

def js(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,allow_nan=False,separators=(',',':'))
def sign(x):return 'unavailable' if x is None else 'near_zero' if abs(x)<=ZERO_ATOL else 'positive' if x>0 else 'negative'
def close(a,b):
 return a is not None and b is not None and math.isclose(a,b,rel_tol=1e-12,abs_tol=1e-12)
def read_input(key):
 p=W/INPUTS[key];reject_links(p)
 limit=80*1024*1024 if key in ('joint8','contrasts8') else 10*1024*1024
 with p.open('rb') as f:b=f.read(limit+1)
 if len(b)>limit:raise ValueError('Input exceeds reviewed size bound: '+str(p))
 return b
def check_output(p,overwrite=False):
 if p not in {W/x for x in OUTPUTS.values()}:raise ValueError('Outside step-9 allowlist: '+str(p))
 reject_links(p)
 if not p.resolve().is_relative_to(W.resolve()):raise ValueError('Output escapes workspace')
 if p.exists():
  if not overwrite:raise FileExistsError('Refusing overwrite: '+str(p))
  if not p.is_file() or p.stat().st_nlink!=1:raise ValueError('Linked/nonregular output: '+str(p))
def write(key,data,overwrite):
 p=W/OUTPUTS[key];check_output(p,overwrite);p.parent.mkdir(parents=True,exist_ok=True);check_output(p,overwrite)
 flags=os.O_WRONLY|os.O_CREAT|os.O_NOFOLLOW|(os.O_TRUNC if overwrite else os.O_EXCL)
 with os.fdopen(os.open(p,flags,0o666),'wb') as f:f.write(data.encode() if isinstance(data,str) else data)
def write_csv(key,rows,overwrite):
 fields=list(dict.fromkeys(k for r in rows for k in r))
 write(key,csv_text(rows,fields),overwrite)
def source_key(r):return {'path':r['source_relative_path'],'sha256':r['source_sha256'],'index':r['source_record_index']}
def row_context(r):
 return {**source_key(r),'sequence':r['sequence_raw'],'run_id':r['run_id_raw'],
         'scene':r['scene'],'altitude_m':r['altitude_m'],'speed_mps':r['speed_mps']}
def load_records(raw):
 schema=json.loads(raw['schema'])
 if schema['schema_version']!='1.0.0' or schema['dataset_status']!='complete_validated':raise ValueError('Unexpected schema')
 h,rows=decode_csv(raw['records']);mh,manifest=decode_csv(raw['manifest'])
 if h!=list(schema['files']['records']['columns']) or mh!=list(schema['files']['manifest']['columns']):raise ValueError('Schema columns changed')
 sources={m['configuration_id']:m for m in manifest}
 if len(sources)!=len(manifest):raise ValueError('Ambiguous configuration source')
 keys=set();counts=Counter();metadata={}
 for r in rows:
  source=sources[r['configuration_id']]
  if any(r[k]!=source[k] for k in (*META,'source_relative_path','source_sha256')):raise ValueError('Metadata mismatch')
  r['source_record_index']=int(r['source_record_index'])
  key=(r['source_relative_path'],r['source_sha256'],r['source_record_index'])
  if key in keys:raise ValueError('Duplicate source key')
  keys.add(key);counts[r['configuration_id']]+=1
  for k in ('speed_mps','altitude_m'):r[k]=int(r[k]) if r[k] else None
  for m in METRICS:
   finite=parse_bool(r[m+'_is_finite']);state=r[m+'_state'];text=r[m+'_value']
   if finite!=state.startswith('finite_'):raise ValueError('Finite/state conflict')
   x=float(text) if text else None
   if finite and (x is None or not math.isfinite(x)):raise ValueError('Bad finite value')
   if not finite and text:raise ValueError('Nonfinite numeric view')
   r[m+'_is_finite']=finite;r[m+'_value']=x
  sq=(r['configuration_id'],r['sequence_raw'])
  met=tuple(r[k] for k in ('scene','speed_mps','altitude_m','speed_level','altitude_level','condition_label_status'))
  if sq in metadata and metadata[sq]!=met:raise ValueError('Sequence conditions conflict')
  metadata[sq]=met
 for c,m in sources.items():
  if counts[c]!=int(m['output_record_count']):raise ValueError('Per-source counts changed')
 expected_records=sum(int(m['output_record_count']) for m in manifest)
 expected_labelled=sum(int(m['condition_labelled_records']) for m in manifest)
 if len(rows)!=expected_records or sum(r['condition_label_status']=='two_tokens' for r in rows)!=expected_labelled:
  raise ValueError('Records do not match current manifest counts')
 return rows,sources,schema

def field_audit(rows,field):
 state_key=field+'_state'
 provided=[r for r in rows if r[state_key]!='source_not_provided']
 finite=[r for r in provided if r[state_key].startswith('finite_')]
 texts=[r[RAW_FIELDS[field]] for r in finite]
 # Auxiliary fields are converted only when their existing state says finite; never parse tuple text.
 nums=[r[field+'_value'] if field in METRICS else float(r[RAW_FIELDS[field]]) for r in finite]
 return {'n_provided':len(provided),'n_finite':len(finite),'n_distinct_finite_text':len(set(texts)),
         'n_distinct_finite_numeric':len(set(nums)),
         'finite_text_identical':len(texts)>=2 and len(set(texts))==1,
         'finite_numeric_identical':len(nums)>=2 and len(set(nums))==1,
         'all_retained_finite_numeric_identical':len(nums)==len(rows)>=2 and len(set(nums))==1,
         'status':'source_not_provided' if not provided else 'insufficient_finite_values' if len(nums)<2 else 'equal_numeric' if len(set(nums))==1 else 'different_numeric',
         'raw_texts':[r[RAW_FIELDS[field]] for r in rows],
         'states':[r[state_key] for r in rows],
         'finite_indices':[r['source_record_index'] for r in finite],
         'finite_values':nums}

def repeat_audit(rows):
 grouped=defaultdict(list)
 for r in rows:grouped[r['configuration_id'],r['sequence_raw']].append(r)
 result=[]
 for (c,name),rs in sorted(grouped.items()):
  first=rs[0];fields={f:field_audit(rs,f) for f in (*ERROR_FIELDS,'fps','runtime','memory')}
  rm=fields['rmse'];provided=[f for f in ERROR_FIELDS if fields[f]['n_provided']]
  comparable=[f for f in provided if fields[f]['n_finite']==len(rs)>=2]
  full_equal=len(comparable)==len(provided) and bool(provided) and all(fields[f]['finite_numeric_identical'] for f in provided)
  equal_aux=[f for f in comparable if f!='rmse' and fields[f]['finite_numeric_identical']]
  eff_equal=all(fields[f]['all_retained_finite_numeric_identical'] for f in ('fps','runtime','memory'))
  labels=[]
  if rm['n_finite']<2:labels.append('insufficient_finite_rmse')
  elif rm['finite_numeric_identical']:
   labels.append('identical_rmse_text' if rm['finite_text_identical'] else 'different_text_same_numeric_rmse')
   if equal_aux:labels.append('multiple_error_fields_identical')
   elif not equal_aux:labels.append('only_rmse_identical_among_comparable_error_fields')
   if eff_equal:labels.append('efficiency_values_also_identical')
   if rm['n_finite']<len(rs):labels.append('rmse_equality_only_among_finite_subset')
  else:labels.append('different_finite_rmse')
  result.append({**{k:first[k] for k in META},'sequence_raw':name,'scene':first['scene'],
   'altitude_m':first['altitude_m'],'speed_mps':first['speed_mps'],
   'subset':'condition_labelled' if first['condition_label_status']=='two_tokens' else 'unlabelled',
   'n_retained':len(rs),'n_finite_rmse':rm['n_finite'],
   'n_distinct_finite_raw_rmse':rm['n_distinct_finite_text'],'n_distinct_finite_rmse_value':rm['n_distinct_finite_numeric'],
   'finite_rmse_identical':rm['finite_numeric_identical'],'finite_rmse_text_identical':rm['finite_text_identical'],
   'provided_error_fields_json':js(provided),'comparable_error_fields_json':js(comparable),
   'all_provided_error_fields_identical':full_equal,'n_equal_comparable_aux_fields':len(equal_aux),
   'all_efficiency_fields_identical':eff_equal,'labels_json':js(labels),
   'rmse_repeat_sd':describe(rm['finite_values'])['sample_sd'],
   'fields_evidence_json':js(fields),'members_json':js([row_context(r) for r in rs]),
   'interpretation':'retained record characteristic only; no deduplication, determinism or provenance claim'})
 return result

def route_id(r):
 suffix='_'+r['speed_level']+'_'+r['altitude_level'];name=r['sequence_raw']
 if r['condition_label_status']!='two_tokens' or not name.endswith(suffix) or not name[:-len(suffix)]:
  raise ValueError('Cannot precisely remove verified condition suffix: '+name)
 return name[:-len(suffix)]

def endpoint(rs):
 finite=[r for r in rs if r['rmse_is_finite']];values=[r['rmse_value'] for r in finite]
 names=sorted({r['sequence_raw'] for r in rs});paths={(r['source_relative_path'],r['source_sha256']) for r in rs}
 ambiguous=len(names)>1 or len(paths)>1
 stat=describe(values) if not ambiguous else describe([])
 return {'n_retained':len(rs),'n_finite':len(finite),'n_sequences':len(names),
         'mean':stat['mean'],'median':stat['median'],'repeat_sd':stat['sample_sd'],
         'state':cell_state(len(rs),len(finite)),'finite_fraction':len(finite)/len(rs) if rs else None,
         'ambiguous':ambiguous,'sequences':names,
         'members':[row_context(r) for r in rs],'finite_members':[row_context(r) for r in finite],
         'finite_values':values}

def support_blocks(rows):
 grouped=defaultdict(lambda:[[],[]])
 for r in rows:
  route=route_id(r)
  for comparison,(axis,lo,hi,fixed) in COMPARISONS.items():
   if r[axis] in (lo,hi):
    grouped[(r['configuration_id'],comparison,r['scene'],route,r[fixed])][r[axis]==hi].append(r)
 result=[]
 for (c,comparison,scene,route,fixed_value),sides in sorted(grouped.items()):
  axis,lo,hi,fixed=COMPARISONS[comparison];a,b=map(endpoint,sides)
  R=bool(a['n_retained'] and b['n_retained'])
  F=R and bool(a['n_finite'] and b['n_finite'])
  C=F and a['n_finite']==a['n_retained'] and b['n_finite']==b['n_retained']
  ambiguous=a['ambiguous'] or b['ambiguous']
  reason_R='' if R else ';'.join(side+':no_retained_records' for side,e in [('low',a),('high',b)] if not e['n_retained'])
  reason_F='' if F else reason_R or ';'.join(side+':all_nonfinite_rmse' for side,e in [('low',a),('high',b)] if not e['n_finite'])
  reason_C='' if C else reason_F or ';'.join(side+':partial_finite_rmse' for side,e in [('low',a),('high',b)] if e['n_finite']<e['n_retained'])
  first=(sides[0]+sides[1])[0]
  result.append({**{k:first[k] for k in META},'block_id':f'{c}|{comparison}|{scene}|{route}|{fixed}={fixed_value}',
   'comparison':comparison,'scene':scene,'route_id':route,'fixed_axis':fixed,'fixed_value':fixed_value,
   'varying_axis':axis,'low_condition':lo,'high_condition':hi,
   'in_R':R,'in_F':F,'in_C':C,'ambiguous':ambiguous,'matching_status':'ambiguous_do_not_pair' if ambiguous else 'nominal_stratum_only',
   'R_exclusion_reason':reason_R,'F_exclusion_reason':reason_F,'C_exclusion_reason':reason_C,
   'low':a,'high':b})
 return result

def public_blocks(blocks):
 return [{**{k:v for k,v in b.items() if k not in ('low','high')},
          **{f'{side}_{k}':v for side in ('low','high') for k,v in b[side].items() if k in ('n_retained','n_finite','n_sequences','state','mean','median','finite_fraction')},
          'low_endpoint_json':js(b['low']),'high_endpoint_json':js(b['high'])} for b in blocks]

def base_estimate(config,comparison,analysis_type,variant,sources):
 return {'estimate_id':f'{config}|{comparison}|{analysis_type}|{variant}',
         'configuration_id':config,'evaluation_scope':sources[config]['evaluation_scope'],'subset':'condition_labelled',
         'comparison':comparison,'analysis_type':analysis_type,'variant':variant,'metric':'rmse',
         'value_unit':'rmse source units','measurement_limit':unit_limit(sources[config],'rmse'),
         'baseline_id':'','baseline_value':None,'delta_from_baseline':None,'direction_changed':None}

def compare_baseline(row,base):
 row.update(baseline_id=base['estimate_id'],baseline_value=base['value'],
            delta_from_baseline=row['value']-base['value'] if row['value'] is not None and base['value'] is not None else None,
            direction_changed=sign(row['value'])!=sign(base['value']) if row['value'] is not None and base['value'] is not None else None)
 return row

def estimate_view(config,comparison,blocks,view,sources,analysis_type='support_view',removed_scene=''):
 b=[x for x in blocks if x['configuration_id']==config and x['comparison']==comparison]
 support={'R':[x for x in b if x['in_R']],'F':[x for x in b if x['in_F']],'C':[x for x in b if x['in_C']]}
 row=base_estimate(config,comparison,analysis_type,view+(' minus '+removed_scene if removed_scene else ''),sources)
 row.update(view=view,removed_scene=removed_scene,n_reference_blocks=len(b),n_R=len(support['R']),n_F=len(support['F']),n_C=len(support['C']))
 if view=='V0':
  left=[x for x in b if x['low']['mean'] is not None];right=[x for x in b if x['high']['mean'] is not None]
 else:
  selected=support['C'] if view=='V3' else support['F']
  selected=[x for x in selected if x['scene']!=removed_scene]
  left=right=selected
 representative='median' if view=='V4' else 'mean'
 def weights(selected):
  nsc=Counter(x['scene'] for x in selected)
  return {x['block_id']:1/(len(nsc)*nsc[x['scene']]) if view=='V2' else 1/len(selected) for x in selected}
 lw,rw=weights(left),weights(right)
 ambiguous=any(x['ambiguous'] for x in b)
 a=sum(x['low'][representative]*lw[x['block_id']] for x in left) if left and not ambiguous else None
 z=sum(x['high'][representative]*rw[x['block_id']] for x in right) if right and not ambiguous else None
 ambiguous=any(x['ambiguous'] for x in b)
 value=z-a if a is not None and z is not None and not ambiguous else None
 reason='ambiguous_block_no_pairing' if ambiguous else 'no_usable_'+('left' if not left else 'right')+'_endpoint_set' if value is None else ''
 row.update(endpoint_low=a,endpoint_high=z,value=value,direction=sign(value),
            status='computed' if value is not None else 'unavailable',unavailable_reason=reason,representative=representative)
 for side,selected,ww in [('low',left,lw),('high',right,rw)]:
  scene_weights=defaultdict(float)
  for x in selected:scene_weights[x['scene']]+=ww[x['block_id']]
  row.update({side+'_n_blocks':len(selected),side+'_n_scenes':len(scene_weights),
              side+'_n_retained':sum(x[side]['n_retained'] for x in selected),side+'_n_finite':sum(x[side]['n_finite'] for x in selected),
              side+'_scene_weights_json':js(scene_weights),side+'_block_weights_json':js(ww),
              side+'_block_ids_json':js([x['block_id'] for x in selected]),
              side+'_members_json':js([{'block_id':x['block_id'],'sequence':x[side]['sequences'],
                       'n_retained':x[side]['n_retained'],'n_finite':x[side]['n_finite'],'weight':ww[x['block_id']],
                       'members':x[side]['members'],'finite_members':x[side]['finite_members']} for x in selected])})
 # C coverage loss is relative to the ORIGINAL F, not the display subset.
 lost=[x for x in support['F'] if not x['in_C']]
 row.update(C_lost_blocks_from_F=len(lost),C_lost_records_from_F=sum(x[s]['n_retained'] for x in lost for s in ('low','high')),
            C_lost_finite_records_from_F=sum(x[s]['n_finite'] for x in lost for s in ('low','high')),
            C_lost_scenes_json=js(sorted({x['scene'] for x in support['F']}-{x['scene'] for x in support['C']})))
 return row

def all_views(blocks,sources):
 result=[]
 for c,comparison in itertools.product(sorted(sources),COMPARISONS):
  local=[b for b in blocks if b['configuration_id']==c and b['comparison']==comparison]
  base=estimate_view(c,comparison,blocks,'V1',sources)
  for view in ('V0','V1','V2','V3','V4'):
   r=base if view=='V1' else estimate_view(c,comparison,blocks,view,sources)
   result.append(compare_baseline(r,base))
  R=[b for b in local if b['in_R']]
  valid=base_estimate(c,comparison,'numeric_validity_R','finite_fraction_on_R',sources)
  valid.update(value_unit='percentage_points',endpoint_value_unit='fraction',n_R=len(R),
               no_record_block_ids_json=js([b['block_id'] for b in local if not b['in_R']]))
  for side in ('low','high'):
   nr=sum(b[side]['n_retained'] for b in R);nf=sum(b[side]['n_finite'] for b in R)
   valid.update({side+'_n_retained':nr,side+'_n_finite':nf,'endpoint_'+side:nf/nr if nr else None,
                 side+'_members_json':js([b[side]['members'] for b in R])})
  value=100*(valid['endpoint_high']-valid['endpoint_low']) if R else None
  valid.update(value=value,status='computed' if value is not None else 'unavailable',unavailable_reason='' if R else 'empty_R',direction=sign(value))
  result.append(valid)
  scenes=sorted({b['scene'] for b in local if b['in_F']})
  for view in ('V1','V2'):
   baseline=base if view=='V1' else estimate_view(c,comparison,blocks,view,sources)
   for scene in scenes:
    result.append(compare_baseline(estimate_view(c,comparison,blocks,view,sources,'leave_one_scene_out',scene),baseline))
    scene_blocks=[b for b in local if b['in_F'] and b['scene']==scene]
    nF=sum(b['in_F'] for b in local)
    weight=1/nF if view=='V1' else 1/(len(scenes)*len(scene_blocks))
    contribution=sum((b['high']['mean']-b['low']['mean'])*weight for b in scene_blocks) if not any(b['ambiguous'] for b in local) else None
    r=base_estimate(c,comparison,'scene_contribution',view+' '+scene,sources)
    r.update(view=view,scene=scene,value=contribution,status='computed' if contribution is not None else 'unavailable',unavailable_reason='ambiguous_block_no_pairing' if contribution is None else '',direction=sign(contribution),
             baseline_id=baseline['estimate_id'],baseline_value=baseline['value'],
             n_blocks=len(scene_blocks),scene_weight=weight*len(scene_blocks),
             block_details_json=js([{'block_id':b['block_id'],'low_mean':b['low']['mean'],'high_mean':b['high']['mean'],
                                    'difference':b['high']['mean']-b['low']['mean'] if not b['ambiguous'] else None,'weight':weight} for b in scene_blocks]))
    result.append(r)
 return result

def sequence_sensitivity(rows,sources):
 grouped=defaultdict(list)
 for r in rows:grouped[r['configuration_id'],r['sequence_raw']].append(r)
 result=[]
 for (c,name),rs in sorted(grouped.items()):
  e=endpoint(rs);values=e['finite_values'];stat=describe(values)
  base=base_estimate(c,name,'sequence_baseline','finite_mean',sources)
  base.update(scene=rs[0]['scene'],sequence_raw=name,altitude_m=rs[0]['altitude_m'],speed_mps=rs[0]['speed_mps'],
    value=stat['mean'],baseline_median=stat['median'],repeat_sd=stat['sample_sd'],direction=sign(stat['mean']),
    status='computed' if values else 'unavailable',unavailable_reason='' if values else 'no_finite_rmse',
    original_n_retained=len(rs),original_n_finite=len(values),original_finite_fraction=len(values)/len(rs),
    original_values_json=js(values),original_members_json=js(e['members']),
    original_finite_members_json=js(e['finite_members']),trial_n_used=len(values))
  compare_baseline(base,base);result.append(base);variants=[]
  if len(values)<2:
   r={**base,'estimate_id':f'{c}|{name}|sequence_drop_one|not_applicable','analysis_type':'sequence_drop_one',
      'variant':'not_applicable','value':None,'trial_n_used':None,'direction':'unavailable',
      'status':'not_applicable','unavailable_reason':'fewer_than_two_finite_rmse'}
   result.append(compare_baseline(r,base))
  else:
   for i,member in enumerate(e['finite_members']):
    v=values[:i]+values[i+1:]
    r={**base,'estimate_id':f'{c}|{name}|sequence_drop_one|{member["index"]}','analysis_type':'sequence_drop_one',
       'variant':'remove_one_finite_record','removed_record_json':js(member),'trial_n_used':len(v),
       'trial_members_json':js(e['finite_members'][:i]+e['finite_members'][i+1:]),
       'value':describe(v)['mean'],'direction':sign(describe(v)['mean']),'trial_repeat_sd':describe(v)['sample_sd']}
    variants.append(compare_baseline(r,base));result.append(variants[-1])
  value_list=[r['value'] for r in variants]
  result.append({**base,'estimate_id':f'{c}|{name}|sequence_variant_range|drop_one',
    'analysis_type':'sequence_variant_range','variant':'drop_one_range',
    'value':None,'delta_from_baseline':None,'direction_changed':None,'trial_n_used':None,'direction':'range_not_scalar','baseline_id':base['estimate_id'],'baseline_value':base['value'],'status':'computed' if value_list else 'not_applicable',
    'unavailable_reason':'' if value_list else 'fewer_than_two_finite_rmse',
    'range_min':min(value_list) if value_list else None,'range_max':max(value_list) if value_list else None,
    'n_variants':len(value_list),'variant_ids_json':js([r['estimate_id'] for r in variants]),
    'range_interpretation':'range of checked single-record-removal means; not CI or a true-effect range'})
 return result

FOCUS={'ORB-SLAM2::mono':('road','building'),'ORB-SLAM3::rgbd':('road','building'),'DROID-SLAM::rgbd':('pool',)}

def evaluate_focus(groups,coeff,representative='mean',removed=None):
 endpoints=[]
 for group in groups:
  e=endpoint(group);used=[r for r in group if r['rmse_is_finite'] and (removed is None or source_key(r)!=removed)]
  values=[r['rmse_value'] for r in used];stat=describe(values)
  endpoints.append({'original_n_retained':e['n_retained'],'original_n_finite':e['n_finite'],
    'original_members':e['members'],'original_finite_members':e['finite_members'],
    'sequences':e['sequences'],'trial_n_used':len(values),'trial_members':[row_context(r) for r in used],
    'representative_value':stat[representative],'ambiguous':e['ambiguous']})
 valid=all(e['representative_value'] is not None and not e['ambiguous'] for e in endpoints)
 value=sum(a*e['representative_value'] for a,e in zip(coeff,endpoints)) if valid else None
 reason='' if valid else ';'.join(f"endpoint_{i}:ambiguous" if e['ambiguous'] else f"endpoint_{i}:no_finite_value" for i,e in enumerate(endpoints) if e['ambiguous'] or e['representative_value'] is None)
 return value,endpoints,reason

def focus_sensitivity(rows,sources):
 groups=defaultdict(list)
 for r in rows:groups[r['configuration_id'],r['scene'],route_id(r),r['altitude_m'],r['speed_mps']].append(r)
 result=[]
 for c,scenes in FOCUS.items():
  for scene in scenes:
   routes=sorted({route_id(r) for r in rows if r['configuration_id']==c and r['scene']==scene})
   for route in routes:
    definitions=[]
    for h in (10,20,30):definitions.append((f'speed8_minus2|H{h}',[(h,2),(h,8)],[-1,1]))
    for v in (2,4,8):definitions.append((f'altitude30_minus10|V{v}',[(10,v),(30,v)],[-1,1]))
    definitions.append(('rmse_four_corner',[(30,8),(30,2),(10,8),(10,2)],[1,-1,-1,1]))
    for problem,conditions,coeff in definitions:
     endpoint_rows=[groups[(c,scene,route,h,v)] for h,v in conditions]
     comp=scene+'|'+route+'|'+problem
     value,ep,reason=evaluate_focus(endpoint_rows,coeff)
     base=base_estimate(c,comp,'focus_contrast_baseline','mean',sources)
     base.update(scene=scene,route_id=route,focus_problem=problem,conditions_json=js(conditions),
       coefficients_json=js(coeff),endpoints_json=js(ep),value=value,direction=sign(value),
       status='computed' if value is not None else 'unavailable',unavailable_reason=reason,
       interpretation='fixed nominal endpoint set; one finite source row removed at a time, never same run_id across conditions')
     compare_baseline(base,base);result.append(base);variants=[]
     for representative,removed in [('median',None)]+[
       ('mean',source_key(r)) for group in endpoint_rows for r in group if r['rmse_is_finite']]:
      value,ep,reason=evaluate_focus(endpoint_rows,coeff,representative,removed)
      kind='focus_contrast_median' if removed is None else 'focus_contrast_drop_one'
      label='within_sequence_median' if removed is None else 'remove_index_'+str(removed['index'])
      r={**base,'estimate_id':f'{c}|{comp}|{kind}|{label}','analysis_type':kind,'variant':label,
         'representative':representative,'removed_record_json':js(removed) if removed else '',
         'value':value,'endpoints_json':js(ep),'direction':sign(value),
         'status':'computed' if value is not None else 'unavailable','unavailable_reason':reason}
      variants.append(compare_baseline(r,base));result.append(variants[-1])
     calculated=[r['value'] for r in [base]+variants if r['value'] is not None]
     result.append({**base,'estimate_id':f'{c}|{comp}|focus_contrast_range|checked','analysis_type':'focus_contrast_range','variant':'checked_range',
       'value':None,'delta_from_baseline':None,'direction_changed':None,'direction':'range_not_scalar','status':'computed' if calculated else 'unavailable','baseline_id':base['estimate_id'],'baseline_value':base['value'],'range_min':min(calculated) if calculated else None,'range_max':max(calculated) if calculated else None,
       'n_variants':len(variants),'n_computed_variants':sum(r['value'] is not None for r in variants),
       'n_unavailable_variants':sum(r['value'] is None for r in variants),
       'n_direction_changes':sum(r.get('direction_changed') is True for r in variants),
       'variant_ids_json':js([r['estimate_id'] for r in variants]),
       'range_interpretation':'range of baseline, within-sequence median and individual finite-record deletions; not CI'})
 return result

def efficiency_decomposition(rows,sources):
 c='hierslam::rgbd_whole';rs=[r for r in rows if r['configuration_id']==c];source=sources[c];result=[]
 for metric in METRICS[1:]:
  A=[r for r in rs if r[metric+'_is_finite']];B=[r for r in A if r['rmse_is_finite']];E=[r for r in A if not r['rmse_is_finite']]
  ma,mb,me=[describe([r[metric+'_value'] for r in group])['mean'] for group in (A,B,E)]
  difference=mb-ma if A and B else None
  common={'configuration_id':c,'evaluation_scope':source['evaluation_scope'],'metric':metric,
    'n_A':len(A),'n_B':len(B),'n_E':len(E),'mean_A':ma,'mean_B':mb,'mean_E':me,
    'overall_B_minus_A':difference,'value_unit':metric+' source units','measurement_limit':unit_limit(source,metric),
    'A_members_json':js([row_context(r) for r in A]),'B_members_json':js([row_context(r) for r in B]),
    'E_members_json':js([row_context(r) for r in E]),
    'interpretation':'fixed-set algebraic decomposition, not causal contribution or leave-one-out marginal effect'}
  terms=[(r,(mb-r[metric+'_value'])/len(A)) for r in E] if A and B else []
  identity=len(E)/len(A)*(mb-me) if A and B and E else 0.0 if A and B else None
  result.append({**common,'row_id':metric+'|overall','row_type':'overall','group_type':'none','group_label':'all_condition_labelled',
     'status':'computed' if difference is not None else 'unavailable','reason':'A_equals_B' if A and not E else 'B_empty' if not B else '',
     'contribution':sum(v for r,v in terms) if difference is not None else None,'identity_rhs':identity,
     'identity_residual':difference-identity if difference is not None else None,
     'record_contribution_sum':sum(v for r,v in terms) if difference is not None else None})
  for r,term in terms:
   result.append({**common,'row_id':metric+'|record|'+str(r['source_record_index']),'row_type':'record','group_type':'none','group_label':'excluded_record',
     'status':'computed','contribution':term,'excluded_value':r[metric+'_value'],'record_json':js(row_context(r)),
     'source_record_index':r['source_record_index'],'scene':r['scene'],'altitude_m':r['altitude_m'],'speed_mps':r['speed_mps'],
     'sum_other_fixed_terms':sum(v for q,v in terms if source_key(q)!=source_key(r)),
     'largest_abs_term':abs(term)==max(abs(v) for q,v in terms)})
  for kind,fields in [('scene',('scene',)),('altitude',('altitude_m',)),('speed',('speed_mps',)),('scene_altitude_speed',('scene','altitude_m','speed_mps'))]:
   grouped=defaultdict(list)
   for r,term in terms:grouped[tuple(r[f] for f in fields)].append((r,term))
   for key,entries in sorted(grouped.items()):
    label=js(dict(zip(fields,key)))
    result.append({**common,'row_id':metric+'|group|'+kind+'|'+label,'row_type':'group','group_type':kind,'group_label':label,
      'status':'computed','contribution':sum(term for r,term in entries),'n_excluded_in_group':len(entries),
      'group_members_json':js([row_context(r) for r,term in entries])})
  if difference is not None:
   assert close(difference,sum(v for r,v in terms)) or abs(difference-sum(v for r,v in terms))<=1e-10
 return result

def make_spec(raw,schema,command):
 return {'generated_by':'scripts/check_benchmark_robustness.py','script_sha256':sha(Path(__file__).read_bytes()),'spec_version':'1.0.0','schema_version':schema['schema_version'],
  'protocol_wording_template':{'path':'scripts/review_all_configurations_narrative.py','sha256':sha(Path(__file__).with_name('review_all_configurations_narrative.py').read_bytes())},
  'command':command,'purpose':'Exploratory deterministic checks chosen after steps 7/8; not preregistration, holdout validation or statistical inference.',
  'inputs':{k:{'path':INPUTS[k],'sha256':sha(b),'role':'only_run_performance_input' if k=='records' else 'context_or_crosscheck'} for k,b in raw.items()},
  'hash_gate':'records/manifest/schema must match step8 spec before formal calculations; no automatic refresh',
  'subset':{'support_and_sensitivity':'two_tokens only','repeat_characteristics':'all observed configuration x sequence; labelled and unlabelled explicitly separated; no invented conditions'},
  'matching':'exact removal of _speed_level_altitude_level verified suffix; fixed configuration, scene, route and the other condition; endpoint union only, no fuzzy pairing or run_id matching',
  'support':{'R':'both endpoints have retained records','F':'R and each endpoint has >=1 finite RMSE','C':'F and every retained RMSE finite at both endpoints',
             'ambiguity':'report multiple sequences/sources; affected comparison unavailable, no Cartesian pairing'},
  'views':{'V0':'endpoint means of all available finite sequence means separately; unmatched membership allowed',
   'V1':'F; equal weight per nominal block; sequence finite-run mean at each endpoint',
   'V2':'F; equal mean block differences within scene, equal weight per usable scene',
   'V3':'C under V1 rule; report blocks, records and scenes lost relative to F',
   'V4':'same F and weights as V1, replace within-sequence finite mean by finite median'},
  'direction':'8-2 m/s or 30-10 m; higher endpoint minus lower; no percent normalization',
  'validity':'finite/retained records on R (not F/C); absent endpoints listed separately, excluded from denominators',
  'scene_deletion':'V1/V2: remove one usable scene from fixed F; no replacement; no discarded variant promoted to primary',
  'sequence_deletion':'all primary observed sequences; remove one finite record only if >=2 finite; original counts preserved, trial counts separate; n<2 marked not applicable',
  'focus':{'configurations_and_scenes':FOCUS,'problems':'V8-V2 at H10/20/30, H30-H10 at V2/4/8, and four-corner (H30V8-H30V2)-(H10V8-H10V2)',
           'variants':'fixed endpoints, baseline mean, median, and each finite endpoint record removed individually; keep unavailable variants',
           'range':'finite baseline + median + all single removals; checked-variant range, not CI'},
  'repeat_equality':{'text':'exact raw string equality among finite values only','numeric':'exact equality of existing finite floats; no tolerance for distinct-value counts',
   'auxiliary':'only fields provided and already marked finite; unavailable/NA never treated as equal finite zeros; tuple memory text never parsed',
   'all_provided_fields':'every provided field must have >=2 finite values and all retained records finite; per-field partial evidence saved'},
  'near_zero':{'absolute_tolerance':ZERO_ATOL,'meaning':'numerical direction label only in source units, not a practical-equivalence or significance threshold'},
  'numeric_crosschecks':{'relative_tolerance':1e-12,'absolute_tolerance':1e-10},
  'efficiency':'Hier rgbd_whole, each metric: (B-A)=nE/nA*(B-E); c_i=(global meanB-x_i)/global nA; group sums separately by scene/height/speed/cell; not causal',
  'claims':'Q1-Q5 link actual step8 IDs; new Q9_DPVO_CANCELLATION from step8 13-positive/2-negative speed observation; parallel descriptive labels with explicit applicability',
  'figures':FIGURES,'max_figures':5,'outputs':list(OUTPUTS.values()),
  'inference':'no p values, significance stars, bootstrap or confidence intervals; evaluate prerequisites separately for fixed-benchmark description and new-scene inference',
  'bounds':['no source experiment directory or logs','no modification/deduplication/imputation of records','no environment or dependency changes',
            'no stage10 analysis','units/alignment/history and unknown scopes stay qualified; numerical stability cannot verify provenance']}

def crosscheck_previous(rows,blocks,estimates,decomp,raw):
 grouped=defaultdict(list)
 for r in rows:grouped[r['configuration_id'],r['sequence_raw']].append(r)
 joint_by_cell={};nseq=0
 for old in csv.DictReader(io.StringIO(raw['joint8'].decode())):
  if old['metric']!='rmse' or old['aggregation_level']!='equal_weight_sequence_means' or old['scene']=='__all_scenes__':continue
  key=(old['configuration_id'],old['scene'],int(old['altitude_m']),int(old['speed_mps']))
  joint_by_cell[key]=old
  for d in json.loads(old['sequence_descriptors_json']):
   rs=grouped[(old['configuration_id'],d['sequence'])];e=endpoint(rs)
   assert close(e['mean'],d['mean']) or e['mean'] is None and d['mean'] is None
   assert close(e['median'],d['median']) or e['median'] is None and d['median'] is None
   assert e['n_retained']==d['n_retained'] and e['n_finite']==d['n_finite']
   assert [m['index'] for m in e['members']]==[x['source_record_index'] for x in d['retained_runs']]
   nseq+=1
 assert nseq==len(grouped)
 blockcheck=0
 for b in blocks:
  for side,value in [('low',b['low_condition']),('high',b['high_condition'])]:
   h=b['fixed_value'] if b['fixed_axis']=='altitude_m' else value
   v=b['fixed_value'] if b['fixed_axis']=='speed_mps' else value
   old=joint_by_cell[(b['configuration_id'],b['scene'],h,v)]
   # Current snapshot: one exact route sequence per populated scene-cell, verified, not assumed.
   if int(old['n_observed_sequences'])>1:raise ValueError('Prior cell spans multiple sequences; verify route-specific baseline separately')
   ep=b[side]
   assert ep['n_retained']==int(old['n_retained_records']) and ep['n_finite']==int(old['n_finite_records'])
   assert (ep['mean'] is None and old['mean']=='') or close(ep['mean'],float(old['mean']))
   assert [m['index'] for m in ep['members']]==json.loads(old['source_record_indices_json'])
   blockcheck+=1
 focus={ (r['configuration_id'],r['scene'],r['focus_problem']):r for r in estimates if r['analysis_type']=='focus_contrast_baseline'}
 checked_focus=0
 for old in csv.DictReader(io.StringIO(raw['contrasts8'].decode())):
  if old['metric']!='rmse' or old['aggregation_level']!='equal_weight_sequence_means':continue
  if old['contrast_kind']=='speed_difference' and old['direction']=='8 - 2':problem='speed8_minus2|H'+old['fixed_value']
  elif old['contrast_kind']=='altitude_difference' and old['direction']=='30 - 10':problem='altitude30_minus10|V'+old['fixed_value']
  elif old['contrast_kind']=='rmse_four_corner':problem='rmse_four_corner'
  else:continue
  r=focus.get((old['configuration_id'],old['scene'],problem))
  if r is None:continue
  assert (r['value'] is None and old['difference']=='') or close(r['value'],float(old['difference']))
  assert (r['status']=='computed')==(old['status']=='computed');checked_focus+=1
 assert checked_focus==len(focus)
 cells=[r for r in csv.DictReader(io.StringIO(raw['efficiency8'].decode())) if r['configuration_id']=='hierslam::rgbd_whole' and r['scene']!='__all_scenes__']
 for overall in [r for r in decomp if r['row_type']=='overall']:
  cells_m=[r for r in cells if r['metric']==overall['metric']]
  for cohort in ('A','B'):
   n=sum(int(r['n_'+cohort]) for r in cells_m)
   mean=sum(float(r[cohort+'_mean'])*int(r['n_'+cohort]) for r in cells_m if r[cohort+'_mean'])/n
   assert n==overall['n_'+cohort] and close(mean,overall['mean_'+cohort])
  excluded={i for r in cells_m for i in json.loads(r['A_not_B_record_indices_json'])}
  assert excluded=={m['index'] for m in json.loads(overall['E_members_json'])}
 assert len({r['estimate_id'] for r in estimates})==len(estimates)
 return {'primary_sequences_crosschecked_step8':nseq,'block_endpoints_crosschecked':blockcheck,
         'focused_contrasts_crosschecked':checked_focus,'efficiency_weighted_baselines_and_members_match':True,
         'estimate_ids_unique':True}

def claim_assessment(prior,repeat,blocks,estimates,decomp):
 result=[];byid={r['estimate_id']:r for r in estimates}
 def views(c,comparison):return {r['view']:r for r in estimates if r['configuration_id']==c and r['comparison']==comparison and r['analysis_type']=='support_view'}
 for p in prior:
  c=p['configuration_id'];qid=p['question_id'];tags=[];evidence=[];obs='';limits=''
  focus=[r for r in estimates if r['configuration_id']==c and r['analysis_type']=='focus_contrast_range']
  if qid=='Q1':
   tested=[r for r in focus if r['focus_problem'] in ('speed8_minus2|H10','speed8_minus2|H30','rmse_four_corner')]
   changes=sum(r['n_direction_changes'] for r in tested)
   if changes==0 and all(r['n_computed_variants']>0 for r in tested):tags.append('stable_within_checked_variants')
   if any(not close(r['range_min'],r['range_max']) for r in tested):tags.append('repeat_sensitive')
   obs='局部速度端点与四角量：'+'；'.join(f"{r['scene']} {r['focus_problem']} 基线={fmt(r['value']) if r['value'] is not None else fmt(byid[r['estimate_id'].replace('focus_contrast_range|checked','focus_contrast_baseline|mean')]['value'])}, 所查范围=[{fmt(r['range_min'])},{fmt(r['range_max'])}], 方向改变={r['n_direction_changes']}, 不可算变体={r['n_unavailable_variants']}" for r in tested)
   evidence=[r['estimate_id'] for r in tested]
   highnames=json.loads(p['anchor_sequence_names_json'])
   high=[r for r in estimates if r['configuration_id']==c and r['analysis_type']=='sequence_variant_range' and r.get('sequence_raw') in highnames]
   obs+='；三条高值序列删一均值范围：'+'；'.join(f"{r['sequence_raw']} [{fmt(r['range_min'])},{fmt(r['range_max'])}]" for r in high)
   evidence += [r['estimate_id'] for r in high]
   limits='稳定标签仅针对所查局部方向；数值幅度仍随单条记录改变。不是总体高度/速度因果效应、全条件单调关系或未来实验保证。'
  elif qid=='Q2':
   pool=[r for r in repeat if r['configuration_id']==c and r['scene']=='pool' and r['subset']=='condition_labelled']
   tags=['repetition_provenance_unresolved']
   tested=[r for r in focus if r['scene']=='pool']
   stable=all(r['n_computed_variants']>0 and r['n_direction_changes']==0 and close(r['range_min'],r['range_max']) for r in tested)
   if stable:tags.append('stable_within_checked_variants')
   obs=f"Pool重复审计覆盖{len(pool)}条sequence；RMSE文本一致 {sum(r['finite_rmse_text_identical'] for r in pool)}，RMSE数值一致 {sum(r['finite_rmse_identical'] for r in pool)}，全部已提供误差字段一致 {sum(r['all_provided_error_fields_identical'] for r in pool)}，连全部效率也一致 {sum(r['all_efficiency_fields_identical'] for r in pool)}。"
   obs+='条件差与四角量范围：'+'；'.join(f"{r['focus_problem']} [{fmt(r['range_min'])},{fmt(r['range_max'])}]" for r in tested)
   evidence=[r['estimate_id'] for r in tested]
   limits='相同重复值下删一与median保持是数学必然；不证明独立重复可靠、确定性算法、固定种子或数据复制。未提供字段不计为相同零，未追查底层过程。'
  elif qid=='Q3':
   names=json.loads(p['anchor_sequence_names_json'])+['road2_medium_medium']
   tested=[r for r in estimates if r['configuration_id']==c and r['analysis_type']=='sequence_variant_range' and r.get('sequence_raw') in names]
   tags=['repeat_sensitive'];obs='逐序列删一均值：'+'；'.join(f"{r['sequence_raw']} 基线={fmt(r['value'])}, median={fmt(r['baseline_median'])}, 范围=[{fmt(r['range_min'])},{fmt(r['range_max'])}]" for r in tested)
   # Range rows keep baseline separately in original sequence-baseline table.
   for r in tested:
    base=byid[f"{c}|{r['sequence_raw']}|sequence_baseline|finite_mean"]
    obs=obs.replace(f"{r['sequence_raw']} 基线=未定义",f"{r['sequence_raw']} 基线={fmt(base['value'])}")
   changed=[r for r in focus if r['n_direction_changes']]
   obs+=f"；road/building共{len(focus)}个端点/四角问题中，{len(changed)}个至少一个变体方向改变。"
   obs+='改变问题：'+'；'.join(r['scene']+' '+r['focus_problem']+f" 范围=[{fmt(r['range_min'])},{fmt(r['range_max'])}]" for r in changed)
   evidence=[r['estimate_id'] for r in tested+changed]
   limits='一低一高或两低一高会使均值敏感；两个有限值时median=mean不代表稳定。相邻三次都较高的单元仍保留；单条记录影响大不等于错误。'
  elif qid=='Q4':
   tags=['finite_support_limited'];parts=[]
   for comp in COMPARISONS:
    v=views(c,comp);F=v['V1'];C=v['V3']
    validity=next(r for r in estimates if r['configuration_id']==c and r['comparison']==comp and r['analysis_type']=='numeric_validity_R')
    parts.append(f"{comp} R/F/C={F['n_R']}/{F['n_F']}/{F['n_C']}；V0..V4="+js({k:r['value'] for k,r in v.items()})+
      f"；R内有限/保留：低端{validity['low_n_finite']}/{validity['low_n_retained']}，高端{validity['high_n_finite']}/{validity['high_n_retained']}；C较F失去{C['C_lost_blocks_from_F']}块")
    evidence.extend(r['estimate_id'] for r in v.values());evidence.append(validity['estimate_id'])
    if any(r['value'] is not None and not close(r['value'],F['value']) for r in v.values()):tags.append('weighting_sensitive')
   obs='；'.join(parts);limits='共同有限集合不能恢复全无效端点；F/C上的变化不能代表R中所有条件，更不能声称整体变好。无记录块不加入分母。'
  elif qid=='Q5':
   tags=[];parts=[]
   for overall in [r for r in decomp if r['row_type']=='overall']:
    metric=overall['metric'];terms=[r for r in decomp if r['row_type']=='record' and r['metric']==metric]
    largest=max(terms,key=lambda r:abs(r['contribution']),default=None)
    stable=all(sign(r['sum_other_fixed_terms'])==sign(overall['overall_B_minus_A']) for r in terms)
    largest_text=(f"最大绝对项来源{largest['source_record_index']}={fmt(largest['contribution'])}" if largest else '无可计算排除项；检查A/B状态')
    parts.append(f"{metric} A/B/E={overall['n_A']}/{overall['n_B']}/{overall['n_E']}, B-A={fmt(overall['overall_B_minus_A'])}；{largest_text}；去掉任一固定代数项后符号均保持={stable if terms else '不适用'}")
    evidence += [r['row_id'] for r in [overall]+terms]
   obs='；'.join(parts);tags=['weighting_sensitive']
   limits='各项用同一global mean(B)和n(A)。sum_other_fixed_terms仅为固定代数项的剩余和，不是重定义A/B或删除记录后的边际效应；不作因果贡献。'
  result.append({'question_id':qid,'origin':'existing_step8_question','configuration_id':c,'original_observation':p['observation'],
    'labels_json':js(sorted(set(tags))),'current_observation':obs,'evidence_ids_json':js(evidence),'limitations':limits,
    'supported_wording':obs,'unsupported_wording':limits,'status':'checked_descriptively','inference':'no p values or confidence intervals'})
 c='DPVO::mono';comp='speed8_minus2';v=views(c,comp)
 loo=[r for r in estimates if r['configuration_id']==c and r['comparison']==comp and r['analysis_type']=='leave_one_scene_out']
 no_pool=next(r for r in loo if r['view']=='V1' and r['removed_scene']=='pool')
 local=[b for b in blocks if b['configuration_id']==c and b['comparison']==comp and b['in_F']]
 diffs=[b['high']['mean']-b['low']['mean'] for b in local]
 contrib=[r for r in estimates if r['configuration_id']==c and r['comparison']==comp and r['analysis_type']=='scene_contribution' and r['view']=='V1']
 tags=['scene_composition_sensitive'] if any(r['direction_changed'] for r in loo) else ['stable_within_checked_variants']
 observation=f"V1={fmt(v['V1']['value'])}, V2={fmt(v['V2']['value'])}；F={len(local)}块中正/负/近零={sum(sign(x)=='positive' for x in diffs)}/{sum(sign(x)=='negative' for x in diffs)}/{sum(sign(x)=='near_zero' for x in diffs)}。各场景对V1代数贡献="+js({r['scene']:r['value'] for r in contrib})+f"；移去pool后V1={fmt(no_pool['value'])}，变化={fmt(no_pool['delta_from_baseline'])}。"
 result.append({'question_id':'Q9_DPVO_CANCELLATION','origin':'new_in_step9_from_step8_positive_negative_endpoint_pattern',
  'configuration_id':c,'original_observation':'Step8: many positive speed endpoint differences alongside a small aggregate difference; cancellation to be checked, not assumed.',
  'labels_json':js(tags),'current_observation':observation,'evidence_ids_json':js([r['estimate_id'] for r in [v['V1'],v['V2'],no_pool]+contrib]),
  'limitations':'15个块共享五类场景，不是15个独立随机样本；符号计数不是显著性投票，删场景不是新主结果或泛化验证。',
  'supported_wording':observation,'unsupported_wording':'不能称DPVO对速度普遍不敏感，也不能用删pool后的结果代替正式基线。',
  'status':'checked_descriptively','inference':'no p values or confidence intervals'})
 for row in result:
  qid=row['question_id'];c=row['configuration_id']
  kinds={'Q1':['sequence_drop_one','focus_contrast_median','focus_contrast_drop_one'],
   'Q2':['repeat_value_audit','focus_contrast_median','focus_contrast_drop_one'],
   'Q3':['sequence_drop_one','focus_contrast_median','focus_contrast_drop_one'],
   'Q4':['support_blocks','support_view','numeric_validity_R'],
   'Q5':['efficiency_decomposition_overall_record_group'],
   'Q9_DPVO_CANCELLATION':['support_view','scene_contribution','leave_one_scene_out']}[qid]
  row['checks_performed_json']=js(kinds)
  checked=[r for r in estimates if r['configuration_id']==c and r['analysis_type'] in kinds]
  row['changed_estimate_ids_json']=js([r['estimate_id'] for r in checked if r.get('direction_changed') is True])
  row['unavailable_estimate_ids_json']=js([r['estimate_id'] for r in checked if r['status'] in ('unavailable','not_applicable')])
 return result

def self_tests():
 """Small hand-calculable cases; no experiment files or prior-stage entrypoints."""
 tests=[]
 source={k:'fixture' for k in META}
 source.update(configuration_id='fixture',evaluation_scope='fixture',rmse_unit_status='fixture_units',alignment_status='fixture',
   efficiency_protocol_json=js({k:'fixture' for k in ('fps_unit_status','runtime_unit_status','memory_conversion_and_kind','evidence_status')}))
 sources={'fixture':source,'hierslam::rgbd_whole':source}
 def record(i,x,scene='s1',route='route',h=10,v=2,text=None,config='fixture',eff=1.0):
  r={**{k:source[k] for k in META},'configuration_id':config,'scene':scene,
     'speed_mps':v,'altitude_m':h,'speed_level':{2:'low',4:'medium',8:'high'}[v],
     'altitude_level':{10:'low',20:'medium',30:'high'}[h],
     'condition_label_status':'two_tokens','source_relative_path':'fixture.csv','source_sha256':'fixture',
     'source_record_index':i,'run_id_raw':str(10+i)}
  r['sequence_raw']=route+'_'+r['speed_level']+'_'+r['altitude_level']
  for field in RAW_FIELDS:
   value=x if field=='rmse' else eff if field in METRICS else None
   state='finite_positive' if value is not None else 'raw_na' if field=='rmse' else 'source_not_provided'
   r[RAW_FIELDS[field]]=text if text is not None and field=='rmse' else str(value) if value is not None else 'NA' if field=='rmse' else ''
   r[field+'_state']=state
   if field in METRICS:r[field+'_value']=value;r[field+'_is_finite']=value is not None
  return r
 a=field_audit([record(1,1,text='1.0'),record(2,1,text='1.0')],'rmse')
 b=field_audit([record(1,1,text='1.0'),record(2,1,text='1.00')],'rmse')
 na=field_audit([record(1,None),record(2,None)],'rmse')
 absent=field_audit([record(1,1),record(2,1)],'std')
 assert a['finite_text_identical'] and a['finite_numeric_identical']
 assert not b['finite_text_identical'] and b['finite_numeric_identical']
 assert not na['finite_numeric_identical'] and na['n_finite']==0
 assert absent['status']=='source_not_provided' and not absent['finite_numeric_identical']
 assert describe([1,9])['median']==describe([1,9])['mean']==5 and describe([1,9])['sample_sd']>0
 tests.append('raw text / equal numeric / multiple NA / absent fields / two-value median')
 rs=[record(1,1,route='a'),record(2,3,route='a',v=8),
     record(3,2,route='b'),record(4,None,route='b'),record(5,5,route='b',v=8),
     record(6,None,route='c'),record(7,6,route='c',v=8),
     record(8,9,route='d')]
 snap=js(rs);blocks=support_blocks(rs);speed=[b for b in blocks if b['comparison']=='speed8_minus2']
 assert (sum(b['in_R'] for b in speed),sum(b['in_F'] for b in speed),sum(b['in_C'] for b in speed))==(3,2,1)
 vr=next(r for r in all_views(blocks,sources={'fixture':source}) if r['comparison']=='speed8_minus2' and r['analysis_type']=='numeric_validity_R')
 assert (vr['low_n_finite'],vr['low_n_retained'],vr['high_n_finite'],vr['high_n_retained'])==(2,4,3,3)
 assert js(rs)==snap and len(speed)==4
 assert all(b[s]['n_sequences']<=1 for b in speed for s in ('low','high'))
 assert route_id(record(1,1,route='keep_low_high_middle'))=='keep_low_high_middle'
 other=record(9,2,route='a');other['source_relative_path']='second_fixture.csv'
 ambiguous=support_blocks(rs+[other])
 unavailable=estimate_view('fixture','speed8_minus2',ambiguous,'V1',sources)
 assert unavailable['value'] is None and unavailable['unavailable_reason']=='ambiguous_block_no_pairing'
 assert any(r['status']=='unavailable' for r in all_views(ambiguous,{'fixture':source}))
 tests.append('R/F/C=3/2/1, R coverage=2/4 vs 3/3; exact routes, unmatched run IDs, ambiguous sources not paired')
 # Three blocks: +2,+4 in s1, +10 in s2; unequal within-block record counts.
 rs=[record(1,1,route='a'),record(2,3,route='a',v=8),
     record(3,1,route='b'),record(4,5,route='b',v=8),
     *[record(10+i,1,scene='s2',route='c') for i in range(3)],
     *[record(20+i,11,scene='s2',route='c',v=8) for i in range(3)]]
 blocks=support_blocks(rs);v1=estimate_view('fixture','speed8_minus2',blocks,'V1',sources)
 v2=estimate_view('fixture','speed8_minus2',blocks,'V2',sources)
 pooled=describe([r['rmse_value'] for r in rs if r['speed_mps']==8])['mean']-1
 assert close(v1['value'],16/3) and close(v2['value'],6.5) and close(pooled,7.2)
 omit=estimate_view('fixture','speed8_minus2',blocks,'V1',sources,'leave_one_scene_out','s1')
 assert omit['value']==10 and set(json.loads(omit['low_block_ids_json']))<set(json.loads(v1['low_block_ids_json']))
 tests.append('pooled=7.2, equal blocks=16/3, equal scenes=6.5; LOSO fixed original F')
 seq=sequence_sensitivity([record(1,1),record(2,9)],sources)
 assert sorted(r['value'] for r in seq if r['analysis_type']=='sequence_drop_one')==[1,9]
 assert all(r['trial_repeat_sd'] is None for r in seq if r['analysis_type']=='sequence_drop_one')
 single=sequence_sensitivity([record(1,1)],sources)
 assert next(r for r in single if r['analysis_type']=='sequence_drop_one')['value'] is None
 assert evaluate_focus([[record(1,1)],[record(2,3,v=8)]],[-1,1],removed=source_key(record(1,1)))[0] is None
 tests.append('single deletion, original counts unchanged, one-value SD undefined, lost required endpoint unavailable')
 rs=[record(1,1,config='hierslam::rgbd_whole',eff=2),
     record(2,2,config='hierslam::rgbd_whole',eff=4),
     record(3,None,config='hierslam::rgbd_whole',eff=12)]
 dd=efficiency_decomposition(rs,sources)
 for m in METRICS[1:]:
  o=next(r for r in dd if r['row_type']=='overall' and r['metric']==m)
  assert close(o['overall_B_minus_A'],-3) and close(o['identity_rhs'],-3) and close(o['record_contribution_sum'],-3)
 for x in rs:x['rmse_is_finite']=True
 assert all(r['overall_B_minus_A']==0 for r in efficiency_decomposition(rs,sources) if r['row_type']=='overall')
 for x in rs:x['rmse_is_finite']=False
 assert all(r['overall_B_minus_A'] is None for r in efficiency_decomposition(rs,sources) if r['row_type']=='overall')
 tests.append('efficiency identity / contribution sum, E empty and B empty')
 # Temporary fixture paths are wholly owned by this invocation; no environment directories touched.
 reject_links(W/'reports')
 with tempfile.TemporaryDirectory(prefix='.09_guard_test_',dir=W/'reports') as temp:
  root=Path(temp);original=root/'input.txt';original.write_text('keep')
  with patch.object(sys.modules[__name__],'W',root),patch.dict(OUTPUTS,{'test':'result.txt'},clear=True):
   write('test',b'one',False)
   try:write('test',b'two',False);raise AssertionError('overwrite accepted')
   except FileExistsError:pass
   write('test',b'two',True)
   try:check_output(original,True);raise AssertionError('outside allowlist accepted')
   except ValueError:pass
   (root/'result.txt').unlink();(root/'result.txt').symlink_to(original)
   try:write('test',b'bad',True);raise AssertionError('symlink accepted')
   except ValueError:pass
   (root/'result.txt').unlink();os.link(original,root/'result.txt')
   try:write('test',b'bad',True);raise AssertionError('hardlink accepted')
   except ValueError:pass
   assert original.read_text()=='keep'
 tests.append('default refusal / step9 allowlist / symlink+hardlink rejection / input unchanged')
 return tests

def draw_figures(estimates,decomp,rows,overwrite):
 reject_links(W/'reports')
 with tempfile.TemporaryDirectory(prefix='.09_plot_tmp_',dir=W/'reports') as temp:
  with patch.dict(os.environ,{'MPLCONFIGDIR':temp,'XDG_CACHE_HOME':temp,'TMPDIR':temp,'PYTHONDONTWRITEBYTECODE':'1'}):
   import matplotlib
   matplotlib.use('Agg')
   import matplotlib.pyplot as plt
   plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'svg.hashsalt':'benchmark-step9',
                        'axes.spines.top':False,'axes.spines.right':False,'axes.grid':True,'grid.alpha':.2})
   def save(fig,name):
    for ext in ('png','svg'):
     b=io.BytesIO();fig.savefig(b,format=ext,dpi=160,metadata={'Software':'benchmark-analysis step9'} if ext=='png' else {'Date':None})
     write(name+'.'+ext,b.getvalue(),overwrite)
    plt.close(fig)
   def select(c,kind):return [r for r in estimates if r['configuration_id']==c and r['analysis_type']==kind]
   def val(x):return 'unavailable' if x is None else f'{x:.4g}'
   # DPVO: scene omission labels and signed additive contributions, not inferential intervals.
   c='DPVO::mono';comp='speed8_minus2';fig,axes=plt.subplots(1,2,figsize=(13,6))
   allv=[r for r in estimates if r['configuration_id']==c and r['comparison']==comp]
   removed=sorted({r['removed_scene'] for r in allv if r['analysis_type']=='leave_one_scene_out'})
   labels=['Full F']+['Remove '+s for s in removed]
   for view,color,offset in [('V1','#2166ac',-.11),('V2','#b35806',.11)]:
    vv=[next(r for r in allv if r['analysis_type']=='support_view' and r['view']==view)]
    vv += [next(r for r in allv if r['analysis_type']=='leave_one_scene_out' and r['view']==view and r['removed_scene']==s) for s in removed]
    for i,r in enumerate(vv):
     if r['value'] is None:axes[0].text(.98,i+offset,'unavailable',transform=axes[0].get_yaxis_transform(),ha='right')
     else:axes[0].scatter(r['value'],i+offset,color=color,label=view if i==0 else None);axes[0].annotate(val(r['value']),(r['value'],i+offset),xytext=(5,0),textcoords='offset points',va='center',fontsize=8)
   axes[0].set_yticks(range(len(labels)),labels);axes[0].invert_yaxis();axes[0].axvline(0,c='gray',lw=1);axes[0].legend()
   axes[0].set(title='Fixed-F leave-one-scene-out',xlabel='RMSE difference: V8 - V2 (source units)')
   cc=[r for r in allv if r['analysis_type']=='scene_contribution' and r['view']=='V1']
   axes[1].barh([r['scene'] for r in cc],[r['value'] for r in cc],color=['#b2182b' if r['value']<0 else '#2166ac' for r in cc])
   for i,r in enumerate(cc):axes[1].text(r['value'],i,' '+val(r['value']),va='center',ha='left' if r['value']>=0 else 'right',fontsize=9)
   axes[1].axvline(0,c='gray',lw=1);axes[1].set(title='Additive contributions to full-F V1',xlabel='Scene sum of block differences / total F blocks')
   axes[1].margins(x=.3)
   fig.suptitle('DPVO::mono | speed endpoint cancellation',fontsize=14)
   fig.text(.5,.025,'V1 = equal blocks; V2 = equal usable scenes. Signed contributions sum to V1. Deterministic checks, not CI.',ha='center',fontsize=9)
   fig.tight_layout(rect=(0,.07,1,.94),w_pad=3);save(fig,'01_dpvo_scene_cancellation')
   # ORB2 focused ranges explicitly show names of extrema-producing removed records.
   c='ORB-SLAM2::mono'
   bases=[r for r in select(c,'focus_contrast_baseline') if r['focus_problem'] in ('speed8_minus2|H10','speed8_minus2|H30','rmse_four_corner')]
   fig,ax=plt.subplots(figsize=(15,9))
   source_by_index={(r['configuration_id'],r['source_record_index']):r for r in rows}
   def variant_name(r):
    if r['analysis_type']=='focus_contrast_baseline':return 'baseline'
    if r['analysis_type']=='focus_contrast_median':return 'sequence median'
    removed=json.loads(r['removed_record_json']);rr=source_by_index[(r['configuration_id'],removed['index'])]
    return 'drop '+rr['sequence_raw']+' / run '+rr['run_id_raw']+' / #'+str(removed['index'])
   ticks=[]
   for i,base in enumerate(bases):
    variants=[base]+[r for r in estimates if r.get('baseline_id')==base['estimate_id'] and r['analysis_type'] in ('focus_contrast_median','focus_contrast_drop_one')]
    valid=[r for r in variants if r.get('value') is not None]
    low=min(valid,key=lambda r:r['value']);high=max(valid,key=lambda r:r['value'])
    med=next(r for r in variants if r['analysis_type']=='focus_contrast_median')
    ax.plot([low['value'],high['value']],[i,i],c='#999',lw=4,label='Checked-variant range (not CI)' if i==0 else None)
    ax.scatter(base['value'],i,c='#2166ac',s=50,label='Baseline mean' if i==0 else None,zorder=3)
    ax.scatter(med['value'],i,c='#b35806',marker='D',s=35,label='Within-sequence median' if i==0 else None,zorder=3)
    ticks.append(base['scene']+' | '+base['focus_problem'])
    ax.text(.01,i+.17,'min '+val(low['value'])+': '+variant_name(low)+'\nmax '+val(high['value'])+': '+variant_name(high),
            transform=ax.get_yaxis_transform(),fontsize=8,va='top',bbox={'facecolor':'white','alpha':.8,'edgecolor':'none'})
   ax.set_yticks(range(len(bases)),ticks);ax.set_ylim(-.65,len(bases)-.25);ax.invert_yaxis();ax.axvline(0,c='gray',lw=1)
   ax.legend(loc='upper left',bbox_to_anchor=(0,1.11),ncol=3)
   ax.set(xlabel='RMSE endpoint difference / four-corner quantity (source units)',title='ORB-SLAM2::mono | fixed road/building conditions')
   fig.text(.5,.02,'Range = baseline + sequence median + each individual finite-run omission. Fixed endpoints; no same-run-ID joint deletion. Not CI.',ha='center',fontsize=9)
   fig.tight_layout(rect=(0,.05,1,.96));save(fig,'02_orb2_local_sensitivity')
   # ORB3: all removal objects preserved in axis labels. Four panels, one configuration.
   c='ORB-SLAM3::rgbd';names=['road2_medium_low','road2_high_high','cross_building_low_low','road2_medium_medium']
   fig,axes=plt.subplots(2,2,figsize=(13,9),sharey=True)
   for ax,name in zip(axes.flat,names):
    base=next(r for r in select(c,'sequence_baseline') if r['sequence_raw']==name)
    variants=[r for r in select(c,'sequence_drop_one') if r['sequence_raw']==name and r['value'] is not None]
    labels=[]
    for i,r in enumerate(variants):
     m=json.loads(r['removed_record_json']);labels.append('drop run '+m['run_id']+'\n#'+str(m['index']))
     ax.scatter(i,r['value'],c='#2166ac');ax.annotate(val(r['value']),(i,r['value']),xytext=(0,7),textcoords='offset points',ha='center',fontsize=9)
    ax.axhline(base['value'],c='#2166ac',label='Baseline finite mean')
    ax.axhline(base['baseline_median'],c='#b35806',ls='--',label='Finite median')
    ax.set_xticks(range(len(labels)),labels)
    ax.set_title(name+f"\nH{base['altitude_m']}, V{base['speed_mps']}; finite/retained {base['original_n_finite']}/{base['original_n_retained']}",fontsize=10)
    ax.set_ylabel('RMSE remaining mean (source units)');ax.margins(x=.3,y=.18)
   axes[0,0].legend(fontsize=9,loc='upper right')
   fig.suptitle('ORB-SLAM3::rgbd | individual finite-run influence',fontsize=14)
   fig.text(.5,.02,'Original records and denominators remain unchanged. Dots are checked omissions, not confidence limits; two-value median = mean.',ha='center',fontsize=9)
   fig.tight_layout(rect=(0,.06,1,.94));save(fig,'03_orb3_repeat_influence')
   # VGGT support diagnostics: no ranking across unrelated configurations.
   c='VGGT-SLAM::mono';fig,axes=plt.subplots(1,2,figsize=(13,6))
   for ax,comp in zip(axes,COMPARISONS):
    vv=[next(r for r in select(c,'support_view') if r['comparison']==comp and r['view']==view) for view in ('V0','V1','V2','V3','V4')]
    for i,r in enumerate(vv):
     if r['value'] is None:ax.text(i,.5,'unavailable',rotation=90,ha='center',transform=ax.get_xaxis_transform())
     else:ax.scatter(i,r['value'],c='#2166ac');ax.annotate(val(r['value']),(i,r['value']),xytext=(0,7),textcoords='offset points',ha='center')
    v1=vv[1];R=next(r for r in select(c,'numeric_validity_R') if r['comparison']==comp)
    ax.set_xticks(range(5),['V0\navailable','V1\nF blocks','V2\nF scenes','V3\nC blocks','V4\nF median'])
    ax.axhline(0,c='gray',lw=1);ax.margins(y=.25,x=.15)
    ax.set_title(comp+f"\nR/F/C={v1['n_R']}/{v1['n_F']}/{v1['n_C']}",fontsize=11)
    ax.set_ylabel('RMSE endpoint difference (source units)')
    ax.text(.5,-.22,f"Finite / retained on R: low {R['low_n_finite']}/{R['low_n_retained']}; high {R['high_n_finite']}/{R['high_n_retained']}\nC loses {vv[3]['C_lost_blocks_from_F']} F blocks, {vv[3]['C_lost_records_from_F']} retained records",ha='center',transform=ax.transAxes,fontsize=9)
   fig.suptitle('VGGT-SLAM::mono | support and weighting sensitivity',fontsize=14)
   fig.text(.5,.015,'F/C exclude unidentifiable endpoints; these views do not recover missing outcomes. Source units unchanged. Not CI.',ha='center',fontsize=9)
   fig.tight_layout(rect=(0,.12,1,.94));save(fig,'04_vggt_support_views')
   # Hier: global algebra, not cell means and not a deletion effect.
   terms=[r for r in decomp if r['metric']=='runtime' and r['row_type']=='record']
   overall=next(r for r in decomp if r['metric']=='runtime' and r['row_type']=='overall')
   fig,ax=plt.subplots(figsize=(12,max(6,.34*(len(terms)+1)+2)))
   labels=[f"#{r['source_record_index']} {r['scene']} H{r['altitude_m']} V{r['speed_mps']}" for r in terms]+['Sum = global B - A']
   values=[r['contribution'] for r in terms]+[overall['overall_B_minus_A']]
   indices=[i for i,x in enumerate(values) if x is not None]
   ax.barh(indices,[values[i] for i in indices],color=['#b2182b' if values[i]<0 else '#2166ac' for i in indices])
   ax.set_yticks(range(len(labels)),labels);ax.axvline(0,c='gray',lw=1);ax.invert_yaxis()
   for i,x in enumerate(values):
    if x is None:ax.text(.02,i,'unavailable',va='center',transform=ax.get_yaxis_transform())
    else:ax.text(x,i,' '+val(x),va='center',ha='left' if x>=0 else 'right')
   ax.margins(x=.3);ax.set_xlabel('Runtime source units: c_i = [global mean(B) - x_i] / n(A)')
   ax.set_title(f"hierslam::rgbd_whole | runtime filtering decomposition\nA/B/E={overall['n_A']}/{overall['n_B']}/{overall['n_E']}; global mean(B)={val(overall['mean_B'])}",fontsize=13)
   fig.text(.5,.025,'Same global mean(B) and n(A) for every term. Fixed-set algebra only; not causal or leave-one-out effects. No confidence intervals.',ha='center',fontsize=9)
   fig.tight_layout(rect=(0,.07,1,1));save(fig,'05_hier_runtime_decomposition')
 return list(FIGURES)


def make_report(rows,repeat,blocks,estimates,decomp,claims,tests,checks,raw,command):
 from review_all_configurations_narrative import protocol_note
 _,manifest_rows=decode_csv(raw['manifest'])
 sources={r['configuration_id']:r for r in manifest_rows}
 def table(headers,rr):
  return '| '+' | '.join(headers)+' |\n| '+' | '.join(['---']*len(headers))+' |\n'+'\n'.join('| '+' | '.join(str(x).replace('|',' / ').replace('\n',' ') for x in row)+' |' for row in rr)+'\n'
 views=[r for r in estimates if r['analysis_type']=='support_view']
 vs={(r['configuration_id'],r['comparison'],r['view']):r for r in views}
 lines=['# 第 9 步：稳健性验证与统计推断适用性评估','',
  protocol_note({'accuracy_protocol_by_configuration':sources}),'',
  '本轮已从不变的标准化逐次记录实际复算；问题依据第 7／8 步选定，属于探索性确定性检查。没有开展显著性检验、bootstrap、底层来源追查或第 10 步。',
  '', '## 结论先行','']
 for q in claims:
  lines.extend([f"### {q['question_id']} — {q['configuration_id']}",'',
    '**原观察：** '+q['original_observation'],'','**本轮观察：** '+q['current_observation'],'',
    '**标签：** '+', '.join(json.loads(q['labels_json'])),'','**可保留的表述及边界：** '+q['limitations'],''])
 lines+=['完整证据键、既有问题 ID 和当前可／不可支持的措辞见 [09_claim_assessment.csv](09_claim_assessment.csv)。稳定仅覆盖实际执行的变体，不表示真实效应或未来重复已确认。','',
  '## 覆盖与重复数值特征','',
  f"唯一逐次输入共 {len(rows)} 行、24 配置；重复数值审计包括全部 {len(repeat)} 个实际 configuration × sequence，并标明无条件标签的子集。其余主要检查使用 two_tokens 的 {sum(r['condition_label_status']=='two_tokens' for r in rows)} 行、{sum(r['subset']=='condition_labelled' for r in repeat)} 个实际序列。没有为未保留或尚未运行的实验补行。",
  '',
  '“相同”分别检查原始有限文本和已有有限数值的精确相等；辅助字段只在原文件提供且标准化状态有限时使用，不把 NA 或 source_not_provided 当成零。内存元组字符串不重新解析。重复运行 SD 用 ddof=1；单值未定义，有限值相同而得到的 0 仅表示保留数值无差异。',
  '']
 audit=[]
 for c in sorted({r['configuration_id'] for r in repeat}):
  rr=[r for r in repeat if r['configuration_id']==c]
  audit.append([c,len(rr),sum(r['subset']=='condition_labelled' for r in rr),sum(r['n_retained'] for r in rr),
    sum(r['n_finite_rmse']<2 for r in rr),sum(r['finite_rmse_text_identical'] for r in rr),
    sum(r['finite_rmse_identical'] for r in rr),sum(r['all_provided_error_fields_identical'] for r in rr),sum(r['all_efficiency_fields_identical'] for r in rr)])
 lines +=[table(['配置','实际序列','有条件序列','保留行','有限RMSE<2','有限RMSE文本同','有限RMSE数值同','全部提供误差字段同','三项效率全同'],audit),
  '最后四列是不同记录特征，不能彼此相加或据此减少实验次数。全部 24 配置均已审计。详细字段证据见 [repeat_value_audit.csv](../tables/09_robustness/repeat_value_audit.csv)。','',
  '### DROID-SLAM RGB-D Pool 局部核对','']
 pool=[r for r in repeat if r['configuration_id']=='DROID-SLAM::rgbd' and r['scene']=='pool' and r['subset']=='condition_labelled']
 pr=[]
 for r in pool:
  f=json.loads(r['fields_evidence_json'])
  equal=[k for k in ERROR_FIELDS if f[k]['all_retained_finite_numeric_identical']]
  txt=[k for k in ERROR_FIELDS if f[k]['finite_text_identical'] and f[k]['n_finite']==r['n_retained']]
  eff=', '.join(k+':'+f[k]['status'] for k in ('fps','runtime','memory'))
  pr.append([r['sequence_raw'],f"{r['n_finite_rmse']}/{r['n_retained']}",fmt(f['rmse']['finite_values'][0]) if f['rmse']['finite_values'] else '未定义',
    ','.join(txt),','.join(equal),eff,','.join(str(m['index']) for m in json.loads(r['members_json']))])
 lines +=[table(['序列','有限/保留','RMSE','文本相同误差字段','数值相同误差字段','效率字段','源索引'],pr),
  '以上特征只能定位需未来授权核实的局部来源问题；本轮没有判断是固定种子、确定性实现、复制还是重复读取，没有去重或加扰动。完整来源路径、SHA-256、索引、run_id 在审计表中。','',
  '## 共同条件支持与五种视图','',
  '路线键从 sequence_raw 尾部精确移去已确认的 _speed_level_altitude_level；原名称不改。对照固定配置、场景、路线及另一个条件，只取实际观察到的端点块并集。先核对每端序列／来源数量，不按 run_id 跨条件配对，不建立笛卡尔积。匹配只是名义分层，不能证明实际轨迹或随机化一致。',
  f"本快照共有 {len(blocks)} 个端点参照块；发现歧义块 {sum(b['ambiguous'] for b in blocks)} 个。",
  '',
  '- R：两端有保留记录；F：R 内两端各有有限 RMSE；C：F 内两端所有保留 RMSE 均有限。',
  '- V0：两端各自可用序列均值的平均之差；成员允许不同。V1：F 内块等权。V2：F 内场景内部块等权，再给可用场景等权。',
  '- V3：C 内按 V1 计算。V4：保持 F 和 V1 权重，仅把序列内部均值换为中位数。',
  '- 主差值为 V8−V2 或 H30−H10；表中保留来源单位与历史对齐限制，不添加 epsilon，不算变化百分比。',
  '- 数值有效比例只在 R 内计算；无记录端点列出但不加入分母。F/C 的结果不能代表未被观测到的有效结果。',
  '',
  '下表每行是配置内部的一个端点问题，没有跨方法排名。V1/V2/V3/V4 均保留实际成员、端点均值、场景／块权重；无法计算写未定义。',
  '']
 vr=[]
 for c in sorted({r['configuration_id'] for r in repeat}):
  for comp in COMPARISONS:
   v=[vs[c,comp,k] for k in ('V0','V1','V2','V3','V4')];one=v[1];cc=v[3]
   rr=next(r for r in estimates if r['configuration_id']==c and r['comparison']==comp and r['analysis_type']=='numeric_validity_R')
   changed=[k for k in ('V0','V2','V3','V4') if vs[c,comp,k]['direction_changed']]
   vr.append([c,'速度' if comp.startswith('speed') else '高度',f"{one['n_R']}/{one['n_F']}/{one['n_C']}",
    *[fmt(r['value']) for r in v],f"{rr['low_n_finite']}/{rr['low_n_retained']} → {rr['high_n_finite']}/{rr['high_n_retained']}",
    f"{cc['C_lost_blocks_from_F']}/{cc['C_lost_records_from_F']}/{len(json.loads(cc['C_lost_scenes_json']))}",','.join(changed) or '无'])
 lines+=[table(['配置','问题','R/F/C','V0','V1','V2','V3','V4','R有限/保留 低→高','C损失块/行/场景','相对V1方向变更'],vr)]
 altered=[r for r in views if r.get('direction_changed')]
 lines +=[f"相对 V1 方向改变的非基线视图共 {len(altered)} 个（判号的绝对容差 1e-12 仅是数值规则，不是实际等效阈值）。方向不变也可能幅度明显改变；数值、delta 和空集合原因均已保存。",
  '支持表保留未进入 F/C 的块与原因；[support_blocks.csv](../tables/09_robustness/support_blocks.csv) 中的 no_retained_records、all_nonfinite_rmse、partial_finite_rmse 分开记录。','',
  '### VGGT：不可识别端点先于可用子集结论','']
 vg=[b for b in blocks if b['configuration_id']=='VGGT-SLAM::mono' and not b['in_F']]
 lines +=[table(['问题','场景／路线','固定条件','低端状态','高端状态','F排除原因'],
  [[b['comparison'],b['scene']+'/'+b['route_id'],str(b['fixed_axis'])+'='+str(b['fixed_value']),b['low']['state'],b['high']['state'],b['F_exclusion_reason']] for b in vg]),
  'C 只说明当前保留 RMSE 全有限，不说明完整轨迹成功或更可靠。跨支持集数值改变可能体现缺失选择，不能据 F/C 的较小均值称整体改进。','',
  '## 场景组成与重复记录的敏感性','']
 loso=[r for r in estimates if r['analysis_type']=='leave_one_scene_out']
 lines +=[f"全部 24 配置 × 两个端点问题 × V1/V2 都已执行逐场景剔除，共 {len(loso)} 个试算；每次只从原 F 去掉该场景，不补入新块。方向改变 {sum(r['direction_changed'] is True for r in loso)} 个；不可计算 {sum(r['value'] is None for r in loso)} 个。",
  '完整 F 是基线；删场景结果只是当前组成敏感性，不可挑选为主结果，也不是新场景的泛化保证。DPVO 的各场景贡献、去 Pool 的变化和正负抵消已在结论及图 1 单独报告。',
  '']
 seq=[r for r in estimates if r['analysis_type']=='sequence_drop_one']
 focused=[r for r in estimates if r['analysis_type']=='focus_contrast_range']
 lines +=[f"逐序列检查保留 {sum(r['analysis_type']=='sequence_baseline' for r in estimates)} 个有条件实际序列：{sum(r['status']=='computed' for r in seq)} 个有限删一试算，{sum(r['status']=='not_applicable' for r in seq)} 个有限数不足的显式不适用项。每个试算保留原 n_retained、原 n_finite、原有限率和来源成员，另存 trial_n_used；不会改写 SR 分母。",
  f"ORB-SLAM2 road/building、ORB-SLAM3 road/building、DROID Pool 共 {len(focused)} 个固定端点／四角问题。四角量 I=(H30V8−H30V2)−(H10V8−H10V2)。均值、序列中位数、每次单独移去一个参与端点的有限记录全部保留。范围包含基线和这些变体，不是 95%CI、bootstrap 区间或真实效应范围。",
  '',
  table(['配置','场景','问题','基线','检查范围','变体可算/不可算','方向改变数'],
   [[r['configuration_id'],r['scene'],r['focus_problem'],
     fmt(next(x['value'] for x in estimates if x['analysis_type']=='focus_contrast_baseline' and x['configuration_id']==r['configuration_id'] and x['comparison']==r['comparison'])),
     f"[{fmt(r['range_min'])}, {fmt(r['range_max'])}]",f"{r['n_computed_variants']}/{r['n_unavailable_variants']}",r['n_direction_changes']] for r in focused]),
  '数值影响大不等于记录错误。两次有限记录的 mean=median 是数学结果，删一后剩单值的重复 SD 未定义；三次都高的 ORB-SLAM3 road H20,V4 背景单元同时保留，避免只挑一个高值解释全部情况。','',
  '## Hier-SLAM 完整轨迹：效率筛选代数分解','',
  '限 two_tokens；每项效率单独定义 A=该指标有限、B=A中RMSE有限、E=A\\B。整体差 B−A=n(E)/n(A)×[mean(B)−mean(E)]；每条 c_i=[同一个整体mean(B)−x_i]/同一个n(A)。不是对各格差值简单平均。',
  '']
 overall=[r for r in decomp if r['row_type']=='overall'];terms=[r for r in decomp if r['row_type']=='record']
 lines +=[table(['指标','A/B/E','mean A','mean B','mean E','B−A','贡献和','恒等式残差'],
 [[r['metric'],f"{r['n_A']}/{r['n_B']}/{r['n_E']}",fmt(r['mean_A']),fmt(r['mean_B']),fmt(r['mean_E']),fmt(r['overall_B_minus_A']),fmt(r['record_contribution_sum']),fmt(r['identity_residual'])] for r in overall]),
 table(['指标','源索引','场景/H/V','排除记录值','固定代数贡献','其余固定项之和'],
 [[r['metric'],r['source_record_index'],f"{r['scene']}/{r['altitude_m']}/{r['speed_mps']}",fmt(r['excluded_value']),fmt(r['contribution']),fmt(r['sum_other_fixed_terms'])] for r in terms]),
 '每个指标的 E 是从实际记录筛选得到。三项指标都关联同一来源行时，不当成三次独立实验。按 scene、altitude、speed、scene_altitude_speed 各自分组的贡献和均恢复整体差；不同 group_type 不能混加，record/group/overall 三类也不能混加。',
 '']
 groups=[r for r in decomp if r['row_type']=='group' and r['group_type'] in ('scene','speed')]
 lines +=[table(['指标','分组维度','分组','排除条数','贡献'],[[r['metric'],r['group_type'],r['group_label'],r['n_excluded_in_group'],fmt(r['contribution'])] for r in groups])]
 # Independent cell display from actual retained records: explicitly NOT additive global contributions.
 hr=[r for r in rows if r['configuration_id']=='hierslam::rgbd_whole' and r['condition_label_status']=='two_tokens']
 cellkeys=sorted({(r['scene'],r['altitude_m'],r['speed_mps']) for r in terms if r['metric']=='runtime'})
 cells=[]
 for scene,h,v in cellkeys:
  A=[r['runtime_value'] for r in hr if r['scene']==scene and r['altitude_m']==h and r['speed_mps']==v and r['runtime_is_finite']]
  B=[r['runtime_value'] for r in hr if r['scene']==scene and r['altitude_m']==h and r['speed_mps']==v and r['runtime_is_finite'] and r['rmse_is_finite']]
  ma,mb=describe(A)['mean'],describe(B)['mean']
  cells.append([scene,h,v,len(A),len(B),fmt(ma),fmt(mb),fmt(mb-ma if ma is not None and mb is not None else None)])
 lines +=['第 8 步受筛选影响的 runtime 单元在本轮逐次输入复算如下。它们是各格自己的 B−A，按当前实际受影响单元核对；不与上表全局 c_i 混用：','',
  table(['场景','高度','速度','A','B','mean A','mean B','格内B−A'],cells),
  'sum_other_fixed_terms 只描述移走一个既定代数项后剩余项的符号／幅度，不是在数据中删除一行后重算 A/B；不作因果归因。来源记录没有删改。','',
  '## 统计推断适用性','',
  table(['目标','当前可做','尚需依据／假设'],
   [['当前固定 benchmark 的保留记录描述','本轮确切成员、均值、支持集、删一／删场景、固定代数分解已经完成；不需要把它们包装成p值。','只描述已保留记录；现有单位、对齐历史、测量定义与评测范围限制继续有效。'],
    ['给定序列上的重复运行不确定性','可以报告实际有限重复值与样本SD；单值SD未定义；相同值SD=0有严格局限。','需要确认重复生成过程、随机性来源、独立性或依赖结构、保留机制；run_id编号本身不证明独立。'],
    ['当前条件的高度／速度效应','可在名义条件块上描述对比、异质性和敏感性。','因果／随机化解释另需采集一致性、实际路线一致性、分配机制和混杂控制；本轮没有这些证明。'],
    ['推广至新场景总体','本轮给出五个已有场景的异质性与剔除敏感性。','需明确目标场景总体、抽样/代表性与独立场景/路线的定义；五类场景不自动成为随机总体样本。根据设计选择合适分层/聚类推断，而非逐行bootstrap。'],
    ['未来正式假设检验与区间','可以另行制定与实际设计匹配的分析方案。','本轮问题来自同一批数据探索，需说明选择过程、多重性与目标估计量；如采用模型/重采样，需相应设计依据与可检查假设，必要时独立验证。']]),
  f'当前{len(rows)}条保留行、共享场景的名义端点块和同序列多个run_id均不能直接当成相互独立样本。实际观测单位是带来源键的一次保留指标行；实际重复结构见审计表，Hier 500帧与完整轨迹仍分开。未保留运行不算失败、不加入分母。',
  '重复来源、测量定义及路线一致性未知只限制相应局部解释，不阻止其他配置的确定性计算。也不意味着任何统计推断永远不可做；具体前提应在未来另行授权阶段核实，本轮没有启动底层调查。','',
  '## 测试、保护与运行记录','',
  '内存测试：','']+['- '+x for x in tests]
 lines +=['','真实数据与第 8 步独立结果对照：','',table(['检查','结果'],[[k,v] for k,v in checks.items()]),
  '',
  '所有估计保留状态和不可计算原因；总体视图、逐场景变体、逐序列不适用项和固定端点试算均未因无值被过滤掉。零与空值分开。数值核对使用 rtol=1e-12、atol=1e-10；精确重复值审计没有容差。',
  '11 项允许输入执行前后 SHA-256 一致；三个标准化输入已与第 8 步约定核对。没有访问 experiment_data、日志或其它仓库。本入口不执行源实验脚本；授权数据版本更新由调度入口逐阶段运行，旧版本由更新快照保留。',
  '默认已存在输出即拒绝；--overwrite 仅允许本轮列明的输出，拒绝符号链接、硬链接和范围外路径。不清空目录。绘图使用 Agg，缓存限定本工作区本轮创建的临时目录，退出清理。',
  '',
  '本会话普通命令执行遇到 mountinfo path is not absolute，使用工具提供的限定审批机制执行指定工作区操作；未关闭沙箱、改权限或扩大读写范围。图形生成不等于视觉验收，视觉验收与额外复核记录在完成检查段落。',
  '',
  '### 运行方式','',chr(96)*3+'bash',command,chr(96)*3,
  '首次运行省略 --overwrite；已有产物复跑需显式 --overwrite。--self-test 只执行本轮小样例和临时输出边界检查，不读取真实逐次输入。','',
  '### 产物','']
 for key,path in OUTPUTS.items():
  if key.endswith('.svg'):continue
  relative='../'+path if not path.startswith('reports/') else Path(path).name
  lines.append('- ['+Path(path).name+']('+relative+')')
 lines+=['','五张图各自只展示一个配置的问题；PNG 与 SVG 成对保存。图例中的范围和点不是置信区间，未计算值不放在零点。','',
  '### 完成检查','',
  '脚本已执行输入哈希和数值检查。PNG逐张打开、额外独立复算及历史文件保护验收在交付时追加；运行脚本本身不会声称已完成人工视觉检查。','']
 return '\n'.join(lines)



def independent_validation(raw,repeat,blocks,estimates,decomp):
 """Recompute with stdlib fmean/median/fsum, without analysis aggregation helpers."""
 import statistics
 original=list(csv.DictReader(io.StringIO(raw['records'].decode())))
 checked=0
 def eq(a,b):
  nonlocal checked
  checked+=1
  if a is None or b is None:assert a is None and b is None,(a,b)
  else:assert math.isclose(float(a),float(b),abs_tol=1e-10,rel_tol=1e-12),(a,b)
 def avg(v):return statistics.fmean(v) if v else None
 def med(v):return statistics.median(v) if v else None
 def sk(r):return (r['source_relative_path'],r['source_sha256'],int(r['source_record_index']))
 def mk(m):return (m['path'],m['sha256'],int(m['index']))
 def vals(rs,m='rmse'):return [float(r[m+'_value']) for r in rs if r[m+'_is_finite'].lower()=='true']
 def memberkeys(rs):return [sk(r) for r in rs]
 allseq=defaultdict(list);nominal=defaultdict(list);primary=[]
 for r in original:
  allseq[r['configuration_id'],r['sequence_raw']].append(r)
  if r['condition_label_status']=='two_tokens':
   primary.append(r);suffix='_'+r['speed_level']+'_'+r['altitude_level']
   assert r['sequence_raw'].endswith(suffix)
   nominal[(r['configuration_id'],r['scene'],r['sequence_raw'][:-len(suffix)],int(r['altitude_m']),int(r['speed_mps']))].append(r)
 assert len(repeat)==len(allseq)
 for r in repeat:
  rs=allseq[r['configuration_id'],r['sequence_raw']]
  eq(r['n_retained'],len(rs));eq(r['n_finite_rmse'],len(vals(rs)))
  assert [mk(m) for m in json.loads(r['members_json'])]==memberkeys(rs)
  fields=json.loads(r['fields_evidence_json'])
  for name,rawcol in RAW_FIELDS.items():
   f=fields[name];finite=[x for x in rs if x[name+'_state'].startswith('finite_')]
   texts=[x[rawcol] for x in finite]
   numbers=[float(x[name+'_value']) if name in METRICS else float(x[rawcol]) for x in finite]
   eq(f['n_finite'],len(finite));eq(f['n_distinct_finite_text'],len(set(texts)));eq(f['n_distinct_finite_numeric'],len(set(numbers)))
   assert f['finite_numeric_identical']==(len(numbers)>=2 and len(set(numbers))==1)
   assert f['finite_text_identical']==(len(texts)>=2 and len(set(texts))==1)
  eq(r['rmse_repeat_sd'],statistics.stdev(vals(rs)) if len(vals(rs))>=2 else None)
 # Rebuild union keys independently and require every observed endpoint to appear once.
 expected_keys=set()
 for (c,scene,route,h,v) in nominal:
  if v in (2,8):expected_keys.add((c,'speed8_minus2',scene,route,h))
  if h in (10,30):expected_keys.add((c,'altitude30_minus10',scene,route,v))
 assert expected_keys=={(b['configuration_id'],b['comparison'],b['scene'],b['route_id'],b['fixed_value']) for b in blocks}
 independent={}
 for b in blocks:
  sides={}
  for side,endpoint_number in [('low',b['low_condition']),('high',b['high_condition'])]:
   h=b['fixed_value'] if b['comparison']=='speed8_minus2' else endpoint_number
   v=endpoint_number if b['comparison']=='speed8_minus2' else b['fixed_value']
   rs=nominal.get((b['configuration_id'],b['scene'],b['route_id'],h,v),[])
   vv=vals(rs);e=b[side]
   eq(e['n_retained'],len(rs));eq(e['n_finite'],len(vv));eq(e['mean'],avg(vv));eq(e['median'],med(vv))
   assert [mk(m) for m in e['members']]==memberkeys(rs)
   sides[side]={'rs':rs,'v':vv,'mean':avg(vv),'median':med(vv)}
  a,z=sides['low'],sides['high'];R=bool(a['rs'] and z['rs']);F=R and bool(a['v'] and z['v'])
  C=F and len(a['rs'])==len(a['v']) and len(z['rs'])==len(z['v'])
  assert (b['in_R'],b['in_F'],b['in_C'])==(R,F,C)
  independent[b['block_id']]={**sides,'R':R,'F':F,'C':C,'scene':b['scene'],'config':b['configuration_id'],'comparison':b['comparison']}
 outputs={r['estimate_id']:r for r in estimates}
 for r in estimates:
  kind=r['analysis_type'];c=r['configuration_id'];comp=r['comparison']
  local={k:b for k,b in independent.items() if b['config']==c and b['comparison']==comp}
  if kind in ('support_view','leave_one_scene_out'):
   sides=[];view=r['view']
   for side in ('low','high'):
    if view=='V0':chosen={k:b for k,b in local.items() if b[side]['v']}
    else:chosen={k:b for k,b in local.items() if b['C' if view=='V3' else 'F'] and b['scene']!=r.get('removed_scene','')}
    byscene=defaultdict(list)
    for b in chosen.values():byscene[b['scene']].append(b[side]['median' if view=='V4' else 'mean'])
    value=avg([avg(v) for v in byscene.values()]) if view=='V2' else avg([v for vs in byscene.values() for v in vs])
    eq(r['endpoint_'+side],value);sides.append(value)
    eq(r[side+'_n_blocks'],len(chosen));eq(r[side+'_n_scenes'],len(byscene))
    eq(r[side+'_n_retained'],sum(len(b[side]['rs']) for b in chosen.values()))
    eq(r[side+'_n_finite'],sum(len(b[side]['v']) for b in chosen.values()))
    assert set(json.loads(r[side+'_block_ids_json']))==set(chosen)
    weights=json.loads(r[side+'_block_weights_json'])
    for k,b in chosen.items():
     eq(weights[k],1/(len(byscene)*len(byscene[b['scene']])) if view=='V2' else 1/len(chosen))
    for member in json.loads(r[side+'_members_json']):
     assert [mk(x) for x in member['members']]==memberkeys(chosen[member['block_id']][side]['rs'])
   eq(r['value'],sides[1]-sides[0] if all(x is not None for x in sides) else None)
   F=[b for b in local.values() if b['F']];lost=[b for b in F if not b['C']]
   eq(r['C_lost_blocks_from_F'],len(lost));eq(r['C_lost_records_from_F'],sum(len(b[s]['rs']) for b in lost for s in ('low','high')))
  elif kind=='numeric_validity_R':
   R=[b for b in local.values() if b['R']];fractions=[]
   for side in ('low','high'):
    nr=sum(len(b[side]['rs']) for b in R);nf=sum(len(b[side]['v']) for b in R)
    eq(r[side+'_n_retained'],nr);eq(r[side+'_n_finite'],nf);fractions.append(nf/nr if nr else None)
   eq(r['value'],100*(fractions[1]-fractions[0]) if R else None)
  elif kind=='scene_contribution':
   F=[b for b in local.values() if b['F']];scene=[b for b in F if b['scene']==r['scene']]
   weight=1/len(F) if r['view']=='V1' else 1/(len({b['scene'] for b in F})*len(scene))
   eq(r['value'],math.fsum((b['high']['mean']-b['low']['mean'])*weight for b in scene))
  elif kind.startswith('sequence_'):
   rs=allseq[c,r['sequence_raw']];finite=[x for x in rs if x['rmse_is_finite'].lower()=='true'];vv=vals(rs)
   eq(r['original_n_retained'],len(rs));eq(r['original_n_finite'],len(vv));eq(r['baseline_median'],med(vv))
   if kind=='sequence_baseline':eq(r['value'],avg(vv))
   elif kind=='sequence_drop_one':
    if len(vv)<2:assert r['status']=='not_applicable' and r['value'] is None
    else:
     removed=mk(json.loads(r['removed_record_json']));used=[x for x in finite if sk(x)!=removed];numbers=vals(used)
     assert len(used)==len(finite)-1 and [mk(x) for x in json.loads(r['trial_members_json'])]==memberkeys(used)
     eq(r['trial_n_used'],len(used));eq(r['value'],avg(numbers));eq(r['delta_from_baseline'],avg(numbers)-avg(vv))
     eq(r['trial_repeat_sd'],statistics.stdev(numbers) if len(numbers)>=2 else None)
   else:
    variants=[avg(vv[:i]+vv[i+1:]) for i in range(len(vv))] if len(vv)>=2 else []
    eq(r['range_min'],min(variants) if variants else None);eq(r['range_max'],max(variants) if variants else None)
  elif kind in ('focus_contrast_baseline','focus_contrast_median','focus_contrast_drop_one'):
   groups=[nominal.get((c,r['scene'],r['route_id'],h,v),[]) for h,v in json.loads(r['conditions_json'])]
   removed=mk(json.loads(r['removed_record_json'])) if r.get('removed_record_json') else None
   coefficients=json.loads(r['coefficients_json']);ee=json.loads(r['endpoints_json']);representatives=[]
   for rs,ep in zip(groups,ee):
    used=[x for x in rs if x['rmse_is_finite'].lower()=='true' and sk(x)!=removed]
    eq(ep['original_n_retained'],len(rs));eq(ep['original_n_finite'],len(vals(rs)));eq(ep['trial_n_used'],len(used))
    assert [mk(x) for x in ep['trial_members']]==memberkeys(used)
    representatives.append(med(vals(used)) if kind=='focus_contrast_median' else avg(vals(used)))
   value=math.fsum(a*x for a,x in zip(coefficients,representatives)) if all(x is not None for x in representatives) else None
   eq(r['value'],value)
   assert (r['status']=='computed')==(value is not None)
  elif kind=='focus_contrast_range':
   related=[outputs[i] for i in json.loads(r['variant_ids_json'])]+[outputs[r['baseline_id']]]
   values=[x['value'] for x in related if x['value'] is not None]
   eq(r['range_min'],min(values) if values else None);eq(r['range_max'],max(values) if values else None)
   eq(r['n_unavailable_variants'],sum(x['value'] is None for x in related[:-1]))
  else:raise AssertionError('Unchecked analysis type: '+kind)
  if r.get('baseline_id') and r.get('value') is not None:
   base=outputs[r['baseline_id']]
   if base['value'] is not None and kind!='scene_contribution':
    eq(r['baseline_value'],base['value']);eq(r['delta_from_baseline'],r['value']-base['value'])
 for metric in METRICS[1:]:
  hr=[r for r in primary if r['configuration_id']=='hierslam::rgbd_whole']
  A=[r for r in hr if r[metric+'_is_finite'].lower()=='true'];B=[r for r in A if r['rmse_is_finite'].lower()=='true'];E=[r for r in A if r['rmse_is_finite'].lower()!='true']
  a,b,e=avg(vals(A,metric)),avg(vals(B,metric)),avg(vals(E,metric))
  difference=b-a
  local=[r for r in decomp if r['metric']==metric]
  for r in local:
   eq(r['n_A'],len(A));eq(r['n_B'],len(B));eq(r['n_E'],len(E));eq(r['mean_A'],a);eq(r['mean_B'],b);eq(r['mean_E'],e);eq(r['overall_B_minus_A'],difference)
   assert [mk(x) for x in json.loads(r['E_members_json'])]==memberkeys(E)
   if r['row_type']=='record':
    row=next(x for x in E if sk(x)==mk(json.loads(r['record_json'])))
    eq(r['contribution'],(b-float(row[metric+'_value']))/len(A))
   elif r['row_type']=='overall':eq(r['record_contribution_sum'],difference);eq(r['identity_rhs'],len(E)/len(A)*(b-e))
   else:
    kk=json.loads(r['group_label']);members=[x for x in E if all(str(x[k])==str(v) for k,v in kk.items())]
    assert [mk(x) for x in json.loads(r['group_members_json'])]==memberkeys(members)
    eq(r['contribution'],math.fsum((b-float(x[metric+'_value']))/len(A) for x in members))
  for kind in ('scene','altitude','speed','scene_altitude_speed'):
   eq(math.fsum(r['contribution'] for r in local if r['row_type']=='group' and r['group_type']==kind),difference)
 return {'stdlib_independent_numeric_checks':checked,'all_estimate_types_recomputed':True,'source_members_and_exclusions_rechecked':True}


def main(argv=None):
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--overwrite',action='store_true',help='Only overwrite this stage reviewed allowlist')
 parser.add_argument('--self-test',action='store_true',help='In-memory examples and task-owned temporary boundary tests only')
 args=parser.parse_args(argv)
 tests=self_tests()
 if args.self_test:
  print(js({'self_tests':'passed','checks':tests}));return
 for path in OUTPUTS.values():check_output(W/path,args.overwrite)
 raw={k:read_input(k) for k in INPUTS}
 prior_spec=json.loads(raw['spec8'])
 for key in ('records','manifest','schema'):
  expected=prior_spec['inputs'][key]['sha256']
  if sha(raw[key])!=expected:raise ValueError('Input hash differs from step8: '+INPUTS[key])
 rows,sources,schema=load_records(raw)
 command='/home/yuan/anaconda3/bin/python3 -B '+str(W/'scripts/check_benchmark_robustness.py')+' --overwrite'
 # Save exploratory contract before descriptive checks or plots. Existing snapshots remain unchanged.
 write('spec',json.dumps(make_spec(raw,schema,command),ensure_ascii=False,indent=2)+'\n',args.overwrite)
 primary=[r for r in rows if r['condition_label_status']=='two_tokens']
 repeat=repeat_audit(rows);blocks=support_blocks(primary)
 estimates=all_views(blocks,sources)+sequence_sensitivity(primary,sources)+focus_sensitivity(primary,sources)
 decomp=efficiency_decomposition(primary,sources)
 checks=crosscheck_previous(primary,blocks,estimates,decomp,raw)
 checks.update(independent_validation(raw,repeat,blocks,estimates,decomp))
 prior=list(csv.DictReader(io.StringIO(raw['questions8'].decode())))
 assert {r['question_id'] for r in prior}=={'Q1','Q2','Q3','Q4','Q5'}
 claims=claim_assessment(prior,repeat,blocks,estimates,decomp)
 for key,values in [('repeat',repeat),('support',public_blocks(blocks)),('estimates',estimates),('efficiency',decomp),('claims',claims)]:
  write_csv(key,values,args.overwrite)
 draw_figures(estimates,decomp,rows,args.overwrite)
 for k,original in raw.items():
  if read_input(k)!=original:raise ValueError('Input changed during execution: '+INPUTS[k])
 checks.update(input_hashes_unchanged=True,configurations=len(sources),repeat_sequences=len(repeat),support_blocks=len(blocks),
               sensitivity_estimates=len(estimates),efficiency_rows=len(decomp),claims=len(claims))
 write('report',make_report(rows,repeat,blocks,estimates,decomp,claims,tests,checks,raw,command),args.overwrite)
 print(js({'status':'computed','checks':checks,'analysis_types':dict(Counter(r['analysis_type'] for r in estimates)),
  'claims':[{'id':r['question_id'],'labels':json.loads(r['labels_json']),'observation':r['current_observation']} for r in claims],
  'figures':list(FIGURES),'visual_review':'pending; not automatically inferred from savefig'}))
if __name__=='__main__':main()
