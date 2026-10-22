"""Pure Step 11B narrative rendering: no file IO or research entry points."""
import html
import json
from collections import Counter

SCENES = ("building", "houses", "pool", "road", "roundabout")
TOPICS = {"grid":"条件网格", "response":"三档条件响应", "distribution_repeat":"序列分布与重复运行",
          "composition_efficiency":"场景组成与配置内效率关联"}
RELATIONS = {"all_same_direction":"五景与整体同向","has_opposite_scenes":"有场景反向",
 "overall_undefined":"整体未定义","incomplete_scenes":"场景不完整",
 "includes_numerical_zero_or_mixed":"含数值零或混合"}

def j(p,k):
 v=p.get(k)
 return [] if v in (None,"") else json.loads(v) if isinstance(v,str) else v
def n(v):return "未定义" if v in (None,"") else format(float(v),".6g")
def i(p,k):return int(p.get(k) or 0)
def b(v):return v is True or v in ("True","true")
def names(rows):return "、".join("「"+p["configuration_id"]+"」" for p in rows) or "无"
def total(rows,k):return sum(i(p,k) for p in rows)
def sign(v):
 return "unavailable" if v in (None,"") else "positive" if float(v)>1e-12 else "negative" if float(v)<-1e-12 else "numerical_zero"
def protocol_note(checks):
 """Render version-bound facts passed from the already verified source manifest."""
 row=checks.get("accuracy_protocol_by_configuration",{}).get("SplaTAM::rgbd",{})
 migrated=(row.get("source_sha256")=="337a4d462b9d238681be52284017b3e3ef445130303911de1cc1601a6d9c8f7b"
  and "Sim(3)" in row.get("alignment_status","") and "/100" not in row.get("rmse_unit_status","")
  and "unverified" not in row.get("rmse_unit_status","").lower())
 splatam=("本版SplaTAM已接入经审计的新CSV，采用米制外部evo/Sim(3)平移APE RMSE。" if migrated else
  "本版未由source_manifest确认SplaTAM新协议数值接入，不能把旧快照改贴新外部evo米制标签。")
 return ("MonoGS为米制evo APE RMSE（keyframes only）；"+splatam+
  __import__('version_support').sgs_accuracy_note(checks.get("accuracy_protocol_by_configuration",{}).get("SGS-SLAM::semantic",{})) +
  "runtime统一为秒，reported FPS为主要吞吐指标；不反推FPS或按相机采样率宣称实时性。"
  "本组memory保持本版旧阶段来源值，不等同独立审计的Table 2 Peak Memory (GiB)及GPU_RESERVED/CPU_RSS*两类型，不跨类型排名。"
  "实验与输出覆盖SR专题已完成并冻结，本组有限RMSE比例不代替SR@80/90/95，也未据SR筛除误差记录。")
def basename(f):return f.get("basename") or str(f["png"]).rsplit("/",1)[-1].rsplit(".",1)[0]
def viewed(f,reviewed):
 r=reviewed.get(basename(f),{})
 return isinstance(r,dict) and r.get("status")=="visually_reviewed" and bool(r.get("sha256"))
def topic(f):
 name=basename(f)
 if name.endswith("_grid"):return "grid"
 if name.endswith("_response"):return "response"
 return next((k for k in TOPICS if name.startswith(k+"_")),"other")
def asset(f,ext):return "../figures/11b_review/"+str(f[ext]).rsplit("/",1)[-1]
def partition(lines,title,patterns,yes,insufficient=lambda p:False):
 positive=[p for p in patterns if yes(p)]
 unknown=[p for p in patterns if not yes(p) and insufficient(p)]
 no=[p for p in patterns if not yes(p) and not insufficient(p)]
 lines.append(f"- **{title}**：观察到{len(positive)}/{len(patterns)}：{names(positive)}。"
              f"已检查未观察到{len(no)}/{len(patterns)}：{names(no)}；"
              f"相关记录／有限值不足而不能完整判断{len(unknown)}/{len(patterns)}：{names(unknown)}。")
def endpoint(p,axis):
 label="速度" if axis=="speed" else "高度"
 d=[i(p,axis+"_endpoint_"+k) for k in ("positive","negative","numerical_zero","unavailable")]
 t=[i(p,axis+"_triple_"+k) for k in ("nondecreasing","nonincreasing","numerically_flat","nonmonotonic","unavailable")]
 return label+"端点正/负/数值零/不可算="+"/".join(map(str,d))+"（分母15）；三档非降/非升/平坦/非单调/缺失="+"/".join(map(str,t))+"（分母15）"
def composition(p,axis):
 label="速度" if axis=="speed" else "高度"
 views=[r for r in j(p,axis+"_views_json") if r.get("value") is not None]
 bounds="["+n(min(r["value"] for r in views))+", "+n(max(r["value"] for r in views))+"]" if views else "未定义"
 flips=[r for r in j(p,axis+"_loso_json") if r.get("value") is not None and sign(r["value"])!=sign(p.get(axis+"_V1"))]
 mixed="含正负场景贡献" if b(p.get(axis+"_opposing_scene_contributions")) else "未见正负场景贡献并存"
 return (f"{label}V1={n(p.get(axis+'_V1'))}（F/C={i(p,axis+'_F_blocks')}/{i(p,axis+'_C_blocks')}块），"
  f"{mixed}；V0–V4范围{bounds}、{i(p,axis+'_view_direction_changes')}视图改变方向，"
  f"删场景{len(flips)}次改变方向（"+("、".join(r["removed_scene"]+"="+n(r["value"]) for r in flips) or "无")+"）")

def build_report(patterns,claims,selections,figures,reviewed,checks):
 patterns=sorted(patterns,key=lambda p:p["configuration_id"])
 N=len(patterns);methods=sorted({p["method_directory"] for p in patterns})
 pending=[f for f in figures if not viewed(f,reviewed)]
 L=["# 第11B步：全配置可视化、共性与反例、选例依据审查","",
 "第11步仍为“待全配置代表性复核的案例草稿”；本报告使用当前冻结输入，早期版本与历史完成记录通过更新存档保留。"
 "本轮是全配置内部审阅，不确定新的论文正文名单，不开始第12步、底层来源调查或补跑。","",
 protocol_note(checks),"",
 "## 共性、差异和反例","",
 f"固定configuration_id字典序检查 **{N}配置、{len(methods)}个原方法目录**。方法数仅按"
 "manifest.method_directory去重；同方法多个配置不是独立支持票。以下报配置清单和条件分母，"
 "不作投票、算法家族推断或显著性解释。原方法目录为："+"、".join(methods)+"。","",
 f"条件分析使用{total(patterns,'n_retained_runs')}条保留运行、"
 f"{total(patterns,'n_observed_sequences')}个观测配置×序列；"
 "条件格网按44个带标签序列标识并集展示。无条件标签记录仍保留在第6步输入，"
 "不填造高度/速度。当前记录不是全部历史尝试。当前评测范围构成："+"、".join(k+"="+str(v) for k,v in sorted(Counter(p["evaluation_scope"] for p in patterns).items()))+"；各范围分开，范围标签不证明逐次完成。","",
 "[图册入口](11b_review_index.html)按配置和问题导航；[现象矩阵](../tables/11b_review/configuration_patterns.csv)"
 "给出精确值、分母、条件、成员与旧表证据键。","",
 "| 问题 | 数值正 | 数值负 | 数值零 | 不可算 | 总条件数 |","|---|---:|---:|---:|---:|---:|"]
 for axis,label in (("speed","速度8−2"),("altitude","高度30−10")):
  nums=[total(patterns,axis+"_endpoint_"+k) for k in ("positive","negative","numerical_zero","unavailable")]
  L.append("| "+label+" | "+" | ".join(map(str,nums+[sum(nums)]))+" |")
 L+=["","上述为配置×场景×固定条件数，不是独立算法/实验数。abs(diff)≤1e-12仅为浮点数值零，"
 "没有实用退化、practically insensitive或显著性阈值。","",
 "| 三档形状 | 非降 | 非升 | 数值平坦 | 非单调 | 因缺失不可判 | 总条件数 |",
 "|---|---:|---:|---:|---:|---:|---:|"]
 for axis,label in (("speed","速度2/4/8"),("altitude","高度10/20/30")):
  nums=[total(patterns,axis+"_triple_"+k) for k in ("nondecreasing","nonincreasing","numerically_flat","nonmonotonic","unavailable")]
  L.append("| "+label+" | "+" | ".join(map(str,nums+[sum(nums)]))+" |")
 L+=["","端点差不能替代三档形状。缺失处不插值、不补零。下面区分观察到、已查未观察到、"
 "数据不足，不能因此前没有重点图就认定没有现象。",""]
 partition(L,"同场景速度方向随高度改变",patterns,lambda p:i(p,"n_speed_reversal_scenes")>0,
           lambda p:i(p,"speed_endpoint_unavailable")>0)
 for axis,label in (("speed","速度"),("altitude","高度")):
  partition(L,label+" V1正负场景贡献并存",patterns,lambda p,a=axis:b(p.get(a+"_opposing_scene_contributions")),
            lambda p,a=axis:len(j(p,a+"_scene_contributions_json"))<5)
  partition(L,label+" V0–V4相对V1改变方向",patterns,lambda p,a=axis:i(p,a+"_view_direction_changes")>0,
            lambda p,a=axis:len([r for r in j(p,a+"_views_json") if r.get("value") is not None])<5)
  partition(L,label+"固定F逐场景剔除改变方向",patterns,lambda p,a=axis:i(p,a+"_loso_direction_changes")>0,
            lambda p,a=axis:bool(j(p,a+"_missing_loso_scenes_json")))
 L+=["","V0保留两端不同成员；V1在共同有限块F上等权，V2对场景等权，V3限完整有限块C，"
 "V4换序列内中位数。删场景固定原F，删后结果不替代主结果。方向未变不等于幅度未变。",""]
 for m in ("fps","runtime","memory"):
  same=[p for p in patterns if p.get(m+"_scene_relation")=="all_same_direction"]
  opp=[p for p in patterns if p.get(m+"_scene_relation")=="has_opposite_scenes"]
  rest=[p for p in patterns if p not in same and p not in opp]
  L.append(f"- **RMSE—{m}整体与五景**：全部同向{len(same)}/{N}：{names(same)}；"
           f"至少一景反向{len(opp)}/{N}：{names(opp)}；含数值零/常数未定义/不完整{len(rest)}/{N}：{names(rest)}。")
 overall=[p for p in patterns if b(p.get("co_worsening_all_three_overall"))]
 allsc=[p for p in patterns if b(p.get("co_worsening_all_scenes_and_three"))]
 L+=["",f"“误差较高与FPS较低、runtime和memory较高同时关联”在整体出现于{len(overall)}/{N}：{names(overall)}；"
 f"三项整体及五场景全部同向{len(allsc)}/{N}：{names(allsc)}。"
 "仅为同配置、同一有限运行交集的序列均值秩关联，不是资源换精度或机制；"
 "常数向量未定义而非0，FPS/runtime关系不能反推已确认帧数。","",
 "## 重复、覆盖与同等检查投入","",
 f"repeat_sd可估{total(patterns,'repeat_sd_estimable')}/{total(patterns,'n_observed_sequences')}序列，"
 f"其余{total(patterns,'repeat_sd_undefined')}未定义。全无效格{total(patterns,'all_nonfinite_cells')}、"
 f"无记录格{total(patterns,'no_record_cells')}分别展示，不合称失败。"]
 special=[p for p in patterns if b(p.get("special_repetition_provenance_unresolved"))]
 partial=[p for p in patterns if i(p,"n_finite_runs")<i(p,"n_retained_runs")]
 L+=["相同重复来源限制继续保留："+names(special)+"。相同值及删一不变不证明独立性；"
 "浮点sd残差也不能反向否定相同原值。",
 f"有限运行少于保留运行的配置{len(partial)}/{N}：{names(partial)}。运行有限率与序列至少一次有限率分开，"
 "两者都不是完整轨迹成功率。"]
 ex=checks.get("expanded_condition_sensitivity",{})
 if ex:
  L.append(f"此前详细条件敏感性仅{ex.get('old_problems','未记录')}问题；本轮以第9步同一确定性纯函数补齐"
  f"{ex.get('newly_checked_problems','未记录')}个，共{ex.get('all_problems','未记录')}个。"
  f"旧{ex.get('old_rows_matched','未记录')}行、{ex.get('old_fields_matched','未记录')}字段一致，未运行旧main或改公式。")
 L.append(f"当前条件基线不可算{total(patterns,'condition_baselines_unavailable')}/"
 f"{total(patterns,'current_condition_sensitivity_problems')}；删一检查中不可算变体"
 f"{total(patterns,'condition_trials_unavailable')}次。这是端点数据不足，"
 "与此前没有投入同等检查分开登记。所查范围不是置信区间。")
 changes=[p for p in patterns if i(p,"condition_problems_any_direction_change")>0]
 L.append(f"条件敏感性至少一个问题所查变体改变方向{len(changes)}/{N}：{names(changes)}。")
 L+=["","## 旧案例与候选主张的处理","",
 "原重点图不是随机样本，也没有已登记的事前技术路线分层抽样。"
 "[选例依据表](../tables/11b_review/selection_rationale.csv)保存第7步实际规则、第11步纳入角色和本轮候选角色；"
 "原依据与本轮建议分栏，不补写不存在的假设。","",
 "- **原ORB-SLAM2条件响应主线**：保留具体局部诊断，先呈现全部配置的反转与非单调名单；"
 "其它配置的相反或更一致模式同样呈现，不能将两个场景推广到全体。",
 "- **原DPVO场景抵消主线**：可保留为一个抵消例子，收窄代表性；"
 "权重、有限集合、代表值和删场景影响的候选例从全配置对照中共同审阅，不预保旧例。",
 "- **原VGGT覆盖／ORB-SLAM3重复主线**：保留覆盖与重复联合解读的问题；"
 "具体选例需比较所有配置的条件敏感性、覆盖和保留次数。"
 "单次未定义、相同重复来源限制和多次均高背景不被极端单次案例遮蔽。",
 "- **原Hier完整轨迹关联主线**：保留为限定配置范围的关联候选，须与其它配置及反向场景对照；"
 "是否仍符合三指标同向模式以当前矩阵为准；三项同向也不是因果tradeoff，500帧配置按独立范围核验。","",
 "这些是候选调整，不是新的正文名单。[主张适用矩阵](../tables/11b_review/claim_applicability.csv)"
 "逐主张覆盖全部配置，区分原字面范围和可供比较的抽象问题；范围不适用、数据不足、尚未检查不混用。"]
 if claims:
  ids=sorted({str(r.get("claim_id","")) for r in claims})
  L.append(f"适用矩阵共{len(claims)}行、{len(ids)}项候选主张；全部名单、理由和证据键以对应行为准。")
  for cid in ids:
   counts=Counter(str(r.get("applicability_category","未登记")) for r in claims if str(r.get("claim_id",""))==cid)
   L.append("- "+cid+"："+ "；".join(k+"="+str(v) for k,v in sorted(counts.items()))+"。")
 if selections:
  L+=["","此前未重点展示配置的候选审阅依据（不自动纳入正文）：",""]
  for r in selections:
   if b(r.get("prior_step7_selected")):continue
   note=r.get("selection_recommendation") or r.get("not_in_manuscript_reason") or ""
   roles=j(r,"candidate_roles_json")
   if note or roles:L.append("- 「"+r["configuration_id"]+"」："+str(note)+
                ("；候选角色："+ "、".join(str(x) for x in roles) if roles else "")+"。")
 L+=["","## 逐配置同结构审阅","",
 "以下与图册顺序一致。数值沿用各来源单位，不能按幅度跨配置排名。每段同时报告端点、"
 "三档、覆盖/重复、场景组成及效率；完整成员、原保留值和敏感性键在现象矩阵JSON列。",""]
 for idx,p in enumerate(patterns,1):
  c=p["configuration_id"];pages=[f for f in figures if c in f.get("configuration_ids",[])]
  seen=sum(viewed(f,reviewed) for f in pages)
  changes=sorted([r for r in j(p,"condition_sensitivity_details_json")
   if r.get("baseline") is not None and int(r.get("direction_changes") or 0)>0],
   key=lambda r:(str(r.get("scene")),str(r.get("problem"))))
  example=""
  if changes:
   r=changes[0]
   example=(f"；按场景/问题字典序列举一个方向改变例：{r['scene']}/{r['problem']}，"
    f"基线{n(r['baseline'])}，所查范围[{n(r.get('range_min'))}, {n(r.get('range_max'))}]"
    f"（键 {r['estimate_id']}）")
  L+=[f"### {idx:02d}. {c}","",
   f"范围「{p['evaluation_scope']}」；模态「{p['modality_declared']}」，语义「{p['semantic_usage']}」。"
   f"有限/保留运行{i(p,'n_finite_runs')}/{i(p,'n_retained_runs')}，"
   f"有限/观测序列{i(p,'n_finite_sequences')}/{i(p,'n_observed_sequences')}；"
   f"全无效/无记录格{i(p,'all_nonfinite_cells')}/{i(p,'no_record_cells')}。"
   f"对应页生成{len(pages)}、已实际查看{seen}、pending={len(pages)-seen}；"
   f"[图册定位](11b_review_index.html#c{idx:02d})。","",
   endpoint(p,"speed")+"；"+endpoint(p,"altitude")+"。速度方向随高度改变的场景为："+
   ("、".join(j(p,"speed_direction_reversal_scenes_json")) or "当前未观察到")+
   "；速度端点不完整场景为："+("、".join(j(p,"speed_direction_incomplete_scenes_json")) or "无")+"。","",
   f"序列均值分布mean/median/p90/max={n(p.get('rmse_sequence_mean'))}/{n(p.get('rmse_sequence_median'))}/"
   f"{n(p.get('rmse_sequence_p90'))}/{n(p.get('rmse_sequence_max'))}，只是本配置有限序列描述。"
   f"repeat_sd可估/未定义={i(p,'repeat_sd_estimable')}/{i(p,'repeat_sd_undefined')}；"
   f"删一序列均值范围非零{i(p,'sequence_drop_range_nonzero')}个，相同有限RMSE重复"
   f"{i(p,'sequences_identical_rmse_repeats')}个。条件敏感性{i(p,'current_condition_sensitivity_problems')}问题中"
   f"{i(p,'condition_problems_any_direction_change')}个所查变体改变方向，"
   f"{i(p,'condition_baselines_unavailable')}个基线不可算"+example+"。"+
   ("原有相同误差重复来源限制仍在。" if b(p.get("special_repetition_provenance_unresolved")) else ""),"",
   composition(p,"speed")+"；"+composition(p,"altitude")+"。","",
   "配置内关联："+ "；".join(m+"整体ρ="+n(p.get(m+"_overall_rho"))+
    "（"+RELATIONS.get(p.get(m+"_scene_relation"),str(p.get(m+"_scene_relation")))+
    "，反向场景="+("、".join(j(p,m+"_opposite_scenes_json")) or "无")+
    "，未定义场景="+("、".join(j(p,m+"_undefined_scenes_json")) or "无")+"）"
    for m in ("fps","runtime","memory"))+
   "。每序列的两指标均值取同一有限运行交集，未推断帧数或机制。",""]
 L+=["## 图册验收、证据与剩余缺口","",
 f"新增PNG{len(figures)}张，实际查看且PNG哈希绑定{len(figures)-len(pending)}，pending={len(pending)}。"
 "生成、实际查看、同问题综合比较分别登记于[覆盖状态](11b_review_coverage.csv)，三者不能替代。"]
 if pending:L.append("尚未实际查看："+ "、".join("["+basename(f)+"]("+asset(f,"png")+")" for f in pending)+"。未计作完成视觉验收。")
 else:L.append("本轮所有新增PNG均有实际视觉审阅记录；不等于正式论文排版或科学来源核验。")
 L+=["",
 "- [输入快照与约定](11b_review_spec.json)：冻结哈希、展示规则、既有公式和新增确定性检查范围。",
 "- [现象矩阵](../tables/11b_review/configuration_patterns.csv)：端点、三档、场景贡献、V0–V4、"
 "删场景、重复值、配置内相关、来源与成员键。",
 "- [条件敏感性补齐表](../tables/11b_review/condition_sensitivity.csv)：旧问题与新增问题分开标记；"
 "[序列索引](../tables/11b_review/sequence_index.csv)解释专题图编号。",
 "- [主张适用矩阵](../tables/11b_review/claim_applicability.csv)与"
 "[选例依据](../tables/11b_review/selection_rationale.csv)：支持、反例、局限、范围和检查状态。","",
 "代表值保持序列内有限运行均值、序列等权；有限比例固定0～1，单配置五场景共用其RMSE色标/纵轴。"
 "跨配置未统一已核实单位，不能色深排名。五景和中间条件全部保留，大值不裁剪；全无效与无记录分开，缺失断线。","",
 "其余误差单位/对齐与生成版本、效率计时范围、旧分析memory与独立有类型内存的版本区别，以及相同重复来源和独立性仍按各自证据限定。"
 "当前记录不是全部历史尝试，未保留或计划补跑不自动入失败分母。跨序列分布、重复运行波动和单次轨迹"
 "误差分布不同；敏感性范围不是置信区间。未做显著性检验、聚类、因果解释、技术路线分类或新模型。","",
 "## 对第11步主张的当前建议","",
 "- **可保留为已观察事实或解释边界**：C11_COV的两种数值覆盖分母、C11_CONSTANT的常数相关未定义、C11_PROVENANCE的来源限制；C11_P1～P6限定在原指定配置对的描述值可留在候选补充材料。它们不证明轨迹成功、独立性或配置间绝对优劣。",
 "- **需要收窄并重组呈现**：C11_A先交代全配置三档形状与方向反转，再决定是否用ORB2；C11_B先交代正负场景贡献的支持与反例，再决定是否保留DPVO；C11_REPEAT需连同有限次数、删一幅度和单次未定义呈现；C11_D只作限定配置内的关联，不以两个Hier范围的相近模式声称普遍规律。C11_T_DPVO与C11_T_ORB-SLAM3只是整体/分景不一致的案例，不是唯一案例。",
 "- **暂缓作为最终论文论证**：原四条主线的整套组织及原重点案例名单仍待用户审阅，不因本轮审查而自动保留。C11_DROID_POOL及四个相同重复配置的独立稳定性或生成机制解释、C11_EXCLUDED中的更强断言，当前证据不能补足；C11_AVAIL保持数值重叠线索，不升级为融合收益。来源未闭合的定量公开解释继续遵守原release_status。",
 "允许原DPVO、ORB2/3等退为极端诊断或被更合适的成对案例替代。候选关注点可按“端点不等于单调”“整体不等于局部”“权重/代表值影响”“数值覆盖与重复边界”重组，但本轮不确定新的正文结构与名单。","",
 "本轮已把条件敏感性补到全部配置；Hier专属逐记录A/B代数分解、六对专属跨配置删场景分析仍限原范围，没有冒充全配置检查，也不以未展开这些附加检查为排除其它配置的理由。报告显示值有舍入，完整精度见矩阵，显示范围两端相同不等于原值逐位相等。","",
 "复核入口：在工作区执行 /home/yuan/anaconda3/bin/python3 -B scripts/review_all_configurations.py --verify。默认生成拒绝覆盖；明确刷新使用 --overwrite，仍要求既有生成哈希无人工修改。只改文档审阅状态不重新计算数值，视觉记录绑定实际PNG哈希。","",
 "历史版本按输入版本记录保留；当前报告与图册由同一冻结版本生成。停在候选审阅，不自动整合论文、追查底层来源或补跑。"]
 return "\n".join(L)+"\n"

def build_index(patterns,figures,reviewed):
 patterns=sorted(patterns,key=lambda p:p["configuration_id"]);figures=list(figures)
 configs={p["configuration_id"]:idx for idx,p in enumerate(patterns,1)}
 e=lambda x:html.escape(str(x),quote=True)
 parts=['<!doctype html><html lang="zh-CN"><meta charset="utf-8">',
 '<meta name="viewport" content="width=device-width,initial-scale=1">',
 '<title>全配置审阅图册 · 11B</title>',
 '<style>body{margin:0;background:#f6f7f9;color:#18232d;font:16px/1.6 system-ui,sans-serif}'
 'header,main{max-width:1500px;margin:auto;padding:1.3rem}nav,figure{background:white;padding:1rem;border:1px solid #ccd3da}'
 'a{color:#0758a1}h1,h2,h3{line-height:1.3}figure{margin:1rem 0 2.2rem}img{display:block;width:100%;height:auto}'
 'figcaption{margin-top:.8rem;overflow-wrap:anywhere}.badge{padding:.2rem .5rem;border:1px solid #708090}'
 '.seen{background:#e8f5e9}.pending{background:#fff0d7}.navcols{columns:3}.navcols li{break-inside:avoid}'
 '.note{background:#eaf1f7;padding:.8rem}@media(max-width:800px){.navcols{columns:1}}'
 '@media print{header nav{display:none}figure{break-inside:avoid}body{background:white}}</style>',
 '<header><h1>全配置审阅图册 · 第11B步</h1><p>24配置均按五场景和相同条件模板展示。'
 '范围按当前manifest证据标注，500帧与完整轨迹分开；跨配置颜色不是统一单位的绝对性能排名。</p>',
 '<p><a href="11b_all_configuration_review.md">综合报告</a> · <a href="11b_review_coverage.csv">审阅状态</a> · '
 '<a href="../tables/11b_review/configuration_patterns.csv">数值/成员矩阵</a> · '
 '<a href="../tables/11b_review/sequence_index.csv">序列编号</a></p><nav><h2>按配置</h2><ol class="navcols">']
 for idx,p in enumerate(patterns,1):
  parts.append(f'<li><a href="#c{idx:02d}">{e(p["configuration_id"])}</a> ({e(p["evaluation_scope"])})</li>')
 parts+=['</ol><h2>按问题</h2><p>']
 for t,title in TOPICS.items():
  parts.append(e(title)+": "+" ".join(f'<a href="#{e(basename(f))}">{e(basename(f))}</a>'
   for f in figures if topic(f)==t)+"<br>")
 parts+=['</p></nav></header><main><p class="note">图中数值沿用来源单位。有限RMSE不是完整轨迹成功；'
 '单次有限结果的repeat_sd、常数向量rho未定义。删一范围不是置信区间。点击PNG按原尺寸查看，SVG供缩放。</p>']
 shown=set()
 def card(f):
  name=basename(f)
  if name in shown:raise ValueError("Repeated figure "+name)
  shown.add(name);good=viewed(f,reviewed);state="已实际查看（PNG哈希绑定）" if good else "pending：尚未实际查看"
  linked="、".join(f'<a href="#c{configs[c]:02d}">{e(c)}</a>' for c in f.get("configuration_ids",[]) if c in configs)
  return (f'<figure id="{e(name)}"><h3>{e(name)} · {e(TOPICS.get(topic(f),"专题"))}</h3>'
   f'<p><span class="badge {"seen" if good else "pending"}">{state}</span> '
   f'<a href="{e(asset(f,"png"))}">原尺寸PNG</a> · <a href="{e(asset(f,"svg"))}">SVG</a></p>'
   f'<a href="{e(asset(f,"png"))}"><img loading="lazy" src="{e(asset(f,"png"))}" alt="{e(name)}：{e(f.get("caption",""))}"></a>'
   f'<figcaption>{e(f.get("caption",""))}<br>配置：{linked}</figcaption></figure>')
 for idx,p in enumerate(patterns,1):
  c=p["configuration_id"];local=[f for f in figures if c in f.get("configuration_ids",[])]
  parts.append(f'<span id="config-{idx:02d}"></span><section id="c{idx:02d}"><h2>{idx:02d}. {e(c)}</h2><p>范围{e(p["evaluation_scope"])}；'
   f'运行有限/保留{i(p,"n_finite_runs")}/{i(p,"n_retained_runs")}；'
   f'序列有限/观测{i(p,"n_finite_sequences")}/{i(p,"n_observed_sequences")}。</p>')
  parts.append('<p>同配置专题：'+" · ".join(f'<a href="#{e(basename(f))}">{e(TOPICS.get(topic(f),basename(f)))}</a>'
   for f in local if topic(f) not in ("grid","response"))+'</p>')
  for f in local:
   if topic(f) in ("grid","response") and basename(f) not in shown:parts.append(card(f))
  parts.append('</section>')
 parts.append('<section id="topics"><h2>全配置专题分页</h2><p>每页配置顺序固定，不按极端程度筛选。</p>')
 for f in figures:
  if basename(f) not in shown:parts.append(card(f))
 parts.append('</section><p>本图册只供全配置审阅，不自动决定论文名单。</p></main></html>')
 if len(shown)!=len(figures):raise ValueError("Every PNG must appear exactly once")
 return "\n".join(parts)+"\n"
