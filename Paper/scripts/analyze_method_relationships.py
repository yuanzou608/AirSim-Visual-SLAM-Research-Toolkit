#!/usr/bin/env python3
"""Step 10: sequence-pattern relationships, availability, and within-configuration tradeoffs."""
import argparse
from collections import Counter,defaultdict
import csv
import io
import itertools
import json
import math
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch
import numpy as np
from scipy.stats import rankdata
from build_analysis_dataset import csv_text,reject_links,decode_csv
from explore_benchmark import describe,parse_bool,unit_limit,SCENES,METRICS,sha,fmt
from check_benchmark_robustness import load_records,source_key,row_context,js

from version_support import workspace
W=workspace(Path('/home/yuan/SLAM/codex_review/benchmark_analysis'))
INPUTS={'records':'derived_data/06_standardized/run_records.csv',
 'manifest':'derived_data/06_standardized/source_manifest.csv','schema':'derived_data/06_standardized/schema.json',
 'spec9':'reports/09_robustness_spec.json','report9':'reports/09_robustness_analysis.md',
 'claims9':'reports/09_claim_assessment.csv','repeat9':'tables/09_robustness/repeat_value_audit.csv',
 'sequences7':'tables/07_eda/sequence_metrics.csv'}
OUTPUTS={'spec':'reports/10_relationship_spec.json','scope':'tables/10_relationships/comparison_scope.csv',
 'evidence':'tables/10_relationships/pair_sequence_evidence.csv','patterns':'tables/10_relationships/pairwise_patterns.csv',
 'availability':'tables/10_relationships/pairwise_availability.csv',
 'tradeoffs':'tables/10_relationships/within_configuration_tradeoffs.csv',
 'report':'reports/10_method_relationships.md','findings':'reports/10_findings_assessment.csv'}
FOCUS=[('DPVO::mono','DROID-SLAM::mono'),('ORB-SLAM2::mono','ORB-SLAM3::mono'),
 ('DROID-SLAM::rgbd','ORB-SLAM3::rgbd'),('VGGT-LONG::mono','VGGT-SLAM::mono'),
 ('MASt3R-SLAM::mono_calib','MASt3R-SLAM::mono_nocalib'),('hierslam::rgbd_500','hierslam::semantic_500')]
FOCUS=[tuple(sorted(p)) for p in FOCUS]
SPECIAL=('DROID-SLAM::rgbd','ElasticFusion::rgbd','SLAM3R::mono','VGGT-LONG::mono')
TRADEOFF_PLOTS=('DPVO::mono','ORB-SLAM3::rgbd','hierslam::rgbd_whole')
FIGURES={'01_focus_rank_positions':'Six user-prespecified pairs, ranks on pair-specific F; scene colors.',
 '02_focus_support_scene_rho':'Six prespecified pairs, F/C/median and within-scene ranks; fixed -1..1 color scale and n.',
 '03_focus_availability':'Six prespecified pairs: four availability categories on P; absent-on-U shown separately.',
 '04_within_configuration_rho':'All 24 configurations, own jointly finite run subsets for RMSE vs each efficiency; fixed lexical order.',
 '05_same_run_tradeoffs':'DPVO, ORB-SLAM3 RGB-D, Hier whole: FPS/runtime scatter of same-run-intersection sequence means; selected from prior coverage/repeat/efficiency questions, not by rho.'}
for name in FIGURES:
 for ext in ('png','svg'):OUTPUTS[name+'.'+ext]='figures/10_relationships/'+name+'.'+ext
STATES=('all_finite','partial_finite','all_nonfinite')
TOL=1e-10

def read_input(key):
 p=W/INPUTS[key];reject_links(p)
 with p.open('rb') as f:data=f.read(12*1024*1024+1)
 if len(data)>12*1024*1024:raise ValueError('Unexpected input size: '+str(p))
 return data
def check_output(path,overwrite=False):
 if path not in {W/x for x in OUTPUTS.values()}:raise ValueError('Outside step10 output allowlist')
 reject_links(path)
 if not path.resolve().is_relative_to(W.resolve()):raise ValueError('Outside workspace')
 if path.exists():
  if not overwrite:raise FileExistsError('Refusing overwrite: '+str(path))
  if not path.is_file() or path.stat().st_nlink!=1:raise ValueError('Nonregular/hardlinked output')
def write(key,data,overwrite):
 p=W/OUTPUTS[key];check_output(p,overwrite);p.parent.mkdir(parents=True,exist_ok=True);check_output(p,overwrite)
 with os.fdopen(os.open(p,os.O_WRONLY|os.O_CREAT|os.O_NOFOLLOW|(os.O_TRUNC if overwrite else os.O_EXCL),0o666),'wb') as f:
  f.write(data.encode() if isinstance(data,str) else data)
def write_csv(key,rows,overwrite):
 write(key,csv_text(rows,list(dict.fromkeys(k for r in rows for k in r))),overwrite)
def pid(a,b):return ' <> '.join(sorted((a,b)))
def numsign(x):return None if x is None else 'zero' if abs(x)<=1e-12 else 'positive' if x>0 else 'negative'
def state(n,f):return 'no_records' if not n else 'all_nonfinite' if not f else 'all_finite' if f==n else 'partial_finite'
def fraction(n,d):return n/d if d else None
def spearman(x,y):
 if len(x)!=len(y) or any(not math.isfinite(v) for v in x+y):raise ValueError('Spearman needs paired finite values')
 n=len(x);rx=rankdata(x,method='average').tolist();ry=rankdata(y,method='average').tolist()
 ux,uy=len(set(x)),len(set(y));reason='insufficient_sequences' if n<3 else 'constant_input' if ux==1 or uy==1 else ''
 rho=None
 if not reason:
  ax=np.asarray(rx)-(n+1)/2;by=np.asarray(ry)-(n+1)/2
  rho=float(np.dot(ax,by)/np.sqrt(np.dot(ax,ax)*np.dot(by,by)))
  rho=max(-1.0,min(1.0,rho))
 return {'rho':rho,'status':reason or 'computed','n_sequences':n,'n_unique_A':ux,'n_unique_B':uy,
  'n_tied_observations_A':sum(v for v in Counter(x).values() if v>1),
  'n_tied_observations_B':sum(v for v in Counter(y).values() if v>1),
  'constant_A':bool(n and ux==1),'constant_B':bool(n and uy==1),'rank_A':rx,'rank_B':ry,
  'relative_rank_A':[(r-1)/(n-1) for r in rx] if n>1 else [None]*n,
  'relative_rank_B':[(r-1)/(n-1) for r in ry] if n>1 else [None]*n}

def sequence_views(rows,audit):
 grouped=defaultdict(list)
 for r in rows:
  if r['condition_label_status']=='two_tokens':grouped[r['configuration_id'],r['sequence_raw']].append(r)
 result={}
 for key,rs in sorted(grouped.items()):
  first=rs[0];finite=[r for r in rs if r['rmse_is_finite']];values=[r['rmse_value'] for r in finite];d=describe(values);a=audit[key]
  paths={(r['source_relative_path'],r['source_sha256']) for r in rs}
  conds={(r['scene'],r['altitude_m'],r['speed_mps']) for r in rs}
  if len(paths)!=1 or len(conds)!=1:raise ValueError('Ambiguous configuration sequence: '+str(key))
  result[key]={'configuration_id':key[0],'sequence_raw':key[1],'scene':first['scene'],'altitude_m':first['altitude_m'],'speed_mps':first['speed_mps'],
   'n_retained':len(rs),'n_finite':len(finite),'mean':d['mean'],'median':d['median'],'state':state(len(rs),len(finite)),
   'run_ids':[r['run_id_raw'] for r in rs],'members':[row_context(r) for r in rs],'finite_members':[row_context(r) for r in finite],
   'finite_values':values,'rmse_repeat_sd':d['sample_sd'],'audit9_key':key[0]+'|'+key[1],
   'finite_rmse_identical':parse_bool(a['finite_rmse_identical']),
   'all_provided_error_fields_identical':parse_bool(a['all_provided_error_fields_identical']),
   'repeat_labels':json.loads(a['labels_json']),'repetition_provenance_unresolved':key[0] in SPECIAL,
   'repeat_independence_status':'not_verified','rows':rs}
 return result

def comparison_scope(sources,seq):
 result=[]
 for a,b in itertools.combinations(sorted(sources),2):
  A,B=sources[a],sources[b];sa,sb=A['evaluation_scope'],B['evaluation_scope'];ma,mb=A['modality_declared'],B['modality_declared']
  namesA={n for c,n in seq if c==a};namesB={n for c,n in seq if c==b}
  conflicts=[n for n in sorted(namesA&namesB) if any(seq[a,n][k]!=seq[b,n][k] for k in ('scene','altitude_m','speed_mps'))]
  if (sa=='500_frames')!=(sb=='500_frames'):
   status,reason='not_computed','known_500_frames_isolated_from_non500_or_unknown'
  elif sa!='unknown' and sb!='unknown' and sa!=sb:status,reason='not_computed','known_incompatible_evaluation_scopes'
  elif conflicts:status,reason='not_computed','same_sequence_conflicting_condition_metadata'
  elif sa==sb=='500_frames':status,reason='allowed','both_user_confirmed_500_frames; pattern_only'
  elif sa==sb=='whole_trajectory':status,reason='limited','both_user_confirmed_whole_trajectory; units_alignment_protocol_unresolved'
  else:status,reason='limited','same_name_numeric_patterns_only; scope_not_jointly_verified'
  modal='unknown_modality_relation' if 'unknown' in (ma,mb) else 'same_declared_modality' if ma==mb else 'cross_modality_exploration'
  result.append({'pair_id':pid(a,b),'configuration_A':a,'configuration_B':b,'processing_status':status,'reason':reason,
   'scope_A':sa,'scope_B':sb,'scope_evidence_A':A['evaluation_scope_evidence'],'scope_evidence_B':B['evaluation_scope_evidence'],
   'modality_A':ma,'modality_B':mb,'modality_relation':modal,'semantic_A':A['semantic_usage'],'semantic_B':B['semantic_usage'],
   'configuration_detail_A':A['configuration'],'configuration_detail_B':B['configuration'],
   'modality_evidence_A':A['modality_evidence'],'modality_evidence_B':B['modality_evidence'],
   'scope_unknown_equality_does_not_verify_compatibility':sa=='unknown' and sb=='unknown',
   'nominal_scope_match_user_confirmed':sa==sb and sa!='unknown' and A['evaluation_scope_evidence']==B['evaluation_scope_evidence']=='user_confirmed',
   'source_A':A['source_relative_path'],'source_B':B['source_relative_path'],
   'measurement_limit_A':unit_limit(A,'rmse'),'measurement_limit_B':unit_limit(B,'rmse'),
   'condition_conflicts_json':js(conflicts),'prespecified_focus':(a,b) in FOCUS,
   'special_repeat_flags_json':js([c for c in (a,b) if c in SPECIAL]),
   'interpretation':'same-name sequence labels only; no absolute performance, causal modality/calibration gain, family or fusion claim'})
 return result

def pair_evidence(scope,seq):
 result=[]
 for p in scope:
  if p['processing_status']=='not_computed':continue
  a,b=p['configuration_A'],p['configuration_B']
  U=sorted({n for c,n in seq if c in (a,b)})
  for name in U:
   A=seq.get((a,name));B=seq.get((b,name));first=A or B;P=A is not None and B is not None
   F=P and A['n_finite']>0 and B['n_finite']>0;C=F and A['state']==B['state']=='all_finite'
   r={'evidence_id':p['pair_id']+'|'+name,'pair_id':p['pair_id'],'configuration_A':a,'configuration_B':b,
      'sequence_raw':name,'scene':first['scene'],'altitude_m':first['altitude_m'],'speed_mps':first['speed_mps'],
      'in_U':True,'in_P':P,'in_F':bool(F),'in_C':bool(C),'scope_reference':p['pair_id'],
      'repetition_provenance_unresolved':a in SPECIAL or b in SPECIAL}
   for side,s in [('A',A),('B',B)]:
    r.update({side+'_present':s is not None,side+'_state':s['state'] if s else 'no_records',
      side+'_n_retained':s['n_retained'] if s else 0,side+'_n_finite':s['n_finite'] if s else 0,
      side+'_finite_fraction':fraction(s['n_finite'],s['n_retained']) if s else None,
      side+'_mean':s['mean'] if s else None,side+'_median':s['median'] if s else None,
      side+'_run_ids_json':js(s['run_ids']) if s else '[]',side+'_members_json':js(s['members']) if s else '[]',
      side+'_finite_members_json':js(s['finite_members']) if s else '[]',
      side+'_repeat_labels_json':js(s['repeat_labels']) if s else '[]',
      side+'_all_provided_error_fields_identical':s['all_provided_error_fields_identical'] if s else None,
      side+'_audit9_key':s['audit9_key'] if s else '',
      side+'_repeat_independence_status':'not_verified' if s else 'not_observed'})
   result.append(r)
 return result

def correlation_row(p,rows,view,support,representative='mean',scene='__all_scenes__',removed_scene=''):
 x=[r['A_'+representative] for r in rows];y=[r['B_'+representative] for r in rows];d=spearman(x,y)
 members=[{'evidence_id':r['evidence_id'],'sequence':r['sequence_raw'],'scene':r['scene'],
    'A_value':x[i],'B_value':y[i],'A_rank':d['rank_A'][i],'B_rank':d['rank_B'][i],
    'A_relative_rank':d['relative_rank_A'][i],'B_relative_rank':d['relative_rank_B'][i]} for i,r in enumerate(rows)]
 return {'row_id':p['pair_id']+'|'+view+'|'+scene+('|minus_'+removed_scene if removed_scene else ''),
  'row_type':'rank_correlation','pair_id':p['pair_id'],'configuration_A':p['configuration_A'],'configuration_B':p['configuration_B'],
  'view':view,'support_set':support,'representative':representative,'scene':scene,'removed_scene':removed_scene,
  **{k:v for k,v in d.items() if k not in ('rank_A','rank_B','relative_rank_A','relative_rank_B')},
  'n_scenes':len({r['scene'] for r in rows}),'members_json':js(members),'member_evidence_ids_json':js([r['evidence_id'] for r in rows]),
  **{s+'_'+k:sum(r[s+'_'+k] for r in rows) for s in ('A','B') for k in ('n_retained','n_finite')},
  'main_text_support':len(rows)>=10 and len({r['scene'] for r in rows})>=3,
  'scope_reference':p['pair_id'],'scope_status':p['processing_status'],
  'measurement_limit_A':p['measurement_limit_A'],'measurement_limit_B':p['measurement_limit_B'],
  'special_repeat_flags_json':p['special_repeat_flags_json'],
  'interpretation':'sequence-equal descriptive Spearman; ranks recomputed on this exact set; no p value or interval'}

def relative_high_row(p,F,baseline):
 x=[r['A_mean'] for r in F];y=[r['B_mean'] for r in F]
 qa=describe(x)['q75'];qb=describe(y)['q75']
 ta={r['sequence_raw'] for r in F if qa is not None and r['A_mean']>qa}
 tb={r['sequence_raw'] for r in F if qb is not None and r['B_mean']>qb};inter=ta&tb;union=ta|tb
 rank=json.loads(baseline['members_json'])
 lookup={r['sequence_raw']:r for r in F}
 def detail(m):
  r=lookup[m['sequence']]
  return {**m,'altitude_m':r['altitude_m'],'speed_mps':r['speed_mps'],
   'A_finite_retained':[r['A_n_finite'],r['A_n_retained']],'B_finite_retained':[r['B_n_finite'],r['B_n_retained']],
   'A_members':json.loads(r['A_members_json']),'B_members':json.loads(r['B_members_json']),
   'relative_rank_gap_A_minus_B':m['A_relative_rank']-m['B_relative_rank'] if m['A_relative_rank'] is not None else None}
 common=sorted([m for m in rank if m['sequence'] in inter],key=lambda m:(-min(m['A_relative_rank'],m['B_relative_rank']),m['sequence']))
 gaps=sorted([m for m in rank if m['A_relative_rank'] is not None],key=lambda m:(-abs(m['A_relative_rank']-m['B_relative_rank']),m['sequence']))
 return {'row_id':p['pair_id']+'|relative_high_F_mean','row_type':'relative_high_overlap','pair_id':p['pair_id'],
  'configuration_A':p['configuration_A'],'configuration_B':p['configuration_B'],'view':'relative_high_F_mean','support_set':'F','representative':'mean',
  'scene':'__all_scenes__','n_sequences':len(F),'n_scenes':baseline['n_scenes'],'q75_A':qa,'q75_B':qb,
  'n_T_A':len(ta),'n_T_B':len(tb),'n_intersection':len(inter),'n_union':len(union),
  'jaccard':fraction(len(inter),len(union)),'status':'computed' if union else 'empty_high_error_union',
  'T_A_json':js(sorted(ta)),'T_B_json':js(sorted(tb)),'intersection_json':js(sorted(inter)),'union_json':js(sorted(union)),
  'members_json':baseline['members_json'],'member_evidence_ids_json':baseline['member_evidence_ids_json'],
  'common_high_cases_json':js([detail(m) for m in common[:3]]) if p['prespecified_focus'] else '[]',
  'rank_gap_cases_json':js([detail(m) for m in gaps[:3]]) if p['prespecified_focus'] else '[]',
  'scope_reference':p['pair_id'],'special_repeat_flags_json':p['special_repeat_flags_json'],
  'interpretation':'strictly > pair-F linear q75; relative difficulty within own configuration only; not a failure or substitution claim'}

def all_pair_patterns(scope,evidence):
 grouped=defaultdict(list)
 for e in evidence:grouped[e['pair_id']].append(e)
 result=[]
 for p in scope:
  if p['processing_status']=='not_computed':continue
  U=grouped[p['pair_id']];P=[r for r in U if r['in_P']];F=[r for r in U if r['in_F']];C=[r for r in U if r['in_C']]
  base=correlation_row(p,F,'F_mean','F');base.update({k+'_members_json':js([r['sequence_raw'] for r in rr]) for k,rr in [('U',U),('P',P),('F',F),('C',C)]})
  base.update(n_U=len(U),n_P=len(P),n_F=len(F),n_C=len(C))
  variants=[base,correlation_row(p,C,'C_mean','C'),correlation_row(p,F,'F_median','F','median')]
  # Include all observed scenes on P, even when F has no usable sequence in that scene.
  scenes=sorted({r['scene'] for r in U})
  variants += [correlation_row(p,[r for r in F if r['scene']==s],'scene_F_mean','F','mean',s) for s in scenes]
  if p['prespecified_focus']:
   variants += [correlation_row(p,[r for r in F if r['scene']!=s],'leave_one_scene_out_F_mean','F','mean',removed_scene=s) for s in sorted({r['scene'] for r in F})]
  for r in variants:
   r.update(baseline_id=base['row_id'],baseline_rho=base['rho'],
    delta_from_baseline=r['rho']-base['rho'] if r['rho'] is not None and base['rho'] is not None else None,
    direction_changed=numsign(r['rho'])!=numsign(base['rho']) if r['rho'] is not None and base['rho'] is not None else None)
   result.append(r)
  result.append(relative_high_row(p,F,base))
 return result

def availability_rows(scope,evidence):
 grouped=defaultdict(list)
 for e in evidence:grouped[e['pair_id']].append(e)
 result=[]
 for p in scope:
  if p['processing_status']=='not_computed':continue
  U=grouped[p['pair_id']];P=[r for r in U if r['in_P']]
  categories={'both_finite':[],'only_A_finite':[],'only_B_finite':[],'neither_finite':[]}
  cross={a+'|'+b:[] for a in STATES for b in STATES}
  for r in P:
   a,b=r['A_n_finite']>0,r['B_n_finite']>0
   key='both_finite' if a and b else 'only_A_finite' if a else 'only_B_finite' if b else 'neither_finite'
   categories[key].append(r['evidence_id']);cross[r['A_state']+'|'+r['B_state']].append(r['evidence_id'])
  faila={r['sequence_raw'] for r in P if not r['A_n_finite']};failb={r['sequence_raw'] for r in P if not r['B_n_finite']}
  r={'pair_id':p['pair_id'],'configuration_A':p['configuration_A'],'configuration_B':p['configuration_B'],'n_U':len(U),'n_P':len(P),
    'P_members_json':js([r['sequence_raw'] for r in P]),'cross_counts_json':js({k:len(v) for k,v in cross.items()}),'cross_members_json':js(cross),
    'A_absent_on_U_json':js([r['sequence_raw'] for r in U if not r['A_present']]),
    'B_absent_on_U_json':js([r['sequence_raw'] for r in U if not r['B_present']]),
    'all_nonfinite_A_json':js(sorted(faila)),'all_nonfinite_B_json':js(sorted(failb)),
    'all_nonfinite_intersection_json':js(sorted(faila&failb)),'all_nonfinite_union_json':js(sorted(faila|failb)),
    'all_nonfinite_jaccard':fraction(len(faila&failb),len(faila|failb)),
    'all_nonfinite_jaccard_status':'computed' if faila|failb else 'both_have_no_all_nonfinite_sequence_on_P',
    'scope_reference':p['pair_id'],'special_repeat_flags_json':p['special_repeat_flags_json'],
    'interpretation':'record-level numeric availability clues, not full-trajectory success, fair reliability or verified switching gain'}
  for k,v in categories.items():r.update({k+'_n':len(v),k+'_fraction_P':fraction(len(v),len(P)),k+'_members_json':js(v)})
  for side in ('A','B'):
   nr=sum(e[side+'_n_retained'] for e in P);nf=sum(e[side+'_n_finite'] for e in P)
   r.update({side+'_n_retained_P':nr,side+'_n_finite_P':nf,side+'_run_finite_fraction_P':fraction(nf,nr),
    side+'_any_finite_sequences_P':sum(e[side+'_n_finite']>0 for e in P),
    side+'_retained_run_count_distribution_json':js(Counter(e[side+'_n_retained'] for e in P))})
  assert sum(len(v) for v in cross.values())==sum(len(v) for v in categories.values())==len(P)
  result.append(r)
 return result

def tradeoff_rows(seq,sources):
 result=[]
 for (c,name),s in seq.items():
  for metric in METRICS[1:]:
   rs=s['rows'];joint=[r for r in rs if r['rmse_is_finite'] and r[metric+'_is_finite']]
   x=[r['rmse_value'] for r in joint];y=[r[metric+'_value'] for r in joint]
   ne=sum(r[metric+'_is_finite'] for r in rs)
   result.append({'row_id':c+'|'+metric+'|sequence|'+name,'row_type':'sequence_joint_means','configuration_id':c,'efficiency_metric':metric,
    'sequence_raw':name,'scene':s['scene'],'altitude_m':s['altitude_m'],'speed_mps':s['speed_mps'],
    'n_retained':len(rs),'n_finite_rmse':s['n_finite'],'n_finite_efficiency':ne,'n_joint_finite':len(joint),
    'rmse_joint_mean':describe(x)['mean'],'efficiency_joint_mean':describe(y)['mean'],
    'retained_members_json':js(s['members']),'joint_members_json':js([row_context(r) for r in joint]),
    'status':'computed' if joint else 'no_joint_finite_runs',
    'reason':'' if joint else 'no_finite_rmse' if not s['n_finite'] else 'no_finite_efficiency' if not ne else 'disjoint_finite_run_sets',
    'rmse_limit':unit_limit(sources[c],'rmse'),'efficiency_limit':unit_limit(sources[c],metric),
    'evaluation_scope':sources[c]['evaluation_scope'],'repetition_provenance_unresolved':c in SPECIAL,
    'repeat_independence_status':'not_verified','audit9_key':s['audit9_key'],
    'interpretation':'both means use exactly the same retained-run intersection; no inferred frame count or causal tradeoff'})
 sequence_rows=list(result)
 for c,metric in itertools.product(sorted(sources),METRICS[1:]):
  allseq=[r for r in sequence_rows if r['configuration_id']==c and r['efficiency_metric']==metric]
  for scene in ('__all_scenes__',*SCENES):
   observed=[r for r in allseq if scene=='__all_scenes__' or r['scene']==scene];used=[r for r in observed if r['n_joint_finite']]
   d=spearman([r['rmse_joint_mean'] for r in used],[r['efficiency_joint_mean'] for r in used])
   result.append({'row_id':c+'|'+metric+'|correlation|'+scene,'row_type':'rank_correlation','configuration_id':c,'efficiency_metric':metric,
    'scene':scene,**{k:v for k,v in d.items() if k not in ('rank_A','rank_B','relative_rank_A','relative_rank_B')},
    'n_observed_sequences':len(observed),'n_scenes':len({r['scene'] for r in used}),
    'n_retained':sum(r['n_retained'] for r in observed),'n_finite_rmse':sum(r['n_finite_rmse'] for r in observed),
    'n_finite_efficiency':sum(r['n_finite_efficiency'] for r in observed),'n_joint_finite':sum(r['n_joint_finite'] for r in observed),
    'used_sequence_row_ids_json':js([r['row_id'] for r in used]),'unavailable_sequence_row_ids_json':js([r['row_id'] for r in observed if not r['n_joint_finite']]),
    'members_json':js([{'sequence':r['sequence_raw'],'row_id':r['row_id'],'scene':r['scene'],'rmse_mean':r['rmse_joint_mean'],'efficiency_mean':r['efficiency_joint_mean'],
      'rmse_rank':d['rank_A'][i],'efficiency_rank':d['rank_B'][i]} for i,r in enumerate(used)]),
    'main_text_support':len(used)>=10 and len({r['scene'] for r in used})>=3,
    'rmse_limit':unit_limit(sources[c],'rmse'),'efficiency_limit':unit_limit(sources[c],metric),
    'evaluation_scope':sources[c]['evaluation_scope'],'repetition_provenance_unresolved':c in SPECIAL,
    'interpretation':'sequence-equal within-configuration rank association; raw metric direction unchanged; constant input undefined'})
 return result

def make_spec(raw,scope):
 return {'stage':10,'generated_by':'scripts/analyze_method_relationships.py','script_sha256':sha(Path(__file__).read_bytes()),
  'protocol_wording_template':{'path':'scripts/review_all_configurations_narrative.py','sha256':sha(Path(__file__).with_name('review_all_configurations_narrative.py').read_bytes())},
  'inputs':{k:{'path':INPUTS[k],'sha256':sha(v),'role':'only_performance_input' if k=='records' else 'context_or_crosscheck'} for k,v in raw.items()},
  'input_gate':'records/manifest/schema match stage9 inputs; changed input stops calculations, no automatic rebuild',
  'subset':'condition_label_status == two_tokens','configurations':24,'unordered_pairs':len(scope),'self_pairs':False,
  'comparison_scope_rules':['500_frames can only compare to 500_frames','other known incompatible scopes not computed',
   'whole_trajectory with whole_trajectory: nominal scope confirmed, still limited by unresolved units/alignment/measurement protocols',
   'unknown with unknown or non500 known scope: same-name numeric patterns only, no verified scope equality',
   'conflicting same-sequence condition metadata blocks pair; preserve reason','cross-modality allowed only as descriptive exploration; unknown declarations kept unknown'],
  'scope_counts':dict(Counter(r['processing_status'] for r in scope)),
  'matching':'exact sequence_raw equality; metadata conflict check; no run_id pairing, Cartesian replicate expansion, imputation or global dropna',
  'representative':'mean of finite retained RMSE per configuration x sequence; median only on unchanged F sensitivity',
  'sets':{'U':'actual observed sequence union','P':'retained records on both sides','F':'P with >=1 finite RMSE per side','C':'F with all retained RMSE finite on both sides'},
  'rho':'Spearman = Pearson of within-current-set average ranks; ranks recomputed for each support/scene/omission; n<3 insufficient_sequences; constant input undefined',
  'relative_rank_position':'(average_rank-1)/(n-1), n>=2; descriptive within-current-set position',
  'minimum_main_text_support':{'n_sequences':10,'n_scenes':3,'meaning':'reporting priority, not statistical sufficiency'},
  'pair_views':['F_mean','C_mean','F_median','scene_F_mean on all observed scenes, including unavailable','focused LOSO on fixed original F'],
  'high_error':{'threshold':'strictly > q75 on same pair F, linear interpolation as stage7','empty_union':'undefined Jaccard','no_fixed_25_percent_count':True,
   'common_cases':'up to3 for each focus pair: descending min(A relative rank,B relative rank), sequence lexical tie break',
   'gap_cases':'up to3 for each focus pair: descending absolute relative-rank gap, sequence lexical tie break'},
  'availability':'3x3 all_finite/partial_finite/all_nonfinite and four any-finite categories on P; absent-on-U listed outside P denominator; run finite fractions separate; empty all-nonfinite union undefined',
  'within_configuration':'each sequence x efficiency: both means on same jointly finite run intersection; overall and scene Spearman; missing-joint sequences explicit',
  'repeat_flags':{'special_configurations':SPECIAL,'source':'stage9 repeat_value_audit; each has48 sequences with within-sequence equal error repeats, not equality across sequences/algorithms',
   'independence':'not verified for any configuration; special four carry repetition_provenance_unresolved; no dedup/no perturbation'},
  'prespecified_focus_pairs':FOCUS,'figures':FIGURES,'tradeoff_scatter_configs':TRADEOFF_PLOTS,
  'matrix_order':'lexical configuration/prespecified focus order; no clustering; color -1 to1; unavailable states distinct',
  'checks':{'rtol':1e-12,'atol':TOL,'near_zero_direction_atol':1e-12,'p_values':False,'confidence_intervals':False},
  'outputs':list(OUTPUTS.values()),'limits':['exploratory retained-data relationships, no causal interpretation','no absolute ranking, winner, cross-method Pareto, family inference or proven fusion gain',
    'sequence labels do not verify actual inputs/trajectories/protocol equality','nominal configuration scopes user-confirmed; units/timing/memory types/history and per-run completion remain unresolved',
    'source experiment directories never accessed','prior data version retained in update backup during an authorized rebuild','stop after stage10']}


def self_tests():
 checks=[]
 def source(scope='unknown'):
  return {'evaluation_scope':scope,'modality_declared':'mono','evaluation_scope_evidence':'fixture',
   'semantic_usage':'unknown','modality_evidence':'fixture','configuration':'mono',
   'source_relative_path':'fixture.csv','rmse_unit_status':'fixture','alignment_status':'fixture',
   'efficiency_protocol_json':js({k:'fixture' for k in ('fps_unit_status','runtime_unit_status','memory_conversion_and_kind','evidence_status')})}
 def rec(c,name,index,rmse,eff=5,scene='road'):
  return {'configuration_id':c,'sequence_raw':name,'condition_label_status':'two_tokens','scene':scene,'altitude_m':10,'speed_mps':2,
   'run_id_raw':str(index),'source_record_index':index,'source_relative_path':c+'.csv','source_sha256':'fixture',
   'rmse_value':rmse,'rmse_is_finite':rmse is not None,
   **{m+'_value':eff for m in METRICS[1:]},**{m+'_is_finite':eff is not None for m in METRICS[1:]}}
 def seqs(rows):
  audit={(r['configuration_id'],r['sequence_raw']):{'finite_rmse_identical':'False','all_provided_error_fields_identical':'False','labels_json':'[]'} for r in rows}
  return sequence_views(rows,audit)
 rows=[rec('A','same',1,1),rec('A','same',2,3),rec('B','same',1,2),rec('B','same',2,4),rec('B','same',3,6)]
 ss=seqs(rows);scope=comparison_scope({'A':source(),'B':source()},ss);ev=pair_evidence(scope,ss)
 assert len(ev)==1 and (ev[0]['A_n_retained'],ev[0]['B_n_retained'])==(2,3)
 assert ev[0]['A_mean']==2 and ev[0]['B_mean']==4
 assert comparison_scope({'A':source('500_frames'),'B':source()},ss)[0]['processing_status']=='not_computed'
 assert comparison_scope({'A':source('500_frames'),'B':source('500_frames')},ss)[0]['processing_status']=='allowed'
 checks.append('exact sequence matching uses one point, not 2x3 run pairs; 500-frame scope isolated')
 d=spearman([1,1,3],[1,2,3]);assert d['rank_A']==[1.5,1.5,3] and math.isclose(d['rho'],math.sqrt(3)/2)
 assert spearman([1,1,1],[1,2,3])['status']=='constant_input'
 assert spearman([1,2],[2,1])['rho'] is None
 assert spearman([],[])['status']=='insufficient_sequences'
 x=[1,2,4,8];y=[4,2,1,8]
 assert math.isclose(spearman(x,y)['rho'],spearman([v**3 for v in x],[math.exp(v) for v in y])['rho'])
 assert [spearman([1,2,3,4],[4,1,2,3])['rank_B'][i] for i in (0,2,3)]!=spearman([1,3,4],[4,2,3])['rank_B']
 assert spearman([1,2,3,4],[4,1,2,3])['rho']!=spearman([2,3,4],[1,2,3])['rho']
 checks.append('average tied ranks, constant/insufficient status, monotone scale invariance, reranking after subset changes')
 rows=[rec('A','both',1,1),rec('B','both',1,2),
  rec('A','allNA',2,None),rec('B','allNA',2,2),
  rec('A','absentB',3,3),rec('A','partial',4,1),rec('A','partial',5,None),rec('B','partial',3,None)]
 ss=seqs(rows);scope=comparison_scope({'A':source(),'B':source()},ss);ev=pair_evidence(scope,ss)
 av=availability_rows(scope,ev)[0]
 assert av['n_U']==4 and av['n_P']==3 and av['only_A_finite_n']==av['only_B_finite_n']==av['both_finite_n']==1
 assert sum(json.loads(av['cross_counts_json']).values())==3
 assert next(e for e in ev if e['sequence_raw']=='allNA')['A_mean'] is None
 assert json.loads(av['B_absent_on_U_json'])==['absentB']
 assert parse_bool('False') is False and parse_bool('True') is True
 checks.append('no-record vs all-nonfinite vs partial kept separate; 3x3 totals restore P; False parsed strictly')
 rows=[rec(c,str(i),i,1) for c in ('A','B') for i in range(3)]
 ss=seqs(rows);scope=comparison_scope({'A':source(),'B':source()},ss);ev=pair_evidence(scope,ss)
 pats=all_pair_patterns(scope,ev);high=next(r for r in pats if r['row_type']=='relative_high_overlap')
 assert high['jaccard'] is None and high['n_union']==0
 av=availability_rows(scope,ev)[0];assert av['all_nonfinite_jaccard'] is None
 checks.append('strict > q75 and empty high-error/all-nonfinite unions remain undefined')
 rows=[rec('A','s1',1,1,10),rec('A','s1',2,9,None),rec('A','s1',3,None,100),
       rec('A','s2',4,2,None),rec('A','s2',5,None,50)]
 tr=tradeoff_rows(seqs(rows),{'A':source()});one=next(r for r in tr if r['row_type']=='sequence_joint_means' and r['sequence_raw']=='s1' and r['efficiency_metric']=='fps')
 assert one['rmse_joint_mean']==1 and one['efficiency_joint_mean']==10 and one['n_joint_finite']==1
 two=next(r for r in tr if r['row_type']=='sequence_joint_means' and r['sequence_raw']=='s2' and r['efficiency_metric']=='fps')
 assert two['rmse_joint_mean'] is None and two['reason']=='disjoint_finite_run_sets'
 checks.append('RMSE and efficiency use exactly same finite-run intersection; disjoint finite sets undefined')
 reject_links(W/'reports')
 with tempfile.TemporaryDirectory(prefix='.10_guard_',dir=W/'reports') as temp:
  root=Path(temp);original=root/'input.txt';original.write_text('original')
  with patch.object(sys.modules[__name__],'W',root),patch.dict(OUTPUTS,{'x':'output.txt'},clear=True):
   write('x','first',False)
   try:write('x','bad',False);raise AssertionError('overwrite accepted')
   except FileExistsError:pass
   write('x','second',True)
   try:check_output(original,True);raise AssertionError('outside allowed')
   except ValueError:pass
   (root/'output.txt').unlink();(root/'output.txt').symlink_to(original)
   try:write('x','bad',True);raise AssertionError('symlink accepted')
   except ValueError:pass
   (root/'output.txt').unlink();os.link(original,root/'output.txt')
   try:write('x','bad',True);raise AssertionError('hardlink accepted')
   except ValueError:pass
   assert original.read_text()=='original'
 checks.append('allowlisted output boundary, no default overwrite, no symlink/hardlink following, input unchanged')
 return checks

def validate(rows,sources,seq,audit,scope,evidence,patterns,availability,tradeoffs,raw):
 """Crosschecks against old snapshots and independent stdlib rank/mean calculations."""
 import statistics
 nchecks=0
 def eq(a,b):
  nonlocal nchecks
  nchecks+=1
  if a is None or b is None:assert a is None and b is None,(a,b)
  else:assert math.isclose(float(a),float(b),rel_tol=1e-12,abs_tol=TOL),(a,b)
 def simple_ranks(x):return [1+sum(y<v for y in x)+(sum(y==v for y in x)-1)/2 for v in x]
 def independent_rho(x,y):
  if len(x)<3:return None,'insufficient_sequences'
  if len(set(x))<2 or len(set(y))<2:return None,'constant_input'
  rx,ry=simple_ranks(x),simple_ranks(y)
  return statistics.correlation(rx,ry),'computed'
 # Raw standardized numeric view, independently parsed. No source CSV access.
 original=list(csv.DictReader(io.StringIO(raw['records'].decode())))
 groups=defaultdict(list)
 for r in original:
  if r['condition_label_status']=='two_tokens':groups[r['configuration_id'],r['sequence_raw']].append(r)
 def vals(rs,metric):return [float(r[metric+'_value']) for r in rs if r[metric+'_is_finite']=='True']
 for key,s in seq.items():
  rs=groups[key];v=vals(rs,'rmse');a=audit[key]
  eq(s['mean'],statistics.fmean(v) if v else None);eq(s['median'],statistics.median(v) if v else None)
  eq(s['n_retained'],int(a['n_retained']));eq(s['n_finite'],int(a['n_finite_rmse']))
  assert [r['source_record_index'] for r in rs]==[str(m['index']) for m in s['members']]
  assert json.loads(a['members_json'])==s['members']
  eq(s['rmse_repeat_sd'],float(a['rmse_repeat_sd']) if a['rmse_repeat_sd'] else None)
  assert v==json.loads(a['fields_evidence_json'])['rmse']['finite_values']
 old7=[r for r in csv.DictReader(io.StringIO(raw['sequences7'].decode())) if r['metric']=='rmse' and r['subset']=='condition_labelled']
 assert len(old7)==len(seq)
 for r in old7:
  s=seq[r['configuration_id'],r['sequence_raw']]
  eq(s['mean'],float(r['mean']) if r['mean'] else None);eq(s['median'],float(r['median']) if r['median'] else None)
  assert [m['index'] for m in s['members']]==json.loads(r['source_record_indices_json'])
 for c in SPECIAL:
  aa=[a for (cc,name),a in audit.items() if cc==c]
  assert len(aa)==48 and all(parse_bool(a['finite_rmse_identical']) and parse_bool(a['all_provided_error_fields_identical']) for a in aa)
 # Scope covers each unordered pair exactly once, and every config is represented.
 assert len(scope)==len(sources)*(len(sources)-1)//2 and len({r['pair_id'] for r in scope})==len(scope)
 assert all(r['configuration_A']<r['configuration_B'] for r in scope)
 assert {r[k] for r in scope for k in ('configuration_A','configuration_B')}==set(sources)
 grouped=defaultdict(list)
 for e in evidence:
  grouped[e['pair_id']].append(e)
  a,b,name=e['configuration_A'],e['configuration_B'],e['sequence_raw']
  A=groups.get((a,name),[]);B=groups.get((b,name),[])
  assert e['in_P']==bool(A and B) and e['in_F']==bool(A and B and vals(A,'rmse') and vals(B,'rmse'))
  assert e['in_C']==bool(e['in_F'] and len(A)==len(vals(A,'rmse')) and len(B)==len(vals(B,'rmse')))
  for side,rs in [('A',A),('B',B)]:
   eq(e[side+'_n_retained'],len(rs));eq(e[side+'_n_finite'],len(vals(rs,'rmse')))
   eq(e[side+'_mean'],statistics.fmean(vals(rs,'rmse')) if vals(rs,'rmse') else None)
   eq(e[side+'_median'],statistics.median(vals(rs,'rmse')) if vals(rs,'rmse') else None)
 for p in scope:
  ev=grouped[p['pair_id']]
  if p['processing_status']=='not_computed':assert not ev;continue
  a,b=p['configuration_A'],p['configuration_B']
  names={n for c,n in groups if c in (a,b)}
  assert len(ev)==len(names)==len({e['evidence_id'] for e in ev})
  assert {e['sequence_raw'] for e in ev}==names
 for r in patterns:
  ev=grouped[r['pair_id']]
  chosen=[e for e in ev if e['in_'+r['support_set']]]
  if r['view']=='scene_F_mean':chosen=[e for e in chosen if e['scene']==r['scene']]
  elif r['view']=='leave_one_scene_out_F_mean':chosen=[e for e in chosen if e['scene']!=r['removed_scene']]
  rep=r['representative'];x=[];y=[]
  for e in chosen:
   for side,arr in [('A',x),('B',y)]:
    v=vals(groups[e['configuration_'+side],e['sequence_raw']],'rmse')
    arr.append(statistics.fmean(v) if rep=='mean' else statistics.median(v))
  assert json.loads(r['member_evidence_ids_json'])==[e['evidence_id'] for e in chosen]
  if r['row_type']=='rank_correlation':
   expected,reason=independent_rho(x,y);eq(r['rho'],expected);assert r['status']==reason
   reversed_rho,_=independent_rho(y,x);eq(r['rho'],reversed_rho)
   mm=json.loads(r['members_json'])
   for i,m in enumerate(mm):
    eq(m['A_value'],x[i]);eq(m['B_value'],y[i]);eq(m['A_rank'],simple_ranks(x)[i]);eq(m['B_rank'],simple_ranks(y)[i])
   eq(r['n_sequences'],len(chosen))
   for side in ('A','B'):
    eq(r[side+'_n_retained'],sum(len(groups[e['configuration_'+side],e['sequence_raw']]) for e in chosen))
  else:
   def q75(v):
    if not v:return None
    z=sorted(v);at=(len(z)-1)*.75;lo=int(at);hi=math.ceil(at);return z[lo]+(at-lo)*(z[hi]-z[lo])
   qa,qb=q75(x),q75(y);eq(r['q75_A'],qa);eq(r['q75_B'],qb)
   ta={e['sequence_raw'] for e,z in zip(chosen,x) if qa is not None and z>qa};tb={e['sequence_raw'] for e,z in zip(chosen,y) if qb is not None and z>qb}
   assert ta==set(json.loads(r['T_A_json'])) and tb==set(json.loads(r['T_B_json']))
   eq(r['jaccard'],len(ta&tb)/len(ta|tb) if ta|tb else None)
 for r in availability:
  pp=[e for e in grouped[r['pair_id']] if e['in_P']]
  eq(r['n_P'],len(pp));cross=Counter((e['A_state'],e['B_state']) for e in pp)
  for a,b in itertools.product(STATES,repeat=2):eq(json.loads(r['cross_counts_json'])[a+'|'+b],cross[a,b])
  aa={e['sequence_raw'] for e in pp if e['A_n_finite']==0};bb={e['sequence_raw'] for e in pp if e['B_n_finite']==0}
  eq(r['all_nonfinite_jaccard'],len(aa&bb)/len(aa|bb) if aa|bb else None)
  for side in ('A','B'):
   allrows=[x for e in pp for x in groups[e['configuration_'+side],e['sequence_raw']]]
   eq(r[side+'_n_retained_P'],len(allrows));eq(r[side+'_n_finite_P'],len(vals(allrows,'rmse')))
 byid={r['row_id']:r for r in tradeoffs}
 for r in tradeoffs:
  c=r['configuration_id'];m=r['efficiency_metric']
  if r['row_type']=='sequence_joint_means':
   rs=groups[c,r['sequence_raw']];joint=[x for x in rs if x['rmse_is_finite']=='True' and x[m+'_is_finite']=='True']
   eq(r['n_joint_finite'],len(joint));eq(r['rmse_joint_mean'],statistics.fmean(vals(joint,'rmse')) if joint else None)
   eq(r['efficiency_joint_mean'],statistics.fmean(vals(joint,m)) if joint else None)
   assert [str(x['index']) for x in json.loads(r['joint_members_json'])]==[x['source_record_index'] for x in joint]
  else:
   members=[byid[i] for i in json.loads(r['used_sequence_row_ids_json'])]
   # Sequence means have just been independently recomputed; correlation uses independent ranks.
   expected,reason=independent_rho([x['rmse_joint_mean'] for x in members],[x['efficiency_joint_mean'] for x in members])
   eq(r['rho'],expected);assert r['status']==reason;eq(r['n_sequences'],len(members))
 assert len({r['row_id'] for r in patterns})==len(patterns) and len(byid)==len(tradeoffs)
 return {'numeric_and_count_checks':nchecks,'stage7_sequence_means_and_members':len(old7),'stage9_repeat_and_coverage_keys':len(seq),
  'four_special_configs_48_sequences_each_confirmed_from_stage9':True,
  'all_pair_supports_ranks_symmetric_and_members_checked':True,'same_run_intersections_and_tradeoff_ranks_checked':True,
  'unavailable_reasons_preserved':True,'unique_output_keys':True}


def pair_facts(pair,scope,patterns,availability):
 key=pid(*pair);p=next(r for r in scope if r['pair_id']==key)
 if p['processing_status']=='not_computed':return {'scope':p}
 rr=[r for r in patterns if r['pair_id']==key]
 return {'scope':p,'F':next(r for r in rr if r['view']=='F_mean'),
   'C':next(r for r in rr if r['view']=='C_mean'),'median':next(r for r in rr if r['view']=='F_median'),
   'scenes':[r for r in rr if r['view']=='scene_F_mean'],
   'loso':[r for r in rr if r['view']=='leave_one_scene_out_F_mean'],
   'high':next(r for r in rr if r['row_type']=='relative_high_overlap'),
   'availability':next(r for r in availability if r['pair_id']==key)}


def interpret_pair(f,index):
 F,C,M=f['F'],f['C'],f['median'];scene={r['scene']:r for r in f['scenes']}
 rr=lambda s:fmt(scene[s]['rho'])
 loso={r['removed_scene']:r for r in f['loso']}
 if index==1:
  return f"总体正关联并非各场景内均一致：Pool内ρ={rr('pool')}接近零，road内ρ={rr('road')}较高；移去Pool后总体ρ由{fmt(F['rho'])}变为{fmt(loso['pool']['rho'])}。Pool共同较难的位置影响总体模式，不能将总体相似性全部解释为场景内排序一致，也不能把road中仍存在的关系全部归为场景间差异。"
 if index==2:
  return f"两个单目配置在共同序列上总体正关联，但building内ρ={rr('building')}接近零，roundabout为{rr('roundabout')}。C和median视图仍为正；保留这种局部不一致，不能据版本名称推断相同机制或某版本性能更好。"
 if index==3:
  return f"支持集合对结论幅度有影响：从F的n={F['n_sequences']}、ρ={fmt(F['rho'])}改到C的n={C['n_sequences']}、ρ={fmt(C['rho'])}；median视图为{fmt(M['rho'])}。Pool和roundabout内为负，不能概括为各场景都同向。DROID这一配置的重复来源仍未确认，C筛选不证明缺失偏差消失。"
 if index==4:
  return f"F中总体ρ={fmt(F['rho'])}；五个场景内ρ均为正（{min(r['rho'] for r in f['scenes']):.3f}～{max(r['rho'] for r in f['scenes']):.3f}），说明不只有场景间位置差异，但局部n仅5～9。比较仅覆盖双方有限的{F['n_sequences']}条，VGGT-SLAM其余全无效序列没有被恢复；VGGT-LONG重复来源限制保留。"
 if index==5:
  return f"calib/nocalib的F均值与中位数排序结果接近（{fmt(F['rho'])}与{fmt(M['rho'])}）；多数场景内为正，roundabout为{rr('roundabout')}。这支持有限的配置模式描述，不能解释为标定因果收益；输入模态按当前manifest确认；上游标定细节仍未核实。"
 if index==6:
  scene_text='；'.join(r['scene']+' rho='+fmt(r['rho'])+' n='+str(r['n_sequences'])+' '+r['status'] for r in f['scenes'])
  repeats=f['availability']
  return f"500帧两配置：F/C序列数={F['n_sequences']}/{C['n_sequences']}，F均值/中位数rho={fmt(F['rho'])}/{fmt(M['rho'])}；场景内为{scene_text}。当前每序列保留数分布A/B={repeats['A_retained_run_count_distribution_json']}/{repeats['B_retained_run_count_distribution_json']}；有限次数和均值/中位数关系按实际记录，不继续沿用旧单次假设。排序相似性不证明语义有无收益或独立重复稳定。"
 raise ValueError(index)

def extra_findings(availability,tradeoffs):
 mutual=[r for r in availability if r['only_A_finite_n'] and r['only_B_finite_n']]
 flags=sorted({c for r in mutual for c in (r['configuration_A'],r['configuration_B']) if c in SPECIAL})
 const=[r for r in tradeoffs if r['row_type']=='rank_correlation' and r['efficiency_metric']=='memory' and r['status']=='constant_input']
 return [
  {'finding_id':'R10_AVAILABILITY_COMPLEMENTARITY','finding_type':'availability_collection','status':'checked_descriptively',
   'observation':f"全部允许/限定对中有{len(mutual)}对同时出现仅A有限和仅B有限序列；每对的两个方向及成员单独保留。",
   'within_scene_observation':'此结论只计P上的记录层数值可用性，不对各场景或run_id做联合成功次数。',
   'special_repeat_flags_json':js(flags),'evidence_ids_json':js([r['pair_id'] for r in mutual]),
   'evidence_table':'tables/10_relationships/pairwise_availability.csv',
   'limitations':'序列至少一次有限的机会随保留运行数变化；仍需看3x3状态及运行级有限率。数据范围、模态与来源限制逐对遵守。',
   'supported_wording':'存在可追溯的数值可用性互补线索。',
   'unsupported_wording':'已验证融合增益、切换系统成功率、公平可靠性排名、不同失败机制。',
   'step11_use':'只能作为未来可研究的记录层线索；同时列方向、成员、P分母和运行数，不能给出系统收益数字。'},
  {'finding_id':'R10_CONSTANT_MEMORY','finding_type':'undefined_correlation','status':'checked_descriptively',
   'observation':f"内存相关中{len(const)}个整体/场景视图为constant_input；包括TartanVO整体与五场景，以及VGGT-LONG的building/pool/roundabout。",
   'within_scene_observation':'常数向量没有可定义的排序相关，不能将空值当0。',
   'special_repeat_flags_json':js(sorted({r['configuration_id'] for r in const if r['configuration_id'] in SPECIAL})),
   'evidence_ids_json':js([r['row_id'] for r in const]),'evidence_table':'tables/10_relationships/within_configuration_tradeoffs.csv',
   'limitations':'这是当前保留数值的特征；不证明真实内存需求恒定或内存与误差没有联系。',
   'supported_wording':'当前常数memory集合的Spearman未定义。',
   'unsupported_wording':'memory与误差不相关、内存没有影响。',
   'step11_use':'表格明确标constant_input／未定义，不用0、显著性星号或遗漏空格掩盖。'}]


def findings_rows(scope,patterns,availability,tradeoffs):
 result=[]
 for i,pair in enumerate(FOCUS,1):
  f=pair_facts(pair,scope,patterns,availability);p=f['scope'];baseid='R10_P'+str(i)
  if p['processing_status']=='not_computed':
   result.append({'finding_id':baseid,'finding_type':'prespecified_pair','pair_id':p['pair_id'],'status':'not_computed','reason':p['reason']});continue
  F,C,M,H,AV=f['F'],f['C'],f['median'],f['high'],f['availability']
  scene_text='；'.join(r['scene']+f" ρ={fmt(r['rho'])}, n={r['n_sequences']}, {r['status']}" for r in f['scenes'])
  loso_text='；'.join('去'+r['removed_scene']+f" ρ={fmt(r['rho'])}, n={r['n_sequences']}" for r in f['loso'])
  labels=[]
  if p['special_repeat_flags_json']!='[]':labels.append('repetition_provenance_unresolved')
  if C['rho'] is not None and F['rho'] is not None and abs(C['rho']-F['rho'])>TOL:labels.append('support_sensitive')
  if M['rho'] is not None and F['rho'] is not None and abs(M['rho']-F['rho'])>TOL:labels.append('representative_sensitive')
  if any(r['direction_changed'] for r in f['scenes']+f['loso']):labels.append('scene_heterogeneity')
  if AV['only_A_finite_n'] or AV['only_B_finite_n']:labels.append('numeric_availability_asymmetry')
  obs=f"U/P/F/C={F['n_U']}/{F['n_P']}/{F['n_F']}/{F['n_C']}；F mean ρ={fmt(F['rho'])}，C mean={fmt(C['rho'])}，F median={fmt(M['rho'])}；共同相对高误差 {H['n_intersection']}/{H['n_union']}，Jaccard={fmt(H['jaccard'])}。"
  obs+=f"P内两边有限/仅A/仅B/均无={AV['both_finite_n']}/{AV['only_A_finite_n']}/{AV['only_B_finite_n']}/{AV['neither_finite_n']}。"
  limits='同名序列标签只表示当前对应；排序关联不是绝对优劣、共同机制或互补系统收益；名义配置范围已按用户确认登记；逐运行完成、历史对齐/单位和独立性限制继续保留。'
  if labels and 'repetition_provenance_unresolved' in labels:limits+='涉及四个特别标记配置之一；相同保留重复不增加独立样本数。'
  result.append({'finding_id':baseid,'finding_type':'prespecified_pair','pair_id':p['pair_id'],'status':F['status'],
   'observation':obs,'relationship_interpretation':interpret_pair(f,i),'within_scene_observation':scene_text,'leave_one_scene_out_observation':loso_text,
   'labels_json':js(labels),'special_repeat_flags_json':p['special_repeat_flags_json'],
   'main_text_support':F['main_text_support'],'scope_status':p['processing_status'],
   'evidence_ids_json':js([r['row_id'] for r in [F,C,M,H]+f['scenes']+f['loso']]),
   'availability_evidence_id':p['pair_id'],'case_evidence_row':H['row_id'],'limitations':limits,
   'supported_wording':obs+' 分场景另见对应证据，不能用场景rho平均替代总体。',
   'unsupported_wording':'绝对更优、语义/标定因果增益、确定方法家族、已验证融合收益或可靠性排名。',
   'step11_use':'可整理为带n、支持集及来源限制的探索性关系；案例引用pair_sequence_evidence。不得转写成显著性或公平性能排名。'})
 for c in TRADEOFF_PLOTS:
  rr=[r for r in tradeoffs if r['configuration_id']==c and r['row_type']=='rank_correlation']
  overall=[r for r in rr if r['scene']=='__all_scenes__']
  obs='；'.join(f"RMSE—{r['efficiency_metric']} ρ={fmt(r['rho'])}, n={r['n_sequences']}, {r['status']}" for r in overall)
  scene_text='；'.join(f"{r['efficiency_metric']}/{r['scene']} ρ={fmt(r['rho'])} (n={r['n_sequences']}, {r['status']})" for r in rr if r['scene']!='__all_scenes__')
  result.append({'finding_id':'R10_T_'+c,'finding_type':'within_configuration','configuration_id':c,
   'status':'checked_descriptively','observation':obs,'within_scene_observation':scene_text,
   'relationship_interpretation':('FPS负、runtime和memory正的方向在总体及五个场景内均保持；只描述当前共同变化，不证明因果。' if all(r['status']=='computed' and numsign(r['rho'])==('negative' if r['efficiency_metric']=='fps' else 'positive') for r in rr) else '当前总体与分场景方向未全部满足FPS负、runtime和memory正；不能沿用统一共同变化叙述，各项方向和n逐一保留。'),
   'special_repeat_flags_json':js([c] if c in SPECIAL else []),'evidence_ids_json':js([r['row_id'] for r in rr]),
   'limitations':'两个序列均值使用完全相同的有限运行交集；相关方向保持原指标，计时/内存定义限制不改变。',
   'supported_wording':obs+'，只描述本配置现存序列的同交集关联。',
   'unsupported_wording':'因果速度—精度机制、FPS×runtime确认帧数、跨方法资源效率排名或Pareto支配。',
   'step11_use':'如使用，应同时展示分场景结果、共同运行定义及单位/计时限制；常数内存写相关未定义。'})
 return result+extra_findings(availability,tradeoffs)

def draw_figures(scope,patterns,availability,tradeoffs,overwrite):
 reject_links(W/'reports')
 with tempfile.TemporaryDirectory(prefix='.10_plot_',dir=W/'reports') as temp:
  with patch.dict(os.environ,{'MPLCONFIGDIR':temp,'XDG_CACHE_HOME':temp,'TMPDIR':temp,'PYTHONDONTWRITEBYTECODE':'1'}):
   import matplotlib
   matplotlib.use('Agg')
   import matplotlib.pyplot as plt
   from matplotlib.colors import Normalize
   from matplotlib.cm import ScalarMappable
   from matplotlib.patches import Patch
   plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'svg.hashsalt':'benchmark-step10',
    'axes.spines.top':False,'axes.spines.right':False,'axes.grid':True,'grid.alpha':.18})
   colors=dict(zip(SCENES,['#0072B2','#E69F00','#009E73','#D55E00','#CC79A7']))
   def save(fig,name):
    for ext in ('png','svg'):
     b=io.BytesIO();fig.savefig(b,format=ext,dpi=150,metadata={'Software':'benchmark-analysis step10'} if ext=='png' else {'Date':None})
     write(name+'.'+ext,b.getvalue(),overwrite)
    plt.close(fig)
   def value(x):return 'undefined' if x is None else f'{x:.3f}'
   # Each panel is a predefined pair, not selected from largest correlations.
   fig,axes=plt.subplots(2,3,figsize=(16,11))
   for i,(ax,pair) in enumerate(zip(axes.flat,FOCUS),1):
    f=pair_facts(pair,scope,patterns,availability)
    if f['scope']['processing_status']=='not_computed':
     ax.text(.5,.5,'Not comparable:\n'+f['scope']['reason'],ha='center',transform=ax.transAxes);continue
    base=f['F'];members=json.loads(base['members_json'])
    for scene in SCENES:
     pts=[m for m in members if m['scene']==scene]
     ax.scatter([m['A_relative_rank'] for m in pts],[m['B_relative_rank'] for m in pts],color=colors[scene],s=30,alpha=.85,label=scene)
    ax.set(xlim=(-.04,1.04),ylim=(-.04,1.04),
     xlabel=pair[0]+'\nrelative rank within F',ylabel=pair[1]+'\nrelative rank within F',
     title=f"P{i}: n={base['n_sequences']}, scenes={base['n_scenes']}, rho={value(base['rho'])}")
    ax.set_aspect('equal',adjustable='box')
   fig.suptitle('Sequence difficulty patterns | six prespecified configuration pairs',fontsize=15)
   fig.legend(handles=[Patch(color=v,label=k) for k,v in colors.items()],loc='lower center',ncol=5,bbox_to_anchor=(.5,.038))
   fig.text(.5,.016,'two_tokens; one finite-run mean per sequence, pair-specific F. Higher rank = relatively higher own error. No absolute-performance equality line.',ha='center',fontsize=9)
   fig.tight_layout(rect=(.02,.09,.98,.94),w_pad=3,h_pad=3);save(fig,'01_focus_rank_positions')
   # Fixed scale; explicit local n; constant/insufficient are text rather than zero.
   fig,ax=plt.subplots(figsize=(16,8));matrix=np.full((6,8),np.nan);labels=[];annotations=[]
   for i,pair in enumerate(FOCUS):
    f=pair_facts(pair,scope,patterns,availability);labels.append(pair[0]+'\nvs '+pair[1]);ann=[]
    if 'F' not in f:
     annotations.append(['NC']*8);continue
    rr=[f['F'],f['C'],f['median']]+[next(r for r in f['scenes'] if r['scene']==s) for s in SCENES]
    for j,r in enumerate(rr):
     if r['rho'] is not None:matrix[i,j]=r['rho']
     tag=value(r['rho']) if r['rho'] is not None else 'C' if r['status']=='constant_input' else 'I'
     ann.append(tag+'\nn='+str(r['n_sequences']))
    annotations.append(ann)
   cmap=plt.get_cmap('RdBu_r').copy();cmap.set_bad('#eeeeee')
   im=ax.imshow(matrix,vmin=-1,vmax=1,cmap=cmap,aspect='auto')
   for i in range(6):
    for j in range(8):ax.text(j,i,annotations[i][j],ha='center',va='center',fontsize=9,color='white' if np.isfinite(matrix[i,j]) and abs(matrix[i,j])>.7 else 'black')
   ax.grid(False);ax.set_yticks(range(6),labels,fontsize=9);ax.set_xticks(range(8),['F mean','C mean','F median',*SCENES],rotation=25,ha='right')
   ax.set_title('Same six pairs | support / representative / within-scene Spearman',pad=16)
   fig.colorbar(im,ax=ax,label='Spearman rho',fraction=.03,pad=.025)
   fig.text(.5,.025,'two_tokens; sequence unit; rerank separately in each cell. I: n<3, C: constant input, NC: incompatible scope. Gray is not zero. No averaged scene rho.',ha='center',fontsize=9)
   fig.tight_layout(rect=(0,.08,1,1));save(fig,'02_focus_support_scene_rho')
   # Availability counted on P, separate from correlation sample F.
   fig,ax=plt.subplots(figsize=(15,7));cats=['both_finite','only_A_finite','only_B_finite','neither_finite'];palette=['#56B4E9','#E69F00','#009E73','#777777'];left=np.zeros(6);yt=[]
   facts=[pair_facts(pair,scope,patterns,availability) for pair in FOCUS]
   for i,(pair,f) in enumerate(zip(FOCUS,facts)):yt.append('A '+pair[0]+'\nB '+pair[1])
   for cat,col in zip(cats,palette):
    vv=[f['availability'][cat+'_n'] if 'availability' in f else 0 for f in facts]
    ax.barh(range(6),vv,left=left,color=col,label=cat.replace('_',' '))
    for i,v in enumerate(vv):
     if v:ax.text(left[i]+v/2,i,str(v),ha='center',va='center',fontsize=10)
    left+=vv
   for i,f in enumerate(facts):
    if 'availability' not in f:ax.text(0,i,'NC');continue
    a=f['availability'];absA=len(json.loads(a['A_absent_on_U_json']));absB=len(json.loads(a['B_absent_on_U_json']))
    ax.text(left[i]+.6,i,f"P={a['n_P']}; absent A/B={absA}/{absB}",va='center',fontsize=9)
   ax.set_yticks(range(6),yt,fontsize=9);ax.invert_yaxis();ax.set_xlim(0,max(left)+16);ax.set_xlabel('Common observed sequences on P (not retained runs)')
   ax.set_title('Numeric availability | six prespecified pairs, two_tokens')
   ax.legend(ncol=4,loc='lower center',bbox_to_anchor=(.5,-.28),fontsize=9)
   fig.text(.5,.018,'At least one finite RMSE is not full-trajectory success. Different retained run counts give different opportunities; 3x3 states and run fractions are in the table.',ha='center',fontsize=9)
   fig.tight_layout(rect=(0,.13,1,1));save(fig,'03_focus_availability')
   # Within-configuration heatmap does not compare absolute memory/time magnitudes.
   rr=[r for r in tradeoffs if r['row_type']=='rank_correlation' and r['scene']=='__all_scenes__']
   configs=sorted({r['configuration_id'] for r in rr});fig,ax=plt.subplots(figsize=(11,13));arr=np.full((len(configs),3),np.nan)
   for i,c in enumerate(configs):
    for j,m in enumerate(METRICS[1:]):
     r=next(r for r in rr if r['configuration_id']==c and r['efficiency_metric']==m)
     if r['rho'] is not None:arr[i,j]=r['rho']
   im=ax.imshow(arr,vmin=-1,vmax=1,cmap=cmap,aspect='auto')
   for i,c in enumerate(configs):
    for j,m in enumerate(METRICS[1:]):
     r=next(r for r in rr if r['configuration_id']==c and r['efficiency_metric']==m)
     t=value(r['rho']) if r['rho'] is not None else 'C' if r['status']=='constant_input' else 'I'
     ax.text(j,i,t+'  (n='+str(r['n_sequences'])+')',ha='center',va='center',fontsize=9,color='white' if np.isfinite(arr[i,j]) and abs(arr[i,j])>.7 else 'black')
   ax.grid(False);ax.set_yticks(range(len(configs)),configs,fontsize=9);ax.set_xticks(range(3),['RMSE / FPS','RMSE / runtime','RMSE / memory'])
   ax.set_title('Within-configuration associations | sequence means on identical run intersections',fontsize=12,pad=18)
   fig.colorbar(im,ax=ax,label='Spearman rho (within each configuration)',fraction=.035,pad=.04)
   fig.text(.5,.025,'two_tokens; lexical order, no clustering/ranking. C: constant input, I: fewer than 3 sequences. Same-run intersection per metric; units/protocols are not unified.',ha='center',fontsize=8)
   fig.tight_layout(rect=(0,.055,1,1));save(fig,'04_within_configuration_rho')
   # Raw axes always restricted to a single configuration and paired run intersection.
   fig,axes=plt.subplots(3,2,figsize=(14,13))
   for i,c in enumerate(TRADEOFF_PLOTS):
    for j,m in enumerate(('fps','runtime')):
     ax=axes[i,j];r=next(r for r in rr if r['configuration_id']==c and r['efficiency_metric']==m)
     ss=[s for s in tradeoffs if s['row_type']=='sequence_joint_means' and s['configuration_id']==c and s['efficiency_metric']==m and s['n_joint_finite']]
     for scene in SCENES:
      pts=[s for s in ss if s['scene']==scene]
      ax.scatter([s['rmse_joint_mean'] for s in pts],[s['efficiency_joint_mean'] for s in pts],color=colors[scene],alpha=.85,s=32)
     ax.set(title=c+f" | n={r['n_sequences']}, rho={value(r['rho'])}",
      xlabel='RMSE mean on joint finite runs (source units)',ylabel='FPS (source-defined interval)' if m=='fps' else 'runtime (source units / stage coverage)')
   fig.suptitle('Same-run precision / efficiency associations | three preselected configurations',fontsize=14)
   fig.legend(handles=[Patch(color=v,label=k) for k,v in colors.items()],loc='lower center',ncol=5,bbox_to_anchor=(.5,.035))
   fig.text(.5,.014,'two_tokens; one point per sequence. Both axes use identical retained-run intersections. Selected from prior repeat/efficiency checks, not largest rho. No causal interpretation.',ha='center',fontsize=9)
   fig.tight_layout(rect=(0,.09,1,.94),w_pad=3,h_pad=3);save(fig,'05_same_run_tradeoffs')
 return list(FIGURES)


def make_report(rows,sources,seq,scope,evidence,patterns,availability,tradeoffs,findings,checks,tests):
 from review_all_configurations_narrative import protocol_note
 def table(headers,records):
  return '| '+' | '.join(headers)+' |\n| '+' | '.join(['---']*len(headers))+' |\n'+'\n'.join('| '+' | '.join(str(v).replace('|',' / ').replace('\n',' ') for v in row)+' |' for row in records)+'\n'
 lines=['# 第 10 步：序列难度关系、数值可用性及配置内精度—效率联系','',
  protocol_note({'accuracy_protocol_by_configuration':sources}),'',
  '本轮已实际计算；唯一逐次性能输入为不变的标准化主表。所有结果是当前保留数据的探索性描述，没有跨方法绝对性能排名、Pareto支配、显著性检验或底层来源调查。','',
  '## 主要关系发现','']
 for finding in findings:
  lines +=['### '+finding['finding_id']+' — '+finding.get('pair_id',finding.get('configuration_id','')),'']
  if finding['status']=='not_computed':
   lines +=['不计算：'+finding['reason'],''];continue
  lines +=[finding['observation'],'']
  if finding.get('relationship_interpretation'):lines +=[finding['relationship_interpretation'],'']
  lines +=['场景内：'+finding['within_scene_observation'],'']
  if finding.get('leave_one_scene_out_observation'):lines+=['固定原 F 逐场景剔除：'+finding['leave_one_scene_out_observation'],'']
  lines +=['限制：'+finding['limitations'],'']
 lines +=['不能由总体ρ单独断言场景内也有相同关系。上述分场景结果在各自集合重新排序；与总体差异说明组成与局部异质性可能影响描述，不能据此量化场景的因果贡献。各场景ρ没有被简单平均为总体ρ。','',
  '## 六对配置的可追溯案例','',
  '相对高误差使用同一个 F 中各自 mean 的线性 q75，严格大于阈值；并列时不要求刚好25%。共同高误差案例按较低一侧的相对秩降序、再按sequence字典序选择；秩差案例按绝对相对秩差降序、再按sequence字典序选择。每类每对最多3条。秩位置=(平均秩−1)/(n−1)，只表示对本配置其它序列的相对位置。','']
 for pair in FOCUS:
  f=pair_facts(pair,scope,patterns,availability);p=f['scope'];lines+=['### '+p['pair_id'],'']
  if 'F' not in f:lines+=[p['reason'],''];continue
  high=f['high'];lines +=[f"F={f['F']['n_sequences']}；q75(A)={fmt(high['q75_A'])}、q75(B)={fmt(high['q75_B'])}；T_A/T_B={high['n_T_A']}/{high['n_T_B']}；交集/并集={high['n_intersection']}/{high['n_union']}，Jaccard={fmt(high['jaccard'])}。阈值分别属于各自来源，不能比较绝对高低。",'']
  out=[]
  for label,key in [('共同相对高误差','common_high_cases_json'),('相对秩差','rank_gap_cases_json')]:
   cases=json.loads(high[key])
   if not cases:out.append([label,'无符合成员','—','—','—','—','—','—','—'])
   for m in cases:
    out.append([label,m['sequence'],f"{m['scene']}/H{m['altitude_m']}/V{m['speed_mps']}",
     fmt(m['A_value'])+'/'+fmt(m['B_value']),fmt(m['A_relative_rank'])+'/'+fmt(m['B_relative_rank']),
     fmt(m['relative_rank_gap_A_minus_B']),
     str(m['A_finite_retained'])+'/'+str(m['B_finite_retained']),
     ','.join(str(x['index']) for x in m['A_members']),','.join(str(x['index']) for x in m['B_members'])])
  lines +=[table(['类型','sequence','条件','mean A/B 各自来源','相对秩 A/B','秩差 A−B','有限/保留 A/B','A源索引','B源索引'],out)]
 lines +=['每条案例的完整来源路径、哈希、参与索引、run_id和部分有限状态在 [pair_sequence_evidence.csv](../tables/10_relationships/pair_sequence_evidence.csv)；选择顺序和证据键在 patterns 表相应 relative_high_overlap 行的 JSON。相对难易不表示另一方法绝对误差更低或可可靠替代。','',
  '## 比较范围和配置处理状态','',
  f"24个配置、{len(scope)}个无序配置对全部登记，不计自比较；范围状态为 {dict(Counter(r['processing_status'] for r in scope))}。500帧仅与500帧比较；双方用户确认完整轨迹时名义范围相同，但单位、历史对齐和效率协议仍限制解释。若出现未知范围则另行保留，不把未知相等当确认。",
  f"主子集实际 {sum(r['condition_label_status']=='two_tokens' for r in rows)} 行、{len(seq)} 个配置×sequence。没有全24配置共同dropna、按run_id配对或复制成额外实验。",
  '']
 configtable=[]
 for c in sorted(sources):
  ss=[s for (cc,n),s in seq.items() if cc==c];pp=[p for p in scope if c in (p['configuration_A'],p['configuration_B'])]
  tr=[r for r in tradeoffs if r['row_type']=='rank_correlation' and r['configuration_id']==c and r['scene']=='__all_scenes__']
  configtable.append([c,sources[c]['evaluation_scope'],len(ss),sum(s['n_retained'] for s in ss),
    sum(p['processing_status']!='not_computed' for p in pp),sum(p['processing_status']=='not_computed' for p in pp),
    '; '.join(r['efficiency_metric']+':'+r['status'] for r in tr),'special unresolved' if c in SPECIAL else 'independence not verified'])
 lines +=[table(['配置','范围','有条件sequence','保留行','允许/限定对','不计算对','配置内整体状态','重复来源'],configtable),
  '[comparison_scope.csv](../tables/10_relationships/comparison_scope.csv)保存每对的范围证据、模态关系、未知信息和不计算原因。跨模态只作探索；MASt3R calib/nocalib按完整ID保留，当前输入模态遵循manifest；上游标定细节未因此核实。',
  '',
  '四个特别标记配置 DROID-SLAM::rgbd、ElasticFusion::rgbd、SLAM3R::mono、VGGT-LONG::mono，复用第9步48条sequence各自重复RMSE及所有提供误差字段相同的审计；本轮主子集各44条。不是48条不同sequence之间相同，也不是四种算法彼此相同。涉及它们的关系附repetition_provenance_unresolved，既不去重，也不把三次相同数值算作三个跨方法相关样本。其它配置也没有自动获得独立重复证明。','',
  '## 数值可用性重叠','',
  '相关性的 F 会筛除无有限结果的序列；本节在共同有记录的 P 上计算，U 层的缺一侧记录单独列出。all_finite、partial_finite、all_nonfinite三态交叉包含零计数，恢复P总数；原运行级有限率与序列至少一次有限分开。','']
 avtable=[]
 for pair in FOCUS:
  f=pair_facts(pair,scope,patterns,availability)
  if 'availability' not in f:continue
  a=f['availability']
  avtable.append([a['pair_id'],f"{a['n_U']}/{a['n_P']}",
   '/'.join(str(a[k+'_n']) for k in ('both_finite','only_A_finite','only_B_finite','neither_finite')),
   f"{a['A_n_finite_P']}/{a['A_n_retained_P']}",f"{a['B_n_finite_P']}/{a['B_n_retained_P']}",
   a['A_retained_run_count_distribution_json'],a['B_retained_run_count_distribution_json'],
   fmt(a['all_nonfinite_jaccard']) if a['all_nonfinite_jaccard'] is not None else '双方在P均无全无效序列'])
 lines +=[table(['配置对（顺序为A/B）','U/P','两边/仅A/仅B/均无','A有限运行/保留','B有限运行/保留','A每序列保留数分布','B每序列保留数分布','全无效集合Jaccard'],avtable)]
 mutual=[a for a in availability if a['only_A_finite_n'] and a['only_B_finite_n']]
 lines +=[f"全部允许/限定对中，{len(mutual)} 对同时存在仅A有限与仅B有限的序列，属于记录层双向数值可用性互补线索。以下完整列出这些对及两个方向的实际数量；不推广为实际切换成功率或融合收益。",'',
  table(['配置对','仅A有限','仅B有限'],[[a['pair_id'],a['only_A_finite_n'],a['only_B_finite_n']] for a in mutual]),
  '保留运行数与有限结果数分别展示；“至少一次有限”不能直接作为公平可靠性比较。有限RMSE不等于完整轨迹成功；所有全无效集合并集为空时Jaccard未定义，不填1或0。同名run_id没有组合成联合成功/失败次数。','',
  '## 配置内部精度—效率结果','',
  '每个配置×sequence×效率指标先取RMSE与该效率同时有限的运行；两个mean严格在同一交集。没有共同有限值的序列保留原因。sequence_joint_means是配对证据，rank_correlation是其派生关系，两种row_type不能相加当新样本。','']
 overall=[r for r in tradeoffs if r['row_type']=='rank_correlation' and r['scene']=='__all_scenes__']
 out=[]
 for c in sorted(sources):
  rr=[next(r for r in overall if r['configuration_id']==c and r['efficiency_metric']==m) for m in METRICS[1:]]
  out.append([c,*[f"{fmt(r['rho'])}; n={r['n_sequences']}; {r['status']}" for r in rr]])
 lines +=[table(['配置','RMSE—FPS','RMSE—runtime','RMSE—memory'],out),
  'ρ符号按原指标解释：误差大而FPS低为负关联，误差大而runtime长为正关联；不统一好坏方向或合成分数。常数memory的相关未定义，不能写成“不相关”。FPS×runtime不用于确认帧数；runtime短不自动等于吞吐高。runtime单位统一为秒（user_confirmed 2026-10-08），覆盖历史source_manifest中的单位疑问；reported FPS为主要吞吐指标，runtime仅补充，不从runtime反推FPS或与相机采样率比较宣称实时性。计时覆盖、内存单位/类型等另按各自证据限定。',
  '',
  '## 方法与可计算边界','',
  '- U为两边实际sequence并集；P两边都有保留记录；F在P中各有至少一个有限RMSE；C在F中两边所有保留RMSE均有限。成员、计数和两边状态保留。',
  '- Spearman使用当前集合内平均并列秩的Pearson相关。每次换F/C、场景或剔除集合都重新排序；n<3为insufficient_sequences，常数输入为constant_input，未定义不填0。',
  '- 主文字优先n≥10且场景数≥3，仅是展示规则，不代表推断样本充分。每场景通常只有8或9条序列，其局部ρ不能强泛化。',
  '- 固定视图为F mean、C mean、F median和各场景F mean。预指定六对额外固定原F逐场景剔除。没有自选删除场景替代主结果。',
  '- 各对F可能不同，关系矩阵不构成已验证完整距离矩阵；没有层次聚类、谱聚类、网络分群或方法家族推断。',
  '- 第7/9步资料只核对均值、覆盖、来源和重复特征，不作为额外实验；同一来源在多个配置对引用不累计新实验次数。',
  '',
  '本轮不据配置内相关开展跨方法绝对误差或资源Pareto比较。各配置误差协议分别按source_manifest及已完成定点审计解释，不能笼统视为全部未知或全部一致；计时覆盖阶段、同名输入实际对应关系及重复独立性限制保留。作者定义的最终导出输出覆盖SR已完成并冻结，不等于100%完整或在线连续定位；旧阶段memory来源值不等同独立的GPU_RESERVED/CPU_RSS*有类型Table 2入口。当前数值版本依source_manifest绑定，各配置修订分别按其审计定义解释，不重开已确认SR、runtime秒或内存类型规则；SGS新批次的独立组件由本轮版本单独登记。',
  '',
  '## 测试、执行与保护','',
  '可手算内存样例：','']+['- '+t for t in tests]
 lines +=['','实际数据验证：','',table(['项目','结果'],[[k,v] for k,v in checks.items()]),
  '',
  f"产物行数：scope={len(scope)}，pair_sequence_evidence={len(evidence)}，pairwise_patterns={len(patterns)}，pairwise_availability={len(availability)}，within_configuration_tradeoffs={len(tradeoffs)}，findings={len(findings)}。",
  f"关系表状态：{dict(Counter(r['status'] for r in patterns if r['row_type']=='rank_correlation'))}；配置内相关状态：{dict(Counter(r['status'] for r in tradeoffs if r['row_type']=='rank_correlation'))}。",
  '真实均值/覆盖与第7/9步对应；从标准化逐次成员用标准库独立求均值、中位数、平均秩及相关，核对对称性、集合成员、阈值、可用性分母与共同运行交集。数值容差rtol=1e-12、atol=1e-10；这只是核对规则，不是显著性或实际等效阈值。',
  '8项指定输入执行前后哈希不变，三个标准化输入与第9步记录一致。默认拒绝覆盖；--overwrite只刷新本轮列明输出，拒绝危险符号链接与硬链接，不清目录。Agg缓存只在本轮工作区临时目录并清理。',
  '本会话常规执行器仍报mountinfo path is not absolute；通过工具允许的限定审批完成指定操作，未关闭沙箱、修改权限、安装或访问底层实验目录。',
  '',
  '### 产物入口','']
 for key,path in OUTPUTS.items():
  if key.endswith('.svg'):continue
  lines.append('- ['+Path(path).name+']('+(Path(path).name if path.startswith('reports/') else '../'+path)+')')
 lines+=['','### 复跑','',chr(96)*3+'bash',
 '/home/yuan/anaconda3/bin/python3 -B /home/yuan/SLAM/codex_review/benchmark_analysis/scripts/analyze_method_relationships.py --overwrite',
 chr(96)*3,'首次生成省略--overwrite；--self-test只执行小样例和工作区自建临时边界检查，不读取性能输入。',
 '',
 '### 交付验收',
 '',
 '数值计算和输入哈希检查已由脚本执行。逐张PNG视觉验收、实际默认拒绝覆盖及历史文件保护检查将在交付时追加；不能从savefig成功自动推断视觉检查已完成。',
 '']
 return '\n'.join(lines)

def main(argv=None):
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--overwrite',action='store_true');p.add_argument('--self-test',action='store_true');args=p.parse_args(argv)
 tests=self_tests()
 if args.self_test:print(js({'self_tests':'passed','checks':tests}));return
 for out in OUTPUTS.values():check_output(W/out,args.overwrite)
 raw={k:read_input(k) for k in INPUTS};prior=json.loads(raw['spec9'])
 for k in ('records','manifest','schema'):
  if sha(raw[k])!=prior['inputs'][k]['sha256']:raise ValueError('Standardized input changed since stage9: '+INPUTS[k])
 rows,sources,schema=load_records(raw)
 metadata={(r['configuration_id'],r['sequence_raw']):r for r in rows if r['condition_label_status']=='two_tokens'}
 scope=comparison_scope(sources,metadata)
 write('spec',json.dumps(make_spec(raw,scope),ensure_ascii=False,indent=2)+'\n',args.overwrite)
 audit={(r['configuration_id'],r['sequence_raw']):r for r in csv.DictReader(io.StringIO(raw['repeat9'].decode()))}
 seq=sequence_views(rows,audit);evidence=pair_evidence(scope,seq)
 patterns=all_pair_patterns(scope,evidence);availability=availability_rows(scope,evidence);tradeoffs=tradeoff_rows(seq,sources)
 checks=validate(rows,sources,seq,audit,scope,evidence,patterns,availability,tradeoffs,raw)
 findings=findings_rows(scope,patterns,availability,tradeoffs)
 for key,data in [('scope',scope),('evidence',evidence),('patterns',patterns),('availability',availability),('tradeoffs',tradeoffs),('findings',findings)]:
  write_csv(key,data,args.overwrite)
 draw_figures(scope,patterns,availability,tradeoffs,args.overwrite)
 for k,b in raw.items():
  if read_input(k)!=b:raise ValueError('Input changed during run: '+INPUTS[k])
 checks.update(input_hashes_unchanged=True,configurations=len(sources),unordered_pairs=len(scope))
 write('report',make_report(rows,sources,seq,scope,evidence,patterns,availability,tradeoffs,findings,checks,tests),args.overwrite)
 print(js({'status':'computed','checks':checks,'scope_counts':dict(Counter(r['processing_status'] for r in scope)),
  'counts':{k:len(v) for k,v in [('scope',scope),('evidence',evidence),('patterns',patterns),('availability',availability),('tradeoffs',tradeoffs),('findings',findings)]},
  'findings':[{k:r[k] for k in ('finding_id','observation','within_scene_observation','leave_one_scene_out_observation') if k in r} for r in findings],
  'visual_review':'pending'}))
if __name__=='__main__':main()
