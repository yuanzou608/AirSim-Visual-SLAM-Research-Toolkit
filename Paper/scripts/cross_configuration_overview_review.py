"""Step 11C synthesis helpers. Pure transformations; no filesystem access."""
from collections import Counter, defaultdict
import html
import json
import math

P = "tables/11b_review/configuration_patterns.csv"
F = "figures/11c_overview/"
NEW = "tables/11c_overview/"
FIGURES = {
 "distribution":"01_distribution_atlas", "speed":"02_speed_response_matrix",
 "altitude":"03_altitude_response_matrix", "coverage":"04_finite_coverage_matrix",
 "efficiency":"05_precision_efficiency_matrix",
}
GROUPS=("Mono","RGB-D","RGB-D + Semantic","Unknown")
SCENES=("building","houses","pool","road","roundabout")
RULES=(
 ("speed_all_positive","所有15个速度端点差均为正","speed"),
 ("speed_height_reversal","至少一个场景内速度方向随高度改变","speed"),
 ("altitude_all_negative","所有15个高度端点差均为负","altitude"),
 ("all_retained_rmse_finite","所有实际保留条件记录的RMSE均有限","coverage"),
 ("fps_negative_all_scenes","RMSE—FPS整体及五场景均为负向秩关联","efficiency"),
 ("three_efficiency_co_worsening","RMSE—FPS负、RMSE—runtime和memory正，整体及五场景均同向","efficiency"),
)

def jj(value,default=None):
 if value in (None,""):return [] if default is None else default
 return json.loads(value) if isinstance(value,str) else value
def js(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False)
def ni(p,k):return int(p.get(k) or 0)
def nf(p,k):
 v=p.get(k)
 return None if v in (None,"") else float(v)
def truth(v):return v is True or v in ("True","true")
def fmt(v):return "未定义" if v in (None,"") else format(float(v),".6g")
def sgn(v):
 return "unavailable" if v in (None,"") else "positive" if float(v)>1e-12 else "negative" if float(v)<-1e-12 else "numeric_zero"
def ordered(data):
 tax=sorted(data["taxonomy"],key=lambda r:int(r["row_order"]))
 pp={r["configuration_id"]:r for r in data["patterns"]}
 assert set(pp)=={t["configuration_id"] for t in tax}
 return tax,pp
def label(t):return t.get("configuration_display_name") or t["method_display_name"]
def make_names(ids,tx):return "、".join(label(tx[c]) for c in ids) or "无"
def evidence(c,fields):return {"table":P,"key":{"configuration_id":c},"fields":fields}
def weight_view_values(p):
 rows={r["view"]:r for r in jj(p.get("speed_views_json"))}
 return {view:rows.get(view,{}).get("value") for view in ("V1","V2")}
def export_correction_note(p,policy):
 if (p["configuration_id"] not in policy.get("authorized_changed_configurations",[]) or
     policy.get("reason")!="user_confirmed_export_omission_corrected"):return ""
 return ("作者已确认该配置的五条既有实验序列曾被导出代码漏掉，本轮按实际CSV恢复；"
         "记录恢复不等于有限结果恢复，不解释为尚未实验或要求补跑。"
         f"当前观测/至少一次有限条件序列={ni(p,'n_observed_sequences')}/{ni(p,'n_finite_sequences')}，"
         f"有限/保留运行={ni(p,'n_finite_runs')}/{ni(p,'n_retained_runs')}；"
         f"无记录格={ni(p,'no_record_cells')}，已有记录全非有限格={ni(p,'all_nonfinite_cells')}。")
def columns_for(rule):
 return {
 "speed_all_positive":["speed_endpoint_positive","speed_endpoint_negative","speed_endpoint_numerical_zero","speed_endpoint_unavailable","speed_endpoints_json","speed_triples_json"],
 "speed_height_reversal":["n_speed_reversal_scenes","speed_direction_reversal_scenes_json","speed_endpoint_unavailable","speed_endpoints_json"],
 "altitude_all_negative":["altitude_endpoint_positive","altitude_endpoint_negative","altitude_endpoint_numerical_zero","altitude_endpoint_unavailable","altitude_endpoints_json","altitude_triples_json"],
 "all_retained_rmse_finite":["n_retained_runs","n_finite_runs","n_observed_sequences","n_finite_sequences","all_nonfinite_cells","no_record_cells","coverage_details_json"],
 "fps_negative_all_scenes":["fps_overall_rho","fps_scene_relation","fps_undefined_scenes_json","efficiency_relations_json"],
 "three_efficiency_co_worsening":["co_worsening_all_three_overall","co_worsening_all_scenes_and_three","fps_overall_rho","runtime_overall_rho","memory_overall_rho","efficiency_relations_json"],
 "scene_cancellation":["speed_opposing_scene_contributions","speed_V1","speed_loso_direction_changes","speed_scene_contributions_json","speed_loso_json"],
 "speed_weight_direction_reversal":["speed_V1","speed_views_json","speed_F_blocks","speed_C_blocks", "n_observed_sequences","n_finite_sequences","n_retained_runs","n_finite_runs","all_nonfinite_cells","no_record_cells","coverage_details_json"],
 "coverage_limited":["n_retained_runs","n_finite_runs","n_observed_sequences","n_finite_sequences","all_nonfinite_cells","no_record_cells","coverage_details_json"],
 "repeat_condition_influence":["condition_problems_any_direction_change","condition_baselines_computed","condition_baselines_unavailable","sequence_drop_range_nonzero","repeat_sd_estimable","repeat_sd_undefined","condition_sensitivity_details_json"],
 "distribution_mean_above_median":["rmse_sequence_mean","rmse_sequence_median","rmse_sequence_p90","rmse_sequence_max","n_finite_sequences","n_observed_sequences","distribution_evidence_json"],
 }[rule]
def relation(p,rule):
 if rule=="speed_all_positive":
  if ni(p,"speed_endpoint_negative") or ni(p,"speed_endpoint_numerical_zero"):return "counterexample"
  if ni(p,"speed_endpoint_unavailable"):return "insufficient"
  return "support" if ni(p,"speed_endpoint_positive")==15 else "insufficient"
 if rule=="altitude_all_negative":
  if ni(p,"altitude_endpoint_positive") or ni(p,"altitude_endpoint_numerical_zero"):return "counterexample"
  if ni(p,"altitude_endpoint_unavailable"):return "insufficient"
  return "support" if ni(p,"altitude_endpoint_negative")==15 else "insufficient"
 if rule=="speed_height_reversal":
  if ni(p,"n_speed_reversal_scenes")>0:return "support"
  return "insufficient" if ni(p,"speed_endpoint_unavailable") else "counterexample"
 if rule=="all_retained_rmse_finite":
  return "insufficient" if not ni(p,"n_retained_runs") else "support" if ni(p,"n_retained_runs")==ni(p,"n_finite_runs") else "counterexample"
 if rule=="fps_negative_all_scenes":
  rr=[r for r in jj(p.get("efficiency_relations_json")) if r["metric"]=="fps"]
  if any(sgn(r.get("rho")) in ("positive","numeric_zero") for r in rr):return "counterexample"
  if len(rr)!=6 or any(r.get("rho") is None for r in rr):return "insufficient"
  return "support"
 if rule=="three_efficiency_co_worsening":
  if any(nf(p,m+"_overall_rho") is None for m in ("fps","runtime","memory")):return "insufficient"
  if truth(p.get("co_worsening_all_scenes_and_three")):return "support"
  return "counterexample"
 if rule=="scene_cancellation":
  if truth(p.get("speed_opposing_scene_contributions")) and ni(p,"speed_loso_direction_changes")>0:return "support"
  return "insufficient" if jj(p.get("speed_missing_loso_scenes_json")) else "counterexample"
 if rule=="speed_weight_direction_reversal":
  signs={sgn(v) for v in weight_view_values(p).values()}
  if "unavailable" in signs:return "insufficient"
  return "support" if signs=={"positive","negative"} else "counterexample"
 if rule=="coverage_limited":
  return "support" if ni(p,"n_finite_runs")<ni(p,"n_retained_runs") else "counterexample"
 if rule=="repeat_condition_influence":
  if ni(p,"condition_problems_any_direction_change")>0:return "support"
  return "insufficient" if ni(p,"condition_baselines_unavailable") or ni(p,"repeat_sd_estimable")==0 else "counterexample"
 if rule=="distribution_mean_above_median":
  a,z=nf(p,"rmse_sequence_mean"),nf(p,"rmse_sequence_median")
  return "insufficient" if a is None or z is None else "support" if a>z+1e-12 else "counterexample"
 raise ValueError(rule)
def facts(p,rule):
 out={}
 for k in columns_for(rule):
  if k.endswith("_json"):continue
  out[k]=p.get(k)
 if rule=="speed_weight_direction_reversal":
  out.update({"speed_"+view:value for view,value in weight_view_values(p).items()})
  out["V1_V2_direction_reversal_status"]=relation(p,rule)
 return out
def memberships(ids,pp,rule):
 r={k:[] for k in ("support","counterexample","insufficient")}
 for c in ids:r[relation(pp[c],rule)].append(c)
 return r

def build_review_tables(data):
 """All-family membership and explicitly non-final case recommendations."""
 tax,pp=ordered(data);tx={t["configuration_id"]:t for t in tax};ids=list(tx)
 policy=data.get("input_update_policy") or {}
 changed=set(policy.get("authorized_changed_configurations",[
  "hierslam::rgbd_500","hierslam::semantic_500","hierslam::rgbd_whole","SplaTAM::rgbd"]))
 families=list(dict.fromkeys(t["algorithm_family"] for t in tax))
 family_rows=[]
 for fi,family in enumerate(families,1):
  members=[t["configuration_id"] for t in tax if t["algorithm_family"]==family]
  methods=sorted({tx[c]["source_method_directory"] for c in members})
  inputs=list(dict.fromkeys(tx[c]["display_input_group"] for c in members))
  for qi,(rule,description,figure) in enumerate(RULES,1):
   m=memberships(members,pp,rule)
   if len(methods)<2:status="insufficient_family_coverage"
   elif m["support"] and m["counterexample"]:status="mixed_with_counterexamples"
   elif m["support"]:status="visual_hypothesis_candidate"
   elif m["insufficient"]:status="insufficient_family_coverage"
   else:status="not_observed"
   family_rows.append({
    "candidate_id":f"F11C_{fi:02d}_{qi:02d}","algorithm_family":family,"input_group":" / ".join(inputs),
    "observed_pattern":description,"predicate_id":rule,
    "all_member_configurations":js(members),"all_member_methods":js(methods),
    "supporting_configurations":js(m["support"]),"counterexample_configurations":js(m["counterexample"]),
    "insufficient_configurations":js(m["insufficient"]),
    "supporting_display_names":js([label(tx[c]) for c in m["support"]]),
    "counterexample_display_names":js([label(tx[c]) for c in m["counterexample"]]),
    "insufficient_display_names":js([label(tx[c]) for c in m["insufficient"]]),
    "n_configurations_descriptive":len(members),"n_original_methods_descriptive":len(methods),
    "member_facts_json":js({c:facts(pp[c],rule) for c in members}),
    "evidence_keys":js([evidence(c,columns_for(rule)) for c in members]),
    "evidence_figure":F+FIGURES[figure]+".png","status":status,
    "modality_confounding":("该family只展示一个输入组，不能分离family与输入构成。" if len(inputs)==1 else
       "该family混有不同输入组；未计算分层总体效应，构成不平衡。"),
    "notes":"用户给定的方法级taxonomy；同方法多配置不是独立支持票。反例含已查不满足该明确谓词的配置；"
    "不足保留缺记录、有限值或常数等原因。范围按当前证据分别保留；未做family均值、排名或推断。",
    "assessment_basis":"既有数值的完整成员审阅；最终PNG视觉完成状态独立记录于本轮报告/manifest。"
   })
 oldsel={r["configuration_id"]:r for r in data["old_selections"]}
 plans=[
 ("C11_A","局部条件响应方向依赖","ORB-SLAM2::mono","speed_height_reversal","extreme_diagnostic_case",
   ["SVO::mono","DROID-SLAM::mono","ORB-SLAM2::rgbd"],"supplement_or_replace_candidate",
   "此前因分布极端规则进入详细跟进；局部反转属于多配置可见现象，不代表典型总体或某family。先以全矩阵说明范围，再决定是否保留两场景特写。"),
 ("C11_B","整体差值掩盖相反场景贡献","DPVO::mono","scene_cancellation","useful_counterexample",
   ["DSO::mono","Photo-slam::mono","ORB-SLAM2::rgbd"],"supplement_candidate",
   "用于反驳整体小差值等于无条件依赖；原选择是检验前序印象，不是随机典型。与权重翻转及其它删场景翻转并列后再决定。"),
 ("C11_COV","有限结果选择限制分布与趋势","VGGT-SLAM::mono","coverage_limited","coverage_limited_case",
   ["SplaTAM::rgbd","SGS-SLAM::semantic","ORB-SLAM2::mono"],"keep_as_boundary_or_replace_candidate",
   "原选例基于无任何有限结果序列比例极端规则。覆盖边界角色须结合当前有限/保留数复核；其它输入组配置按同一分母规则对照，不将NA解释为失败机制。"),
 ("C11_REPEAT","重复值影响局部条件差方向","ORB-SLAM3::rgbd","repeat_condition_influence","extreme_diagnostic_case",
   ["ORB-SLAM2::rgbd","Photo-slam::rgbd","ORB-SLAM3::mono"],"supplement_or_replace_candidate",
   "原选例来自有限极差/均值极端诊断。全配置确定性检查表明其它配置也存在条件方向变化；不把旧例冒充通常波动。"),
 ("C11_D","同配置误差与效率共同变化","hierslam::rgbd_whole","three_efficiency_co_worsening","representative_pattern",
   ["hierslam::rgbd_500","DROID-SLAM::mono","SGS-SLAM::semantic"],"keep_as_configuration_pattern_candidate",
   "这是原配置内同向模式的候选；当前是否仍满足须按整体与五场景全部指标核查，不能保留旧版本的满足者名单。不同范围不能称独立方法或family复现。"),
 ("C11_A","端点同号不等于三档单调","DROID-SLAM::mono","altitude_all_negative","useful_counterexample",
   ["VGGT-LONG::mono"],"supplement_candidate",
   "高度端点方向均负，但三档有转折；适合作为端点与形状分开报告的候选，不能推断模态因果。"),
 ("C11_B","总体速度方向的反例","SVO::mono","scene_cancellation","useful_counterexample",
   ["DSO::mono"],"supplement_candidate",
   "速度V1及五景贡献为负，但局部仍有正向端点。它反驳统一速度方向，也反驳用总体代替全部条件；不是抵消谓词的支持者。"),
 ("C11_B","权重视图的方向核查","DSO::mono","speed_weight_direction_reversal","useful_counterexample",
   ["Photo-slam::mono"],"supplement_candidate",
   "块等权V1与场景等权V2使用实际有限支持集合，直接核对两种权重的方向，不借用场景抵消谓词代替。"),
 ("C11_COV","实际保留次数与有限结果的覆盖边界","SplaTAM::rgbd","coverage_limited","coverage_limited_case",
   ["VGGT-SLAM::mono"],"supplement_or_replace_candidate",
   "按当前每序列保留次数与有限次数检查分布和条件可算范围。重复次数由当前输入核验，不能沿用旧版两次说明，也不能因均值/中位数差异称输入模态优劣。"),
 ("C11_REPEAT","补充局部方向敏感性的配置","ORB-SLAM2::rgbd","repeat_condition_influence","useful_counterexample",
   ["Photo-slam::rgbd"],"supplement_or_replace_candidate",
   "全配置等同检查后提供另一个实际方向变化案例，作为只检查旧ORB3案例的反例；变化问题数量不是独立证据票数。"),
 ("C11_D","同方法不同范围的关系对照","hierslam::rgbd_500","three_efficiency_co_worsening","not_yet_justified",
   ["hierslam::rgbd_whole"],"supplement_as_scope_boundary_candidate",
   "关系模式及重复波动均按当前有限记录核验，可供同方法不同范围对照；不能因新增重复而当作第二个独立方法或独立支持票。"),
 ("Q1_to_C11_A","完整分布及mean/median关系","ORB-SLAM2::mono","distribution_mean_above_median","extreme_diagnostic_case",
   ["ElasticFusion::rgbd","TartanVO::mono","VGGT-SLAM::mono"],"keep_as_diagnostic_or_supplement_candidate",
   "第7步明确按mean–median相对差极端规则选出。当前全图必须同时呈现较小mean/median比值与覆盖不足的对照；不新设长尾阈值。"),
 ]
 cases=[]
 for idx,(claim,phenomenon,current,rule,role,alternatives,advice,reason) in enumerate(plans,1):
  m=memberships(ids,pp,rule);old=oldsel[current];p=pp[current]
  def composition(group_key):
   return {g:[c for c in ids if tx[c][group_key]==g] for g in dict.fromkeys(tx[c][group_key] for c in ids)}
  updated_config=current in changed
  current_relation=relation(p,rule)
  previous_role=role
  reassess=bool(data.get("controlled_input_update")) and (updated_config or (role=="representative_pattern" and current_relation!="support"))
  repeat_counts=Counter(int(r["n_retained"]) for r in jj(p["repeat_details_json"]))
  finite_counts=Counter(int(r["n_finite"]) for r in jj(p["repeat_details_json"]))
  if reassess:
   role="needs_reassessment"
   advice="needs_reassessment_after_controlled_input_update"
   reason=("当前冻结版本重新计算后，该候选谓词关系="+current_relation+"；每序列保留次数分布="+js(dict(repeat_counts))+
     "，有限次数分布="+js(dict(finite_counts))+"。旧候选角色不能仅通过替换数值继续确认；须与本轮全配置支持/反例名单重新审阅。"
     "保留次数不等于有限次数、完整轨迹完成或独立性；不同范围仍分开。")
  if rule=="speed_weight_direction_reversal":
   values=weight_view_values(p)
   role={"support":"useful_counterexample","counterexample":"historical_case_not_supported",
         "insufficient":"not_yet_justified"}[current_relation]
   advice={"support":"retain_weight_sensitivity_candidate_after_current_evidence_check",
           "counterexample":"retire_weight_reversal_role_for_current_version",
           "insufficient":"defer_weight_reversal_role_pending_finite_evidence"}[current_relation]
   reason=(f"当前块等权V1={fmt(values['V1'])}、场景等权V2={fmt(values['V2'])}；"+
     {"support":"两者数值方向相反，保留限定于当前有限集合的权重敏感性候选。",
      "counterexample":"两者未呈相反数值方向，旧权重反号角色不作为当前实证结论。",
      "insufficient":"至少一个视图不可算，当前不能确认权重反号角色。"}[current_relation]+
     f"观测条件序列{ni(p,'n_observed_sequences')}条，其中{ni(p,'n_finite_sequences')}条至少一次RMSE有限；"
     "V1/V2的精确值、块数、权重和成员见speed_views_json；该核查与逐场景剔除是不同问题。"+
     export_correction_note(p,policy))
   reassess=current_relation=="insufficient"
  cases.append({
   "case_review_id":f"C11C_CASE_{idx:02d}","claim_id":claim,"phenomenon":phenomenon,
   "current_example":label(tx[current]),"current_example_configuration_id":current,
   "all_configs_checked":True,"checked_configuration_ids":js(ids),
   "comparison_predicate_id":rule,
   "supporting_configs":js(m["support"]),"counterexample_configs":js(m["counterexample"]),
   "insufficient_configs":js(m["insufficient"]),
   "modality_distribution":js(composition("display_input_group")),
   "family_distribution":js(composition("algorithm_family")),
   "current_example_relation_to_predicate":relation(p,rule),
   "current_example_role":role,"previous_candidate_role_in_selection_template":previous_role,
   "current_retained_repeat_distribution_json":js(dict(repeat_counts)),"current_finite_repeat_distribution_json":js(dict(finite_counts)),
   "alternative_example_candidates":js(alternatives),
   "alternative_display_names":js([label(tx[c]) for c in alternatives]),
   "keep_replace_supplement_candidate":advice,"rationale":reason,
   "current_facts":js(facts(p,rule)),
   "alternative_facts":js({c:facts(pp[c],rule) for c in alternatives}),
   "evidence_keys":js([evidence(c,columns_for(rule)) for c in [current]+alternatives]),
   "prior_selection_evidence":js({"table":"tables/11b_review/selection_rationale.csv",
    "key":{"configuration_id":current},"prior_step7_selected":old.get("prior_step7_selected"),
    "prior_step7_rule":old.get("prior_step7_rule"),"prior_step11_selection_type":old.get("prior_step11_selection_type")}),
   "candidate_status":"needs_reassessment" if reassess else "numeric_review_candidate_not_final_manuscript_decision",
   "stronger_claim_not_supported":"统计总体代表性、family性能结论、模态因果效应、完整轨迹成功或机制解释。"
  })
 # Preserve every configuration actually present in an original main-text claim.
 # Coverage-table context is not retroactively invented as a focus-case selection.
 oldmain={r["claim_id"]:r for r in data["old_claims"] if r.get("placement")=="main_text_candidate"}
 present={(r["claim_id"],r["current_example_configuration_id"]) for r in cases}
 for claim,oldclaim in oldmain.items():
  for current in jj(oldclaim["configurations_json"]):
   if (claim,current) in present:continue
   if claim!="C11_COV":raise ValueError("Unhandled original main-text member "+claim+" "+current)
   rule="coverage_limited";m=memberships(ids,pp,rule);p=pp[current]
   limited=relation(p,rule)=="support"
   role="coverage_limited_case" if limited else "useful_counterexample"
   reason=("原第11步覆盖表的上下文配置，并非独立重点案例。有限/保留运行与有限/观测序列分开陈列；"
           "该配置支持有限性边界检查。" if limited else
           "原第11步覆盖表的全有限上下文配置，并非重点案例。它为数值覆盖不足提供反向对照；"
           "全有限不证明独立稳定、完整轨迹成功或真实尝试无失败。")
   cases.append({
    "case_review_id":f"C11C_CASE_{len(cases)+1:02d}","claim_id":claim,"phenomenon":"原覆盖表上下文与分母差异",
    "current_example":label(tx[current]),"current_example_configuration_id":current,
    "all_configs_checked":True,"checked_configuration_ids":js(ids),"comparison_predicate_id":rule,
    "supporting_configs":js(m["support"]),"counterexample_configs":js(m["counterexample"]),
    "insufficient_configs":js(m["insufficient"]),
    "modality_distribution":js({g:[c for c in ids if tx[c]["display_input_group"]==g] for g in GROUPS}),
    "family_distribution":js({f:[c for c in ids if tx[c]["algorithm_family"]==f] for f in families}),
    "current_example_relation_to_predicate":relation(p,rule),"current_example_role":role,
    "alternative_example_candidates":"[]","alternative_display_names":"[]",
    "keep_replace_supplement_candidate":"retain_comparison_context_not_automatic_focus",
    "rationale":reason,"current_facts":js(facts(p,rule)),"alternative_facts":"{}",
    "evidence_keys":js([evidence(current,columns_for(rule))]),
    "prior_selection_evidence":js({"table":"reports/11_claim_registry.csv","key":{"claim_id":claim},
                                 "configuration_member":current,"material_role":"supporting_table_context"}),
    "candidate_status":"numeric_review_candidate_not_final_manuscript_decision",
    "stronger_claim_not_supported":"原上下文配置已被重点选中、统计总体代表性、完整轨迹成功或模态因果。"
   })
   present.add((claim,current))
 for r in cases:
  claim,current=r["claim_id"],r["current_example_configuration_id"]
  member=claim in oldmain and current in jj(oldmain[claim]["configurations_json"])
  r["original_main_claim_member"]=member
  r["original_material_role"]=("supporting_table_context" if member and claim=="C11_COV" and current!="VGGT-SLAM::mono"
    else "registered_focus_case" if member else "new_alternative_or_context_review")
  r["original_claim_reference"]=("reports/11_claim_registry.csv#claim_id="+claim) if claim in oldmain else "earlier_Q1_distribution_context"
 expected={(claim,c) for claim,r in oldmain.items() for c in jj(r["configurations_json"])}
 assert expected.issubset({(r["claim_id"],r["current_example_configuration_id"]) for r in cases})
 return family_rows,cases

def figbase(f):return f.get("basename") or str(f["png"]).rsplit("/",1)[-1].rsplit(".",1)[0]
def viewed(f,reviewed):
 r=reviewed.get(figbase(f),{})
 return isinstance(r,dict) and r.get("status")=="visually_reviewed" and bool(r.get("sha256"))
def figpath(f,ext):return "../"+F+str(f[ext]).rsplit("/",1)[-1]
def _sum(pp,ids,key):return sum(ni(pp[c],key) for c in ids)
def _slist(ids,tx):return make_names(ids,tx)
def _table(lines,headers,rows):
 lines.append("| "+" | ".join(headers)+" |");lines.append("|"+"|".join("---" for _ in headers)+"|")
 for row in rows:lines.append("| "+" | ".join(str(x).replace("|","/") for x in row)+" |")
 lines.append("")
def _partition_text(pp,ids,tx,rule):
 m=memberships(ids,pp,rule)
 return ("支持该明确数值条件："+_slist(m["support"],tx)+"；反例／已查不满足："+_slist(m["counterexample"],tx)+
         "；数据不足："+_slist(m["insufficient"],tx)+"。")
def _value_details(p,axis):
 return "、".join(f"{r['view']}={fmt(r.get('value'))}" for r in jj(p[axis+"_views_json"]))

def build_report(data,family_rows,case_rows,figures,reviewed,checks):
 from review_all_configurations_narrative import protocol_note
 tax,pp=ordered(data);tx={t["configuration_id"]:t for t in tax};ids=list(tx);N=len(ids)
 pending=[f for f in figures if not viewed(f,reviewed)]
 names=lambda cc:_slist(cc,tx)
 L=["# 第11C步：跨配置综合可视化与模式审阅","",
 "## 1. 为什么补充跨配置视图","",
 "11B解决全部配置是否接受同结构检查；11C将同一问题放入同一视觉坐标，比较共性、反例与选例依据。"
 "这五张总览与11B单配置图互补，不替代旧产物，也不按绝对RMSE或资源效率排名。",
 protocol_note(checks),"",
 f"本轮{N}配置、{len({t['source_method_directory'] for t in tax})}个原方法目录。"
 "配置排序仅由输入组、用户给定family、显示名与variant决定。family与输入是独立字段，"
 "只有SGS-SLAM语义配置及Hier-SLAM语义500帧配置属于RGB-D + Semantic，其余22配置不使用语义。"
 "Hier-SLAM的无语义配置仍继承方法级3DGS & Semantic-enhanced family，不能据family反推输入。","",
 "MonoGS为本轮确认的显示名，历史MongGS只保留在configuration_id/source追溯字段，不改旧目录或统计。"
 "MASt3R-SLAM的mono_calib与mono_nocalib当前输入均由用户确认是Mono；旧source字段中的Unknown仅保留为历史来源审计，"
 "评测范围另按当前manifest的明确用户证据标注；上游校准细节不随模态或范围确认而自动解决。",
 "当前输入构成："+"；".join(f"{g}={sum(t['display_input_group']==g for t in tax)}" for g in GROUPS)+"。","",
 f"PNG已实际查看{len(figures)-len(pending)}/{len(figures)}，pending={len(pending)}。"
 "下文为既有数值完整对照后的候选；只有图像实际查看后才算本轮视觉验收，尚未决定正文名单。",
 "[离线总览](11c_overview_index.html) · [taxonomy](../tables/11c_overview/configuration_taxonomy.csv) · "
 "[11B单配置图册](11b_review_index.html)","",
 "## 2. 分布形状、尾部与覆盖","",
 "每条条件标签序列一个有限RMSE均值，序列等权。各ECDF的y轴0–1、x轴独立；"
 "只看形状、尾部和mean/median关系，不横向解释原始幅度。"
 "所有有限值保留，不截尾或winsorize。本轮没有新设“明显长尾”“均值接近中位数”阈值；"
 "下面列全部实际数值和无量纲比值，供逐面板检查，不能据mean>median单独判定某种分布族。",""]
 if data.get("controlled_input_update"):
  current_notes=["当前受控输入版本：评测范围构成为 "+"、".join(k+"="+str(v) for k,v in sorted(Counter(t["evaluation_scope"] for t in tax).items()))+
   "。未带明确帧限制的当前逐次输入按用户确认标为完整轨迹；这不是每条保留记录均完整成功的断言。", ""]
  for c in ("hierslam::rgbd_500","hierslam::semantic_500","hierslam::rgbd_whole","SplaTAM::rgbd"):
   rr=jj(pp[c]["repeat_details_json"])
   current_notes.extend([label(tx[c])+"：当前条件标签序列的保留次数分布="+js(dict(Counter(int(r["n_retained"]) for r in rr)))+
    "，有限次数分布="+js(dict(Counter(int(r["n_finite"]) for r in rr)))+"；实际编号和全部序列见本次输入变更记录，不能由三次保留推断三次有限或独立。", ""])
  L[3:3]=current_notes
 rows=[]
 for t in tax:
  p=pp[t["configuration_id"]];a,z,q=[nf(p,k) for k in ("rmse_sequence_mean","rmse_sequence_median","rmse_sequence_p90")]
  ratio=None if z in (None,0) or a is None else a/z
  tail=None if z in (None,0) or q is None else q/z
  rows.append([label(t),t["display_input_group"],f"{ni(p,'n_finite_sequences')}/{ni(p,'n_observed_sequences')}",
   fmt(a),fmt(z),fmt(q),fmt(ratio),fmt(tail)])
 _table(L,["配置","输入","有限/观测序列","mean","median","p90","mean/median","p90/median"],rows)
 above=[c for c in ids if relation(pp[c],"distribution_mean_above_median")=="support"]
 L.append(f"当前mean高于median的配置为{len(above)}/{N}；这是逐配置描述，不是独立方法投票。")
 for c in ("ORB-SLAM2::mono","ElasticFusion::rgbd","TartanVO::mono","VGGT-SLAM::mono"):
  p=pp[c];a,z,q=[nf(p,k) for k in ("rmse_sequence_mean","rmse_sequence_median","rmse_sequence_p90")]
  L.append(f"- {label(tx[c])}：mean/median={fmt(a/z)}、p90/median={fmt(q/z)}，"
   f"有限/观测序列={ni(p,'n_finite_sequences')}/{ni(p,'n_observed_sequences')}。"+
   ("其原入图规则就是相对mean–median差的极端诊断，因此不能称典型分布。" if c=="ORB-SLAM2::mono" else
    "较小的该比值也不证明无尾部、独立稳定或覆盖充分。"))
 L+=["","分布差异在输入组内部也存在；不能将上面某个形状归因于Mono、RGB-D或语义。"
 "来源限制、实际有限重复数与有限结果选择仍跟随每个面板。","",
 "## 3. 速度响应：共同方向与局部反例",""]
 counts=[_sum(pp,ids,"speed_endpoint_"+k) for k in ("positive","negative","numerical_zero","unavailable")]
 shapes=[_sum(pp,ids,"speed_triple_"+k) for k in ("nondecreasing","nonincreasing","numerically_flat","nonmonotonic","unavailable")]
 L.append("360个配置×场景×高度端点正/负/数值零/不可算="+"/".join(map(str,counts))+
 "；三档非降/非升/平坦/非单调/缺失="+"/".join(map(str,shapes))+"。这些条件不视为独立实验。")
 L+=["全部15端点均正："+_partition_text(pp,ids,tx,"speed_all_positive"),
 "同场景方向随高度改变："+_partition_text(pp,ids,tx,"speed_height_reversal")]
 for c in ("SVO::mono","DROID-SLAM::mono","VGGT-LONG::mono","hierslam::rgbd_500"):
  p=pp[c]
  L.append(f"- {label(tx[c])}：速度正/负/不可算={ni(p,'speed_endpoint_positive')}/"
   f"{ni(p,'speed_endpoint_negative')}/{ni(p,'speed_endpoint_unavailable')}，"
   f"三档非单调={ni(p,'speed_triple_nonmonotonic')}，V1={fmt(nf(p,'speed_V1'))}。"
   "端点与三档不能互相替代。")
 L.append("V0–V4／逐场景剔除的成员与边界仍见11B；例如"+
  label(tx["DSO::mono"])+"速度视图为"+_value_details(pp["DSO::mono"],"speed")+
  "。块等权V1与场景等权V2的方向核查="+relation(pp["DSO::mono"],"speed_weight_direction_reversal")+
  "；仅按当前有限支持集合解释，不是失败机制或输入模态效应。"+
  export_correction_note(pp["DSO::mono"],data.get("input_update_policy") or {}))
 L+=["","## 4. 高度响应：端点同向不保证中间条件单调",""]
 counts=[_sum(pp,ids,"altitude_endpoint_"+k) for k in ("positive","negative","numerical_zero","unavailable")]
 shapes=[_sum(pp,ids,"altitude_triple_"+k) for k in ("nondecreasing","nonincreasing","numerically_flat","nonmonotonic","unavailable")]
 L.append("高度端点正/负/数值零/不可算="+"/".join(map(str,counts))+
 "；三档非降/非升/平坦/非单调/缺失="+"/".join(map(str,shapes))+"。")
 L.append("以下名单检验的是15个高度端点均为负："+_partition_text(pp,ids,tx,"altitude_all_negative"))
 p=pp["DROID-SLAM::mono"];nonmono=[r for r in jj(p["altitude_triples_json"]) if r["classification"]=="nonmonotonic"]
 if nonmono:
  r=next((r for r in nonmono if r["scene"]=="pool" and int(r["fixed_value"])==2),nonmono[0])
  L.append(f"{label(tx['DROID-SLAM::mono'])}有{ni(p,'altitude_endpoint_negative')}个负高度端点，"
   f"却有{ni(p,'altitude_triple_nonmonotonic')}组三档非单调；{r['scene']}固定V={r['fixed_value']}，"
   "H10/H20/H30均值为"+"/".join(fmt(v) for v in r["values"])+
   "。这是端点与中间形状不同的直接反例，不能写成高度单调改善。")
 L+=["","## 5. 数值覆盖：实际分母与条件相关缺口",""]
 full=[c for c in ids if relation(pp[c],"all_retained_rmse_finite")=="support"]
 partial=[c for c in ids if c not in full]
 L.append("全部实际保留条件记录RMSE均有限："+names(full)+"。其它配置："+names(partial)+
 "。这只是数值可用性；没有观测到的运行不补为失败，不能使用success rate或trajectory completion表述。")
 rows=[]
 for t in tax:
  c=t["configuration_id"];p=pp[c]
  if ni(p,"n_finite_runs")==ni(p,"n_retained_runs") and ni(p,"no_record_cells")==1:continue
  bad=[r for r in jj(p["coverage_details_json"]) if r["state"]!="observed_all_finite"]
  per_scene={s:Counter(r["state"] for r in bad if r["scene"]==s) for s in SCENES}
  rows.append([label(t),f"{ni(p,'n_finite_runs')}/{ni(p,'n_retained_runs')}",
   f"{ni(p,'n_finite_sequences')}/{ni(p,'n_observed_sequences')}",
   "；".join(s+":"+",".join(k+"="+str(v) for k,v in per_scene[s].items()) for s in SCENES if per_scene[s])])
 _table(L,["有缺口配置","有限/保留运行","有限/观测序列","非全有限格的场景分布"],rows)
 L.append("无记录与观测到但全非有限分开编码；roundabout的共同空格不能解释为某方法失败。"
 "覆盖矩阵保留每格真实保留记录分母，来源和条件键可从CSV回查，不展开底层日志。")
 L+=["","## 6. 配置内精度—效率关联",""]
 for m in ("fps","runtime","memory"):
  same=[c for c in ids if pp[c][m+"_scene_relation"]=="all_same_direction"]
  opp=[c for c in ids if pp[c][m+"_scene_relation"]=="has_opposite_scenes"]
  other=[c for c in ids if c not in same and c not in opp]
  L.append(f"- {m}：整体与五景同向={names(same)}；至少一景反向={names(opp)}；"
   f"数值零/常数/不完整={names(other)}。")
 L.append("三指标整体及五景共同变化："+_partition_text(pp,ids,tx,"three_efficiency_co_worsening"))
 L.append("所有rho来自同序列内RMSE与效率同时有限的运行交集。常数与不足保留未定义，不填0。"
 "不构造资源效率排名或因果tradeoff；内存类型和FPS/runtime计时协议限制没有因画图消失。")
 L+=["","## 7. 输入组观察：构成、内部反例与同方法对照",""]
 for g in GROUPS:
  members=[t["configuration_id"] for t in tax if t["display_input_group"]==g]
  if not members:continue
  L.append("**"+g+"**："+names(members)+"。")
  L.append("速度15端点全正这一具体问题："+_partition_text(pp,members,tx,"speed_all_positive"))
  L.append("三项效率整体及五景共同变化这一具体问题："+_partition_text(pp,members,tx,"three_efficiency_co_worsening"))
 bymethod=defaultdict(list)
 for t in tax:bymethod[t["source_method_directory"]].append(t)
 pairs=[]
 for method,tt in bymethod.items():
  groups={t["display_input_group"] for t in tt}
  if len(groups)>1:pairs.append("、".join(label(t) for t in tt))
 L.append("跨输入组的同方法配置是内部对照候选："+ "；".join(pairs)+
 "。本轮未确认其余协议与范围可交换，尤其Hier500与完整轨迹隔离，不能将差异直接变成模态或语义因果效应。")
 semantic_members=[t for t in tax if t["semantic_usage"]=="yes"]
 L.append("RGB-D + Semantic仅两个配置，来自两个不同family。当前范围："+
  "；".join(label(t)+"="+t["evaluation_scope"] for t in semantic_members)+
  "。两者不是同范围语义效应对照；保留/有限次数按当前记录显示。输入组与评测范围分开，不作输入组总体优劣。")
 L+=["","## 8. Family层候选：名单、反例与混杂","",
 "六类family由用户给定，不从数值推断。下面只列明确现象的成员关系；"
 "每个family全部成员均出现在[候选表](../tables/11c_overview/family_pattern_candidates.csv)，"
 "包含支持、反例与不足以及精确配置事实。没有family均值、速度平均效应、胜率、显著性或排名。",""]
 for family in dict.fromkeys(t["algorithm_family"] for t in tax):
  tt=[t for t in tax if t["algorithm_family"]==family];members=[t["configuration_id"] for t in tt]
  methods=list(dict.fromkeys(t["method_display_name"] for t in tt));groups=list(dict.fromkeys(t["display_input_group"] for t in tt))
  L.append("**"+family+"**：方法="+ "、".join(methods)+"；配置="+names(members)+"；输入构成="+"/".join(groups)+"。")
  for r in [r for r in family_rows if r["algorithm_family"]==family and r["predicate_id"] in ("speed_height_reversal","three_efficiency_co_worsening")]:
   L.append(r["observed_pattern"]+"：支持="+names(jj(r["supporting_configurations"]))+
    "；反例/未观察到="+names(jj(r["counterexample_configurations"]))+
    "；不足="+names(jj(r["insufficient_configurations"]))+"；状态="+r["status"]+"。")
  if len(methods)==1:L.append("该family当前只有一个原方法；多个配置不能补成多个独立方法。")
  L.append("输入、测量协议与评测范围构成不平衡，不能将重复视觉模式归因为family。")
 L+=["","当前不足以形成family-level性能结论；候选表是以后独立问题设计的线索，不是结论已获支持的投票表。","",
 "## 9. 对论文案例选择的影响","",
 "原五图由极端诊断规则或前序印象检验进入跟进，并非随机代表。"
 "当前所有24配置已在相同问题下列出支持、反例和不足；"
 "下面是候选取舍，允许旧案例替换或降为边界材料，不自动重写第11步原稿。",""]
 for r in case_rows:
  L.append("**"+r["current_example"]+" / "+r["phenomenon"]+"**："+
   r["current_example_role"]+"；"+r["rationale"]+" 备选/补充="+
   "、".join(jj(r["alternative_display_names"]))+"；建议="+r["keep_replace_supplement_candidate"]+"。")
 L+=["","完整[案例选择表](../tables/11c_overview/case_selection_review.csv)保存每现象的全部配置名单、"
 "输入和family构成、原选择证据及当前备选事实。representative_pattern仅表示某配置符合明确模式，"
 "不表示统计总体典型或算法family代表。",
 "材料建议：速度/高度符号矩阵与有限覆盖矩阵可作为正文总览候选；24面板分布及三指标全景rho"
 "更适合补充材料或内部审阅。是否压缩或选择局部须由用户审阅，完整图与CSV均保留。","",
 "## 验收、追溯与停止点",""]
 for f in figures:
  L.append("- ["+figbase(f)+"]("+figpath(f,"png")+")："+
   ("已实际查看，PNG哈希绑定" if viewed(f,reviewed) else "pending：尚未实际查看")+
   "；[SVG]("+figpath(f,"svg")+")。")
 L+=["","输入及旧统计核对见[本轮约定](11c_cross_configuration_spec.json)与产物manifest；"
 "图中数值来自同一当前冻结版本的已验证上游表，具体成员按当前路径和记录索引追溯；旧版本由更新存档保留。"
 "本轮补充比值只由已存mean/median/p90相除，不拟合分布、不调阈值或修改样本集合。",
 "入口：scripts/build_cross_configuration_overview.py。默认不覆盖；如本轮受保护输出已存在，"
 "显式刷新仍检查人工编辑冲突，并通过版本记录保护历史快照。",
 "复跑命令：/home/yuan/anaconda3/bin/python3 -B "
 "/home/yuan/SLAM/codex_review/benchmark_analysis/scripts/build_cross_configuration_overview.py --overwrite",
 "本轮停止在跨配置综合审阅。论文仍待决定是否重写；不自动开展family推断、方法排名、底层来源调查、补跑或第12步。"]
 # Keep paragraph boundaries visible while preserving contiguous table/list rows.
 formatted=[]
 for line in L:
  if line and formatted and formatted[-1]:
   same_block=any(line.startswith(prefix) and formatted[-1].startswith(prefix) for prefix in ("|", "- "))
   if not same_block:formatted.append("")
  formatted.append(line)
 return "\n".join(formatted)+"\n"

def build_index(taxonomy,figures,reviewed):
 tax=sorted(taxonomy,key=lambda r:int(r["row_order"]));old={c:i for i,c in enumerate(sorted(t["configuration_id"] for t in tax),1)}
 e=lambda x:html.escape(str(x),quote=True)
 L=['<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">',
 '<title>跨配置总览 · 第11C步</title><style>body{font:16px/1.6 system-ui,sans-serif;color:#192a36;max-width:1800px;margin:auto;padding:1.5rem}'
 'a{color:#0758a1}table{border-collapse:collapse;font-size:.9rem}td,th{border:1px solid #bdc7d0;padding:.35rem .55rem;text-align:left}'
 'figure{margin:2rem 0;padding:1rem;border:1px solid #c6ced7}img{width:100%;height:auto;display:block}figcaption{margin-top:1rem}'
 '.note{background:#edf3f8;padding:1rem}.pending{color:#8b4500}.ok{color:#176429}.scroll{overflow-x:auto}</style>',
 '<h1>第11C步：跨配置综合总览</h1><p>同一组24配置、五个问题、固定行序。'
 '仅用于分布形状、条件方向和配置内关联的比较，不做绝对性能排名。</p>',
 '<p><a href="11c_cross_configuration_review.md">综合审阅报告</a> · '
 '<a href="11b_review_index.html">11B单配置图册</a> · '
 '<a href="../tables/11c_overview/case_selection_review.csv">案例候选</a> · '
 '<a href="../tables/11c_overview/family_pattern_candidates.csv">Family候选</a></p>',
 '<p class="note">M=Mono；D=RGB-D；DS=RGB-D + Semantic。'
 '输入维度独立于family：TRAD=Traditional、LEARN=Learning-based、3DGS、FF=Feedforward、'
 'SEM=Semantic-enhanced、3DGS+SEM=3DGS & Semantic-enhanced。'
 '语义组有RGB-D输入；无语义Hier配置仍保留其方法级family。MASt3R两配置当前输入均由用户确认是Mono；'
 '历史source Unknown不再作为当前输入，评测范围和上游校准细节不因本次确认而改变。'
 'MonoGS显示名可通过原MongGS source ID追溯。当前输入构成：'+
 '；'.join(e(g)+'='+str(sum(t['display_input_group']==g for t in tax)) for g in GROUPS)+
 '。</p><nav>']
 for f in figures:L.append('<a href="#'+e(figbase(f))+'">'+e(figbase(f))+'</a> · ')
 L+=['</nav><h2>固定顺序与taxonomy</h2><div class="scroll"><table><thead><tr>'+
 "".join('<th>'+x+'</th>' for x in ["顺序","配置显示名","输入","Family","范围","来源configuration_id","11B细节"])+
 '</tr></thead><tbody>']
 for t in tax:
  c=t["configuration_id"]
  L.append('<tr>'+ "".join('<td>'+e(v)+'</td>' for v in [t["row_order"],label(t),t["display_input_group"],t["algorithm_family"],t["evaluation_scope"],c])+
   f'<td><a href="11b_review_index.html#config-{old[c]:02d}">单配置页</a></td></tr>')
 L+=['</tbody></table></div><p><a href="../tables/11c_overview/configuration_taxonomy.csv">完整taxonomy和证据CSV</a></p>']
 csvs=dict(zip(FIGURES.values(),["distribution_summary","speed_response_matrix","altitude_response_matrix","finite_coverage_matrix","precision_efficiency_matrix"]))
 for f in figures:
  name=figbase(f);good=viewed(f,reviewed)
  L.append('<figure id="'+e(name)+'"><h2>'+e(name)+'</h2><p class="'+("ok" if good else "pending")+'">'+
    ("已实际查看，PNG哈希绑定" if good else "pending：尚未实际查看")+
    ' · <a href="'+e(figpath(f,"png"))+'">原尺寸PNG</a> · <a href="'+e(figpath(f,"svg"))+'">放大SVG</a>'+
    ' · <a href="../tables/11c_overview/'+csvs.get(name,"configuration_taxonomy")+'.csv">数值CSV</a></p>'+
    '<a href="'+e(figpath(f,"png"))+'"><img loading="lazy" src="'+e(figpath(f,"png"))+'" alt="'+e(name)+'"></a>'+
    '<figcaption>'+e(f.get("caption",""))+'</figcaption></figure>')
 L+=['<p>大图按浏览器宽度显示时可点击原PNG或SVG放大；不省略行标签。'
 '这些材料不自动形成新论文名单或family-level结论。</p></html>']
 return "\n".join(L)+"\n"
