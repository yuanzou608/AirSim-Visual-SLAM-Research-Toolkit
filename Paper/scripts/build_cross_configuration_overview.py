#!/home/yuan/anaconda3/bin/python3
"""Step 11C: frozen-table cross-configuration views, never an experiment runner."""
import argparse
from collections import Counter
import csv
import hashlib
import io
import json
import math
import os
from pathlib import Path
import sys
import tempfile
from datetime import date
from version_support import workspace, current_version, expected_inputs, check_version_history
from claim_review_support import apply_reviewed_rows

W=workspace(Path(__file__).resolve().parents[1])
VERSION=current_version(W)
SCENES=("building","houses","pool","road","roundabout")
HEIGHTS=(10,20,30);SPEEDS=(2,4,8);TOL=1e-12
M="derived_data/06_standardized/source_manifest.csv"
REC="derived_data/06_standardized/run_records.csv"
D="tables/07_eda/descriptive_summary.csv";S="tables/07_eda/sequence_metrics.csv"
J="tables/08_conditions/joint_metrics.csv";C="tables/08_conditions/conditional_contrasts.csv"
T="tables/10_relationships/within_configuration_tradeoffs.csv"
P="tables/11b_review/configuration_patterns.csv"
A="tables/11b_review/claim_applicability.csv";L="tables/11b_review/selection_rationale.csv"
CLAIMS="reports/11_claim_registry.csv"
SPEC="reports/11c_cross_configuration_spec.json"
REPORT="reports/11c_cross_configuration_review.md"
INDEX="reports/11c_overview_index.html"
MANIFEST="reports/11c_artifact_manifest.json"
ROOT="tables/11c_overview/"
TABLE_NAMES={"taxonomy":"configuration_taxonomy.csv","distribution":"distribution_summary.csv",
 "speed":"speed_response_matrix.csv","altitude":"altitude_response_matrix.csv",
 "coverage":"finite_coverage_matrix.csv","efficiency":"precision_efficiency_matrix.csv",
 "family":"family_pattern_candidates.csv","cases":"case_selection_review.csv"}
BASENAMES=["01_distribution_atlas","02_speed_response_matrix","03_altitude_response_matrix",
 "04_finite_coverage_matrix","05_precision_efficiency_matrix"]
FIGROOT="figures/11c_overview/"
OUTPUTS=[ROOT+n for n in TABLE_NAMES.values()]+[SPEC,REPORT,INDEX]+[
 FIGROOT+n+"."+e for n in BASENAMES for e in ("png","svg")]
SCRIPTS=["scripts/build_cross_configuration_overview.py","scripts/cross_configuration_taxonomy.py","scripts/claim_review_support.py",
 "scripts/cross_configuration_overview_plots.py","scripts/cross_configuration_overview_review.py","scripts/version_support.py",
 "scripts/review_all_configurations_narrative.py"]
CACHE={};STAGING=None;CHECKS={}
csv.field_size_limit(30_000_000)

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def js(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,allow_nan=False,separators=(",",":"))
def num(value):return None if value in (None,"") else float(value)
def close(a,b):
 if a in (None,"") or b in (None,""):return a in (None,"") and b in (None,"")
 return math.isclose(float(a),float(b),rel_tol=1e-12,abs_tol=1e-10)
def sign(v):
 v=num(v)
 return "unavailable" if v is None else "numeric_zero" if abs(v)<=TOL else "positive" if v>0 else "negative"
def safe(rel):
 p=Path(rel)
 if p.is_absolute() or ".." in p.parts:raise ValueError("Outside workspace")
 q=W
 for part in p.parts:
  q/=part
  if q.is_symlink():raise ValueError("Symlink rejected: "+str(q))
 if q.is_file() and q.stat().st_nlink!=1:raise ValueError("Hardlink rejected: "+str(q))
 if not q.resolve().is_relative_to(W):raise ValueError("Outside workspace")
 return q
def out(rel):
 if rel not in OUTPUTS:raise ValueError("Not an 11C output: "+rel)
 safe(rel)
 return STAGING/rel if STAGING else safe(rel)
def write(rel,text):
 p=out(rel);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text,encoding="utf-8")
def csv_text(rows):
 f=io.StringIO(newline="");keys=list(dict.fromkeys(k for r in rows for k in r))
 wr=csv.DictWriter(f,keys,lineterminator="\n");wr.writeheader()
 wr.writerows({k:"" if v is None else v for k,v in r.items()} for r in rows);return f.getvalue()
def table(rel):
 if rel not in INPUT_HASHES:raise ValueError("Undeclared input: "+rel)
 if rel not in CACHE:
  with safe(rel).open(encoding="utf-8",newline="") as f:CACHE[rel]=list(csv.DictReader(f))
 return CACHE[rel]
def ref(path,**key):return {"table":path,"key":key}
def joint_key(r):
 return ref(J,configuration_id=r["configuration_id"],scene=r["scene"],altitude_m=str(r["altitude_m"]),
   speed_mps=str(r["speed_mps"]),metric="rmse",aggregation_level="equal_weight_sequence_means")
def metadata(t):
 return {k:t[k] for k in ("configuration_id","source_method_directory","method_display_name",
 "configuration_display_name","row_order","base_modality","semantic_usage","display_input_group",
 "algorithm_family","evaluation_scope")}
def check_inputs():
 check_version_history(W)
 for p,h in INPUT_HASHES.items():
  if sha(safe(p))!=h:raise ValueError("Frozen input changed: "+p)
 return {p:{"sha256":h,"bytes":safe(p).stat().st_size} for p,h in INPUT_HASHES.items()}
def check_history():
 if check_version_history(W):return {"verified_version_backup_and_protected_history":True}
 for p,h in HISTORICAL_HASHES.items():
  data=safe(p).read_bytes()
  if p in APPEND_ONLY_PREFIX_BYTES:data=data[:APPEND_ONLY_PREFIX_BYTES[p]]
  if hashlib.sha256(data).hexdigest()!=h:raise ValueError("Historical file changed: "+p)
 return len(HISTORICAL_HASHES)
def preflight(overwrite=False):
 for p in OUTPUTS+[MANIFEST]:safe(p)
 existing=[p for p in OUTPUTS+[MANIFEST] if safe(p).exists()]
 if not existing:return None
 if not safe(MANIFEST).is_file():raise ValueError("Unrecorded existing output; preserve: "+", ".join(existing))
 if not overwrite:raise ValueError("Default refuses overwrite; review files before --overwrite")
 m=json.loads(safe(MANIFEST).read_text())
 if set(m["outputs"])!=set(OUTPUTS):raise ValueError("Output allowlist changed")
 for p,r in m["outputs"].items():
  if not safe(p).is_file() or sha(safe(p))!=r["sha256"]:raise ValueError("Manual edit/missing output: "+p)
 return m

def member_audit(sequences,within):
 """Only audit members used by plotted summaries; do not recompute their means/ranks."""
 record_rows=table(REC)
 records={(r["source_relative_path"],r["source_record_index"]):r for r in record_rows}
 assert len(records)==len(record_rows),"Duplicate source record keys"
 retained_keys=set();paired_keys=set()
 verified=0
 for r in sequences.values():
  path=r["source_relative_path"]
  ids=json.loads(r["source_record_indices_json"]);finite_ids=json.loads(r["finite_source_record_indices_json"])
  members=[records[path,str(i)] for i in ids]
  assert len(ids)==int(r["n_retained_runs"])
  assert all(x["configuration_id"]==r["configuration_id"] and x["sequence_raw"]==r["sequence_raw"] and
    x["condition_label_status"]=="two_tokens" and x["source_sha256"]==r["source_sha256"] for x in members)
  actual=[x for x in members if x["rmse_is_finite"]=="True"]
  assert [int(x["source_record_index"]) for x in actual]==finite_ids
  assert len(actual)==int(r["n_finite_runs"])
  assert all(close(x["rmse_value"],v) for x,v in zip(actual,json.loads(r["finite_values_json"])))
  verified+=len(members)
  retained_keys.update((x["source_relative_path"],x["source_record_index"]) for x in members)
 paired=0
 for r in within:
  if r["row_type"]!="sequence_joint_means":continue
  retained=json.loads(r["retained_members_json"]);joint=json.loads(r["joint_members_json"])
  metric=r["efficiency_metric"]
  expected={(x["path"],x["index"]) for x in retained if records[x["path"],str(x["index"])]["rmse_is_finite"]=="True"
     and records[x["path"],str(x["index"])][metric+"_is_finite"]=="True"}
  assert expected=={(x["path"],x["index"]) for x in joint}
  assert len(joint)==int(r["n_joint_finite"])
  key=(r["configuration_id"],r["sequence_raw"],metric)
  assert key not in paired_keys;paired_keys.add(key)
  paired+=1
 CHECKS["standardized_member_checks"]={"sequence_rows":len(sequences),"retained_members":verified,
  "same_finite_run_intersections":paired,"reason":"Trace exact members displayed in ECDFs/condition cells/efficiency views; no new aggregation"}
 primary_keys={k for k,r in records.items() if r["condition_label_status"]=="two_tokens"}
 assert retained_keys==primary_keys and verified==len(primary_keys)
 assert paired_keys=={(c,name,m) for c,name in sequences for m in ("fps","runtime","memory")}
 assert paired==len(sequences)*3
 CHECKS["standardized_member_checks"]["all_retained_records"]=len(records)

def extract():
 from cross_configuration_taxonomy import build_taxonomy
 tax=build_taxonomy(table(M));byid={r["configuration_id"]:r for r in tax}
 assert len(tax)==24 and [r["row_order"] for r in tax]==list(range(1,25))
 patterns={r["configuration_id"]:r for r in table(P)}
 seq={(r["configuration_id"],r["sequence_raw"]):r for r in table(S) if r["metric"]=="rmse" and r["subset"]=="condition_labelled"}
 summaries={r["configuration_id"]:r for r in table(D) if r["metric"]=="rmse" and r["subset"]=="condition_labelled"
  and r["group_type"]=="overall" and r["aggregation_level"]=="equal_weight_sequence_means"}
 # Saved tables use an explicit overall scene marker, regardless of group label spelling.
 if len(summaries)!=24:
  summaries={r["configuration_id"]:r for r in table(D) if r["metric"]=="rmse" and r["subset"]=="condition_labelled"
   and r["scene"]=="__all__" and r["aggregation_level"]=="equal_weight_sequence_means"}
 assert len(summaries)==24
 joint={(r["configuration_id"],r["scene"],int(r["altitude_m"]),int(r["speed_mps"])):r for r in table(J)
  if r["metric"]=="rmse" and r["aggregation_level"]=="equal_weight_sequence_means" and r["scene"] in SCENES}
 assert len(joint)==1080
 contrasts={(r["configuration_id"],r["scene"],r["contrast_kind"],r["direction"],r["fixed_value"]):r
  for r in table(C) if r["metric"]=="rmse" and r["aggregation_level"]=="equal_weight_sequence_means"}
 member_audit(seq,table(T))
 distribution=[];speed=[];altitude=[];coverage=[];efficiency=[]
 within={r["row_id"]:r for r in table(T)}
 for t in tax:
  c=t["configuration_id"];p=patterns[c];r=summaries[c]
  sr=sorted([v for (cf,name),v in seq.items() if cf==c],key=lambda r:r["sequence_raw"])
  finite=[x for x in sr if num(x["mean"]) is not None]
  assert len(sr)==int(r["n_observed_sequences"]) and len(finite)==int(r["n_sequences_with_finite"])
  ds={**metadata(t),"subset":"condition_labelled","aggregation_level":"equal_weight_sequence_means",
   "n_finite_sequences":len(finite),"n_observed_sequences":len(sr),
   "n_retained_records":int(r["n_retained_records"]),"n_finite_records":int(r["n_finite_records"]),
   **{k:num(r[k]) for k in ("mean","median","q25","q75","p90","min","max")},
   "status":"computed" if len(finite)>=2 else "insufficient_sequences" if finite else "all_nonfinite",
   "finite_sequence_values_json":js([num(x["mean"]) for x in finite]),
   "sequence_members_json":js([{"sequence_raw":x["sequence_raw"],"mean":num(x["mean"]),
     "n_retained":int(x["n_retained_runs"]),"n_finite":int(x["n_finite_runs"]),
     "source_relative_path":x["source_relative_path"],"source_sha256":x["source_sha256"],
     "finite_source_record_indices":json.loads(x["finite_source_record_indices_json"]),
     "evidence":ref(S,configuration_id=c,sequence_raw=x["sequence_raw"],metric="rmse")} for x in sr]),
   "evidence_key_json":js(ref(D,configuration_id=c,subset="condition_labelled",scene="__all__",
                             metric="rmse",aggregation_level="equal_weight_sequence_means")),
   "source_measurement_limit":r["measurement_limit"]}
  for field,pfield in [("mean","rmse_sequence_mean"),("median","rmse_sequence_median"),("p90","rmse_sequence_p90"),("max","rmse_sequence_max")]:
   assert close(ds[field],p[pfield])
  # Display descriptors of saved scalars; no threshold, reweighting, trimming or changed population.
  ds["mean_median_gap"]=None if ds["mean"] is None else ds["mean"]-ds["median"]
  ds["mean_to_median_ratio"]=None if ds["median"] in (None,0) else ds["mean"]/ds["median"]
  ds["p90_to_median_ratio"]=None if ds["median"] in (None,0) else ds["p90"]/ds["median"]
  ds["ratio_interpretation"]="shape descriptors only; no tail/close threshold or cross-method absolute ranking"
  distribution.append(ds)
  for scene in SCENES:
   for h in HEIGHTS:
    for v in SPEEDS:
     q=joint[c,scene,h,v];nr=int(q["n_retained_records"]);nf=int(q["n_finite_records"]);fr=num(q["finite_fraction"])
     assert close(fr,None if not nr else nf/nr)
     assert (q["cell_state"]=="no_retained_records")==bool(not nr)
     coverage.append({**metadata(t),"scene":scene,"altitude_m":h,"speed_mps":v,"n_finite_records":nf,
      "n_retained_records":nr,"n_finite_sequences":int(q["n_sequences_with_finite"]),
      "n_observed_sequences":int(q["n_observed_sequences"]),"finite_fraction":fr,"cell_state":q["cell_state"],
      "sequence_members_json":q["sequences_json"],"finite_sequences_json":q["finite_sequences_json"],
      "source_record_indices_json":q["source_record_indices_json"],
      "finite_source_record_indices_json":q["finite_source_record_indices_json"],
      "source_relative_path":q["source_relative_path"],"source_sha256":q["source_sha256"],
      "evidence_key_json":js(joint_key(q))})
   for axis,fixeds,target in (("speed",HEIGHTS,speed),("altitude",SPEEDS,altitude)):
    triples={(x["scene"],int(x["fixed_value"])):x for x in json.loads(p[axis+"_triples_json"])}
    oldends={(x["scene"],int(x["fixed_value"])):x for x in json.loads(p[axis+"_endpoints_json"])}
    for fixed in fixeds:
     rows=[joint[c,scene,fixed,v] for v in SPEEDS] if axis=="speed" else [joint[c,scene,h,fixed] for h in HEIGHTS]
     values=[num(q["mean"]) for q in rows];tr=triples[scene,fixed];oldend=oldends[scene,fixed]
     assert all(close(a,b) for a,b in zip(values,tr["values"]))
     direction="8 - 2" if axis=="speed" else "30 - 10"
     old=contrasts[c,scene,axis+"_difference",direction,str(fixed)];difference=num(old["difference"])
     assert close(difference,None if values[0] is None or values[2] is None else values[2]-values[0])
     assert close(difference,oldend["value"])
     endpoint_direction=sign(difference)
     assert endpoint_direction==oldend["direction"].replace("numerical_zero","numeric_zero")
     reasons=[label+":"+q["cell_state"] for label,q in zip(("low","high"),(rows[0],rows[2]))
              if q["cell_state"] in ("no_retained_records","observed_all_nonfinite")]
     state=endpoint_direction
     if state=="unavailable":
      state="no_retained_records" if any("no_retained_records" in x for x in reasons) else (
       "observed_all_nonfinite" if reasons else "unavailable")
     target.append({**metadata(t),"scene":scene,"fixed_axis":"altitude_m" if axis=="speed" else "speed_mps",
      "fixed_value":fixed,"endpoint_difference":difference,"endpoint_direction":endpoint_direction,"display_status":state,
      "missing_reasons_json":js(reasons),"source_contrast_status":old["status"],"source_unavailable_reason":old["unavailable_reason"],
      "triple_shape":tr["classification"].replace("numerically_flat","numeric_flat"),
      "source_triple_classification":tr["classification"],"three_level_values_json":js(values),
      "three_level_states_json":js([q["cell_state"] for q in rows]),
      "finite_fraction_difference_pp":num(old["finite_fraction_difference_pp"]),
      "endpoint_counts_json":js([{k:q[k] for k in ("n_retained_records","n_finite_records","n_observed_sequences","n_sequences_with_finite")} for q in (rows[0],rows[2])]),
      "endpoint_members_json":old["endpoints_json"],"three_level_evidence_keys_json":js([joint_key(q) for q in rows]),
      "evidence_key_json":js(ref(C,configuration_id=c,scene=scene,metric="rmse",aggregation_level="equal_weight_sequence_means",
        contrast_kind=axis+"_difference",direction=direction,fixed_value=str(fixed))),
      "shape_evidence_key_json":js({"table":P,"key":{"configuration_id":c},"field":axis+"_triples_json","scene":scene,"fixed_value":fixed}),
      "measurement_limit":old["measurement_limit"]})
  for metric in ("fps","runtime","memory"):
   for scene in ("__all_scenes__",)+SCENES:
    r=within[f"{c}|{metric}|correlation|{scene}"]
    assert r["row_type"]=="rank_correlation"
    oldmatch=[x for x in json.loads(p["efficiency_relations_json"]) if x["metric"]==metric and x["scene"]==scene]
    assert len(oldmatch)==1 and close(r["rho"],oldmatch[0]["rho"])
    status=r["status"];rho=num(r["rho"])
    assert status in ("computed","constant_input","insufficient_sequences","unavailable","incompatible")
    assert (rho is not None)==(status=="computed")
    members=json.loads(r["used_sequence_row_ids_json"])
    assert len(members)==int(r["n_sequences"])
    assert sum(int(within[key]["n_joint_finite"]) for key in members)==int(r["n_joint_finite"])
    efficiency.append({**metadata(t),"efficiency_metric":metric,"scene":scene,"rho":rho,"status":status,
     "reason":r["reason"],"n_sequences":int(r["n_sequences"]),"n_joint_finite":int(r["n_joint_finite"]),
     "n_observed_sequences":int(r["n_observed_sequences"]),"constant_A":r["constant_A"],"constant_B":r["constant_B"],
     "n_unique_A":r["n_unique_A"],"n_unique_B":r["n_unique_B"],
     "sequence_members_json":r["members_json"],"used_sequence_row_ids_json":r["used_sequence_row_ids_json"],
     "unavailable_sequence_row_ids_json":r["unavailable_sequence_row_ids_json"],
     "evidence_key_json":js(ref(T,row_id=r["row_id"])),"rmse_limit":r["rmse_limit"],"efficiency_limit":r["efficiency_limit"],
     "same_finite_run_intersection":True,"repetition_provenance_unresolved":r["repetition_provenance_unresolved"]})
 data={"taxonomy":tax,"distribution":distribution,"speed":speed,"altitude":altitude,"coverage":coverage,"efficiency":efficiency,
   "patterns":[patterns[t["configuration_id"]] for t in tax],"old_claims":table(CLAIMS),
   "old_selections":table(L),"old_applicability":table(A),"controlled_input_update":bool(VERSION),
   "input_update_policy":(VERSION or {}).get("update_policy",{})}
 assert [len(data[k]) for k in ("taxonomy","distribution","speed","altitude","coverage","efficiency")]==[24,24,360,360,1080,432]
 for axis,historical_expected in [("speed",{"positive":273,"negative":65,"unavailable":22}),("altitude",{"positive":121,"negative":213,"unavailable":26})]:
  actual=Counter(r["endpoint_direction"] for r in data[axis])
  expected={k:sum(int(p[axis+"_endpoint_"+("numerical_zero" if k=="numeric_zero" else k)]) for p in patterns.values())
    for k in ("positive","negative","numeric_zero","unavailable")}
  assert all(actual[k]==n for k,n in expected.items())
  if VERSION is None:assert dict(actual)==historical_expected
  CHECKS[axis+"_endpoint_states"]=dict(Counter(r["display_status"] for r in data[axis]))
  CHECKS[axis+"_triple_shapes"]=dict(Counter(r["triple_shape"] for r in data[axis]))
 CHECKS["counts"]={k:len(data[k]) for k in ("taxonomy","distribution","speed","altitude","coverage","efficiency")}
 CHECKS["coverage_states"]=dict(Counter(r["cell_state"] for r in coverage))
 CHECKS["correlation_states"]=dict(Counter(r["status"] for r in efficiency))
 CHECKS["input_groups"]=dict(Counter(t["display_input_group"] for t in tax))
 CHECKS["actual_source_methods"]=len({t["source_method_directory"] for t in tax})
 assert CHECKS["input_groups"]=={"Mono":14,"RGB-D":8,"RGB-D + Semantic":2}
 assert {t["configuration_id"] for t in tax if t["semantic_usage"]=="yes"}=={"SGS-SLAM::semantic","hierslam::semantic_500"}
 CHECKS["same_version_upstream_numeric_values_matched"]=True
 CHECKS["current_version_manifest"]="reports/current_input_manifest.json" if VERSION else None
 CHECKS["accuracy_protocol_by_configuration"]={r["configuration_id"]:{k:r.get(k,"")
  for k in ("source_sha256","rmse_unit_status","alignment_status","input_version")} for r in table(M)}
 return data

INPUT_HASHES={
  "derived_data/06_standardized/run_records.csv": "f73b70914b7f60bfcad03f92e799631da679d43aaa893316c6b3514d27a054db",
  "derived_data/06_standardized/source_manifest.csv": "34d7cea320aa53e2b5dc6124bdc1971d0ed8d6ce7917fbccf25423dd6aa2ba5e",
  "derived_data/06_standardized/schema.json": "6ebb38d127ec556c6da5a93fd8f4ef93faf0a70c3960662e8379959cf63dbe90",
  "tables/07_eda/descriptive_summary.csv": "24588a099afb73b4863c7ea9f06dfbc6b93c63495a9f05347c25b2f4b7922b7e",
  "tables/07_eda/sequence_metrics.csv": "0459ebab01c89e59bcc208e7e5ff8963dad7bd6710061cf4e1e17beecf45bf91",
  "tables/08_conditions/joint_metrics.csv": "6b34a00ac0e655b0c4c7acd5416a31a26842b9397798e8763f2506070bfbec74",
  "tables/08_conditions/conditional_contrasts.csv": "f4eece936b3e1108c91a8506bb05ff213f417a0e7588e47f63ed0a70135d2bc8",
  "tables/09_robustness/sensitivity_estimates.csv": "8bfd9440c0582f9cea82b34b79a8dee2bf199d33bd9d45a6c018c1fb0fb944a2",
  "tables/10_relationships/within_configuration_tradeoffs.csv": "ebe2d124345a2ed5a3378abf108215295ce919e8ff9d0a55988c90d9e9cd5c9a",
  "tables/11b_review/configuration_patterns.csv": "4cba7fc870cf2c1ca12ab70ec9d163d012a5c3452d11b9bcda827c80cd46d6ac",
  "tables/11b_review/claim_applicability.csv": "88c99c43c827ab6ca5a9bf95845cf1dd734833d1175395f0f526fc0cd4840503",
  "tables/11b_review/selection_rationale.csv": "d27ee08b5b79097c97be581945953f15c360e0c0684e8832421985fd23ba4c5e",
  "reports/11b_all_configuration_review.md": "3ac45a1c6b4c08d456dbce7b1c25c170c68f94bf5ef80fa715ba1070d748ef4f",
  "reports/11b_review_spec.json": "6181484466e4dc26fe2c099ee234e1ad1a768538e3dbbb6df19673e59d13ac7c",
  "reports/07_exploration_spec.json": "0f6790a086e494d479dccaaa299728b6a80760e8c5df299072ea726c65b47502",
  "reports/08_condition_analysis_spec.json": "d7146979a097f61a39c317bf3f568b40f5b348edcb7f6b697c1e83ad3361d98a",
  "reports/10_relationship_spec.json": "ee3f990151675ee661d99463cd3058efd4ca34b8e68aa2c9b0cd15c0f4a12c86",
  "reports/11_claim_registry.csv": "d7518ba2d7b73e311432ed55bf69b79fd6c8a373f3c947e7e28ae65c23f9567d",
  "reports/11_paper_synthesis.md": "4ccef7590d0346a882a822e1490d63f08db43c0a9187613e8ea56a24f8a165fa"
}
INPUT_HASHES=expected_inputs("11C",INPUT_HASHES,W)
HISTORICAL_HASHES={
  "AGENTS.md": "e73dfd095942b9a63bc12431d2977949eff30cf58253f2460a9ac8fbf91da7ca",
  "PROJECT_STATUS.md": "24842642c3314ecd19226dc713a6061935f0a4be8204359d42361775d24be181",
  "README.md": "23df60bdfea0dd1349d24e19ea922efe6e9b7701de0b0659a7b20459ac520775",
  "derived_data/05_dpvo_pilot/run_records.csv": "b8bce3f7e3cf3b435dac537dcce3f599af44ed95e04cf34921e80fe79ceec012",
  "derived_data/06_standardized/run_records.csv": "f73b70914b7f60bfcad03f92e799631da679d43aaa893316c6b3514d27a054db",
  "derived_data/06_standardized/schema.json": "6ebb38d127ec556c6da5a93fd8f4ef93faf0a70c3960662e8379959cf63dbe90",
  "derived_data/06_standardized/source_manifest.csv": "34d7cea320aa53e2b5dc6124bdc1971d0ed8d6ce7917fbccf25423dd6aa2ba5e",
  "figures/07_eda/01_rmse_distribution.png": "8047ca9bafc84be42d2610f89244e2b00a0e083e5341f95b8e1a3f7eab49fe6d",
  "figures/07_eda/01_rmse_distribution.svg": "a7925916704ca5f517114d88a60bd6509a704d1271aa9e2304ad326c2911a8c2",
  "figures/07_eda/02_scene_rmse.png": "69e234ae8eee8a684125240f6b52b0a0b59d742faab4edfb8b483018a9a4177e",
  "figures/07_eda/02_scene_rmse.svg": "34d22f590acd8ab5638f6d28b167e3eddf99dceeb864f41855b491cf8682cb64",
  "figures/07_eda/03_repeat_rmse.png": "281111baee5110d8e37ea1a1586163e4ffd79d68957d9c940b32fc6fe416589a",
  "figures/07_eda/03_repeat_rmse.svg": "d3448176f4970c5b407313fa730aac44080a33e53a4977376aff27565e50f45c",
  "figures/07_eda/04_finite_rmse_fraction.png": "e21651e339405c25d81e304b5c439df3bfc28b0e031b25e229aa205e55ce14a2",
  "figures/07_eda/04_finite_rmse_fraction.svg": "643b986f8f8fb092ede65df27cc81553cf17d6db6dd04eaa68df7662883f99c1",
  "figures/07_eda/05_efficiency_cohorts.png": "9ff1e5dcafff66b732181ec97f626e8b4c4acde67f9c0015863ed8b7dc470c77",
  "figures/07_eda/05_efficiency_cohorts.svg": "a9e0fb3fd523beb2609ef14343d0461314831442bfc13f10bf26e59de5ca437a",
  "figures/08_conditions/01_orb2_condition_rmse.png": "5d80e66a95c2e7469c7d85b77fa1b1cb1f8f3ff15120e4fa12dcdcffeb6b6354",
  "figures/08_conditions/01_orb2_condition_rmse.svg": "93a6cbf59c6b3ca62c9832d320de0b9a8c2278db93991d3bd5cde2ef8212a206",
  "figures/08_conditions/02_orb2_speed_curves.png": "ea2cdafdaa0b8fdcd52d69b537b443ff407a51055ce04a965bdfe851828a45da",
  "figures/08_conditions/02_orb2_speed_curves.svg": "c2d21e727034fb6b5600b31fa38acec84d01460206bfa16a17b7ab3f755ad09d",
  "figures/08_conditions/03_droid_pool_conditions.png": "cdd74b67c33e27d6b322be5b54cdbaa653d8e03576000fae78f28befa0f88acc",
  "figures/08_conditions/03_droid_pool_conditions.svg": "ec13dcb9ac3c306f575da930abd82f37e7b6be5cf85add06a1873a93a6e23db8",
  "figures/08_conditions/04_orb3_condition_rmse.png": "75464b72235bbbb632eecae5e0b9e9669906a4496a1628d675176748feaf2f7c",
  "figures/08_conditions/04_orb3_condition_rmse.svg": "1a2d1b75018bf0441ce665f53e9e6fe63bd3e234992e5e9ab6565faff0cbf35f",
  "figures/08_conditions/05_orb3_retained_repeats.png": "6f04b70d1f3e626066ffcc77f2b6bb0e8fcf59f089405be45442ee4236b73f49",
  "figures/08_conditions/05_orb3_retained_repeats.svg": "ea2db05e1b4c76e4debec9323a26fb36483ae7abddc018346b35e0484dae6ecd",
  "figures/08_conditions/06_vggt_coverage_rmse.png": "05455320c5d7321bee6f59478efd0a7b2e12f0a68116d38715395c709ef1a66f",
  "figures/08_conditions/06_vggt_coverage_rmse.svg": "7728dc35d63ef61c6422342cdb5fe023500c2f9f69354191ae3d6db983400822",
  "figures/08_conditions/07_hier_runtime_cohorts.png": "346440e43bbe9d49e8e3f319f5e88a0a3f53566178ef6112f079bf747a0be3ec",
  "figures/08_conditions/07_hier_runtime_cohorts.svg": "cdaebd18bef2c85f8cae6a573ff11c5357c887a0eff199b023a436e53098ada2",
  "figures/09_robustness/01_dpvo_scene_cancellation.png": "542e8f3d65e7205830b501f35e49cda8370a173f29787a8fd011a41640876b42",
  "figures/09_robustness/01_dpvo_scene_cancellation.svg": "658827c3ce36784e4a0fe66e0b40615d2165db6f98b7249a3e996ec7399dee1a",
  "figures/09_robustness/02_orb2_local_sensitivity.png": "ddf5af9e5a35f0d0202c6173cc86c33c20a193bd8b8df249da36fdcbdceedb81",
  "figures/09_robustness/02_orb2_local_sensitivity.svg": "64499ac00560d656c43d66558771bc239fcbea4cada21f306340227ca6c55e5c",
  "figures/09_robustness/03_orb3_repeat_influence.png": "c41d68d5ea175e1d50a6e91fd2884297dfaac3a6fcd5b5b7d7e194e238ad7887",
  "figures/09_robustness/03_orb3_repeat_influence.svg": "533c5d32797c4c9f57bd5cff51147a6927c7c87541cb9141fa4f070ce1349db5",
  "figures/09_robustness/04_vggt_support_views.png": "8ab7587fb7575f3b8d59a594a60a1111d2bb294207b6feafc23a1d0ab0bd7baa",
  "figures/09_robustness/04_vggt_support_views.svg": "7505af1b82ae719f806cc71bf7241781a0cec510c7550e130cd3af7e8a1e484b",
  "figures/09_robustness/05_hier_runtime_decomposition.png": "d9d2ae00465a534a6ea75a63e199c4470d99e393e5de3e0b5eee7f43ef975f06",
  "figures/09_robustness/05_hier_runtime_decomposition.svg": "1fd06a701d5983ef9482f569f09bcf6cff95dae3f2d9333d3ca4a84a3e3c05d6",
  "figures/10_relationships/01_focus_rank_positions.png": "bb5cb12ad3e2afcda90b555ef424b6dbdb9f28bb08d122c20eaac285d1659f7b",
  "figures/10_relationships/01_focus_rank_positions.svg": "bcd597605db5625eccd0b152304e249c264838eeaf82883c4e6dc4d553319550",
  "figures/10_relationships/02_focus_support_scene_rho.png": "1ce2beba69022c5061cf45eb9d5941fbb5dc5c9a3c9a3bda4f499e5551cd5a60",
  "figures/10_relationships/02_focus_support_scene_rho.svg": "c327f18a914fb70c8350f7ce837312f1e1eb7f2b32b7084cc4f03d7acd1b0224",
  "figures/10_relationships/03_focus_availability.png": "f57e8bc763e76309d2aedd8b91d3812d5d0863eb0e661ac9223c4cc92f58ef1d",
  "figures/10_relationships/03_focus_availability.svg": "ed6fa2961499c1144245067839edaa42624c28dff8756771d659f6134a2d6cce",
  "figures/10_relationships/04_within_configuration_rho.png": "ffcda1b13ce30bd2d733d952f25f0c832db71aa3f68b74ef5fb529aa161e91cb",
  "figures/10_relationships/04_within_configuration_rho.svg": "f0297dcfd8883e4315dac6ec691cd1b398c138e7112df0ceaeba4d41c868a7af",
  "figures/10_relationships/05_same_run_tradeoffs.png": "cbcfbbd5a70ddf74ab6829ef0809c13117e84b12eb0513086760e2fcb285b2ff",
  "figures/10_relationships/05_same_run_tradeoffs.svg": "44fbaae0aa13d34ac45a5fd3143c86094458dd1bf4398f581feff35d32cfd4af",
  "figures/11_paper/01_orb_condition_response.png": "e75a2ce8bdeded538987c253a784f45543ab7bb61990f89252a0138252df4c6b",
  "figures/11_paper/01_orb_condition_response.svg": "b8c88fde197998d1a327513d06357c5586245e209b2dd77732d0f8cdda2c992a",
  "figures/11_paper/02_dpvo_scene_composition.png": "59f4593bebbb87ebb3d16eacb90a0b386e3275bfa6bddac2e747950130dcfe35",
  "figures/11_paper/02_dpvo_scene_composition.svg": "76b090290b9959b320ec9b3cf18c10d994f1f8b3b4aca6306750aff55b3d6033",
  "figures/11_paper/03_hier_joint_association.png": "3bff4796d33a9e307132f80e77be3a83e475e8f1892a177c65f12ccb1055b00e",
  "figures/11_paper/03_hier_joint_association.svg": "50ce110a6cca51eecf8bfd1a7bcbb289805dd6aba6fcfd6d70bac55e8d2a401d",
  "figures/11b_review/c01_grid.png": "f20a31f5d0e4a021b75f8c034227999fcd86aa2dfabf90edbedb87d26740cd9f",
  "figures/11b_review/c01_grid.svg": "aa2044a802089cc17d5c3ea740b8734f6d73a6addb8d2b0ec9abc92bc3676cbf",
  "figures/11b_review/c01_response.png": "60e1f8bb4d70fa32e79c00d1af31945c726c4b4abe32be2f04c26818d004e7ed",
  "figures/11b_review/c01_response.svg": "74c376cca01b22a8246503b8e6762fa084d8ed1be5af0a6f4f12f48dbde4bec9",
  "figures/11b_review/c02_grid.png": "1a5c277981a58228e7dfd168c17e561e0d2a3f2a3820bc7a69b19eebbdbb44a0",
  "figures/11b_review/c02_grid.svg": "06dd930e68bc922b349e477f49bb509c84c0c175778c8b8a8adf4373f549ed05",
  "figures/11b_review/c02_response.png": "dd8726ac604b17856bc3f5098b67e10c772c22fa3df3fc8cea349fa9049d6bb1",
  "figures/11b_review/c02_response.svg": "91467360630d0c34d77abf80cd41f9a07992f02e9bc0db70ccd5979c551bc5ca",
  "figures/11b_review/c03_grid.png": "55b61799553643ba4e7c9f1d523270e506613bd59c6ce8851d2ef6f4a01110c9",
  "figures/11b_review/c03_grid.svg": "7b56841bcf11646ca94088757a00c973165db0d4abb7c818984a58d8351f105e",
  "figures/11b_review/c03_response.png": "c354663047b7a7aa14a70e7ab4693f0b528a2ff69b2e464b94ecdf273a4bc693",
  "figures/11b_review/c03_response.svg": "76b8c800dd47782e9b0d023e4aa335bf135e17f6a5cbca684ae45ae09a92fb2c",
  "figures/11b_review/c04_grid.png": "813c798a6f7741fa05a746e66c1fb045adcfa21621303bf7b14ba3d42a2a832b",
  "figures/11b_review/c04_grid.svg": "a97e1234c21d05d765f2e3e6e9c5b4b1d4907f15e9cfdad4d61de31cb9d71978",
  "figures/11b_review/c04_response.png": "6b0ce528a2dca30a94d679beec9070a096c8d90c4ce5315aefacb0f261f277a4",
  "figures/11b_review/c04_response.svg": "f582a63494b6da98d98414819dff806c395303177e7c9a9f610361027d45a0d6",
  "figures/11b_review/c05_grid.png": "7700ef7be6a812bda3f8e2d0602842e3ec6f3a7d89aceedca9ef421cd4583109",
  "figures/11b_review/c05_grid.svg": "f833ac5ab17a1121942b1ad1fdc2ebcc611c992f6e7a5cb55d37ed8f92db0fdd",
  "figures/11b_review/c05_response.png": "b20583d5bb49edc4bcd48e3de615870f9825fcf379a238ea02b84848389c1264",
  "figures/11b_review/c05_response.svg": "64b1572e4c423b323c6e56b833c42c4485980b7f64bc9fa16395f3bf3c325d54",
  "figures/11b_review/c06_grid.png": "81e76bf23ccc30a405b25ee95b567dd665301e8e63fbbe1da2d3b8cc4fb9ac2f",
  "figures/11b_review/c06_grid.svg": "4c8494439b9df16d30c2134c22e4a2686637b14603368a73f3f7844a645fcbd1",
  "figures/11b_review/c06_response.png": "db1adfb33dc90c79036aa7555962c3b203dc261144f885bff7ddf4400dce8fe7",
  "figures/11b_review/c06_response.svg": "643f11d2d8be78d3248a651488806376297667488fc7783dfdf7353ded97af51",
  "figures/11b_review/c07_grid.png": "7bdbe5da10834bb157efb8ded759a14175991ec81f2a06b3623746d31a57c016",
  "figures/11b_review/c07_grid.svg": "d4dc5e915c460ae6a676ae42074ac2bb4d6bae860f07311ee9ec52e3a7e1ced7",
  "figures/11b_review/c07_response.png": "1f8d29fe9a8d8c40ab5c610c3c6dc20d4d4ada07f532f921c74afef059421baa",
  "figures/11b_review/c07_response.svg": "2e2e66449b5062abe86259b85998348783e4418e800e3f46044c9c1585061bbf",
  "figures/11b_review/c08_grid.png": "33a38de347f8a03866d8d735a9e13cf155e7d76d699f290dc13e34ea2fa7efcb",
  "figures/11b_review/c08_grid.svg": "6d24cc3019faee3b4a0a3966c2cdf2b158310ff8d6eb7f1f6ca3831443267222",
  "figures/11b_review/c08_response.png": "c642afd6bd90c9f8fcf149caf48d16d30177069b3faac15bf4f29645290e2c76",
  "figures/11b_review/c08_response.svg": "75bf4564aeb34579e5677d1ac994e8d2713a7e1b8d525004ddcf4a74585becf6",
  "figures/11b_review/c09_grid.png": "2c2d343957a03a13750ad006617a73d5559c829acaaaed61c5d2f1a5288f42b7",
  "figures/11b_review/c09_grid.svg": "a243d1d33f8b554b5ba10e97cfdd152c6f56ed5bc5708dac4304f24605fd9aa6",
  "figures/11b_review/c09_response.png": "4e76e749ae33f2a061f2cb35a53430b9a6e035b2e1f95d3f990871b42d6126aa",
  "figures/11b_review/c09_response.svg": "96a9b4bed4dc2ae4b8b29fe570df647d395e2b374e1b767cb6434017e179e606",
  "figures/11b_review/c10_grid.png": "3eb6a6c8253ba106572f6e53760839518c3106db5b08065e888ac8d398ae760f",
  "figures/11b_review/c10_grid.svg": "35b6d568aca3399f9b260d7850178b45c2b59ff4b9d53d1f0b33b8138d76cf7c",
  "figures/11b_review/c10_response.png": "3d73a9c155e3b1d3174580cca57d7880fb8744623dcf4938105cc1c22920ed23",
  "figures/11b_review/c10_response.svg": "b4021ccba106d16ac26cc65cccaa0651721fbe1cae7cdb6acd9011852fd1a4f8",
  "figures/11b_review/c11_grid.png": "55c7e740b7f6e4376de807b4b2b93f69d51fda904bc703b16b3d3de0da79f4b0",
  "figures/11b_review/c11_grid.svg": "6d2a557907e9edd61f8d3e16935dc0c62de64656ded066fc2b2016bd55be935d",
  "figures/11b_review/c11_response.png": "6a50a64491fca26cdfff7755c0a23e1f426e78045a474b5e08f182a2950e273b",
  "figures/11b_review/c11_response.svg": "c009d7f7bd3788ec3f551e5d5b02eef146ffffb11e85633bb0e6217d22d6cf79",
  "figures/11b_review/c12_grid.png": "0a3b2b10987a23f8fa123a021afceffab368cf996888c10a4dd72542488b3967",
  "figures/11b_review/c12_grid.svg": "ad76dc54cd421018b7da1aab20253bd7d017814438c3a2976d5a8a78ea15f9a0",
  "figures/11b_review/c12_response.png": "c29a997b2157ac8105672cad5510aa164b000960fc6b82958cdca4554fad4883",
  "figures/11b_review/c12_response.svg": "7b43ca7c17618cb8ef2799921eee37d83e33a9685019b62597d1392d254d9932",
  "figures/11b_review/c13_grid.png": "432e42ecaf05922d8bc41bf41193537579e74f1423f73b13e205f0012289f72c",
  "figures/11b_review/c13_grid.svg": "601b076f1b79db2da7cecbc5244ff7c3549b77541de747b6e791b919184bc6f5",
  "figures/11b_review/c13_response.png": "c26e79dbec9db5797c46376cc4f313834b2447eff63a70c8020c2230870c3b15",
  "figures/11b_review/c13_response.svg": "27d5047834d9634777e9e88a96b1215ae7207c1313999bdc6ea3a4463a370a5c",
  "figures/11b_review/c14_grid.png": "d73e1529898c891ff64340f8c8115aa82dc96ed289f0c6b21f0e180bbfc6a9b3",
  "figures/11b_review/c14_grid.svg": "81376bba5ca799e278db134099b810f4abb7e38172c9479aaa5a603f3cdd7211",
  "figures/11b_review/c14_response.png": "7c02740acb467603957f2c88c0349770fa0a8163a52931840a59ea5599db7b05",
  "figures/11b_review/c14_response.svg": "17aea7b22b50741318fcbd4f5550bd7781057a6de4c6b1a45aa339275d914b3f",
  "figures/11b_review/c15_grid.png": "7a130787ea8c90318fb108f17511c84bb0b25d71a86216050beaf74bc72694db",
  "figures/11b_review/c15_grid.svg": "0b93632a0561584790a4d8a008f4b58eed0b4ee40eea0cc91730870839de3c90",
  "figures/11b_review/c15_response.png": "6d50bfcdd63a83647caecb387c7e8842569f22a35d32d3fcc3776fb77ed2024f",
  "figures/11b_review/c15_response.svg": "634e999495f2b2b890132880e1be2e90dc081e3b5ecb885f4e1c272327c88248",
  "figures/11b_review/c16_grid.png": "270c439cdc586784f09904142e1c1e11c0cd69f2ccda46e94bfc90899f302057",
  "figures/11b_review/c16_grid.svg": "d7c8edb652cdbc0223e6525cb7547725931ce502aef5aa7f217e8f347af7e141",
  "figures/11b_review/c16_response.png": "47f5f4bdb428ebfad421b607336323c0da0ca6801948b7038ec07327f5e60d71",
  "figures/11b_review/c16_response.svg": "210462d3283a2727dc6f09155117d76f68d4f3a50fe9500e03294eba8188adc0",
  "figures/11b_review/c17_grid.png": "32a83603ad53663def9bf2fbf8c48c857a56f749b16ada3acdbf858e3444686f",
  "figures/11b_review/c17_grid.svg": "2522b870deec3fd91b422be6f9c30a09e00c0c73189f8fa00022d899ded88f06",
  "figures/11b_review/c17_response.png": "ac8ddd866acefab8e199d9f3ffc42beaa806687bfc8c9b5e6baa6d013b650eff",
  "figures/11b_review/c17_response.svg": "7ddb9a825db822ae12238bc8df1aa7f1f1ce40a2860af784f41de2254cf1f532",
  "figures/11b_review/c18_grid.png": "2467d3dc31639714a8ab7f1f1a794a54452568f7de00c7400a161c7b3d1978fe",
  "figures/11b_review/c18_grid.svg": "fd35a879d3b72022e1daea2a601770ab23d97819ef5ca362e484434264f2285b",
  "figures/11b_review/c18_response.png": "905ef2b9d784b742141df14b2c15d675c96a96ea8dbcbf66801b1967945ebc1a",
  "figures/11b_review/c18_response.svg": "a95b5708ff801490137edca20c8f601529c66e8ddc1fa4194fc4f0bbf90330e4",
  "figures/11b_review/c19_grid.png": "d62cf79082c42df51323043c5ee4aa840a3075048b660e87e638d5c4c6f32e6d",
  "figures/11b_review/c19_grid.svg": "4439a2f7ab99ec8d3f011733d902ff04a8ffeb2d3f573824fc0fd934e4cc7301",
  "figures/11b_review/c19_response.png": "918b1f6d2bacc354055cdcb5e4735f892b063649b9dae8781c55de923846a5cc",
  "figures/11b_review/c19_response.svg": "e21be4f3018d902d84517970805a630e58c2817cdda22ddee84298596e57466a",
  "figures/11b_review/c20_grid.png": "3bf8631f590d10aec6315bef3333664b7509cbb0913e896b75fa40402561e679",
  "figures/11b_review/c20_grid.svg": "9c16cc505109c972583b05bf45e26ee962a004667646e2e88238d4476ae9139d",
  "figures/11b_review/c20_response.png": "7599753fe4f397625008dae2dba8ac49fa2acc93703b5b1548bf97669014c062",
  "figures/11b_review/c20_response.svg": "5ef2ff73d73ff989933caa88ebe7e0513b11edc980a4a148b3c481e88d3da113",
  "figures/11b_review/c21_grid.png": "8f5ce2136996020a163b624eb51146e037c3f06bd0e618c1486ef1008e38ebf1",
  "figures/11b_review/c21_grid.svg": "b6104fa82c9bd4dc8aa6f41f3d4c32bc9a977f90f86e367dc631bf9ae06073b1",
  "figures/11b_review/c21_response.png": "422194c9ca93e8aa3d07bcb6c1fbc30b30c6666404305b82b7256e62fe576c9f",
  "figures/11b_review/c21_response.svg": "bad70fad8997cc4d1e468fd9c4153d71f2081fca0d2bf8f7d2b0d04a5fcea648",
  "figures/11b_review/c22_grid.png": "7a1199b58dbdd72c4ff25aa3d41aa216f749732fd0222ef8b4087d0d6648cf7e",
  "figures/11b_review/c22_grid.svg": "aec7e30890d289d4f1f113bc21d4724862d4cadb52f5731f18b1e291c15fb623",
  "figures/11b_review/c22_response.png": "1252a92ad91380872e8c93dc772e95074c8aa26f16a39874079090de95acec74",
  "figures/11b_review/c22_response.svg": "2ca8bfc1d8500f0a8de0dd00c45e4825116e83a30fa0bf377de2993fa72d80e3",
  "figures/11b_review/c23_grid.png": "11987050b06e59d7c9b39ce32e34a3407ad79bc12fdf0e82ed4ed16ec6dfaadf",
  "figures/11b_review/c23_grid.svg": "6bd56896c7789b90beb0fb07e874e30a4a691a0bc2b02b06eeae54514ddd77fb",
  "figures/11b_review/c23_response.png": "054a45dead97958382dc5e9d5ec75725cb4421926d4df72d3b8d35a20f2fab04",
  "figures/11b_review/c23_response.svg": "45618379f27c074578721c4a33d5ce6aea74f951d354537ff8d9d980cdb6bd13",
  "figures/11b_review/c24_grid.png": "df7ce2fa3637e84b1355bb8b01b7fea8b7cdb970bc9d8341409d2a909862cc8b",
  "figures/11b_review/c24_grid.svg": "243b3bb6bbdd73c89ff0b2d3fdeaafe483acc8d1884d0d8132f2092c89999c4f",
  "figures/11b_review/c24_response.png": "63306eb3b6586b358fdd9826ed93ac4d2b81b3a7d180b26d5f2a1baefd7df855",
  "figures/11b_review/c24_response.svg": "88fb8e099e38222fd9341d3a7988684add18816ed1bcf5604e67293c0c0610d8",
  "figures/11b_review/composition_efficiency_p01.png": "4e6b95260e42ebe67f908f0340f926d373849293359518fc904a90531e1378c9",
  "figures/11b_review/composition_efficiency_p01.svg": "20dde5472d8a23ed7968db024532189c8c4b2006e5b6901a9ad9c061f2b33af7",
  "figures/11b_review/composition_efficiency_p02.png": "ec48d2b92cf3a9f4f2486597a35f76ff3ecd9c29f3a2b3864a6e119397834026",
  "figures/11b_review/composition_efficiency_p02.svg": "04ae440e3233daf59ccb5e4609ebc71539916f9aa7744e293edc9e5acd916a68",
  "figures/11b_review/composition_efficiency_p03.png": "ebe4c43e23d8b5e30ecad5bfc93d59e2af41ad62022463a17498aac4fa5fe00f",
  "figures/11b_review/composition_efficiency_p03.svg": "a0b6ac8ed435f61523103dd254f478960d19ab07c84dd5438a80d5b7321757ed",
  "figures/11b_review/composition_efficiency_p04.png": "4f40fb0101210213659419db1027f699d19cf50f391561725ad3a1ea707f1f8f",
  "figures/11b_review/composition_efficiency_p04.svg": "9238d983db8fcaceb78542bd5dfee4348fda4b5e6d00fe45bddf796dba9d8dc8",
  "figures/11b_review/composition_efficiency_p05.png": "7e464eaae8e851366f1e7e79af46afb076027601c55b4daac3e2bcb61b6051a9",
  "figures/11b_review/composition_efficiency_p05.svg": "d212f3b421f2175473101af20d1a72f3fae2703fc07b2fa01eb5a7d8973ec3f8",
  "figures/11b_review/composition_efficiency_p06.png": "bf88352a7ab48aa924e989e380d8581bef4775d97771518058b01fa8947f4280",
  "figures/11b_review/composition_efficiency_p06.svg": "8bb780e9d3c568b6f3352296b8eafbfd2064603ff86774f018b8863302e5bf51",
  "figures/11b_review/distribution_repeat_p01.png": "85ca6f3d007de3dd7c287e929acd3aaf32e796478b87cd8bf317f773625c4647",
  "figures/11b_review/distribution_repeat_p01.svg": "baabd4f2d25436fc108634dd8e56eccbfe66aec39d49e23427d237ee8dbcaa6e",
  "figures/11b_review/distribution_repeat_p02.png": "e0910d99f1c2fce92e3c57b43861845da2387627a9564d0310a8eb9a1b948c15",
  "figures/11b_review/distribution_repeat_p02.svg": "f2812fb3327719fcab1e6cd10f7e6ca239e35b44b235ce44991a706fe8448d54",
  "figures/11b_review/distribution_repeat_p03.png": "a3faf8f521044334eb3ece473c8041328058f14fc30981731d14833a34eee023",
  "figures/11b_review/distribution_repeat_p03.svg": "ea59705beb28b06df1f52a8bc156664a1a249f2d18e68e31bdfb330b87bebefa",
  "figures/11b_review/distribution_repeat_p04.png": "005f9adea8f0a9ddeb648d991fc9a0badf6002de6e33727b3926ee1677220f2b",
  "figures/11b_review/distribution_repeat_p04.svg": "2bfb0c82644f2bcd62be30e0d995c37ae690ab8ca8785a278f15fd88c45fe00c",
  "figures/11b_review/distribution_repeat_p05.png": "b3e40aa0eea6053f0e11b468312bf059c3c456066367e1b520381e1ba2f00686",
  "figures/11b_review/distribution_repeat_p05.svg": "68cff8c19e39a95a64b3da02c44bd125153a4c704c2d23e236110325b922ddbf",
  "figures/11b_review/distribution_repeat_p06.png": "433b23e3095e8600f8d18503e852e4a47459bd4619144c8140fe5247a2c050ca",
  "figures/11b_review/distribution_repeat_p06.svg": "f99523b8c8c5637b2efaa2ae0494b3921599a7e7bb045b8f79c1a399a45c9204",
  "paper/11_draft/artifact_manifest.json": "e84d24e778d5cfcaf3beedf22d424b870a0f873208f6a6c51bf2d783c2759e0f",
  "paper/11_draft/reproducibility.md": "8341bba8890fd16c8f10666768bfbc49f7e290be95633894caa59f9cd82cfabd",
  "paper/11_draft/results_discussion.md": "840ae600cb56b924f851c830690a2524f30a652a65163d304df0fe3eae9c4ab2",
  "paper/11_draft/results_discussion.tex": "02a2e38c263f0b7ba521052e4c8b239ec0fdc6b2b5364438bcc44f2cb46e142a",
  "reports/02_environment_skills_check.md": "44ff373dd190e059389d34602cbe261781e08d9ebd44e7758a825ea328bd0f54",
  "reports/03_input_inventory.csv": "e8e083e9ce97dc1c0aea9ed56d8e1646fed6b473a1fa06e6e86e1c07ece7c983",
  "reports/03_input_inventory.md": "62757dc34781a41862522ed241f106c686c11edc1fd236858e533587b1e4ffb2",
  "reports/04_input_protocol_matrix.csv": "ec04df2a4de15f1848c5fe77e0c044ccd94156a940b7228b30bc22191766526f",
  "reports/04_metric_protocol_audit.md": "7cba51c29b5bd907c003d4002fa599202af92154432b53fa4f3cdc7a992e79c2",
  "reports/04_sgs_rename_log.md": "c730494d88ba5ed042fe47406d46756b982eafcc2f06a10b635fc06e300be029",
  "reports/05_dpvo_comparison.csv": "2805b354f1590bc83966a00d9cc35ef849a6fe7ad22dc4c6f86bf6f02edcb283",
  "reports/05_dpvo_pilot.md": "dd225ff6320c36828753ede9fccda43bdf95b024aa5d9fbc16179630aae686bc",
  "reports/06_data_quality.md": "cc6c8e5be18f64b739c6db442b0c33057689b3d630fdb2a386a7b4a2926c6da7",
  "reports/06_sequence_coverage.csv": "96080b48244f5af8b1db9e5becac59ba266e41341f01dedc9532b8b52be85a52",
  "reports/07_exploration_spec.json": "0f6790a086e494d479dccaaa299728b6a80760e8c5df299072ea726c65b47502",
  "reports/07_exploratory_analysis.md": "cb3bd88e736bd344e90fcb54f8f79406bcf99267ec25f230e514e06b3a6cdf47",
  "reports/07_research_questions.csv": "49eb5de9c5633f1b846da76b49f7a1d82e65e6296e63346beacc557e8900c5e0",
  "reports/08_altitude_speed_analysis.md": "d630f886049a8a8e3d85db8234d602c5ce209e559c08abc0605fa7308432380d",
  "reports/08_condition_analysis_spec.json": "d7146979a097f61a39c317bf3f568b40f5b348edcb7f6b697c1e83ad3361d98a",
  "reports/08_question_assessment.csv": "0fdf1a5d98a25f277a2bbae6583cfadf660452568ef385fc65bed47173d16b58",
  "reports/09_claim_assessment.csv": "5b0c94db7f3b1c5866ec67380d948bfebd9e876a55360e5fbf7f0badfd54342d",
  "reports/09_robustness_analysis.md": "cd9dacaa2c0abff96f9569398b73ea8b53ea7a3e2eaa40d53a2d8a05ee338970",
  "reports/09_robustness_spec.json": "a08680a5f4e17c2a0660ab52b972dfae886762b9d81afdd35e9a98b1b02909f5",
  "reports/10_findings_assessment.csv": "e9a40aba14c118310589765e6ec62f94bafda02ef470bce15dcfa27118f645d8",
  "reports/10_method_relationships.md": "8affd76f5c1be36d78a4b19bc8436b4a993afc23b1d5a8e986f43492023609a8",
  "reports/10_relationship_spec.json": "ee3f990151675ee661d99463cd3058efd4ca34b8e68aa2c9b0cd15c0f4a12c86",
  "reports/11_claim_registry.csv": "d7518ba2d7b73e311432ed55bf69b79fd6c8a373f3c947e7e28ae65c23f9567d",
  "reports/11_paper_synthesis.md": "4ccef7590d0346a882a822e1490d63f08db43c0a9187613e8ea56a24f8a165fa",
  "reports/11b_all_configuration_review.md": "3ac45a1c6b4c08d456dbce7b1c25c170c68f94bf5ef80fa715ba1070d748ef4f",
  "reports/11b_artifact_manifest.json": "c22787c670ebb0e905613043f7c4e08613517d661ded296cb74a1aaa0f70645f",
  "reports/11b_review_coverage.csv": "cb1d32af91b7a471c4de8a699606280e3fb40db607cc3696bbc04001a22d1844",
  "reports/11b_review_index.html": "600cdf712d2f87700ca6e59aacaf3accf71b153dd86366b597f53f468de8cbb3",
  "reports/11b_review_spec.json": "6181484466e4dc26fe2c099ee234e1ad1a768538e3dbbb6df19673e59d13ac7c",
  "scripts/analyze_altitude_speed.py": "5964774f6ecc51aaa31c5447b285cf4b66f983d8495809376c63c367fffda433",
  "scripts/analyze_method_relationships.py": "6dcad496873478f2ca85bff2a7f5fa283b029b1b6b4eb07a2946472d5a3d7539",
  "scripts/audit_metric_protocol.py": "ae077a344f6cca040166ac2ca59aa10adddc2ff3cfbbe7f41e398773fd1645c2",
  "scripts/build_analysis_dataset.py": "829bb183874b210f5b474892e08f935f8a0b2c3f0e5e252ee986503690099046",
  "scripts/build_paper_materials.py": "21945c6df77cc1a62a19fd199a6417740a8028f8af471889b4d190634be7c22d",
  "scripts/check_benchmark_robustness.py": "fa1c658c9d3720d44ad445795866463d087b0e43e86857cd9a85b7e914fdd71d",
  "scripts/explore_benchmark.py": "7a972d636aebab1806247ead68dceec5ea96c7d271ebc8544476159c75159519",
  "scripts/inventory_inputs.py": "d32e5fa56b1c3f24f898c9ab543d65a9b99f8740eff1fb9ad9af8fa3e2a7472f",
  "scripts/review_all_configurations.py": "b5a50e82af5d941f81d86461432a8c4ed76fc63c3ceb887da60ee83d4e4e1147",
  "scripts/review_all_configurations_claims.py": "7b86e2f86616a57f8a1b3c609c7790e978f0354b809c24e86527a9b2de8e3c0f",
  "scripts/review_all_configurations_narrative.py": "b9aabda0827f246694e1deb3af8fc08565beeb23deb3054135030307f0fd0c26",
  "scripts/review_all_configurations_plots.py": "8e314b09da26521596427943bd6d8f8efe890f94a40f3f39df679cbc5713abf0",
  "scripts/run_dpvo_pilot.py": "aabce7b595ba5c66f8d3fa250afc8866f010e4467d5bf381c8074e123217d815",
  "tables/05_dpvo_pilot/altitude_recomputed.csv": "b64b841a6fc34c848a2ecad0e94d6233783d21a2fc8eee7675c9315b1cfb260f",
  "tables/05_dpvo_pilot/scene_recomputed.csv": "052119d50e5b865f42652792223079337a35e20503b4d0e3db382a30be8ef808",
  "tables/05_dpvo_pilot/speed_recomputed.csv": "8819d2046210aada14a871c37d8f128531994a55d0fff92ac74ff0accc14f908",
  "tables/07_eda/descriptive_summary.csv": "24588a099afb73b4863c7ea9f06dfbc6b93c63495a9f05347c25b2f4b7922b7e",
  "tables/07_eda/efficiency_cohort_comparison.csv": "6b323589083955daa36fb9bb5fa4f917d4b1cb0f61ae01cd9f38bcfc7de3938d",
  "tables/07_eda/flagged_cases.csv": "5ca7b3cd6e6ccdb2981d2178df1cac460e52742143199fac7de3f3d423ccb34b",
  "tables/07_eda/sequence_metrics.csv": "0459ebab01c89e59bcc208e7e5ff8963dad7bd6710061cf4e1e17beecf45bf91",
  "tables/08_conditions/conditional_contrasts.csv": "f4eece936b3e1108c91a8506bb05ff213f417a0e7588e47f63ed0a70135d2bc8",
  "tables/08_conditions/efficiency_cohort_cells.csv": "801f51ce08415914fba43a2ee06468d73866f5fda8f8a223869243494ea8b392",
  "tables/08_conditions/joint_metrics.csv": "6b34a00ac0e655b0c4c7acd5416a31a26842b9397798e8763f2506070bfbec74",
  "tables/09_robustness/efficiency_decomposition.csv": "7a480dc6044efeeaac7123c971696fb087746d1083d91dc21eae461dcf905e47",
  "tables/09_robustness/repeat_value_audit.csv": "32f6b715826ebd11c2da4c019dd4b2f6f4b5359144d5319ab97fcc4baf95dd04",
  "tables/09_robustness/sensitivity_estimates.csv": "8bfd9440c0582f9cea82b34b79a8dee2bf199d33bd9d45a6c018c1fb0fb944a2",
  "tables/09_robustness/support_blocks.csv": "0afe0a5fb10ddc4ddcd5ed922eb2e4239da952af7af4d278e9fbf6b64b60d5a3",
  "tables/10_relationships/comparison_scope.csv": "ba0d4e5b5b1b5b4261f5d6fb36b80e4771e02782eb660ee887379b8c5f9ce04b",
  "tables/10_relationships/pair_sequence_evidence.csv": "e6831a6c9e309b9872996bd43b152260e668f7161b34666a42d2ff6be751d2b7",
  "tables/10_relationships/pairwise_availability.csv": "a1b19fc7f6f910b8980a39d24933ecf8428e02110cdc68266c5386e9f6e35156",
  "tables/10_relationships/pairwise_patterns.csv": "4cd21359ab1211e0829f39f18c68b7c4cd291f2114c5d56e2382d38a4a1412d8",
  "tables/10_relationships/within_configuration_tradeoffs.csv": "ebe2d124345a2ed5a3378abf108215295ce919e8ff9d0a55988c90d9e9cd5c9a",
  "tables/11_paper/analysis_coverage.csv": "9a78c8aa60d31ce5f86b882cc4ac397927ca60c2e9f5ce743481ef1e92d413b5",
  "tables/11_paper/analysis_coverage.tex": "d1f5f453952a5d7d44255b2481ba059e45027340a1598fd9e491ced9a86bb09b",
  "tables/11_paper/six_pair_patterns.csv": "43c0f7b69e9afc9fdee4d9ef74529f6209c219ae9f4ccde4e57c77f08ddfbb63",
  "tables/11_paper/six_pair_patterns.tex": "dbf65c2f6560297f1d9df898af75a6b8afc5568b3e04a2b0c2bbb6adcaee2405",
  "tables/11b_review/claim_applicability.csv": "88c99c43c827ab6ca5a9bf95845cf1dd734833d1175395f0f526fc0cd4840503",
  "tables/11b_review/condition_sensitivity.csv": "cb0ec5caca364a98f94e4392f853ace76c76e4fe9a9010f8d9e29236f6f84974",
  "tables/11b_review/configuration_patterns.csv": "4cba7fc870cf2c1ca12ab70ec9d163d012a5c3452d11b9bcda827c80cd46d6ac",
  "tables/11b_review/selection_rationale.csv": "d27ee08b5b79097c97be581945953f15c360e0c0684e8832421985fd23ba4c5e",
  "tables/11b_review/sequence_index.csv": "9994751041beca4b7b31be59d4341495b147489fe0c55f1a2b0c0795ecfae950"
}

APPEND_ONLY_PREFIX_BYTES={"README.md":16798,"PROJECT_STATUS.md":41872}

def make_spec(data,inputs,figures,checks):
 return {
 "stage":"11C cross-configuration synthesis; not family-level inference",
 "date":date.today().isoformat(),"interpreter":sys.executable,"inputs":inputs,
 "input_version_manifest":"reports/current_input_manifest.json" if VERSION else None,
 "taxonomy":{"configuration_order":[r["configuration_id"] for r in data["taxonomy"]],
  "mapping":data["taxonomy"],"input_group_order":["Mono","RGB-D","RGB-D + Semantic","Unknown"],
  "base_modality_values":["mono","rgbd","unknown"],"semantic_usage_values":["yes","no","unknown"],
  "semantic_user_confirmation":{"status":"user_confirmed","only_semantic_configurations":["SGS-SLAM::semantic","hierslam::semantic_500"],
    "actual_inputs":"RGB + Depth + Semantic","semantic_only_exists":False,"remaining_22_semantic_usage":"no",
    "scope":"current 24 configurations only; original metadata snapshots are not edited"},
  "display_mapping":{"MongGS":"MonoGS","hierslam":"Hier-SLAM","Photo-slam":"Photo-slam"},
  "mast3r_user_confirmation":{"status":"user_confirmed","configurations":["MASt3R-SLAM::mono_calib","MASt3R-SLAM::mono_nocalib"],"base_modality":"mono","semantic_usage":"no","display_input_group":"Mono","evidence":"user_confirmed:11C_MASt3R_mono_clarification","history":"source audit fields retained separately; current scope/repeat metadata follows the frozen input version"},
  "unknown_policy":"Unknown remains allowed but is not substituted for explicit user confirmation. Modality and scope follow separate current evidence; calibration evidence is not inferred",
 "current_scope_counts":dict(Counter(r["evaluation_scope"] for r in data["taxonomy"])),
  "family_usage":"user-provided method taxonomy; only labels, row order, annotation and hypothesis candidates. No family aggregation/ranking/inference."},
 "statistics":{"subset":"condition_labelled","representative":"existing equal_weight_sequence_means",
  "distribution":"one existing finite mean per sequence, all values retained; existing summary mean/median/p90/q25/q75 read verbatim",
  "distribution_display_descriptors":"mean-minus-median, mean/median and p90/median use existing summary scalars only; zero median yields undefined; no classification thresholds",
  "response":"existing 08 endpoint difference; existing 11B three-level class copied separately and checked against the same three joint-table cells",
  "coverage":"finite RMSE retained records / actually retained records, no new planned-repeat denominator",
  "efficiency":"existing within-configuration Spearman rho; same-finite-run intersection verified using exact standardized member keys",
  "additional_run_level_statistics_computed":False,
  "numeric_zero_absolute_tolerance":TOL,"numeric_zero_meaning":"floating convention only, not practical insensitivity or significance"},
 "missing_encoding":{"response":"signed categories when both endpoints finite; otherwise NR if any endpoint absent, AF if an observed endpoint entirely nonfinite, NA for other unavailable; all simultaneous reasons preserved",
  "triple":"nondecreasing/nonincreasing/nonmonotonic/numeric_flat/unavailable independent of endpoint direction; middle missing may coexist with a computable endpoint difference",
  "coverage":"no_retained_records distinct from observed_all_nonfinite, observed_partial_finite and observed_all_finite",
  "correlation":"computed rho only; insufficient_sequences/constant_input/unavailable/incompatible kept distinct, never filled with zero"},
 "figures":{"basenames":BASENAMES,"full_overviews_required":True,"configuration_row_order_identical":True,
  "canvas_inches":[26,34],"PNG_DPI":110,"PNG_pixels":[2860,3740],"scene_order":list(SCENES),
  "speed_columns":"5 scenes x H10/H20/H30; V8 minus V2","altitude_columns":"5 scenes x V2/V4/V8; H30 minus H10",
  "coverage_columns":"5 scenes x H10/H20/H30 x V2/V4/V8; height-major then speed",
  "efficiency_columns":"FPS/runtime/memory, each overall then five scenes",
  "distribution_axes":"independent x scale in each of 24 mini-ECDF rows; identical ECDF y=[0,1]; not an absolute cross-method RMSE comparison",
  "response_color":"categorical signs and missing states, no global continuous absolute-effect scale",
  "coverage_color_range":[0,1],"correlation_color_range":[-1,1],
  "annotations":"separate Input M/D/DS/U and Family TRAD/LEARN/3DGS/FF/3DGS+SEM/SEM; text + group titles + separators",
  "metadata":figures},
 "output_files":OUTPUTS+[MANIFEST],
 "audit":{"history_validation":"verified_version_backup_and_protected_steps3_5" if VERSION else "original_historical_hashes",
   "original_historical_files":len(HISTORICAL_HASHES),"append_only_docs":APPEND_ONLY_PREFIX_BYTES,"checks":checks,
   "visual_state":"PNG actual-view receipts in artifact manifest; no automatic completion from file existence",
   "SVG_check":"native SVG renderer text bboxes against viewBox; SVG typography preserved"},
 "limits":["24 configurations are 17 original methods, not independent votes",
  "Scopes remain distinct according to current explicit evidence; frame limits are not inferred from metric values","units/alignment history and efficiency measurement protocols not unified",
  "finite RMSE does not prove trajectory completion","identical repeat sources and independence unresolved",
  "family and modality composition confounded; no group performance conclusions",
  "no causality, significance tests, cluster models, frame-count inference or new ranking"],
 "rerun":"/home/yuan/anaconda3/bin/python3 -B scripts/build_cross_configuration_overview.py",
 "overwrite":"default refusal; --overwrite permits only the fixed 11C output set with all recorded current hashes unchanged"}

def write_review_documents(data,family,cases,figures,reviewed,checks):
 from cross_configuration_overview_review import build_report,build_index
 write(REPORT,build_report(data,family,cases,figures,reviewed,checks))
 write(INDEX,build_index(data["taxonomy"],figures,reviewed))

def validate_outputs(data,family,cases,figures):
 import xml.etree.ElementTree as ET
 from html.parser import HTMLParser
 from urllib.parse import urlsplit,unquote
 ids=[r["configuration_id"] for r in data["taxonomy"]]
 assert len(figures)==5 and {r["basename"] for r in figures}==set(BASENAMES)
 for f in figures:
  assert f["row_order"]==ids and f["configuration_ids"]==ids
  assert f["svg_clipping_check"]["outside_canvas"]==[]
  assert f["svg_clipping_check"]["visible_text_bboxes_checked"]>0
  svg=out(FIGROOT+f["svg"]);root=ET.fromstring(svg.read_text())
  text=" ".join("".join(e.itertext()) for e in root.iter() if e.tag.endswith("text"))
  assert "RGB-D + Semantic" in text and "MonoGS" in text
  assert "MongGS" not in text and "Semantic-enabled" not in text
 assert {r["configuration_id"] for r in data["distribution"]}==set(ids)
 for name in ("speed","altitude","coverage","efficiency"):
  assert {r["configuration_id"] for r in data[name]}==set(ids)
 for rows in (family,cases):
  assert rows
  assert not any(k in r for r in rows for k in ("family_mean_rmse","family_win_rate","family_average_speed_effect","family_average_altitude_effect","family_p_value","family_ranking"))
 class Page(HTMLParser):
  def __init__(self):super().__init__();self.images=[];self.links=[];self.ids=[]
  def handle_starttag(self,tag,attrs):
   a=dict(attrs)
   if tag=="img":self.images.append(a.get("src",""))
   for k in ("href","src"):
    if k in a:self.links.append(a[k])
   if "id" in a:self.ids.append(a["id"])
 p=Page();p.feed(out(INDEX).read_text())
 assert len(p.images)==5 and len(set(p.images))==5
 assert len(p.ids)==len(set(p.ids))
 for href in p.links:
  u=urlsplit(href);assert not u.scheme and not u.netloc,href
  if u.path:
   candidate=(Path("reports")/unquote(u.path))
   # Resolve relative HTML paths within the allowed workspace.
   dest=(W/candidate).resolve();assert dest.is_relative_to(W),href
   relative=str(dest.relative_to(W))
   actual=out(relative) if relative in OUTPUTS else safe(relative)
   assert actual.is_file(),href
  elif u.fragment:assert unquote(u.fragment) in p.ids,href
 CHECKS["rendered_figures"]=5
 CHECKS["SVG_text_bbox_checks"]=sum(f["svg_clipping_check"]["visible_text_bboxes_checked"] for f in figures)
 CHECKS["HTML_local_links"]=len(p.links)
 CHECKS["HTML_unique_overview_images"]=len(p.images)
 CHECKS["family_candidates"]=len(family);CHECKS["case_selection_rows"]=len(cases)
 CHECKS["semantic_labels_checked_all_SVG"]=True

def generate(overwrite=False):
 global STAGING
 old=preflight(overwrite);inputs=check_inputs();check_history()
 # Import helpers before any heavy rendering so an incomplete implementation cannot leave outputs.
 from cross_configuration_overview_plots import render_overviews
 from cross_configuration_overview_review import build_review_tables
 data=extract()
 family,cases=build_review_tables(data)
 cases=apply_reviewed_rows(W,"cases",cases)
 reviewed={}
 with tempfile.TemporaryDirectory(prefix=".11c_build_",dir=safe("reports")) as tmp:
  STAGING=Path(tmp);cache=STAGING/"cache";cache.mkdir()
  os.environ["MPLCONFIGDIR"]=str(cache/"matplotlib");os.environ["XDG_CACHE_HOME"]=str(cache/"xdg")
  os.environ["TMPDIR"]=str(cache);os.environ["PYTHONDONTWRITEBYTECODE"]="1"
  for key in ("taxonomy","distribution","speed","altitude","coverage","efficiency"):
   write(ROOT+TABLE_NAMES[key],csv_text(data[key]))
  write(ROOT+TABLE_NAMES["family"],csv_text(family));write(ROOT+TABLE_NAMES["cases"],csv_text(cases))
  write(SPEC,json.dumps(make_spec(data,inputs,[],CHECKS),ensure_ascii=False,indent=2)+"\n")
  print("Frozen values, members, taxonomy and review tables checked",flush=True)
  target=STAGING/FIGROOT;target.mkdir(parents=True,exist_ok=True)
  figures=render_overviews(target,*[data[k] for k in ("taxonomy","distribution","speed","altitude","coverage","efficiency")])
  if old:
   for n,r in old.get("visual_reviews",{}).items():
    if sha(out(FIGROOT+n+".png"))==r["sha256"]:reviewed[n]=r
  write_review_documents(data,family,cases,figures,reviewed,CHECKS)
  validate_outputs(data,family,cases,figures)
  write(SPEC,json.dumps(make_spec(data,inputs,figures,CHECKS),ensure_ascii=False,indent=2)+"\n")
  write_review_documents(data,family,cases,figures,reviewed,CHECKS)
  check_inputs();check_history()
  manifest={"stage":"11C","inputs":inputs,"checks":CHECKS,"figures":figures,"visual_reviews":reviewed,
   "scripts":{p:sha(safe(p)) for p in SCRIPTS},
   "outputs":{p:{"sha256":sha(out(p)),"bytes":out(p).stat().st_size} for p in OUTPUTS},
   "command":"/home/yuan/anaconda3/bin/python3 -B scripts/build_cross_configuration_overview.py",
   "review_source":"Current frozen inputs and generated tables; visual reviews must bind actual PNG bytes",
   "history_validation":check_history()}
  for p in OUTPUTS:
   safe(p).parent.mkdir(parents=True,exist_ok=True);os.replace(out(p),safe(p))
  safe(MANIFEST).write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
  STAGING=None
 print(json.dumps({"generated_files":len(OUTPUTS)+1,"full_overviews":5,"actually_viewed":len(reviewed),"pending":5-len(reviewed)}))

def verify():
 m=preflight(True)
 if m is None:raise ValueError("11C not generated")
 check_inputs();check_history()
 for p,h in m["scripts"].items():assert sha(safe(p))==h,("Script changed",p)
 for name,r in m["visual_reviews"].items():assert sha(safe(FIGROOT+name+".png"))==r["sha256"]
 print(json.dumps({"frozen_inputs":len(INPUT_HASHES),"history_validation":check_history(),
   "verified_generated_files":len(OUTPUTS),"actually_viewed_PNG":len(m["visual_reviews"]),
   "pending_PNG":5-len(m["visual_reviews"]),"full_overviews_each_configuration_count":[len(f["configuration_ids"]) for f in m["figures"]]}))
 return m

def record_review(names,reviewer,note):
 global STAGING
 m=verify()
 for n in names:
  if n not in BASENAMES:raise ValueError("Unknown figure "+n)
  m["visual_reviews"][n]={"status":"visually_reviewed","sha256":sha(safe(FIGROOT+n+".png")),
    "reviewer":reviewer,"note":note}
 # Numeric results only re-extracted for text; no recomputation or image regeneration.
 data=extract()
 from cross_configuration_overview_review import build_review_tables
 family,cases=build_review_tables(data)
 cases=apply_reviewed_rows(W,"cases",cases)
 assert csv_text(family)==safe(ROOT+TABLE_NAMES["family"]).read_text()
 assert csv_text(cases)==safe(ROOT+TABLE_NAMES["cases"]).read_text()
 with tempfile.TemporaryDirectory(prefix=".11c_view_record_",dir=safe("reports")) as tmp:
  STAGING=Path(tmp)
  write_review_documents(data,family,cases,m["figures"],m["visual_reviews"],m["checks"])
  for p in (REPORT,INDEX):
   m["outputs"][p]={"sha256":sha(out(p)),"bytes":out(p).stat().st_size}
   os.replace(out(p),safe(p))
  STAGING=None
 safe(MANIFEST).write_text(json.dumps(m,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
 print(json.dumps({"actually_viewed":len(m["visual_reviews"]),"pending":5-len(m["visual_reviews"])}))

def main():
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument("--overwrite",action="store_true")
 parser.add_argument("--verify",action="store_true")
 parser.add_argument("--record-reviewed",nargs="+",metavar="PNG_BASENAME")
 parser.add_argument("--reviewer",default="root")
 parser.add_argument("--review-note",default="Actually opened final PNG; labels, states, scales and SVG clipping checks reviewed.")
 args=parser.parse_args()
 if sum(bool(v) for v in (args.overwrite,args.verify,args.record_reviewed))>1:parser.error("Choose one operation")
 if args.verify:verify()
 elif args.record_reviewed:record_review(args.record_reviewed,args.reviewer,args.review_note)
 else:generate(args.overwrite)
if __name__=="__main__":main()
