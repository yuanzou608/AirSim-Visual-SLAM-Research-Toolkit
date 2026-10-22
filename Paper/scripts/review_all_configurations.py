#!/home/yuan/anaconda3/bin/python3
"""Step 11B only: same-template all-configuration review, not manuscript revision."""
import argparse
from collections import Counter,defaultdict
import csv
import hashlib
import html
import io
import json
import math
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch
from importlib import metadata
from datetime import date
from version_support import workspace, current_version, expected_inputs, check_version_history

W=workspace(Path(__file__).resolve().parents[1])
VERSION=current_version(W)
SCENES=("building","houses","pool","road","roundabout")
HEIGHTS=(10,20,30);SPEEDS=(2,4,8);TOL=1e-12
J="tables/08_conditions/joint_metrics.csv"
C="tables/08_conditions/conditional_contrasts.csv"
S="tables/07_eda/sequence_metrics.csv"
D="tables/07_eda/descriptive_summary.csv"
E="tables/07_eda/efficiency_cohort_comparison.csv"
R="tables/09_robustness/sensitivity_estimates.csv"
A="tables/09_robustness/repeat_value_audit.csv"
B="tables/09_robustness/support_blocks.csv"
T="tables/10_relationships/within_configuration_tradeoffs.csv"
M="derived_data/06_standardized/source_manifest.csv"
PAT="tables/11b_review/configuration_patterns.csv"
APP="tables/11b_review/claim_applicability.csv"
SEL="tables/11b_review/selection_rationale.csv"
NEW="tables/11b_review/condition_sensitivity.csv"
SEQ="tables/11b_review/sequence_index.csv"
SPEC="reports/11b_review_spec.json"
COV="reports/11b_review_coverage.csv"
REPORT="reports/11b_all_configuration_review.md"
INDEX="reports/11b_review_index.html"
MANIFEST="reports/11b_artifact_manifest.json"
SPECIAL=("DROID-SLAM::rgbd","ElasticFusion::rgbd","SLAM3R::mono","VGGT-LONG::mono")
SCRIPT="scripts/review_all_configurations.py"
PLOT_SCRIPT="scripts/review_all_configurations_plots.py"
FILES=[SPEC,COV,PAT,APP,SEL,NEW,SEQ,REPORT,INDEX]
FIG_NAMES=[f"c{i:02d}_{t}" for i in range(1,25) for t in ("grid","response")]+[
 f"{topic}_p{i:02d}" for topic in ("distribution_repeat","composition_efficiency") for i in range(1,7)]
OUTPUTS=FILES+[f"figures/11b_review/{n}.{ext}" for n in FIG_NAMES for ext in ("png","svg")]
TABLES={}
CHECKS={}
STAGING=None

def js(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,allow_nan=False,separators=(",",":"))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def safe(rel):
 p=Path(rel)
 if p.is_absolute() or ".." in p.parts:raise ValueError("Outside workspace: "+str(p))
 q=W
 for part in p.parts:
  q/=part
  if q.is_symlink():raise ValueError("Symlink rejected: "+str(q))
 if q.is_file() and q.stat().st_nlink!=1:raise ValueError("Hardlink rejected: "+str(q))
 if not q.resolve().is_relative_to(W):raise ValueError("Escaping workspace")
 return q
def out(rel):
 if rel not in OUTPUTS:raise ValueError("Outside 11B output allowlist: "+rel)
 safe(rel)
 return STAGING/rel if STAGING else safe(rel)
def write(rel,text):
 p=out(rel);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text,encoding="utf-8")
def csv_text(rows):
 buf=io.StringIO(newline="")
 keys=list(dict.fromkeys(k for r in rows for k in r))
 wr=csv.DictWriter(buf,keys,lineterminator="\n");wr.writeheader()
 wr.writerows({k:("" if v is None else v) for k,v in r.items()} for r in rows)
 return buf.getvalue()
def table(rel):
 if rel not in INPUT_HASHES:raise ValueError("Undeclared input "+rel)
 if rel not in TABLES:
  with safe(rel).open(encoding="utf-8",newline="") as f:TABLES[rel]=list(csv.DictReader(f))
 return TABLES[rel]
def numeric(v):return None if v is None or v=="" else float(v)
def direction(v):
 v=numeric(v)
 return "unavailable" if v is None else "numerical_zero" if abs(v)<=TOL else "positive" if v>0 else "negative"
def close(a,b):
 if a in (None,"") or b in (None,""):return a in (None,"") and b in (None,"")
 return math.isclose(float(a),float(b),rel_tol=1e-12,abs_tol=1e-10)
def fmt(v):return "未定义" if v in (None,"") else format(float(v),".5g")
def require_equal(a,b):
 assert a==b,(a,b)
def row_key(path,row):
 if path==J:return {k:row[k] for k in ("configuration_id","scene","metric","aggregation_level","altitude_m","speed_mps")}
 if path==C:return {k:row[k] for k in ("configuration_id","scene","metric","aggregation_level","contrast_kind","direction","fixed_value")}
 if path==S:return {k:row[k] for k in ("configuration_id","sequence_raw","metric")}
 if path==D:return {k:row[k] for k in ("configuration_id","subset","group_type","scene","metric","aggregation_level")}
 if path==E:return {k:row[k] for k in ("configuration_id","subset","metric")}
 if path==A:return {k:row[k] for k in ("configuration_id","sequence_raw")}
 if path==M:return {"configuration_id":row["configuration_id"]}
 for k in ("estimate_id","row_id","block_id","pair_id"):
  if k in row:return {k:row[k]}
 raise ValueError(path)
def evidence(path,row):
 e={"table":path,"key":row_key(path,row)}
 fields=[k for k,v in row.items() if v and any(s in k for s in ("members_json","indices_json","endpoints_json","sequence_descriptors_json"))]
 e["member_fields"]=fields
 if path==R and row.get("baseline_id"):e["baseline_id"]=row["baseline_id"]
 return e
def check_inputs():
 check_version_history(W)
 oldhashes=defaultdict(list)
 for p in ("reports/07_exploration_spec.json","reports/08_condition_analysis_spec.json",
           "reports/09_robustness_spec.json","reports/10_relationship_spec.json"):
  for e in json.loads(safe(p).read_text()).get("inputs",{}).values():
   oldhashes[e["path"]].append((p,e["sha256"]))
 result={}
 for p,h in INPUT_HASHES.items():
  actual=sha(safe(p))
  if actual!=h:raise ValueError("Frozen input changed; stop: "+p)
  for spec,old in oldhashes[p]:
   if actual!=old:raise ValueError("Input conflicts with saved snapshot: "+p+" / "+spec)
  result[p]={"sha256":actual,"prior_hashes_checked":[s for s,h in oldhashes[p]],
             "hash_basis":"saved_snapshot_match" if oldhashes[p] else "actual_11B_snapshot"}
 return result
def preflight(overwrite=False):
 for p in OUTPUTS+[MANIFEST]:safe(p)
 existing=[p for p in OUTPUTS+[MANIFEST] if safe(p).exists()]
 if not existing:return None
 if not safe(MANIFEST).is_file():raise ValueError("Existing 11B files without generation record; preserve: "+", ".join(existing))
 if not overwrite:raise ValueError("Default refuses overwrite. Review outputs before --overwrite.")
 old=json.loads(safe(MANIFEST).read_text())
 if set(old["outputs"])!=set(OUTPUTS):raise ValueError("Output allowlist changed")
 changed=[p for p,v in old["outputs"].items() if not safe(p).is_file() or sha(safe(p))!=v["sha256"]]
 if changed:raise ValueError("Manual edit/missing output conflict; preserve: "+", ".join(changed))
 return old

def indexes():
 manifests={r["configuration_id"]:r for r in table(M)}
 configs=sorted(manifests)
 assert len(configs)==24 and len({m["method_directory"] for m in manifests.values()})==17
 joint={}
 for r in table(J):
  if r["scene"] in SCENES and r["metric"]=="rmse" and r["aggregation_level"]=="equal_weight_sequence_means":
   key=(r["configuration_id"],r["scene"],int(r["altitude_m"]),int(r["speed_mps"]))
   assert key not in joint;joint[key]=r
 assert len(joint)==24*5*9
 summaries={(r["configuration_id"],r["scene"]):r for r in table(D)
            if r["subset"]=="condition_labelled" and r["metric"]=="rmse" and r["aggregation_level"]=="equal_weight_sequence_means"}
 sequences={(r["configuration_id"],r["sequence_raw"]):r for r in table(S) if r["subset"]=="condition_labelled" and r["metric"]=="rmse"}
 order={}
 for (c,name),r in sequences.items():
  meta=(r["scene"],int(r["altitude_m"]),int(r["speed_mps"]),name)
  if name in order:assert order[name]==meta
  order[name]=meta
 seqorder=sorted(order.values(),key=lambda v:(SCENES.index(v[0]),v[1],v[2],v[3]))
 assert len(seqorder)==44
 assert len(sequences)==sum(int(summaries[c,"__all__"]["n_observed_sequences"]) for c in configs)
 sensitivity={r["estimate_id"]:r for r in table(R)}
 within=table(T)
 return configs,manifests,joint,summaries,sequences,seqorder,sensitivity,within

def expanded_checks(configs):
 import check_benchmark_robustness as r9
 raw={key:safe(p).read_bytes() for key,p in {"records":"derived_data/06_standardized/run_records.csv","manifest":M,
      "schema":"derived_data/06_standardized/schema.json"}.items()}
 rows,sources,schema=r9.load_records(raw)
 primary=[r for r in rows if r["condition_label_status"]=="two_tokens"]
 original=dict(r9.FOCUS)
 with patch.object(r9,"FOCUS",{c:tuple(SCENES) for c in configs}):
  expanded=r9.focus_sensitivity(primary,sources)
 assert r9.FOCUS==original
 old={r["estimate_id"]:r for r in table(R) if r["analysis_type"].startswith("focus_contrast")}
 count=0
 def eq(x,y):
  if isinstance(x,(dict,list)):return x==y
  if isinstance(x,bool):return str(x)==y
  if x is None:return y==""
  if isinstance(x,(int,float)):return close(x,y)
  if isinstance(x,str) and x.startswith(("[","{")):
   return json.loads(x)==json.loads(y)
  return str(x)==y
 for r in expanded:
  if r["estimate_id"] not in old:continue
  for k,v in r.items():
   assert eq(v,old[r["estimate_id"]].get(k,"")),(r["estimate_id"],k)
   count+=1
 assert sum(r["analysis_type"]=="focus_contrast_baseline" for r in expanded)==840
 assert sum(r["analysis_type"]=="focus_contrast_baseline" for r in old.values())==35
 assert len({r["estimate_id"] for r in expanded})==len(expanded)
 assert set(old)<=set(r["estimate_id"] for r in expanded)
 if VERSION is None:assert len(old)==330 and len(expanded)==7495
 CHECKS["expanded_condition_sensitivity"]={"old_problems":35,"newly_checked_problems":805,"all_problems":840,
    "all_variant_rows":len(expanded),"old_rows_matched":len(old),"old_fields_matched":count,
    "by_type_status":dict(Counter(r["analysis_type"]+"/"+r["status"] for r in expanded)),
    "same_function":"scripts/check_benchmark_robustness.py:focus_sensitivity",
    "old_main_executed":False}
 # Serialize exactly as existing scalar/JSON fields; mark origin separately without changing the formula.
 for r in expanded:r["check_origin"]="rechecked_original_35" if r["estimate_id"] in old else "new_11B_same_formula"
 write(NEW,csv_text(expanded))
 return expanded
def monotonic(values):
 if any(x is None for x in values):return "unavailable"
 s=[direction(b-a) for a,b in zip(values,values[1:])]
 if all(x=="numerical_zero" for x in s):return "numerically_flat"
 if all(x in ("positive","numerical_zero") for x in s):return "nondecreasing"
 if all(x in ("negative","numerical_zero") for x in s):return "nonincreasing"
 return "nonmonotonic"
def pick_rows(path,c,**kw):
 return [r for r in table(path) if r["configuration_id"]==c and all(r.get(k)==str(v) for k,v in kw.items())]

def pattern_rows(data,expanded):
 configs,manifest,joint,summaries,sequences,seqorder,sens,within=data
 result=[]
 ranges=defaultdict(list)
 for r in expanded:
  if r["analysis_type"]=="focus_contrast_range":ranges[r["configuration_id"]].append(r)
 for c in configs:
  meta=manifest[c];summary=summaries[c,"__all__"]
  p={"configuration_id":c,"method_directory":meta["method_directory"],"modality_declared":meta["modality_declared"],
     "semantic_usage":meta["semantic_usage"],"evaluation_scope":meta["evaluation_scope"],
     "subset":"condition_labelled","zero_absolute_tolerance":TOL,
     "n_observed_sequences":int(summary["n_observed_sequences"]),"n_finite_sequences":int(summary["n_sequences_with_finite"]),
     "n_retained_runs":int(summary["n_retained_records"]),"n_finite_runs":int(summary["n_finite_records"]),
     "finite_fraction":numeric(summary["finite_fraction"]),
     "rmse_sequence_mean":numeric(summary["mean"]),"rmse_sequence_median":numeric(summary["median"]),
     "rmse_sequence_p90":numeric(summary["p90"]),"rmse_sequence_max":numeric(summary["max"]),
     "distribution_evidence_json":js(evidence(D,summary)),
     "special_repetition_provenance_unresolved":c in SPECIAL}
  cells=[joint[c,s,h,v] for s in SCENES for h in HEIGHTS for v in SPEEDS]
  states=Counter(r["cell_state"] for r in cells)
  p["cell_state_counts_json"]=js(dict(states))
  p["all_nonfinite_cells"]=states["observed_all_nonfinite"]
  p["no_record_cells"]=states["no_retained_records"]
  p["coverage_details_json"]=js([{"scene":r["scene"],"H":int(r["altitude_m"]),"V":int(r["speed_mps"]),
      "state":r["cell_state"],"mean":numeric(r["mean"]),"n_finite_records":int(r["n_finite_records"]),
      "n_retained_records":int(r["n_retained_records"]),"n_finite_sequences":int(r["n_sequences_with_finite"]),
      "n_observed_sequences":int(r["n_observed_sequences"]),"finite_fraction":numeric(r["finite_fraction"]),
      "evidence":evidence(J,r)} for r in cells])
  for axis,fixed_values in [("speed",HEIGHTS),("altitude",SPEEDS)]:
   details=[];tri=[]
   for scene in SCENES:
    for fixed in fixed_values:
     rows=[joint[c,scene,fixed,v] for v in SPEEDS] if axis=="speed" else [joint[c,scene,h,fixed] for h in HEIGHTS]
     vals=[numeric(r["mean"]) for r in rows]
     match=pick_rows(C,c,scene=scene,metric="rmse",aggregation_level="equal_weight_sequence_means",
                     contrast_kind=axis+"_difference",direction="8 - 2" if axis=="speed" else "30 - 10",fixed_value=fixed)
     assert len(match)==1
     r=match[0];d=numeric(r["difference"])
     assert close(d,None if vals[0] is None or vals[2] is None else vals[2]-vals[0])
     details.append({"scene":scene,"fixed_value":fixed,"value":d,"direction":direction(d),"status":r["status"],
       "finite_fraction_difference_pp":numeric(r["finite_fraction_difference_pp"]),
       "evidence":evidence(C,r),"endpoint_members":json.loads(r["endpoints_json"])})
     tri.append({"scene":scene,"fixed_value":fixed,"values":vals,"classification":monotonic(vals),
                 "adjacent_differences":[None if x is None or y is None else y-x for x,y in zip(vals,vals[1:])],
                 "evidence":[evidence(J,r) for r in rows]})
   ct=Counter(d["direction"] for d in details);mt=Counter(d["classification"] for d in tri)
   for k in ("positive","negative","numerical_zero","unavailable"):p[f"{axis}_endpoint_{k}"]=ct[k]
   for k in ("nondecreasing","nonincreasing","numerically_flat","nonmonotonic","unavailable"):p[f"{axis}_triple_{k}"]=mt[k]
   p[axis+"_endpoints_json"]=js(details);p[axis+"_triples_json"]=js(tri)
   comp="speed8_minus2" if axis=="speed" else "altitude30_minus10"
   views=[sens[f"{c}|{comp}|support_view|V{i}"] for i in range(5)]
   baseline=views[1]
   contributions=[r for r in table(R) if r["configuration_id"]==c and r["comparison"]==comp and
                   r["analysis_type"]=="scene_contribution" and r["view"]=="V1"]
   loso=[r for r in table(R) if r["configuration_id"]==c and r["comparison"]==comp and
                   r["analysis_type"]=="leave_one_scene_out" and r["view"]=="V1"]
   signs={direction(r["value"]) for r in contributions}
   p[axis+"_opposing_scene_contributions"]=("positive" in signs and "negative" in signs)
   p[axis+"_F_blocks"]=int(baseline["n_F"]);p[axis+"_C_blocks"]=int(baseline["n_C"])
   p[axis+"_V1"]=numeric(baseline["value"])
   p[axis+"_view_direction_changes"]=sum(direction(r["value"])!=direction(baseline["value"]) for r in views if r["status"]=="computed")
   p[axis+"_loso_direction_changes"]=sum(direction(r["value"])!=direction(baseline["value"]) for r in loso if r["status"]=="computed")
   p[axis+"_missing_loso_scenes_json"]=js([s for s in SCENES if not any(r["removed_scene"]==s for r in loso)])
   p[axis+"_views_json"]=js([{"view":r["view"],"value":numeric(r["value"]),"delta":numeric(r["delta_from_baseline"]),
       "direction":direction(r["value"]),"n_blocks":r["low_n_blocks"],"low_retained_finite":[r["low_n_retained"],r["low_n_finite"]],
       "high_retained_finite":[r["high_n_retained"],r["high_n_finite"]],"evidence":evidence(R,r)} for r in views])
   p[axis+"_scene_contributions_json"]=js([{"scene":r["scene"],"value":numeric(r["value"]),"n_blocks":r["n_blocks"],
      "weight":r["scene_weight"],"evidence":evidence(R,r)} for r in contributions])
   p[axis+"_loso_json"]=js([{"removed_scene":r["removed_scene"],"value":numeric(r["value"]),
       "delta":numeric(r["delta_from_baseline"]),"direction":direction(r["value"]),"n_blocks":r["low_n_blocks"],
       "evidence":evidence(R,r)} for r in loso])
   assert close(sum(float(r["value"]) for r in contributions),baseline["value"])
  speed_details=json.loads(p["speed_endpoints_json"])
  reversal=[];incomplete=[]
  for scene in SCENES:
   signs={d["direction"] for d in speed_details if d["scene"]==scene}
   if "positive" in signs and "negative" in signs:reversal.append(scene)
   if "unavailable" in signs:incomplete.append(scene)
  p["speed_direction_reversal_scenes_json"]=js(reversal);p["n_speed_reversal_scenes"]=len(reversal)
  p["speed_direction_incomplete_scenes_json"]=js(incomplete)
  seqs=[r for (cf,name),r in sequences.items() if cf==c]
  assert sum(int(r["n_retained_runs"]) for r in seqs)==p["n_retained_runs"]
  assert sum(int(r["n_finite_runs"]) for r in seqs)==p["n_finite_runs"]
  repeats=[]
  for r in seqs:
   name=r["sequence_raw"];rg=sens[f"{c}|{name}|sequence_variant_range|drop_one"]
   aud=pick_rows(A,c,sequence_raw=name);assert len(aud)==1
   repeats.append({"sequence":name,"scene":r["scene"],"H":int(r["altitude_m"]),"V":int(r["speed_mps"]),
       "n_retained":int(r["n_retained_runs"]),"n_finite":int(r["n_finite_runs"]),
       "finite_values":json.loads(r["finite_values_json"]),"mean":numeric(r["mean"]),"median":numeric(r["median"]),
       "repeat_sd":numeric(r["repeat_sd"]),"repeat_sd_status":r["repeat_sd_status"],
       "drop_mean_min":numeric(rg["range_min"]),"drop_mean_max":numeric(rg["range_max"]),
       "drop_status":rg["status"],"finite_error_identical":aud[0]["all_provided_error_fields_identical"],
       "evidence":[evidence(S,r),evidence(R,rg),evidence(A,aud[0])]})
  p["repeat_sd_estimable"]=sum(r["repeat_sd"] is not None for r in repeats)
  p["repeat_sd_undefined"]=len(repeats)-p["repeat_sd_estimable"]
  p["sequences_identical_rmse_repeats"]=sum(len(r["finite_values"])>=2 and len(set(r["finite_values"]))==1 for r in repeats)
  p["sequences_identical_provided_error_fields"]=sum(r["finite_error_identical"]=="True" for r in repeats)
  p["sequences_mean_median_numeric_difference"]=sum(r["mean"] is not None and abs(r["mean"]-r["median"])>TOL for r in repeats)
  p["sequence_drop_range_nonzero"]=sum(r["drop_mean_min"] is not None and r["drop_mean_max"]-r["drop_mean_min"]>TOL for r in repeats)
  p["repeat_details_json"]=js(repeats)
  oldranges=[r for r in table(R) if r["configuration_id"]==c and r["analysis_type"]=="focus_contrast_range"]
  cr=ranges[c]
  p["prior_condition_sensitivity_problems"]=len(oldranges);p["current_condition_sensitivity_problems"]=len(cr)
  p["condition_baselines_computed"]=sum(r["baseline_value"] is not None for r in cr)
  p["condition_baselines_unavailable"]=sum(r["baseline_value"] is None for r in cr)
  p["condition_problems_any_direction_change"]=sum(r["n_direction_changes"]>0 for r in cr)
  p["condition_trials_unavailable"]=sum(r["n_unavailable_variants"] for r in cr)
  p["condition_sensitivity_details_json"]=js([{"estimate_id":r["estimate_id"],"scene":r["scene"],"problem":r["focus_problem"],
      "baseline":r["baseline_value"],"range_min":r["range_min"],"range_max":r["range_max"],
      "direction_changes":r["n_direction_changes"],"computed_variants":r["n_computed_variants"],
      "unavailable_variants":r["n_unavailable_variants"],"origin":r["check_origin"],
      "evidence":{"table":NEW,"key":{"estimate_id":r["estimate_id"]},"member_fields":["endpoints_json"],"variants":json.loads(r["variant_ids_json"])}} for r in cr])
  rels=[]
  for metric in ("fps","runtime","memory"):
   rr=[r for r in within if r["configuration_id"]==c and r["efficiency_metric"]==metric and r["row_type"]=="rank_correlation"]
   overall=next(r for r in rr if r["scene"]=="__all_scenes__");sub=[r for r in rr if r["scene"]!="__all_scenes__"]
   assert len(rr)==6
   sd=direction(overall["rho"])
   opp=[r["scene"] for r in sub if direction(r["rho"]) in ("positive","negative") and sd in ("positive","negative") and direction(r["rho"])!=sd]
   bad=[r["scene"] for r in sub if r["status"]!="computed"]
   relation="overall_undefined" if overall["status"]!="computed" else "has_opposite_scenes" if opp else "incomplete_scenes" if bad else "all_same_direction" if all(direction(r["rho"])==sd for r in sub) else "includes_numerical_zero_or_mixed"
   p[metric+"_overall_rho"]=numeric(overall["rho"]);p[metric+"_scene_relation"]=relation
   p[metric+"_opposite_scenes_json"]=js(opp);p[metric+"_undefined_scenes_json"]=js(bad)
   rels += [{"metric":metric,"scene":r["scene"],"rho":numeric(r["rho"]),"n_sequences":int(r["n_sequences"]),
       "n_joint_finite_runs":int(r["n_joint_finite"]),"status":r["status"],"evidence":evidence(T,r)} for r in rr]
  p["efficiency_relations_json"]=js(rels)
  p["constant_correlation_views"]=sum(r["status"]=="constant_input" for r in rels)
  p["co_worsening_all_three_overall"]=all(direction(p[m+"_overall_rho"])==s for m,s in [("fps","negative"),("runtime","positive"),("memory","positive")])
  p["co_worsening_all_scenes_and_three"]=p["co_worsening_all_three_overall"] and all(p[m+"_scene_relation"]=="all_same_direction" for m in ("fps","runtime","memory"))
  ee=pick_rows(E,c,subset="condition_labelled")
  p["efficiency_cohorts_json"]=js([{"metric":r["metric"],"n_A":int(r["n_A"]),"n_B":int(r["n_B"]),
    "A_mean":numeric(r["A_mean"]),"B_mean":numeric(r["B_mean"]),"B_minus_A":numeric(r["B_minus_A_mean"]),
    "evidence":evidence(E,r)} for r in ee])
  p["n_efficiency_metrics_with_A_B_exclusion"]=sum(int(r["n_A_not_B"])>0 for r in ee)
  p["cross_configuration_review_status"]="computed_with_explicit_unavailable_states"
  result.append(p)
 assert len(result)==24
 # Independent audit totals specify equality of existing counts, not thresholds tuned to data.
 CHECKS["grid_cells"]=len(joint);CHECKS["sequence_primary_records"]=sum(p["n_retained_runs"] for p in result)
 CHECKS["endpoint_count_unit"]="24 configurations x 5 scenes x 3 fixed conditions; not independent observations"
 return result

INPUT_HASHES={
  "derived_data/06_standardized/run_records.csv": "f73b70914b7f60bfcad03f92e799631da679d43aaa893316c6b3514d27a054db",
  "derived_data/06_standardized/source_manifest.csv": "34d7cea320aa53e2b5dc6124bdc1971d0ed8d6ce7917fbccf25423dd6aa2ba5e",
  "derived_data/06_standardized/schema.json": "6ebb38d127ec556c6da5a93fd8f4ef93faf0a70c3960662e8379959cf63dbe90",
  "reports/07_exploration_spec.json": "0f6790a086e494d479dccaaa299728b6a80760e8c5df299072ea726c65b47502",
  "reports/07_exploratory_analysis.md": "cb3bd88e736bd344e90fcb54f8f79406bcf99267ec25f230e514e06b3a6cdf47",
  "reports/08_condition_analysis_spec.json": "d7146979a097f61a39c317bf3f568b40f5b348edcb7f6b697c1e83ad3361d98a",
  "reports/08_altitude_speed_analysis.md": "d630f886049a8a8e3d85db8234d602c5ce209e559c08abc0605fa7308432380d",
  "reports/09_robustness_spec.json": "a08680a5f4e17c2a0660ab52b972dfae886762b9d81afdd35e9a98b1b02909f5",
  "reports/09_robustness_analysis.md": "cd9dacaa2c0abff96f9569398b73ea8b53ea7a3e2eaa40d53a2d8a05ee338970",
  "reports/10_relationship_spec.json": "ee3f990151675ee661d99463cd3058efd4ca34b8e68aa2c9b0cd15c0f4a12c86",
  "reports/10_method_relationships.md": "8affd76f5c1be36d78a4b19bc8436b4a993afc23b1d5a8e986f43492023609a8",
  "reports/11_paper_synthesis.md": "4ccef7590d0346a882a822e1490d63f08db43c0a9187613e8ea56a24f8a165fa",
  "reports/11_claim_registry.csv": "d7518ba2d7b73e311432ed55bf69b79fd6c8a373f3c947e7e28ae65c23f9567d",
  "tables/07_eda/sequence_metrics.csv": "0459ebab01c89e59bcc208e7e5ff8963dad7bd6710061cf4e1e17beecf45bf91",
  "tables/07_eda/descriptive_summary.csv": "24588a099afb73b4863c7ea9f06dfbc6b93c63495a9f05347c25b2f4b7922b7e",
  "tables/07_eda/efficiency_cohort_comparison.csv": "6b323589083955daa36fb9bb5fa4f917d4b1cb0f61ae01cd9f38bcfc7de3938d",
  "tables/08_conditions/joint_metrics.csv": "6b34a00ac0e655b0c4c7acd5416a31a26842b9397798e8763f2506070bfbec74",
  "tables/08_conditions/conditional_contrasts.csv": "f4eece936b3e1108c91a8506bb05ff213f417a0e7588e47f63ed0a70135d2bc8",
  "tables/08_conditions/efficiency_cohort_cells.csv": "801f51ce08415914fba43a2ee06468d73866f5fda8f8a223869243494ea8b392",
  "tables/09_robustness/sensitivity_estimates.csv": "8bfd9440c0582f9cea82b34b79a8dee2bf199d33bd9d45a6c018c1fb0fb944a2",
  "tables/09_robustness/support_blocks.csv": "0afe0a5fb10ddc4ddcd5ed922eb2e4239da952af7af4d278e9fbf6b64b60d5a3",
  "tables/09_robustness/repeat_value_audit.csv": "32f6b715826ebd11c2da4c019dd4b2f6f4b5359144d5319ab97fcc4baf95dd04",
  "tables/09_robustness/efficiency_decomposition.csv": "7a480dc6044efeeaac7123c971696fb087746d1083d91dc21eae461dcf905e47",
  "tables/10_relationships/within_configuration_tradeoffs.csv": "ebe2d124345a2ed5a3378abf108215295ce919e8ff9d0a55988c90d9e9cd5c9a",
  "tables/10_relationships/pairwise_patterns.csv": "4cd21359ab1211e0829f39f18c68b7c4cd291f2114c5d56e2382d38a4a1412d8",
  "tables/10_relationships/pairwise_availability.csv": "a1b19fc7f6f910b8980a39d24933ecf8428e02110cdc68266c5386e9f6e35156",
  "tables/10_relationships/comparison_scope.csv": "ba0d4e5b5b1b5b4261f5d6fb36b80e4771e02782eb660ee887379b8c5f9ce04b",
  "scripts/check_benchmark_robustness.py": "fa1c658c9d3720d44ad445795866463d087b0e43e86857cd9a85b7e914fdd71d",
  "scripts/analyze_altitude_speed.py": "5964774f6ecc51aaa31c5447b285cf4b66f983d8495809376c63c367fffda433",
  "scripts/explore_benchmark.py": "7a972d636aebab1806247ead68dceec5ea96c7d271ebc8544476159c75159519",
  "scripts/build_analysis_dataset.py": "829bb183874b210f5b474892e08f935f8a0b2c3f0e5e252ee986503690099046"
}
INPUT_HASHES=expected_inputs("11B",INPUT_HASHES,W)


# All generation is confined to this explicit 11B set. Historical files are never targets.
HELPERS=[PLOT_SCRIPT,"scripts/review_all_configurations_claims.py","scripts/review_all_configurations_narrative.py","scripts/version_support.py"]
csv.field_size_limit(20_000_000)

def config_pages(i):
 return [f"c{i:02d}_grid",f"c{i:02d}_response",
         f"distribution_repeat_p{(i-1)//4+1:02d}",f"composition_efficiency_p{(i-1)//4+1:02d}"]

def coverage_rows(patterns,figures,reviewed):
 rows=[]
 # These are actual prior focused figure selections, not assertions that other CSV rows were visualized.
 prior_focus={"ORB-SLAM2::mono":"07 tail diagnostic; 11 A material",
   "DROID-SLAM::rgbd":"07 scene contrast diagnostic",
   "ORB-SLAM3::rgbd":"07 repeat diagnostic; 11 repeat material",
   "VGGT-SLAM::mono":"07 coverage diagnostic",
   "hierslam::rgbd_whole":"07 efficiency cohort; 11 D",
   "DPVO::mono":"08/09 focused Q9; 11 B"}
 for i,p in enumerate(patterns,1):
  names=config_pages(i);seen=[n for n in names if n in reviewed]
  rows.append({"configuration_id":p["configuration_id"],"method_directory":p["method_directory"],
   "evaluation_scope":p["evaluation_scope"],"fixed_order":i,
   "prior_numerical_status":"computed_in_07_10",
   "prior_complete_five_scene_grid_and_response":"not_generated_as_same_template",
   "prior_focused_figure_context":prior_focus.get(p["configuration_id"],"no_same_template_focus_selected"),
   "prior_focus_visual_review_status":"not_reaudited_in_11B",
   "prior_complete_same_question_comparison":"not_previously_established_for_11B_checklist",
   "prior_local_sensitivity_problems":p["prior_condition_sensitivity_problems"],
   "numerical_status":"computed_and_old_values_checked",
   "corresponding_charts_generated":"complete",
   "png_visual_review_status":"complete" if len(seen)==4 else "pending",
   "png_pages_reviewed":len(seen),"png_pages_required":4,
   "same_question_comparison_status":"complete_with_explicit_unavailable_results",
   "sensitivity_execution_status":"complete_for_35_local_problems",
   "sensitivity_computable_baselines":p["condition_baselines_computed"],
   "sensitivity_unavailable_baselines":p["condition_baselines_unavailable"],
   "sensitivity_unavailable_variants":p["condition_trials_unavailable"],
   "repeat_sd_estimable_sequences":p["repeat_sd_estimable"],
   "repeat_sd_undefined_sequences":p["repeat_sd_undefined"],
   "other_unexpanded_checks":"Hier-only per-record algebraic A/B decomposition and six-pair LOSO remain scoped; not used to rank selection evidence",
   "required_pages_json":js(names),"reviewed_pages_json":js(seen),
   "pattern_key":p["configuration_id"],"atlas_anchor":f"11b_review_index.html#config-{i:02d}"})
 return rows

def specification(patterns,inputs,figures):
 return {
 "stage":"11B full-configuration review, not manuscript revision",
 "date":date.today().isoformat(),"interpreter":sys.executable,"inputs":inputs,
 "input_version_manifest":"reports/current_input_manifest.json" if VERSION else None,
 "configuration_order":[p["configuration_id"] for p in patterns],"scene_order":list(SCENES),
 "altitudes_m":list(HEIGHTS),"speeds_mps":list(SPEEDS),
 "method_count_rule":"17 distinct original method_directory values; multiple configurations are not independent votes",
 "primary_subset":{"label":"condition_labelled (two_tokens)","n_retained_runs":sum(p["n_retained_runs"] for p in patterns),
   "n_configuration_sequences":sum(p["n_observed_sequences"] for p in patterns),"n_unique_sequences":len({r["sequence_raw"] for r in table(S) if r["subset"]=="condition_labelled" and r["metric"]=="rmse"})},
 "unlabelled_policy":{"n_retained_runs":sum(r["condition_label_status"]!="two_tokens" for r in table("derived_data/06_standardized/run_records.csv")),"rule":"Preserved in current frozen 06; not assigned invented H/V"},
 "scope_policy":{"counts":dict(Counter(p["evaluation_scope"] for p in patterns)),"rule":"Scopes follow current manifest evidence; frame-limited configurations stay separate; unknown is never inferred from numeric values"},
 "representative_values":"Exact keys in frozen 08 joint table, rmse/equal_weight_sequence_means; finite repeats -> sequence mean -> equal sequence weights, not a new aggregation",
 "grid_policy":{"pages_per_config":2,"scene_panels":5,"mean_scale":"full finite range, shared within configuration over five scenes",
   "finite_fraction_scale":[0,1],"cell_counts":"R=finite/retained runs; S=sequences with finite RMSE/observed sequences",
   "missing":"No records differs from retained-but-all-nonfinite. Missing response points break lines, no interpolation or zero fill."},
 "topic_policy":"All24 distribution/repeats + composition/efficiency in 12 four-configuration pages; stable sequence index shared with sequence_index.csv",
 "statistical_policy":{"direction_tolerance_absolute":TOL,"meaning":"floating sign convention only, not practical significance",
   "three_level_rule":"adjacent differences at all 3 levels; nondecreasing/nonincreasing include numerical-zero steps; all-numeric-zero is flat; missing any value is unavailable",
   "endpoint_rule":"8-2 m/s or 30-10 m, never a substitute for three-level monotonicity",
   "repeat_sd":"existing ddof=1; <2 finite values undefined; exact equality detected from actual values, not sd==0",
   "V0_V4":"existing 09 support/view definitions reused; memberships preserved by exact evidence keys",
   "scene_deletion":"existing fixed-F V1 leave-one-scene views, not a new weighting model",
   "efficiency":"existing 10 same-finite-run paired sequence means and overall/scene Spearman coefficients, constants undefined",
   "new_inference":"none; no p-values, models, clustering, thresholds or causal mechanisms"},
 "gap_completion":CHECKS.get("expanded_condition_sensitivity"),
 "claim_review":"18 original candidate claims x24. Literal pair/config scopes distinguished from cross-configuration phenomenon transfer. Candidate roles only.",
 "selection_audit":"Actual post-data diagnostic selection rules preserved; no fabricated preregistration, random sampling or algorithm-family mapping",
 "figure_count":len(figures),"png_review_policy":"pending until actual PNG viewing; receipts bound to PNG SHA256",
 "overwrite_policy":"Default refuse. Explicit --overwrite only exact known output set with unchanged stored hashes; manual edits stop.",
 "preserved_history":"Prior affected artifacts preserved in the verified version backup; protected steps3-5 remain unchanged" if VERSION else "No steps1-11 output regenerated or edited; README/PROJECT_STATUS append separately",
 "limitations":["finite RMSE fraction is not trajectory SR","ATE units/alignment and source provenance remain unresolved; scope is limited to current manifest evidence",
 "sequence/scene/config counts are not independent algorithm samples","no empirical practical-insensitivity threshold",
 "Previously scoped pair LOSO/algebraic decomposition not presented as all-config tests"],
 "checks":CHECKS}

def read_generated(rel):
 with safe(rel).open(encoding="utf-8",newline="") as f:return list(csv.DictReader(f))

def validate_numbers(patterns):
 assert len(patterns)==24
 primary=[r for r in table("derived_data/06_standardized/run_records.csv") if r["condition_label_status"]=="two_tokens"]
 assert sum(p["n_retained_runs"] for p in patterns)==len(primary)
 assert sum(p["n_observed_sequences"] for p in patterns)==len({(r["configuration_id"],r["sequence_raw"]) for r in primary})
 for p in patterns:
  for ax in ("speed","altitude"):
   assert sum(p[f"{ax}_endpoint_{k}"] for k in ("positive","negative","numerical_zero","unavailable"))==15
   assert sum(p[f"{ax}_triple_{k}"] for k in ("nondecreasing","nonincreasing","numerically_flat","nonmonotonic","unavailable"))==15
  assert p["repeat_sd_estimable"]+p["repeat_sd_undefined"]==p["n_observed_sequences"]
  assert p["condition_baselines_computed"]+p["condition_baselines_unavailable"]==35
  assert len(json.loads(p["coverage_details_json"]))==45
  assert len(json.loads(p["efficiency_relations_json"]))==18
 CHECKS["independent_aggregate_audit"]={}
 historical_expected={"speed_endpoint_positive":273,"speed_endpoint_negative":65,"speed_endpoint_unavailable":22,
 "altitude_endpoint_positive":121,"altitude_endpoint_negative":213,"altitude_endpoint_unavailable":26,
 "speed_triple_nondecreasing":190,"speed_triple_nonincreasing":20,"speed_triple_nonmonotonic":101,"speed_triple_unavailable":49,
 "altitude_triple_nondecreasing":51,"altitude_triple_nonincreasing":113,"altitude_triple_nonmonotonic":148,"altitude_triple_unavailable":48}
 expected={}
 for axis,fixed_values in (("speed",HEIGHTS),("altitude",SPEEDS)):
  # Independent current-table cross-check; original frozen totals remain historical guards.
  endpoint_rows=[r for r in table(C) if r["metric"]=="rmse" and r["aggregation_level"]=="equal_weight_sequence_means"
    and r["contrast_kind"]==axis+"_difference" and r["direction"]==("8 - 2" if axis=="speed" else "30 - 10") and r["scene"] in SCENES]
  assert len(endpoint_rows)==len(patterns)*len(SCENES)*len(fixed_values)
  counts=Counter(direction(r["difference"]) for r in endpoint_rows)
  for k in ("positive","negative","numerical_zero","unavailable"):expected[axis+"_endpoint_"+k]=counts[k]
  cells={(r["configuration_id"],r["scene"],int(r["altitude_m"]),int(r["speed_mps"])):numeric(r["mean"])
   for r in table(J) if r["metric"]=="rmse" and r["aggregation_level"]=="equal_weight_sequence_means" and r["scene"] in SCENES}
  triples=Counter(monotonic([cells[p["configuration_id"],scene,fixed,v] for v in SPEEDS] if axis=="speed" else
   [cells[p["configuration_id"],scene,h,fixed] for h in HEIGHTS]) for p in patterns for scene in SCENES for fixed in fixed_values)
  for k in ("nondecreasing","nonincreasing","numerically_flat","nonmonotonic","unavailable"):expected[axis+"_triple_"+k]=triples[k]
 for field,n in expected.items():
  actual=sum(p[field] for p in patterns);assert actual==n,(field,actual,n)
  if VERSION is None and field in historical_expected:assert actual==historical_expected[field]
  CHECKS["independent_aggregate_audit"][field]=actual
 CHECKS["current_version_manifest"]="reports/current_input_manifest.json" if VERSION else None
 # Minimal checks exercise the distinction the review depends on, not experimental validity.
 assert monotonic([1,4,2])=="nonmonotonic" and direction(2-1)=="positive"
 assert monotonic([1,None,2])=="unavailable"
 assert monotonic([1,1+TOL/2,2])=="nondecreasing"
 assert direction(None)=="unavailable" and direction(0)=="numerical_zero"
 CHECKS["semantic_guard_checks"]="endpoint is not monotonic; missing is not zero; numerical tolerance only"

def materialize(patterns,claims,selections,figures,reviewed,checks):
 from review_all_configurations_narrative import build_report,build_index
 checks["accuracy_protocol_by_configuration"]={r["configuration_id"]:{k:r.get(k,"")
  for k in ("source_sha256","rmse_unit_status","alignment_status","input_version")} for r in table(M)}
 write(COV,csv_text(coverage_rows(patterns,figures,reviewed)))
 write(REPORT,build_report(patterns,claims,selections,figures,reviewed,checks))
 write(INDEX,build_index(patterns,figures,reviewed))

def output_hashes():
 return {p:{"sha256":sha(out(p)),"bytes":out(p).stat().st_size} for p in OUTPUTS}

def commit_outputs(manifest):
 # All computational/rendering checks complete before any final output replacement.
 for rel in OUTPUTS:
  dest=safe(rel);dest.parent.mkdir(parents=True,exist_ok=True)
  os.replace(out(rel),dest)
 target=safe(MANIFEST)
 target.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

def generate(overwrite=False):
 global STAGING
 old=preflight(overwrite)
 inputs=check_inputs()
 # Byte-preserve all existing historical inputs; append docs is a separate explicit final action.
 historical={p:sha(safe(p)) for p in INPUT_HASHES}
 with tempfile.TemporaryDirectory(prefix=".11b_build_",dir=safe("reports")) as tmp:
  STAGING=Path(tmp)
  cache=STAGING/"cache";cache.mkdir()
  os.environ["MPLCONFIGDIR"]=str(cache/"matplotlib")
  os.environ["XDG_CACHE_HOME"]=str(cache/"xdg")
  os.environ["TMPDIR"]=str(cache)
  os.environ["PYTHONDONTWRITEBYTECODE"]="1"
  data=indexes();expanded=expanded_checks(data[0])
  patterns=pattern_rows(data,expanded);validate_numbers(patterns)
  write(PAT,csv_text(patterns))
  write(SEQ,csv_text([{"index":i,"scene":s,"altitude_m":h,"speed_mps":v,"sequence_raw":name}
    for i,(s,h,v,name) in enumerate(data[5],1)]))
  print("Numerical matrix and same-formula gap checks complete",flush=True)
  from review_all_configurations_plots import render_all
  target=STAGING/"figures/11b_review";target.mkdir(parents=True)
  figures=render_all(target,*data)
  assert {r["basename"] for r in figures}==set(FIG_NAMES)
  print("60 PNG/SVG page pairs generated",flush=True)
  from review_all_configurations_claims import build_claims,build_selections
  oldclaims=table("reports/11_claim_registry.csv")
  policy=(VERSION or {}).get("update_policy",{})
  claims=build_claims(patterns,oldclaims,table("tables/10_relationships/pairwise_availability.csv"),update_policy=policy)
  selections=build_selections(patterns,oldclaims,update_policy=policy)
  assert len(claims)==432 and len(selections)==24
  write(APP,csv_text(claims));write(SEL,csv_text(selections))
  reviewed={}
  if old:
   for name,receipt in old.get("visual_reviews",{}).items():
    if receipt["sha256"]==sha(out(f"figures/11b_review/{name}.png")):reviewed[name]=receipt
  materialize(patterns,claims,selections,figures,reviewed,CHECKS)
  write(SPEC,json.dumps(specification(patterns,inputs,figures),ensure_ascii=False,indent=2)+"\n")
  assert {p for p in OUTPUTS if out(p).is_file()}==set(OUTPUTS)
  check_inputs()
  assert all(sha(safe(p))==h for p,h in historical.items())
  manifest={"stage":"11B","outputs":output_hashes(),"inputs":inputs,
    "scripts":{p:sha(safe(p)) for p in [SCRIPT]+HELPERS},
    "figures":figures,"visual_reviews":reviewed,"checks":CHECKS,
    "patterns":patterns,"claims":claims,"selections":selections,
    "command":"/home/yuan/anaconda3/bin/python3 -B scripts/review_all_configurations.py",
    "versions":{k:metadata.version(k) for k in ("numpy","pandas","matplotlib")},
    "history_inputs_unchanged":True}
  commit_outputs(manifest)
  STAGING=None
 print(json.dumps({"outputs":len(OUTPUTS)+1,"pngs":60,"visual_reviewed":len(reviewed),"remaining":60-len(reviewed)}))

def verify():
 m=preflight(True);assert m is not None
 check_inputs()
 for p,h in m["scripts"].items():
  assert sha(safe(p))==h,("Script changed",p)
 for name,r in m["visual_reviews"].items():
  assert r["sha256"]==sha(safe(f"figures/11b_review/{name}.png"))
 assert len(m["patterns"])==24 and len(m["claims"])==432
 cov=read_generated(COV)
 assert len(cov)==24
 print(json.dumps({"verified_outputs":len(m["outputs"]),"input_snapshots":len(m["inputs"]),
   "pngs_actually_reviewed":len(m["visual_reviews"]),"pending":60-len(m["visual_reviews"]),
   "configurations_visual_complete":sum(r["png_visual_review_status"]=="complete" for r in cov)}))
 return m

def record_reviews(names,reviewer,note):
 global STAGING
 m=verify()
 for n in names:
  if n not in FIG_NAMES:raise ValueError("Unknown figure "+n)
  m["visual_reviews"][n]={"status":"visually_reviewed","sha256":sha(safe(f"figures/11b_review/{n}.png")),
    "reviewer":reviewer,"note":note}
 # Only three review-status documents change; no numerical table/image regeneration.
 with tempfile.TemporaryDirectory(prefix=".11b_review_",dir=safe("reports")) as tmp:
  STAGING=Path(tmp)
  materialize(m["patterns"],m["claims"],m["selections"],m["figures"],m["visual_reviews"],m["checks"])
  for rel in (COV,REPORT,INDEX):
   m["outputs"][rel]={"sha256":sha(out(rel)),"bytes":out(rel).stat().st_size}
  for rel in (COV,REPORT,INDEX):os.replace(out(rel),safe(rel))
  safe(MANIFEST).write_text(json.dumps(m,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
  STAGING=None
 print(json.dumps({"reviewed":len(m["visual_reviews"]),"pending":60-len(m["visual_reviews"])}))

def main():
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument("--overwrite",action="store_true",help="Refresh only unchanged, recorded 11B generated files")
 parser.add_argument("--verify",action="store_true",help="Read-only snapshot/output check")
 parser.add_argument("--record-reviewed",nargs="+",metavar="PNG_BASENAME",help="Record pages only after actual visual inspection")
 parser.add_argument("--reviewer",default="root")
 parser.add_argument("--review-note",default="Actual PNG inspected: panels, labels, missing states and full ranges checked.")
 args=parser.parse_args()
 if sum(bool(x) for x in (args.overwrite,args.verify,args.record_reviewed))>1:parser.error("Choose one operation")
 if args.verify:verify()
 elif args.record_reviewed:record_reviews(args.record_reviewed,args.reviewer,args.review_note)
 else:generate(args.overwrite)
if __name__=="__main__":main()
