"""Pure renderable evidence classification for the step 11B all-configuration review.

No file access, performance aggregation, ranking, model fitting or manuscript edits.
The caller supplies checked pattern rows and original stage-11 registry/pair rows.
"""
import json

PAT = "tables/11b_review/configuration_patterns.csv"
REGISTRY = "reports/11_claim_registry.csv"
AVAIL = "tables/10_relationships/pairwise_availability.csv"
TOL = 1e-12
SPECIAL = {"DROID-SLAM::rgbd", "ElasticFusion::rgbd", "SLAM3R::mono", "VGGT-LONG::mono"}
STEP7_RULES = {
    "ORB-SLAM2::mono": ("01_rmse_distribution",
        "至少10条有限序列且均值为正；(mean-median)/abs(mean)最大，按configuration_id破同分；展示完整ECDF。"),
    "DROID-SLAM::rgbd": ("02_scene_rmse",
        "每个场景至少2条有限序列且总体均值为正；(最大场景均值-最小场景均值)/abs(总体序列均值)最大。"),
    "ORB-SLAM3::rgbd": ("03_repeat_rmse",
        "至少2次有限运行且均值为正的序列中，有限极差/abs(mean)最大；展示所属配置repeat_sd最大的3条序列。"),
    "VGGT-SLAM::mono": ("04_finite_rmse_fraction",
        "观测序列中无任何有限RMSE结果的比例最大，按configuration_id破同分。"),
    "hierslam::rgbd_whole": ("05_efficiency_cohorts",
        "存在A非B记录、B非空且A均值非零的效率比较中，abs(B-A)/abs(A_mean)最大；配置名和指标破同分。"),
}

def js(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False, separators=(",", ":"))

def decoded(value):
    return json.loads(value) if isinstance(value, str) else value

def flag(value):
    if value in (True, "True"):
        return True
    if value in (False, "False"):
        return False
    raise ValueError("Expected explicit boolean: " + repr(value))

def number(value):
    return None if value in (None, "") else float(value)

def integer(value):
    return int(value)

def sg(value):
    value = number(value)
    return "unavailable" if value is None else "numerical_zero" if abs(value) <= TOL else "positive" if value > 0 else "negative"

def selected_evidence(pattern, fields):
    """Keep exact values and full JSON members, not a prose-only classification."""
    return {field: decoded(pattern[field]) if field.endswith("_json") else pattern[field] for field in fields}

def _pair_details(c, pairrows):
    details = []
    for r in pairrows:
        if c not in (r["configuration_A"], r["configuration_B"]):
            continue
        own = "A" if c == r["configuration_A"] else "B"
        other = "B" if own == "A" else "A"
        details.append({
            "pair_id": r["pair_id"], "own_side": own,
            "other_configuration": r["configuration_" + other],
            "n_P": integer(r["n_P"]), "n_U": integer(r["n_U"]),
            "both_finite_n": integer(r["both_finite_n"]),
            "only_this_configuration_finite_n": integer(r["only_" + own + "_finite_n"]),
            "only_other_configuration_finite_n": integer(r["only_" + other + "_finite_n"]),
            "neither_finite_n": integer(r["neither_finite_n"]),
            "only_this_members": decoded(r["only_" + own + "_finite_members_json"]),
            "only_other_members": decoded(r["only_" + other + "_finite_members_json"]),
            "neither_members": decoded(r["neither_finite_members_json"]),
            "both_members": decoded(r["both_finite_members_json"]),
            "scope_reference": r["scope_reference"],
            "evidence": {"table": AVAIL, "key": {"pair_id": r["pair_id"]},
                "member_fields": ["only_" + own + "_finite_members_json",
                                  "only_" + other + "_finite_members_json", "neither_finite_members_json"]},
        })
    return details

def export_correction_note(pattern, policy):
    policy = policy or {}
    if (pattern["configuration_id"] not in policy.get("authorized_changed_configurations", []) or
            policy.get("reason") != "user_confirmed_export_omission_corrected"):
        return ""
    return ("作者确认此前五条既有实验序列被导出代码遗漏，本轮恢复实际保留记录；"
            "不能再解释为尚未实验，记录恢复不自动增加有限值。"
            f"当前观测/至少一次有限条件序列={pattern['n_observed_sequences']}/{pattern['n_finite_sequences']}，"
            f"有限/保留运行={pattern['n_finite_runs']}/{pattern['n_retained_runs']}。")

def build_claims(patterns, oldclaims, pairrows, update_policy=None):
    """Return all 18 x 24 rows; literal scope and abstract phenomenon are separate."""
    if len(patterns) != 24 or len(oldclaims) != 18:
        raise ValueError("Expected checked 24 configurations and original 18 claims")
    result = []
    for old in oldclaims:
        claim = old["claim_id"]
        literal = set(decoded(old["configurations_json"]))
        for p in patterns:
            c = p["configuration_id"]
            fields = ["n_observed_sequences", "n_finite_sequences", "n_retained_runs", "n_finite_runs"]
            extra = {}
            category = "checked_not_observed"
            question = ""
            reason = ""
            additional_limit = ""
            if claim == "C11_A":
                question = "同一场景的速度端点数值方向是否随固定高度改变；不是把ORB2专属H10/H30主张迁到所有配置。"
                fields += ["speed_endpoints_json", "speed_triples_json", "speed_direction_reversal_scenes_json",
                           "speed_direction_incomplete_scenes_json", "condition_sensitivity_details_json",
                           "prior_condition_sensitivity_problems", "current_condition_sensitivity_problems"]
                n = integer(p["n_speed_reversal_scenes"])
                missing = decoded(p["speed_direction_incomplete_scenes_json"])
                category = "local_support" if n else "data_insufficient_for_complete_comparison" if missing else "checked_not_observed"
                reason = f"五场景中{n}场景存在跨高度正负速度端点方向；{len(missing)}场景至少一个端点差不可算。三档分类与35问题变体另列，不把端点方向当严格单调。"
            elif claim == "C11_B":
                question = "完整F上的速度总体差是否由相反场景贡献组成；不预设其他配置也具有DPVO所述的小总体差。"
                fields += ["speed_V1", "speed_F_blocks", "speed_C_blocks", "speed_scene_contributions_json",
                           "speed_views_json", "speed_loso_json", "speed_missing_loso_scenes_json",
                           "speed_view_direction_changes", "speed_loso_direction_changes"]
                opposing = flag(p["speed_opposing_scene_contributions"])
                category = "support" if opposing else "counterpattern"
                reason = ("存在正负场景贡献。" if opposing else "已检查未观察到正负场景贡献同时存在。") + \
                         f"完整F差={p['speed_V1']}，块数={p['speed_F_blocks']}；V0～V4方向改变{p['speed_view_direction_changes']}，逐场景剔除方向改变{p['speed_loso_direction_changes']}。"
                additional_limit = "没有定义实际小效应阈值；正负抵消不等于整体实际不敏感。"
            elif claim == "C11_COV":
                question = "逐运行和至少一次有限序列的数值覆盖、全无效条件与缺记录如何影响可见均值。"
                fields += ["finite_fraction", "all_nonfinite_cells", "no_record_cells", "coverage_details_json",
                           "speed_endpoints_json", "altitude_endpoints_json"]
                nf, nr = integer(p["n_finite_runs"]), integer(p["n_retained_runs"])
                ns, no = integer(p["n_finite_sequences"]), integer(p["n_observed_sequences"])
                category = "local_support" if nf < nr else "checked_not_observed"
                reason = f"有限运行{nf}/{nr}，至少一次有限序列{ns}/{no}；全无效格{p['all_nonfinite_cells']}，无记录格{p['no_record_cells']}。"
                additional_limit = "区分指标定义适用于所有配置；当前全有限仅表示没有此缺失模式，不反驳概念区别或证明完整轨迹成功。"
            elif claim == "C11_REPEAT":
                question = "有限重复对序列均值、中位数及条件端点差的影响；不以未定义阈值宣称单条主导，也不移植ORB3三高案例。"
                fields += ["repeat_sd_estimable", "repeat_sd_undefined", "sequence_drop_range_nonzero",
                           "sequences_mean_median_numeric_difference", "repeat_details_json",
                           "condition_problems_any_direction_change", "condition_sensitivity_details_json"]
                n = integer(p["repeat_sd_estimable"])
                changed = integer(p["sequence_drop_range_nonzero"])
                category = "data_insufficient" if not n else "local_support" if changed else "checked_not_observed"
                reason = f"重复SD可估{n}/{p['n_observed_sequences']}，未定义{p['repeat_sd_undefined']}；删一均值范围非零{changed}；条件问题方向改变{p['condition_problems_any_direction_change']}/{p['condition_baselines_computed']}个可算问题。"
                additional_limit = "非零是数值规则，不等于实际影响大；全相同重复有来源限制，单个有限值不能估计重复波动。"
            elif claim == "C11_D":
                question = "同运行有限交集中的RMSE—FPS负、RMSE—runtime/memory正关联是否同时存在，以及场景内是否保留。"
                fields += ["co_worsening_all_three_overall", "co_worsening_all_scenes_and_three",
                           "fps_overall_rho", "runtime_overall_rho", "memory_overall_rho",
                           "efficiency_relations_json", "efficiency_cohorts_json", "constant_correlation_views"]
                allsc = flag(p["co_worsening_all_scenes_and_three"])
                overall = flag(p["co_worsening_all_three_overall"])
                available = sum(number(p[m + "_overall_rho"]) is not None for m in ("fps", "runtime", "memory"))
                category = "support" if allsc else "local_support" if overall else "data_insufficient_for_three_metrics" if available < 3 else "counterpattern"
                reason = f"三个总体rho={p['fps_overall_rho']}/{p['runtime_overall_rho']}/{p['memory_overall_rho']}；总体三方向共同恶化={overall}，五场景全部保留={allsc}；A/B组成另列。"
                additional_limit = "只复用同运行交集关联及已有A/B均值；未为其它配置新做Hier专属E记录代数分解，不推断帧数、资源换精度或机制。"
            elif claim == "C11_DROID_POOL":
                question = "Pool条件差和重复误差相同、删一不变的数值模式是否在本配置同时存在。"
                fields += ["repeat_details_json", "condition_sensitivity_details_json", "special_repetition_provenance_unresolved"]
                pool = [r for r in decoded(p["repeat_details_json"]) if r["scene"] == "pool"]
                comparable = [r for r in pool if r["n_finite"] >= 2]
                equal = [r for r in comparable if r["finite_error_identical"] in (True, "True")]
                category = "data_insufficient" if not comparable else "local_support" if equal else "checked_not_observed"
                reason = f"Pool观测{len(pool)}序列，其中{len(comparable)}至少两个有限值；已提供误差字段完全相同的序列{len(equal)}。条件差值和检查范围需同时查看，不能由重复相同声称独立稳定。"
                extra["pool_comparable_sequences"] = [r["sequence"] for r in comparable]
                extra["pool_identical_sequences"] = [r["sequence"] for r in equal]
            elif claim.startswith("C11_P") and claim[5:].isdigit():
                question = "指定两个配置之间的序列排序关系；非单配置可泛化事实。"
                category = "specific_pair_participant" if c in literal else "scope_not_applicable"
                reason = ("本配置是原指定配置对成员；整对数值、场景分层、F/C与中位数证据保留。" if c in literal else
                          "本配置不是该主张指定配置对成员；范围不适用，不标为未检查或证据较弱。")
                if c in literal:
                    extra["specific_pair"] = sorted(literal)
                    extra["pair_numeric_evidence"] = decoded(old["key_numbers_and_denominators_json"])
                additional_limit = "不能拆成两票独立支持；没有将该配置对相关性外推到其它配置。"
            elif claim == "C11_AVAIL":
                question = "本配置参与的允许/限定配置对中，是否存在双方各自独有有限结果及共同无有限结果。"
                pairs = _pair_details(c, pairrows)
                bilateral = [r for r in pairs if r["only_this_configuration_finite_n"] > 0 and r["only_other_configuration_finite_n"] > 0]
                category = "local_support" if bilateral else "checked_not_observed" if pairs else "scope_not_applicable"
                reason = f"实际核查{len(pairs)}个可用性配置对，双向各自独有有限结果的配置对{len(bilateral)}；每对双方独有、共同有限与共同无有限的计数和成员分别列出，不把pair相加当独立样本。"
                extra["pair_availability_details"] = pairs
                extra["bilateral_pair_ids"] = [r["pair_id"] for r in bilateral]
                additional_limit = "只在实际共同观测集合P上描述；500帧与其它范围不直接配对；线索不等于已实现融合或切换收益。"
            elif claim in ("C11_T_DPVO", "C11_T_ORB-SLAM3"):
                question = "总体RMSE—效率关联方向是否在场景内出现相反结果；原配置专属数值另保留。"
                fields += ["efficiency_relations_json", "fps_scene_relation", "runtime_scene_relation", "memory_scene_relation",
                           "fps_opposite_scenes_json", "runtime_opposite_scenes_json", "memory_opposite_scenes_json",
                           "fps_undefined_scenes_json", "runtime_undefined_scenes_json", "memory_undefined_scenes_json"]
                opposites = {m: decoded(p[m + "_opposite_scenes_json"]) for m in ("fps", "runtime", "memory")}
                undefined = {m: decoded(p[m + "_undefined_scenes_json"]) for m in ("fps", "runtime", "memory")}
                anyopp = any(opposites.values())
                category = "local_support" if anyopp else "data_insufficient_for_complete_comparison" if any(undefined.values()) else "counterpattern"
                reason = "相反场景=" + js(opposites) + "；未定义场景=" + js(undefined) + "。逐场景n和rho逐项列出，无显著性或实际效应阈值。"
            elif claim == "C11_CONSTANT":
                question = "RMSE—效率相关是否出现常数输入导致未定义的视图。"
                fields += ["constant_correlation_views", "efficiency_relations_json"]
                n = integer(p["constant_correlation_views"])
                category = "local_support" if n else "checked_not_observed"
                reason = f"18个总体/分场景×指标视图中，常数相关未定义{n}；未定义不填0，也不解释为真实资源恒定。"
            elif claim == "C11_PROVENANCE":
                question = "已标记四配置的重复来源限制与本配置是否相关；数值相同本身不能确认来源机制。"
                fields += ["special_repetition_provenance_unresolved", "sequences_identical_provided_error_fields",
                           "sequences_identical_rmse_repeats", "repeat_sd_estimable", "repeat_sd_undefined", "repeat_details_json"]
                marked = flag(p["special_repetition_provenance_unresolved"])
                category = "specific_case_with_source_limit" if marked else "scope_not_applicable"
                reason = f"原来源特别标记={marked}；当前带条件序列误差字段全相同{p['sequences_identical_provided_error_fields']}/{p['n_observed_sequences']}，只RMSE重复相同{p['sequences_identical_rmse_repeats']}。"
                additional_limit = (f"原主张各48条包含无标签序列；本11B矩阵中本配置有{p['n_observed_sequences']}条观测条件序列，"
                                    f"其中{p['n_finite_sequences']}条至少一次有限，两类分母分别保留。"
                                    "其它配置未列四配置来源警示，不代表来源已全部闭合。")
            elif claim == "C11_EXCLUDED":
                question = "现有描述性材料是否支持因果机制、赢家、语义无效、融合收益或全轨迹成功等更强命题。"
                fields += ["evaluation_scope", "constant_correlation_views"]
                category = "unsupported_stronger_claim"
                reason = "本轮仍没有随机/因果设计、统一绝对口径、实际融合系统或逐次完成标识；本配置的描述值不能补足这些证据。"
            else:
                raise ValueError("Unexpected stage-11 claim " + claim)
            fields = list(dict.fromkeys(fields))
            if claim in ("C11_A", "C11_B", "C11_COV", "C11_REPEAT"):
                reason += export_correction_note(p, update_policy)
            result.append({
                "claim_id": claim, "configuration_id": c, "method_directory": p["method_directory"],
                "evaluation_scope": p["evaluation_scope"],
                "literal_scope_status": "original_specific_configuration_or_pair_member" if c in literal else
                                        "universal_interpretive_boundary" if claim == "C11_EXCLUDED" else "outside_original_literal_configuration_scope",
                "review_question": question, "applicability_category": category,
                "support_level": "phenomenon_review_only_not_literal_claim_transfer",
                "reason": reason, "pattern_key_json": js({"table": PAT, "key": {"configuration_id": c}}),
                "evidence_fields_json": js(["$." + k for k in fields]),
                "evidence_values_json": js({**selected_evidence(p, fields), **extra}),
                "old_claim_reference": REGISTRY + "#claim_id=" + claim, "old_statement": old["statement"],
                "old_placement": old["placement"], "old_release_status": old["release_status"],
                "original_evidence_rows_json": old["evidence_rows_json"] if c in literal else js([]),
                "checks": "全部配置同模板检查；条件敏感性35问题/配置；数值与缺失适用性另列；本行分类不自动构成论文选例",
                "limitations": old["known_limits"] + " " + additional_limit +
                               " 数值正负容差1e-12只处理浮点；24配置不是24个独立方法/实验。",
            })
    if len(result) != 432 or len({(r["claim_id"], r["configuration_id"]) for r in result}) != 432:
        raise ValueError("Claim cross-product incomplete")
    return result

def build_selections(patterns, oldclaims, update_policy=None):
    """Document actual historical choices, then leave any new paper selection open."""
    result = []
    for i, p in enumerate(patterns, 1):
        c = p["configuration_id"]
        prior = [r for r in oldclaims if c in decoded(r["configurations_json"])]
        chosen = c in STEP7_RULES
        rule_key, rule = STEP7_RULES.get(c, ("", "未作为第7步五张重点图对象；不能据此推断没有相关规律。"))
        roles = []
        ev = {}
        def role(text, fields):
            roles.append(text)
            ev[text] = selected_evidence(p, fields)
        if integer(p["n_speed_reversal_scenes"]):
            role("条件响应方向依赖的候选对照", ["n_speed_reversal_scenes", "speed_direction_reversal_scenes_json",
                 "speed_endpoints_json", "condition_sensitivity_details_json"])
        else:
            role("速度方向反转问题的非支持或缺口对照", ["speed_endpoint_positive", "speed_endpoint_negative",
                 "speed_endpoint_unavailable", "speed_direction_incomplete_scenes_json"])
        if flag(p["speed_opposing_scene_contributions"]):
            role("场景抵消现象的候选对照", ["speed_V1", "speed_scene_contributions_json", "speed_views_json", "speed_loso_json"])
        else:
            role("速度场景贡献不呈正负并存的对照", ["speed_scene_contributions_json"])
        if integer(p["all_nonfinite_cells"]):
            role("全无效条件与可算均值边界候选", ["all_nonfinite_cells", "n_finite_runs", "n_retained_runs",
                 "n_finite_sequences", "n_observed_sequences", "coverage_details_json"])
        correction_note = export_correction_note(p, update_policy)
        if correction_note:
            role("导出恢复后的观测记录与有限结果边界", ["n_observed_sequences", "n_finite_sequences",
                 "n_retained_runs", "n_finite_runs", "all_nonfinite_cells", "no_record_cells", "coverage_details_json"])
        if integer(p["sequence_drop_range_nonzero"]):
            role("重复均值与条件敏感性候选；实际幅度待逐案审阅", ["sequence_drop_range_nonzero", "repeat_sd_estimable",
                 "condition_problems_any_direction_change", "repeat_details_json"])
        elif not integer(p["repeat_sd_estimable"]):
            role("单次有限结果不能估计重复波动的边界", ["repeat_sd_estimable", "repeat_sd_undefined", "repeat_details_json"])
        if flag(p["special_repetition_provenance_unresolved"]):
            role("相同重复误差且来源未闭合的边界", ["sequences_identical_provided_error_fields",
                 "special_repetition_provenance_unresolved", "repeat_details_json"])
        if flag(p["co_worsening_all_scenes_and_three"]):
            role("三指标总体及五场景共同恶化关联候选", ["efficiency_relations_json", "efficiency_cohorts_json"])
        elif flag(p["co_worsening_all_three_overall"]):
            role("总体共同恶化但场景受限的对照", ["efficiency_relations_json"])
        else:
            role("三指标共同恶化叙述的相反或未定义对照", ["efficiency_relations_json"])
        if integer(p["constant_correlation_views"]):
            role("常数向量相关未定义边界", ["constant_correlation_views", "efficiency_relations_json"])
        result.append({
            "configuration_id": c, "method_directory": p["method_directory"], "evaluation_scope": p["evaluation_scope"],
            "prior_step7_selected": chosen, "prior_step7_rule": rule,
            "prior_step7_rule_reference": "reports/07_exploration_spec.json#figure_selection." + rule_key if chosen else
                "reports/07_exploratory_analysis.md#图表选择与图注",
            "prior_step7_selection_type": "extreme_diagnostic_exploratory_rule" if chosen else "not_one_of_five_focus_figures",
            "prior_step11_claim_ids_json": js([r["claim_id"] for r in prior]),
            "prior_step11_roles_json": js([{"claim_id": r["claim_id"], "placement": r["placement"],
                                           "release_status": r["release_status"]} for r in prior]),
            "prior_step11_selection_type": "test_prior_impression_Q9_DPVO_CANCELLATION" if c == "DPVO::mono" else
                "followup_of_extreme_diagnostic_with_detailed_checks" if chosen else
                "supplementary_relation_or_coverage_context" if prior else "not_a_registered_case",
            "prior_step11_reason": (("DPVO不是第7步五个极端选图对象；Q9检验完整F的13正/2负与小总体速度差是否来自抵消；" if c == "DPVO::mono" else "") + "；".join(r["claim_id"] + "：" + r["checks_done"] for r in prior)
                                   if prior else "原第11步未登记为指定案例；没有可据以补写的事前选例理由。"),
            "prior_step11_reason_reference": "reports/11_paper_synthesis.md#实际论证取舍与关键修正；reports/11_claim_registry.csv",
            "historical_selection_boundary": "第7步规则是探索性极端诊断；第11步延续已有检查较细的案例。未记录随机抽样、事前假设或技术路线代表性。",
            "candidate_roles_json": js(roles), "candidate_evidence_json": js(ev),
            "pattern_key_json": js({"table": PAT, "key": {"configuration_id": c}}),
            "selection_recommendation": "候选角色供审阅；不据此自动决定新正文名单，也不预设保留旧主线。" + correction_note,
            "not_in_manuscript_reason": "本轮未进行最终正文取舍；未进入正文不等于未分析。若以后删繁，可根据同现象证据重复、边界差异及篇幅说明，当前不补造历史理由。",
            "complete_results": f"reports/11b_review_index.html#config-{i:02d}；figures/11b_review/c{i:02d}_grid.png；figures/11b_review/c{i:02d}_response.png；{PAT}#configuration_id={c}",
        })
    if len(result) != 24:
        raise ValueError("Selection overview must retain all configurations")
    return result
