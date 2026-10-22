#!/home/yuan/anaconda3/bin/python3
"""Extract frozen step 7–10 evidence and render the bounded step 11 review package.
No old main functions, experiment sources, new statistical models or installations.
"""
import argparse
import csv
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import sys
import tempfile
from importlib import metadata

from version_support import workspace, expected_inputs, current_version
from claim_review_support import apply_reviewed_rows, reviewed_paragraph, reviewed_patch
W = workspace(Path(__file__).resolve().parents[1])
PYTHON = "/home/yuan/anaconda3/bin/python3"
MANIFEST = "paper/11_draft/artifact_manifest.json"
SCRIPT = "scripts/build_paper_materials.py"
PLAN_HASH = "3ff40876228dde3aabcc717ba710b1bdc6620171b4dd734ad81779ebe14885b8"
SCENES = ["building", "houses", "pool", "road", "roundabout"]
S7 = "tables/07_eda/sequence_metrics.csv"
D7 = "tables/07_eda/descriptive_summary.csv"
J8 = "tables/08_conditions/joint_metrics.csv"
S9 = "tables/09_robustness/sensitivity_estimates.csv"
E9 = "tables/09_robustness/efficiency_decomposition.csv"
B9 = "tables/09_robustness/support_blocks.csv"
A9 = "tables/09_robustness/repeat_value_audit.csv"
P10 = "tables/10_relationships/pairwise_patterns.csv"
A10 = "tables/10_relationships/pairwise_availability.csv"
Q10 = "tables/10_relationships/pair_sequence_evidence.csv"
T10 = "tables/10_relationships/within_configuration_tradeoffs.csv"
M6 = "derived_data/06_standardized/source_manifest.csv"
PAIRS = [
("DPVO::mono", "DROID-SLAM::mono"),
("ORB-SLAM2::mono", "ORB-SLAM3::mono"),
("DROID-SLAM::rgbd", "ORB-SLAM3::rgbd"),
("VGGT-LONG::mono", "VGGT-SLAM::mono"),
("MASt3R-SLAM::mono_calib", "MASt3R-SLAM::mono_nocalib"),
("hierslam::rgbd_500", "hierslam::semantic_500")]
PAIR_LABELS = ["DPVO / DROID mono", "ORB2 / ORB3 mono", "DROID / ORB3 RGB-D",
               "VGGT-LONG / VGGT-SLAM", "MASt3R calib / nocalib", "Hier RGB-D / semantic (500)"]
COVERAGE_CONFIGS = ["DPVO::mono","ORB-SLAM2::mono","ORB-SLAM3::mono","ORB-SLAM3::rgbd",
                    "VGGT-SLAM::mono","SplaTAM::rgbd","hierslam::rgbd_500",
                    "hierslam::semantic_500","hierslam::rgbd_whole"]
FIGS = ["01_orb_condition_response","02_dpvo_scene_composition","03_hier_joint_association"]
OUTPUTS = ["reports/11_paper_synthesis.md","reports/11_claim_registry.csv",
           "paper/11_draft/results_discussion.md","paper/11_draft/results_discussion.tex",
           "paper/11_draft/reproducibility.md"] + [
           f"tables/11_paper/{n}.{e}" for n in ["analysis_coverage","six_pair_patterns"] for e in ["csv","tex"]] + [
           f"figures/11_paper/{n}.{e}" for n in FIGS for e in ["png","svg"]]
TABLES = {}
ROW_SOURCES = {}
DISPLAY = []
PARAGRAPHS = []
CHECKS = {}
def js(v):
    return json.dumps(v, ensure_ascii=False, sort_keys=True, separators=(",",":"))
def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()
def safe(rel):
    p = Path(rel)
    if p.is_absolute() or ".." in p.parts:
        raise ValueError(f"Outside workspace: {rel}")
    q = W
    for part in p.parts:
        q /= part
        if q.is_symlink():
            raise ValueError(f"Symlink not allowed: {q}")
    if q.exists() and q.is_file() and q.stat().st_nlink != 1:
        raise ValueError(f"Hardlinked file not allowed: {q}")
    if not q.resolve().is_relative_to(W):
        raise ValueError(f"Escaping workspace: {q}")
    return q
def text_input(p):
    if p not in INPUT_HASHES:
        raise ValueError(f"Not a declared input: {p}")
    return safe(p).read_text(encoding="utf-8")
def table(p):
    if p not in TABLES:
        TABLES[p] = list(csv.DictReader(io.StringIO(text_input(p))))
    return TABLES[p]
def key_for(p,r):
    for field in ["estimate_id","row_id","evidence_id","block_id"]:
        if field in r:
            return {field:r[field]}
    if p in [A10,"tables/10_relationships/comparison_scope.csv"]:
        return {"pair_id":r["pair_id"]}
    if p==M6:
        return {"configuration_id":r["configuration_id"]}
    if p==A9:
        return {k:r[k] for k in ["configuration_id","sequence_raw"]}
    if p==S7:
        return {k:r[k] for k in ["configuration_id","sequence_raw","metric"]}
    if p==D7:
        return {k:r[k] for k in ["configuration_id","subset","group_type","scene","metric","aggregation_level"]}
    if p==J8:
        return {k:r[k] for k in ["configuration_id","subset","group_type","scene","metric","aggregation_level","altitude_m","speed_mps"]}
    field="finding_id" if "finding_id" in r else "question_id"
    return {field:r[field]}
def tag(p,r):
    key = key_for(p,r)
    rid = p+"#"+js(key)
    if rid not in ROW_SOURCES:
        member_fields = [k for k,v in r.items() if v and any(s in k for s in
                         ["members_json","indices_json","sequences_json","descriptors_json","block_details","evidence_ids","variant_ids"])]
        ROW_SOURCES[rid] = {"table":p,"key":key,"source_row_sha256":hashlib.sha256(js(r).encode()).hexdigest(),
                            "member_fields":member_fields,
                            "membership_note":"Resolve listed fields in this exact frozen row; no source directory access."}
        if p==D7:
            ROW_SOURCES[rid]["member_lookup"]={"table":S7,"where":{"configuration_id":r["configuration_id"],
                      "subset":r["subset"],"metric":r["metric"]},"fields":["source_relative_path","source_sha256",
                       "source_record_indices_json","finite_source_record_indices_json","retained_run_ids_json"]}
        if p in [P10,A10]:
            ROW_SOURCES[rid]["member_lookup"]={"table":Q10,"pair_id":r["pair_id"],
                        "fields":["evidence_id","sequence_raw","A_members_json","B_members_json",
                                  "A_finite_members_json","B_finite_members_json"]}
        if p==S9 and r.get("baseline_id"):
            ROW_SOURCES[rid]["baseline_lookup"]={"table":S9,"estimate_id":r["baseline_id"]}
    return dict(r,__ref=rid)
def select(p, **criteria):
    rows=[r for r in table(p) if all(r.get(k)==str(v) for k,v in criteria.items())]
    if len(rows)!=1:
        raise ValueError(f"Expected unique evidence row, got {len(rows)}: {p} {criteria}")
    return tag(p,rows[0])
def chosen(p,pred):
    return [tag(p,r) for r in table(p) if pred(r)]
def accuracy_version_note():
    """Describe the loaded SplaTAM snapshot, not a newer file elsewhere on disk."""
    row = select(M6, configuration_id="SplaTAM::rgbd")
    audited_sha = "337a4d462b9d238681be52284017b3e3ef445130303911de1cc1601a6d9c8f7b"
    unit = row.get("rmse_unit_status", "")
    alignment = row.get("alignment_status", "")
    migrated = (row.get("source_sha256") == audited_sha and
                "Sim(3)" in alignment and "/100" not in unit and
                "unverified" not in unit.lower())
    splatam = ("当前SplaTAM数值已接入经审计的新CSV，为米制外部evo/Sim(3)平移APE RMSE；"
               if migrated else
               "当前图表中的SplaTAM仍是旧冻结快照，尚未接入已审计的新CSV，不能改贴外部evo米制标签；")
    return ("MonoGS已确认米制evo APE RMSE（keyframes only）；" + splatam +
            __import__('version_support').sgs_accuracy_note(select(M6, configuration_id="SGS-SLAM::semantic")) +
            "本次接入不批准跨配置绝对排名；各配置仍分别按其协议与范围解释。")

def current_measurement_note():
    return (accuracy_version_note() +
            "runtime统一为秒（s），reported FPS仍为主要吞吐指标；不从runtime反推FPS，"
            "不与相机采样率直接比较宣称实时性。本组旧阶段memory沿用本版标准化来源值，"
            "不等同独立审计的Table 2 Peak Memory (GiB)：后者区分GPU_RESERVED与CPU_RSS*，不跨类型排名。"
            "实验及SR专题已完成并冻结；本组有限RMSE比例不替代SR@80/90/95，未重新计算或据SR筛除误差记录。"
            "其它尚未闭合的误差协议、计时范围及重复独立性限制保留。")
def ref(r):
    return r["__ref"]
def value(r,field,fmt=".4f",use="draft",index=None):
    raw=r[field]
    if index is not None:
        raw=json.loads(raw)[index]
    if raw=="":
        raise ValueError(f"Undefined displayed value: {ref(r)} {field}")
    if fmt=="text":
        display=str(raw)
    elif fmt=="d":
        if float(raw)!=int(float(raw)):
            raise ValueError("Noninteger count")
        display=str(int(float(raw)))
    elif fmt=="plot_full_precision":
        display=repr(float(raw))
    else:
        if not math.isfinite(float(raw)):
            raise ValueError("Nonfinite display")
        display=format(float(raw),fmt)
    entry={"source_ref":ref(r),"field":field,"json_index":index,"unrounded_value":raw,
           "format":fmt,"display":display,"use":use}
    if entry not in DISPLAY:
        DISPLAY.append(entry)
    return display
def nullable_rho(r,fmt=".3f",use="draft"):
    """Display an explicitly undefined correlation without inventing a zero."""
    if r["rho"] != "":
        if r["status"] != "computed":
            raise ValueError(f"Unexpected defined rho/status: {ref(r)}")
        return value(r,"rho",fmt,use)
    if r["status"] not in {"insufficient_sequences","constant_input","incompatible_scope"}:
        raise ValueError(f"Unexplained undefined rho: {ref(r)} {r['status']}")
    entry={"source_ref":ref(r),"field":"rho","json_index":None,"unrounded_value":"",
           "format":"undefined","display":"未定义","use":use,
           "status_field":"status","source_status":r["status"],"n_sequences":r["n_sequences"]}
    if entry not in DISPLAY:
        DISPLAY.append(entry)
    return "未定义"

def number(r,f,use):
    return float(value(r,f,"plot_full_precision",use))
def close(a,b):
    assert math.isclose(float(a),float(b),rel_tol=1e-12,abs_tol=1e-10),(a,b)
def sen(eid):
    return select(S9,estimate_id=eid)
def joint(c,scene,h,v):
    return select(J8,configuration_id=c,subset="condition_labelled",scene=scene,
                  group_type="scene_condition",metric="rmse",aggregation_level="equal_weight_sequence_means",
                  altitude_m=h,speed_mps=v)
def desc(c):
    return select(D7,configuration_id=c,subset="condition_labelled",group_type="configuration",
                  scene="__all__",metric="rmse",aggregation_level="equal_weight_sequence_means")
def seq(c,s):
    return select(S7,configuration_id=c,sequence_raw=s,metric="rmse")
def pair(i,view="F_mean",scene="__all_scenes__"):
    pid=" <> ".join(PAIRS[i])
    return select(P10,row_id=f"{pid}|{view}|{scene}")
def within(c,metric,scene="__all_scenes__"):
    return select(T10,row_id=f"{c}|{metric}|correlation|{scene}")
def orb(scene,h,kind="range"):
    route={"road":"road2","building":"cross_building"}[scene]
    suffix={"range":"focus_contrast_range|checked","mean":"focus_contrast_baseline|mean",
            "median":"focus_contrast_median|within_sequence_median"}[kind]
    return sen(f"ORB-SLAM2::mono|{scene}|{route}|speed8_minus2|H{h}|{suffix}")
def output_text(path,s):
    if path not in OUTPUTS:
        raise ValueError(f"Output not allowed: {path}")
    p=outpath(path);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(s,encoding="utf-8")
def csv_string(rows):
    buf=io.StringIO(newline="")
    keys=list(dict.fromkeys(k for r in rows for k in r))
    writer=csv.DictWriter(buf,keys,lineterminator="\n");writer.writeheader();writer.writerows(rows)
    return buf.getvalue()
def tex_escape(s):
    return "".join({"\\":r"\textbackslash{}","&":r"\&","%":r"\%","$":r"\$","#":r"\#",
                    "_":r"\_","{":r"\{","}":r"\}","~":r"\textasciitilde{}","^":r"\textasciicircum{}",
                    "ρ":r"\ensuremath{\rho}","−":r"\ensuremath{-}","×":r"\ensuremath{\times}",
                    "→":r"\ensuremath{\rightarrow}","≥":r"\ensuremath{\geq}","∈":r"\ensuremath{\in}"} .get(c,c) for c in s)
def preflight(overwrite):
    paths=OUTPUTS+[MANIFEST]
    for p in paths:safe(p)
    existing=[p for p in paths if safe(p).exists()]
    if not existing:return None
    if not safe(MANIFEST).exists():
        if existing==["reports/11_paper_synthesis.md"] and sha(safe(existing[0]))==PLAN_HASH:
            return None  # exact agent-created, pre-render plan only
        raise ValueError("Existing outputs without a generation manifest; preserve and review: "+", ".join(existing))
    if not overwrite:
        raise ValueError("Default refuses overwrite; use --overwrite only after review.")
    old=json.loads(safe(MANIFEST).read_text())
    recorded=old.get("outputs",{})
    if set(recorded)!=set(OUTPUTS):
        raise ValueError("Prior output allowlist differs; do not overwrite.")
    conflicts=[p for p in OUTPUTS if not safe(p).is_file() or sha(safe(p))!=recorded[p]["sha256"]]
    if conflicts:
        raise ValueError("Manual edits/missing outputs detected; preserve files: "+", ".join(conflicts))
    return old
def check_inputs():
    problems=[]
    result={}
    saved={}
    for spec in ["reports/07_exploration_spec.json","reports/08_condition_analysis_spec.json",
                 "reports/09_robustness_spec.json","reports/10_relationship_spec.json"]:
        for record in json.loads(text_input(spec)).get("inputs",{}).values():
            saved.setdefault(record["path"],[]).append({"spec":spec,"sha256":record["sha256"]})
    for p,expected in expected_inputs("11",INPUT_HASHES,W).items():
        actual=sha(safe(p))
        if actual!=expected:problems.append(p+" differs from active frozen step11 input version")
        old=saved.get(p,[])
        for s in old:
            if actual!=s["sha256"]:problems.append(p+" differs from "+s["spec"])
        result[p]={"sha256":actual,"prior_snapshots_checked":old,
                   "status":"matches_saved_snapshots" if old else "actual_step11_snapshot_no_prior_hash_claim",
                   "role":"hash_only" if p.endswith("run_records.csv") else "evidence_or_protocol"}
    if problems:
        raise ValueError("Changed evidence; no output written. Affected source paths:\n"+"\n".join(problems)+
                         "\nUse prior artifact_manifest row_sources/displays and claim registry to locate affected claims. Do not auto-refresh.")
    for k in ["records","manifest","schema"]:
        entry=json.loads(text_input("reports/10_relationship_spec.json"))["inputs"][k]
        assert result[entry["path"]]["sha256"]==entry["sha256"]
    return result

INPUT_HASHES = {
  "derived_data/06_standardized/run_records.csv": "f73b70914b7f60bfcad03f92e799631da679d43aaa893316c6b3514d27a054db",
  "derived_data/06_standardized/source_manifest.csv": "34d7cea320aa53e2b5dc6124bdc1971d0ed8d6ce7917fbccf25423dd6aa2ba5e",
  "derived_data/06_standardized/schema.json": "6ebb38d127ec556c6da5a93fd8f4ef93faf0a70c3960662e8379959cf63dbe90",
  "reports/05_dpvo_pilot.md": "dd225ff6320c36828753ede9fccda43bdf95b024aa5d9fbc16179630aae686bc",
  "reports/07_exploration_spec.json": "0f6790a086e494d479dccaaa299728b6a80760e8c5df299072ea726c65b47502",
  "reports/07_exploratory_analysis.md": "cb3bd88e736bd344e90fcb54f8f79406bcf99267ec25f230e514e06b3a6cdf47",
  "reports/07_research_questions.csv": "49eb5de9c5633f1b846da76b49f7a1d82e65e6296e63346beacc557e8900c5e0",
  "reports/08_condition_analysis_spec.json": "d7146979a097f61a39c317bf3f568b40f5b348edcb7f6b697c1e83ad3361d98a",
  "reports/08_altitude_speed_analysis.md": "d630f886049a8a8e3d85db8234d602c5ce209e559c08abc0605fa7308432380d",
  "reports/08_question_assessment.csv": "0fdf1a5d98a25f277a2bbae6583cfadf660452568ef385fc65bed47173d16b58",
  "reports/09_robustness_spec.json": "a08680a5f4e17c2a0660ab52b972dfae886762b9d81afdd35e9a98b1b02909f5",
  "reports/09_robustness_analysis.md": "cd9dacaa2c0abff96f9569398b73ea8b53ea7a3e2eaa40d53a2d8a05ee338970",
  "reports/09_claim_assessment.csv": "5b0c94db7f3b1c5866ec67380d948bfebd9e876a55360e5fbf7f0badfd54342d",
  "reports/10_relationship_spec.json": "ee3f990151675ee661d99463cd3058efd4ca34b8e68aa2c9b0cd15c0f4a12c86",
  "reports/10_method_relationships.md": "8affd76f5c1be36d78a4b19bc8436b4a993afc23b1d5a8e986f43492023609a8",
  "reports/10_findings_assessment.csv": "e9a40aba14c118310589765e6ec62f94bafda02ef470bce15dcfa27118f645d8",
  "tables/07_eda/descriptive_summary.csv": "24588a099afb73b4863c7ea9f06dfbc6b93c63495a9f05347c25b2f4b7922b7e",
  "tables/07_eda/sequence_metrics.csv": "0459ebab01c89e59bcc208e7e5ff8963dad7bd6710061cf4e1e17beecf45bf91",
  "tables/08_conditions/joint_metrics.csv": "6b34a00ac0e655b0c4c7acd5416a31a26842b9397798e8763f2506070bfbec74",
  "tables/09_robustness/sensitivity_estimates.csv": "8bfd9440c0582f9cea82b34b79a8dee2bf199d33bd9d45a6c018c1fb0fb944a2",
  "tables/09_robustness/efficiency_decomposition.csv": "7a480dc6044efeeaac7123c971696fb087746d1083d91dc21eae461dcf905e47",
  "tables/09_robustness/support_blocks.csv": "0afe0a5fb10ddc4ddcd5ed922eb2e4239da952af7af4d278e9fbf6b64b60d5a3",
  "tables/09_robustness/repeat_value_audit.csv": "32f6b715826ebd11c2da4c019dd4b2f6f4b5359144d5319ab97fcc4baf95dd04",
  "tables/10_relationships/comparison_scope.csv": "ba0d4e5b5b1b5b4261f5d6fb36b80e4771e02782eb660ee887379b8c5f9ce04b",
  "tables/10_relationships/pair_sequence_evidence.csv": "e6831a6c9e309b9872996bd43b152260e668f7161b34666a42d2ff6be751d2b7",
  "tables/10_relationships/pairwise_patterns.csv": "4cd21359ab1211e0829f39f18c68b7c4cd291f2114c5d56e2382d38a4a1412d8",
  "tables/10_relationships/pairwise_availability.csv": "a1b19fc7f6f910b8980a39d24933ecf8428e02110cdc68266c5386e9f6e35156",
  "tables/10_relationships/within_configuration_tradeoffs.csv": "ebe2d124345a2ed5a3378abf108215295ce919e8ff9d0a55988c90d9e9cd5c9a"
}
INITIAL_PLAN = "# 第 11 步论文材料整理\n\n## 先行图表方案\n\n本方案在制作新图和排版表之前确定。主线为名义高度、速度和场景异质性；3张正文候选图、1张正文候选表、1张补充表。正文候选只表示论证位置，绝不等同可投稿。\n\n| 内部标签 | 支持主张 | 已有数值/图来源 | 位置、理由 | 必须保留的数量与限制 | 与其它材料的区别 |\n|---|---|---|---|---|---|\n| fig:s11-orb-response | C11_A：ORB-SLAM2局部速度响应反转及H20反例 | 08 joint_metrics；09 sensitivity_estimates；08图02、09图02 | 正文；同时呈现曲线与已查范围 | road/building全部H10/20/30、V2/4/8；每格序列/有限运行数；范围非CI；Building H20跨零 | 一图连接条件均值与重复敏感性，不另制重复差值表 |\n| fig:s11-dpvo-composition | C11_B：总体速度差中的场景抵消 | 09 sensitivity_estimates/support_blocks；09图01 | 正文；完整集合与所有单场景剔除并列 | F=15名义条件块、五场景；完整集合是基线；每种视图块数 | 展示场景组成，不重复ORB局部重复删一 |\n| fig:s11-hier-association | C11_D：完整轨迹配置内误差与资源共同变化 | 10 within_configuration_tradeoffs；10图05；09 efficiency_decomposition | 正文；三个指标的同运行交集序列均值 | 各指标当前有限/观测序列数由关系表生成，显示场景；单位和测量范围未闭合；图注保留A/B差异 | 配置内关联，不是跨方法效率排名或机制 |\n| tab:s11-coverage | C11_COV与分析范围 | 07 descriptive_summary/sequence_metrics；06 source_manifest；10 pairwise_availability | 正文；明确运行、序列与重复层级 | 主子集；至少一次有限序列/观测序列、有限运行/保留运行；Hier两种500帧单独列；按当前用户确认区分500帧与完整轨迹 | 不给综合得分、不比较“成功率” |\n| tab:s11-pair-patterns | C11_P1～P6 | 10 pairwise_patterns/pair_sequence_evidence/comparison_scope | 补充；六对总体与场景rho紧凑并列 | 每格rho与序列n；F/C/中位数；Hier500按当前实际有限重复生成；VGGT双方有限；四配置来源限制 | 不重复绘制六对秩散点或配置大热图 |\n\n全部新图暂定插入宽度180 mm，实际模板未知；按此宽度审查字体、完整值域和反例。PNG逐张实际打开后才能记录视觉通过。CSV保留未舍入值、精确行键和成员引用，TeX只呈现读者所需字段。\n\n## 论证与发布边界\n\n四条主线：C11_A局部反转；C11_B场景抵消；C11_COV/C11_REPEAT共同支持“有限覆盖与重复结果联合阅读”；C11_D配置内关联。Q2的DROID Pool重复特征及六对方法关系作为补充。双向可用性配置对必须引用完整可用性表；恒定内存仅作解释边界。因果机制、融合增益、可靠性赢家、语义无效和已证明独立重复等排除。\n\n下一项工作是在同一报告补全实际证据、定向核验表与验收结果；本材料入口不启动底层来源调查；授权版本更新另由调度入口重建依赖。\n"

def repetition_summary(configs):
    parts=[]
    for c in configs:
        m=select(M6,configuration_id=c)
        parts.append(c+" 每序列保留数分布="+value(m,"records_per_sequence_json","text","current repetition fact"))
    return "；".join(parts)

def hier_relation_facts():
    rows=chosen(T10,lambda r:r["configuration_id"]=="hierslam::rgbd_whole" and r["row_type"]=="rank_correlation")
    expected={"fps":-1,"runtime":1,"memory":1}
    def agrees(r):
        return r["status"]=="computed" and bool(r["rho"]) and float(r["rho"])*expected[r["efficiency_metric"]]>1e-12
    opposite=[r["efficiency_metric"]+"/"+r["scene"] for r in rows if not agrees(r)]
    return not opposite,opposite

def assess_claim_updates(claims):
    if not current_version(W):return claims
    prior_path=safe("reports/11_claim_registry.csv")
    prior={r["claim_id"]:r for r in csv.DictReader(io.StringIO(prior_path.read_text()))} if prior_path.is_file() else {}
    for r in claims:
        old=prior.get(r["claim_id"],{})
        old_numbers={x["source_ref"]:x["values"] for x in json.loads(old.get("key_numbers_and_denominators_json","[]"))}
        new_numbers={x["source_ref"]:x["values"] for x in json.loads(r["key_numbers_and_denominators_json"])}
        changed=[k for k in sorted(set(old_numbers)|set(new_numbers)) if old_numbers.get(k)!=new_numbers.get(k)]
        statement_changed=bool(old and old["statement"]!=r["statement"])
        invalid=r["claim_id"]=="C11_D" and not hier_relation_facts()[0]
        pending=old.get("update_assessment_status")=="needs_reassessment"
        r["previous_statement"]=old.get("previous_statement") or old.get("statement","")
        r["previous_release_status"]=old.get("previous_release_status") or old.get("release_status","")
        r["changed_numeric_evidence_refs_json"]=js(sorted(set(changed)|set(json.loads(old.get("changed_numeric_evidence_refs_json") or "[]"))))
        r["update_assessment_status"]="needs_reassessment" if invalid or changed or statement_changed or pending else "retained_with_current_scope_metadata"
        r["claim_changed"]=bool(invalid or changed or statement_changed or pending)
        r["update_assessment_basis"]="Original case anchors retained. Numeric/source-set changes and current wording are compared with the protected previous generated registry; no replacement case selected. Pending reassessment is not cleared by a repeated build."
        if invalid or changed or statement_changed or pending:r["release_status"]="needs_reassessment"
    return apply_reviewed_rows(W, "claims", claims)

def build_claims():
    claims=[]
    def add(cid,prior,statement,placement,release,configs,scope,unit,representative,weights,sets,rows,
            figures,done,notdone,limits,stronger,core=""):
        numeric=[]
        fields=["value","baseline_value","range_min","range_max","n_direction_changes","n_R","n_F","n_C",
                "rho","n_sequences","n_scenes","n_observed_sequences","n_retained_records","n_finite_records",
                "n_sequences_with_finite","mean","median","original_n_retained","original_n_finite",
                "n_A","n_B","n_E","mean_A","mean_B","overall_B_minus_A","A_n_finite_P","B_n_finite_P",
                "A_n_retained_P","B_n_retained_P","A_any_finite_sequences_P","B_any_finite_sequences_P",
                "n_P","both_finite_n","only_A_finite_n","only_B_finite_n"]
        for r in rows:
            numeric.append({"source_ref":ref(r),"values":{k:r[k] for k in fields if r.get(k)!="" and k in r}})
        claims.append(dict(claim_id=cid,core_observation_group=core,previous_evidence_ids_json=js(prior),
                  statement=statement,placement=placement,release_status=release,configurations_json=js(configs),
                  scenes_conditions_subset=scope,statistical_unit=unit,representative=representative,
                  weights=weights,finite_sets=sets,key_numbers_and_denominators_json=js(numeric),
                  source_units=current_measurement_note(),
                  evidence_rows_json=js([ROW_SOURCES[ref(r)] for r in rows]),
                  corresponding_materials=figures,checks_done=done,checks_not_done=notdone,
                  known_limits=limits,unsupported_stronger_claims=stronger))
    unitlim="误差协议按配置分别核实，独立性限制保留；仅当前保留记录。名义评测范围和有限RMSE不替代已冻结的输出覆盖SR。"
    A=[orb(s,h,k) for s in ["road","building"] for h in [10,20,30] for k in ["range","mean","median"]]
    A += [joint("ORB-SLAM2::mono",s,h,v) for s in ["road","building"] for h in [10,20,30] for v in [2,4,8]]
    for s,route in [("road","road2"),("building","cross_building")]:
        A.append(sen(f"ORB-SLAM2::mono|{s}|{route}|rmse_four_corner|focus_contrast_range|checked"))
    for s in ["road2_high_high","road2_medium_high","cross_building_high_high"]:
        A += [seq("ORB-SLAM2::mono",s),sen(f"ORB-SLAM2::mono|{s}|sequence_variant_range|drop_one")]
    add("C11_A",["F1","Q1"],
        "ORB-SLAM2 mono在road/building的H10与H30速度端点响应方向相反，所查变体保持这四个方向；building H20存在方向改变。",
        "main_text_candidate","requires_targeted_verification",["ORB-SLAM2::mono"],
        "condition_labelled；road/building；H10/20/30，V2/4/8","名义端点块与配置×sequence",
        "各sequence有限RMSE算术均值；median/删一仅敏感性","同一局部问题固定端点","每端至少1有限；本图每格3/3",A,
        "fig:s11-orb-response","固定端点中位数、逐个有限记录删一；包括H20及四角量",
        "因果/显著交互检验、外部场景验证、历史对齐追溯",unitlim+"范围不是CI；路线名分层不证明物理路径一致。",
        "所有高度/所有方法方向稳定；因果DID；高空普遍变差","O1")
    B=chosen(S9,lambda r:r["configuration_id"]=="DPVO::mono" and r["comparison"]=="speed8_minus2" and
             r["analysis_type"] in ["support_view","scene_contribution","leave_one_scene_out"])
    B+=chosen(B9,lambda r:r["configuration_id"]=="DPVO::mono" and r["comparison"]=="speed8_minus2")
    add("C11_B",["Q9_DPVO_CANCELLATION"],"DPVO完整F上的小总体速度差包含正负场景贡献抵消；删Pool是敏感性视图，不替代基线。",
        "main_text_candidate","requires_targeted_verification",["DPVO::mono"],
        "condition_labelled；全部五场景；V8−V2，固定路线标签和H","名义条件块",
        "端点内有限RMSE均值的差","原F块等权；V2按场景等权为已检查敏感性","R/F/C",B,
        "fig:s11-dpvo-composition","完整F、场景等权、C、中位数、每次剔除一个场景",
        "新场景泛化、效应显著性、机制调查",unitlim+"共享场景的块不当作独立随机样本。",
        "DPVO对速度普遍不敏感；删Pool后结果是正式主结果；符号计数证明显著性","O2")
    C=[desc(c) for c in COVERAGE_CONFIGS]
    C+=[select(A10,pair_id=" <> ".join(PAIRS[1]))]
    C+= [joint("VGGT-SLAM::mono",s,h,v) for s in ["pool","roundabout"] for h in [10,20,30] for v in [2,4,8]]
    C += [sen(f"VGGT-SLAM::mono|{cmp}|support_view|{v}") for cmp in ["speed8_minus2","altitude30_minus10"] for v in ["V0","V1","V2","V3","V4"]]
    add("C11_COV",["F4","Q4","R10_P2"],"有限运行覆盖、至少一次有限的序列覆盖与完整轨迹成功是不同量；VGGT可算均值不代表全无效条件，ORB2/ORB3两个层级给出不同印象。",
        "main_text_candidate","draft_supported_with_limits",COVERAGE_CONFIGS,
        "condition_labelled；覆盖表全部五场景；VGGT pool/roundabout细节","保留运行记录、实际观测sequence，分别作分母",
        "数量与比例；有有限值的sequence均值单列","不把无记录格或计划补跑加入分母",
        "有限RMSE/实际保留，sequence至少1有限/实际观测",C,
        "tab:s11-coverage；旧08图06、09图04（补充登记，未重绘）",
        "逐序列有限性、R/F/C与V0～V4、运行和序列层计数交叉核对",
        "轨迹完成判据与历史未保留尝试；来源完整性调查",
        "支持当前CSV数值可用性描述；不表示全部尝试或轨迹成功。重复结构不均匀。",
        "有限率即完整轨迹SR；配置可靠性赢家；空白格=0；VGGT有限均值说明整体改善","O3")
    cases=["cross_building_low_low","road2_high_high","road2_medium_low","road2_medium_medium"]
    R=[seq("ORB-SLAM3::rgbd",s) for s in cases]+[sen(f"ORB-SLAM3::rgbd|{s}|sequence_variant_range|drop_one") for s in cases]
    add("C11_REPEAT",["F3","Q3"],"ORB-SLAM3 RGB-D部分高均值对单条记录敏感，同时road H20V4三次均较高；两类情况应同时保留。",
        "main_text_candidate","requires_targeted_verification",["ORB-SLAM3::rgbd"],
        "condition_labelled；四条已选sequence，包括三高背景","同配置×sequence的有限运行",
        "有限均值、中位数、逐条有限记录删一均值","每次只删除一条；不删改原记录","保留数和有限数同时展示",R,
        "正文P09；旧09图03（补充登记，未重绘）","逐序列删一、固定条件问题；保留三高背景",
        "记录错误/失败机制、独立性和追加实验",unitlim+"少量重复不能估计总体不确定性；n=1重复SD未定义。",
        "所有高均值由一个异常点造成；单条影响大即错误；两个有限值mean=median即稳定","O3")
    D=chosen(E9,lambda r:True)
    D+=chosen(T10,lambda r:r["configuration_id"]=="hierslam::rgbd_whole" and r["row_type"]=="rank_correlation")
    add("C11_D",["F5","Q5","R10_T_hierslam::rgbd_whole"],
        ("Hier-SLAM完整轨迹配置内较大RMSE伴随较低FPS、较长runtime与较高memory；当前总体及五景方向一致，效率A/B筛选另有影响。" if hier_relation_facts()[0] else "Hier-SLAM完整轨迹当前总体或分场景结果不再全部支持较大RMSE伴随较低FPS、较长runtime与较高memory；旧统一方向主张需重新审阅。"),
        "main_text_candidate","requires_targeted_verification",["hierslam::rgbd_whole"],
        "condition_labelled；完整轨迹配置，五场景","同运行交集的sequence均值；A/B另以运行记录为单位",
        "每sequence的RMSE和效率均在同一共同有限运行上取均值；Spearman",
        "相关中sequence等权；A/B为pooled运行算术均值","共同有限运行；A效率有限，B=A且RMSE有限，E=A−B",D,
        "fig:s11-hier-association","总体/场景rho、同运行交集、A/B/E代数分解与实际受影响条件单元",
        "资源计量来源、底层机制、因果取舍与正式推断",
        unitlim+"用户确认完整轨迹配置不等于每条运行完整成功；A/B没有唯一正确集合。",
        "多计算换精度；Gaussian/关键帧/初始化/运动模糊机制；所有条件筛选差值同向","O4")
    Q2=chosen(A9,lambda r:r["configuration_id"]=="DROID-SLAM::rgbd" and r["scene"]=="pool" and r["subset"]=="condition_labelled")
    Q2+=chosen(S9,lambda r:r["configuration_id"]=="DROID-SLAM::rgbd" and r["analysis_type"]=="focus_contrast_range")
    add("C11_DROID_POOL",["F2","Q2"],"DROID RGB-D Pool的条件差是现有数值特征；重复误差相同导致删一不变，不能证明独立稳定。",
        "supplementary","requires_targeted_verification",["DROID-SLAM::rgbd"],"Pool九条双标签sequence",
        "sequence和其保留运行","有限均值及现有条件差","原条件定义","当前有限集合",Q2,
        "旧08图03；09重复审计，未重绘","原文/数值重复一致性；固定端点变体","生成来源和独立性",
        unitlim+"误差字段相同但效率未全部相同。","固定种子/复制/确定性已证实；来源已闭合")
    for i,(a,b) in enumerate(PAIRS):
        old=select("reports/10_findings_assessment.csv",finding_id=f"R10_P{i+1}")
        rows=[select(P10,row_id=e) for e in json.loads(old["evidence_ids_json"])]
        rows+=[select(A10,pair_id=" <> ".join((a,b)))]
        release="draft_supported_with_limits" if i==5 else "requires_targeted_verification"
        add(f"C11_P{i+1}",[f"R10_P{i+1}"],old["relationship_interpretation"],"supplementary",release,[a,b],
            "condition_labelled；总体及全部五场景；Hier仅500帧，不与其它范围混合",
            "双方同名sequence（不是run配对）","有限RMSE均值的Spearman；median为敏感性",
            "每sequence等权，场景内重排；不平均场景rho","U/P/F/C定义见草稿",rows,
            "tab:s11-pair-patterns；旧10图01/02登记未重绘","C限制、F中位数、固定F逐场景剔除、并列秩",
            "实际输入/历史评测同口径、因果收益、独立重复、外部泛化",
            old["limitations"]+" "+old["special_repeat_flags_json"],
            "高rho=误差相等/语义无收益/相关百分比；共同机制或已验证融合")
    mutual=chosen(A10,lambda r:int(r["only_A_finite_n"])>0 and int(r["only_B_finite_n"])>0)
    mutual_count=len(mutual)
    add("C11_AVAIL",["R10_AVAILABILITY_COMPLEMENTARITY"],
        f"全部允许/限定配置对中有{mutual_count}对双向数值可用性线索；不是实现过的切换或融合收益。",
        "supplementary","draft_supported_with_limits",sorted(set(r[k] for r in mutual for k in ["configuration_A","configuration_B"])),
        "condition_labelled；各对自己的共同有记录P","配置对与P内sequence","四类可用性计数",
        "每对独立P，缺席U不进P分母","P；仅A有限且仅B有限两类均非空",mutual,
        f"tables/10_relationships/pairwise_availability.csv；{mutual_count}个精确pair_id；不以六对图代替",
        "四类与3×3计数、U/P/F/C成员","实际融合/切换系统验证、端到端运行和轨迹完成",
        "计数是符合两类非空条件的配置对数，不是独立系统/实验数。",
        "已经实现的互补收益；零成本融合；公平可靠性排名")
    for c in ["DPVO::mono","ORB-SLAM3::rgbd"]:
        rows=chosen(T10,lambda r:r["configuration_id"]==c and r["row_type"]=="rank_correlation")
        add("C11_T_"+c.split("::")[0],[f"R10_T_{c}"],"该配置总体精度—效率rho不代表各场景统一取舍；保留为补充背景。",
            "supplementary","requires_targeted_verification",[c],"condition_labelled；总体及分场景",
            "同运行交集的sequence均值","Spearman","sequence等权","RMSE和该效率共同有限",rows,
            "旧10图04/05，未重绘","分场景和共同有限交集","机制/测量协议与因果分析",unitlim,
            "可移植到其它方法的普遍精度—效率规律")
    constants=chosen(T10,lambda r:r["row_type"]=="rank_correlation" and r["status"]=="constant_input")
    add("C11_CONSTANT",["R10_CONSTANT_MEMORY"],"恒定内存视图的相关未定义，不能填零或解读为无关系。",
        "internal_only","draft_supported_with_limits",sorted(set(r["configuration_id"] for r in constants)),
        "TartanVO整体及五场景；VGGT-LONG部分场景","sequence均值","Spearman未定义","不适用",
        "共同有限运行",constants,"原10配置内关系表，未重绘","输入常数检查","内存采集来源",
        "常数记录特征不等于真实资源需求恒定。","rho=0；已证实固定内存机制")
    special=["DROID-SLAM::rgbd","ElasticFusion::rgbd","SLAM3R::mono","VGGT-LONG::mono"]
    repeats=chosen(A9,lambda r:r["configuration_id"] in special)
    assert all(r["all_provided_error_fields_identical"]=="True" for r in repeats)
    assert len(repeats)==192
    add("C11_PROVENANCE",["Q2","R10_P3","R10_P4","R10_CONSTANT_MEMORY"],
        "四配置各48条sequence内的已提供误差重复相同；原因和独立性未确认，不能当作确定错误或独立稳定证据。",
        "internal_only","requires_targeted_verification",special,"all_retained，标注主子集/无标签",
        "配置×sequence的保留重复","原文与现有有限数值相等","不去重、不增添噪声","已提供且可比误差字段",repeats,
        "定向核验表A；旧09重复审计","字段原文/数值一致性","导出版本/尝试标识/日志与重用链",
        "未访问底层来源；相同误差不等于全部效率相同。","数据复制/固定种子/确定性已证实；独立重复稳定")
    add("C11_EXCLUDED",["Q1","Q3","Q4","Q5","R10_P6","R10_AVAILABILITY_COMPLEMENTARITY"],
        "因果机制、方法赢家、语义无效、已实现融合，以及由有限RMSE直接推出完整成功或在线连续稳定等更强结论排除；独立冻结的输出覆盖SR不属于本项否定范围。",
        "excluded","unsupported",[],"不适用","不适用","不适用","不适用","不适用",[],
        "无","只核对现有描述边界","这些主张所需新证据不在本轮授权范围",
        "没有正面支持证据；不能由免责声明补足。","同statement")
    return assess_claim_updates(claims)

def tables_materials():
    rows=[];texrows=[]
    for c in COVERAGE_CONFIGS:
        r=desc(c);m=select(M6,configuration_id=c)
        seqs=chosen(S7,lambda x:x["configuration_id"]==c and x["subset"]=="condition_labelled" and x["metric"]=="rmse")
        assert sum(int(x["n_retained_runs"]) for x in seqs)==int(r["n_retained_records"])
        assert sum(int(x["n_finite_runs"]) for x in seqs)==int(r["n_finite_records"])
        assert sum(int(x["n_finite_runs"])>0 for x in seqs)==int(r["n_sequences_with_finite"])
        repeats=json.loads(m["records_per_sequence_json"])
        assert len(repeats)==1
        repeated=next(iter(repeats))
        assert all(int(x["n_retained_runs"])==int(repeated) for x in seqs)
        repeatdisplay=value(m,"records_per_sequence_json","text","tab:s11-coverage")
        DISPLAY.append({"source_ref":ref(m),"field":"records_per_sequence_json",
                        "json_operation":"sole object key (verified uniform by selected primary sequence rows)",
                        "unrounded_value":repeated,"display":repeated,"format":"d","use":"tab:s11-coverage retained/sequence"})
        ns=value(r,"n_sequences_with_finite","d","tab:s11-coverage")+"/"+value(r,"n_observed_sequences","d","tab:s11-coverage")
        nr=value(r,"n_finite_records","d","tab:s11-coverage")+"/"+value(r,"n_retained_records","d","tab:s11-coverage")
        name=c.replace("::"," / ")
        scope={"unknown":"未核实","500_frames":"500帧","whole_trajectory":"完整轨迹"}.get(r["evaluation_scope"],r["evaluation_scope"])
        texrows.append([name,scope,ns,nr,repeated])
        rows.append({"configuration_id":c,"evaluation_scope":r["evaluation_scope"],
            **{k:r[k] for k in ["n_sequences_with_finite","n_observed_sequences","n_finite_records","n_retained_records","finite_fraction"]},
            "retained_per_sequence":repeated,"display_sequences":ns,"display_records":nr,
            "source_table":D7,"source_row_key":js(ROW_SOURCES[ref(r)]["key"]),
            "manifest_source_key":js(ROW_SOURCES[ref(m)]["key"]),"raw_repetition_distribution":repeatdisplay,
            "member_refs_json":js([ref(s) for s in seqs]),"formats_json":js({"counts":"d","fraction":"not displayed"}),
            "subset":"condition_labelled","claim_ids_json":js(["C11_COV"])})
    output_text("tables/11_paper/analysis_coverage.csv",csv_string(rows))
    caption="主条件子集的数值覆盖和保留重复结构。分子/分母分别为至少一次有限RMSE的sequence/观测sequence，以及有限RMSE运行/保留运行。末列是当前每条sequence保留的运行数，不是历史尝试数或成功数；两种500帧配置单列；其余逐次来源按本次用户确认登记完整轨迹配置，不代表逐运行完成。"
    tex=tex_table("tab:s11-coverage",caption,["配置","评测范围","序列有限/观测","运行有限/保留","保留/序列"],texrows,"l l r r r")
    output_text("tables/11_paper/analysis_coverage.tex",tex)
    compact=[];longrows=[]
    for i in range(6):
        fields=[];cells=[]
        for view,scene in [("F_mean","__all_scenes__"),("C_mean","__all_scenes__"),("F_median","__all_scenes__")]+[("scene_F_mean",s) for s in SCENES]:
            r=pair(i,view,scene)
            rho=nullable_rho(r,".3f","tab:s11-pair-patterns")
            n=value(r,"n_sequences","d","tab:s11-pair-patterns")
            cells.append(f"{rho} ({n})")
            longrows.append({"pair_id":r["pair_id"],"view":view,"scene":scene,"rho":r["rho"],
                "n_sequences":r["n_sequences"],"status":r["status"],"display_rho_n":cells[-1],"rho_format":".3f" if r["rho"] else "undefined","n_format":"d",
                "source_table":P10,"source_row_id":r["row_id"],"source_ref":ref(r),
                "member_evidence_ids_json":r["member_evidence_ids_json"],"scope_status":r["scope_status"],
                "special_repeat_flags_json":r["special_repeat_flags_json"],"claim_id":f"C11_P{i+1}"})
        compact.append([PAIR_LABELS[i]]+cells)
    output_text("tables/11_paper/six_pair_patterns.csv",csv_string(longrows))
    # Two vertically stacked panels retain legibility at a provisional 180 mm width.
    cap="六对配置的排序关系，单元格为Spearman rho（参与sequence数）。F：双方至少一次有限RMSE；C：双方全部保留RMSE有限。均值/中位数均在sequence内计算；每个场景另行重排，场景rho不作平均。未定义值保留状态与参与数，空集合或常数向量不填0。500帧与完整轨迹配置分开；当前保留数与有限数见来源表，排序相似不证明语义无收益或独立重复稳定。VGGT关系只覆盖双方有限序列，DROID RGB-D与VGGT-LONG重复来源未闭合。"
    tex=tex_table("tab:s11-pair-patterns",cap,["配置对","F均值","C均值","F中位数"],[r[:4] for r in compact],"l r r r",extra_headers=["配置对","Building","Houses","Pool","Road","Roundabout"],extra_rows=[[r[0]]+r[4:] for r in compact])
    output_text("tables/11_paper/six_pair_patterns.tex",tex)
    return caption,cap

def tex_table(label,caption,headers,rows,alignment,extra_headers=None,extra_rows=None):
    out=["% Generated step11; provisional 180 mm layout, not a journal template.",
         r"\begin{table}[htbp]",r"\centering",r"\small",r"\caption{"+tex_escape(caption)+"}",
         r"\label{"+label+"}",r"\setlength{\tabcolsep}{4pt}",r"\begin{tabular}{"+alignment+"}",r"\hline",
         " & ".join(tex_escape(x) for x in headers)+r" \\",r"\hline"]
    out+=[" & ".join(tex_escape(str(x)) for x in r)+r" \\" for r in rows]
    out += [r"\hline",r"\end{tabular}"]
    if extra_headers:
        out += [r"\par\medskip",r"\begin{tabular}{l r r r r r}",r"\hline",
                " & ".join(tex_escape(x) for x in extra_headers)+r" \\",r"\hline"]
        out+=[" & ".join(tex_escape(str(x)) for x in r)+r" \\" for r in extra_rows]
        out += [r"\hline",r"\end{tabular}"]
    out += [r"\end{table}",""]
    return "\n".join(out)

def figures_materials():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    plt.rcParams.update({"font.family":"DejaVu Sans","font.size":9,"axes.titlesize":10,
                         "axes.labelsize":9,"xtick.labelsize":8,"ytick.labelsize":8,
                         "svg.hashsalt":"benchmark-step11","figure.dpi":180,"savefig.dpi":180})
    metadata_png={"Software":"benchmark_analysis step11"}
    colors=["#0072B2","#D55E00","#009E73","#CC79A7","#6B6B6B"]
    def save(fig,name):
        fig.savefig(outpath(f"figures/11_paper/{name}.png"),metadata=metadata_png)
        fig.savefig(outpath(f"figures/11_paper/{name}.svg"),metadata={"Date":None,"Creator":"benchmark_analysis step11"})
        plt.close(fig)
    for rel in [f"figures/11_paper/{n}.{e}" for n in FIGS for e in ["png","svg"]]:
        outpath(rel).parent.mkdir(parents=True,exist_ok=True)
    fig,axes=plt.subplots(2,2,figsize=(180/25.4,6.35),gridspec_kw={"height_ratios":[1.25,1]})
    for j,s in enumerate(["road","building"]):
        for h in [10,20,30]:
            for v in [2,4,8]:
                cell=joint("ORB-SLAM2::mono",s,h,v)
                for f in ["altitude_m","speed_mps","n_observed_sequences","n_retained_records","n_finite_records"]:
                    value(cell,f,"d","fig:s11-orb-response labels/caption")
                assert cell["n_observed_sequences"]=="1"
                assert cell["n_retained_records"]==cell["n_finite_records"]=="3"
        ax=axes[0,j]
        for h,col,mark,style in zip([10,20,30],colors,["o","s","^"],["-","--",":"]):
            vals=[number(joint("ORB-SLAM2::mono",s,h,v),"mean","fig:s11-orb-response") for v in [2,4,8]]
            ax.plot([2,4,8],vals,marker=mark,ls=style,c=col,lw=1.5,ms=4,label=f"H{h}")
        ax.set_title(s.title()+" | one sequence per cell\n3/3 retained RMSE finite")
        ax.set_xticks([2,4,8]);ax.set_xlabel("Nominal speed V (source labels)")
        ax.set_ylabel("Mean RMSE (source units)")
        ax.grid(alpha=.2);ax.legend(fontsize=8)
        ax=axes[1,j]
        for y,h,col in zip([0,1,2],[10,20,30],colors):
            r=orb(s,h);b=orb(s,h,"mean");m=orb(s,h,"median")
            lo=number(r,"range_min","fig:s11-orb-response");hi=number(r,"range_max","fig:s11-orb-response")
            ax.hlines(y,lo,hi,color=col,lw=3,alpha=.6)
            ax.plot(number(b,"value","fig:s11-orb-response"),y,"o",color=col,ms=5)
            ax.plot(number(m,"value","fig:s11-orb-response"),y,"D",color="black",ms=3)
        ax.axvline(0,c="#555555",lw=.8,ls="--")
        ax.set_yticks([0,1,2],["H10","H20","H30"]);ax.set_ylim(-.55,2.65)
        ax.set_xlabel("V8 minus V2 RMSE (source units)")
        ax.set_title("Checked variation range (not CI)")
        ax.grid(axis="x",alpha=.2)
    fig.suptitle("ORB-SLAM2 mono: speed response depends on height",fontsize=11,y=.98)
    fig.legend(handles=[Line2D([],[],marker="o",color="#555555",ls="",label="Finite-run mean baseline"),
                         Line2D([],[],marker="D",color="black",ls="",ms=4,label="Within-sequence median"),
                         Line2D([],[],color="#555555",lw=3,alpha=.6,label="Baseline / median / single-record deletion range")],
               loc="lower center",bbox_to_anchor=(.5,.004),ncol=1,fontsize=8,frameon=False)
    fig.subplots_adjust(left=.10,right=.98,top=.875,bottom=.18,hspace=.58,wspace=.34)
    save(fig,FIGS[0])
    fig,axes=plt.subplots(1,2,figsize=(180/25.4,3.65))
    for y,s,col in zip(range(5),SCENES,colors):
        r=sen(f"DPVO::mono|speed8_minus2|scene_contribution|V1 {s}")
        val=number(r,"value","fig:s11-dpvo-composition")
        axes[0].barh(y,val,color=col,height=.6,hatch="/" if val<0 else None)
    axes[0].set_yticks(range(5),[s.title() for s in SCENES])
    axes[0].invert_yaxis();axes[0].axvline(0,color="#555555",lw=.8)
    axes[0].set_title("Signed scene contributions\nOriginal F: 15 nominal blocks")
    axes[0].set_xlabel("Contribution to mean difference\n(RMSE source units)")
    views=[sen("DPVO::mono|speed8_minus2|support_view|V1")]+[sen(f"DPVO::mono|speed8_minus2|leave_one_scene_out|V1 minus {s}") for s in SCENES]
    labels=["Full F"]+["Omit "+s.title() for s in SCENES]
    for y,r in enumerate(views):
        val=number(r,"value","fig:s11-dpvo-composition")
        axes[1].plot(val,y,marker="D" if y==0 else "o",color="black" if y==0 else colors[y-1],ms=5,ls="")
        labels[y]+=" (n="+value(r,"low_n_blocks","d","fig:s11-dpvo-composition")+")"
    axes[1].set_yticks(range(6),labels);axes[1].invert_yaxis()
    axes[1].axvline(0,color="#555555",lw=.8,ls="--")
    axes[1].set_title("Full-set baseline and omissions\nOmissions are sensitivity views")
    axes[1].set_xlabel("Mean V8 minus V2 difference\n(RMSE source units)")
    for ax in axes:ax.grid(axis="x",alpha=.2);ax.margins(x=.12)
    fig.suptitle("DPVO mono: a small overall change contains scene cancellation",fontsize=10,y=.98)
    fig.subplots_adjust(left=.115,right=.97,top=.78,bottom=.20,wspace=.95)
    save(fig,FIGS[1])
    fig,axes=plt.subplots(1,3,figsize=(180/25.4,3.35))
    markers=["o","s","^","D","v"]
    for ax,metric,label in zip(axes,["fps","runtime","memory"],["Reported FPS","Runtime (s)","Memory (source units)"]):
        cor=within("hierslam::rgbd_whole",metric)
        points=chosen(T10,lambda r:r["configuration_id"]=="hierslam::rgbd_whole" and
                      r["efficiency_metric"]==metric and r["row_type"]=="sequence_joint_means" and r["status"]=="computed")
        expected=json.loads(cor["used_sequence_row_ids_json"])
        assert {p["row_id"] for p in points}==set(expected)
        for s,c,m in zip(SCENES,colors,markers):
            ps=[r for r in points if r["scene"]==s]
            ax.scatter([number(r,"rmse_joint_mean","fig:s11-hier-association") for r in ps],
                       [number(r,"efficiency_joint_mean","fig:s11-hier-association") for r in ps],
                       s=24,marker=m,c=c,linewidths=.4,edgecolors="white",label=s.title(),alpha=.85)
        ax.set_xlabel("RMSE (source units)");ax.set_ylabel(label)
        ax.set_title("rho="+value(cor,"rho",".3f","fig:s11-hier-association")+
                     "; n="+value(cor,"n_sequences","d","fig:s11-hier-association")+" seq",fontsize=9)
        ax.grid(alpha=.18);ax.margins(x=.07,y=.09)
    fig.suptitle("Hier-SLAM whole trajectory: within-configuration associations",fontsize=10,y=.97)
    handles,labels=axes[0].get_legend_handles_labels()
    fig.legend(handles,labels,loc="lower center",ncol=5,frameon=False,fontsize=8,bbox_to_anchor=(.5,.005))
    fig.subplots_adjust(left=.095,right=.985,top=.79,bottom=.26,wspace=.62)
    save(fig,FIGS[2])

def paragraph(pid,section,claims,evidence,text):
    text = reviewed_paragraph(W, pid, text)
    PARAGRAPHS.append({"paragraph_id":pid,"section":section,"claim_ids":claims,
                       "earlier_evidence_ids":evidence,"text":text})

def draft_materials():
    def v(r,f="value",fmt=".4f"):return value(r,f,fmt,"draft")
    paragraph("P01","分析范围与指标解释",["C11_COV"],["Q1","Q2","Q3","Q4","Q5"],
        "本分析使用已保留的逐次指标记录。一条记录对应某配置、某序列的一次已导出结果；sequence保留原始路线与条件标识，场景是其上层类别。"
        "名义高度H与速度V是从序列标签解析的实验条件，不是本轮测得的实际飞行量。"
        "主要条件分析使用同时具有高度、速度标签的记录；无条件标签记录仍保留在补充数据中，不视为废弃。"
        "表tab:s11-coverage列出选定配置的实际观测数与保留重复数。这些记录不等于全部历史尝试；计划补跑与未保留结果既不补成失败，也不加入当前分母。")
    paragraph("P02","分析范围与指标解释",["C11_COV","C11_REPEAT"],["Q3","Q4"],
        "均方根误差（root mean square error，RMSE）沿用现有字段。逐次pooled均值对有限运行记录等权；序列均值等权先在每条sequence内取有限运行的算术均值，再对可计算的序列等权。"
        "后者不会恢复全无效序列，也不等同均方根的再次合成。repeat_sd描述同一sequence的有限重复波动，跨序列sample_sd描述序列代表值之间的差异，raw_std则是源记录中的单次轨迹误差分布字段，三者不可互换。"
        "探索统计的标准差使用ddof=1；只有一个有限值时重复标准差未定义，不填0，也不平均多个场景的标准差来冒充pooled标准差。")
    paragraph("P03","分析范围与指标解释",["C11_COV","C11_P1","C11_D"],["Q4","R10_P1","R10_T_hierslam::rgbd_whole"],
        "数值非有限、没有记录、尚未补跑与实际轨迹失败是不同状态。本文只称有限运行比例和至少一次有限的序列比例，不将其改名为完整轨迹成功率。"
        "方法间比较的P为双方有记录的同名序列集合，F为P内双方至少有一次有限RMSE的序列，C为F内双方全部保留RMSE均有限的序列；不以run_id配对。"
        "速度端点分析另以固定场景、路线标签和高度构成名义条件块，其F/C按两端同样的有限性定义；块数不能当作序列数。"
        "Spearman rho描述当前集合中重新计算的相对秩关联，不是误差相等或相关百分比。敏感性变体范围只覆盖实际检查的替代值，不是置信区间。")
    paragraph("P04","分析范围与指标解释",["C11_A","C11_D"],["Q1","Q5"],
        current_measurement_note()+
        "已核对的DPVO旧summary与当前探索规则也不完全相同：旧场景表有RMSE转换门控且采用ddof=0，旧高度/速度表各指标独立取有限集合、ddof=1；两类表的分子定义和无记录处理亦有区别。"
        "本稿不替换这些原表的门控、分母或权重。若原稿继续使用旧表，应在整合时保留其定义并注明与序列等权分析的区别。")
    r10=orb("road",10);r30=orb("road",30);b10=orb("building",10);b30=orb("building",30)
    paragraph("P05","飞行条件与场景相关的表现差异",["C11_A"],["Q1"],
        f"ORB-SLAM2单目的速度响应随名义高度改变方向。Road中，V8相对V2的RMSE均值差在H10为{v(r10,'baseline_value')}，在H30为{v(r30,'baseline_value')}；"
        f"Building中对应为{v(b10,'baseline_value')}与{v(b30,'baseline_value')}（图fig:s11-orb-response）。"
        f"这四项对照的每个端点都来自一条sequence，且均有三条有限保留记录。"
        f"Road两项的已查范围分别为[{v(r10,'range_min')}, {v(r10,'range_max')}]、[{v(r30,'range_min')}, {v(r30,'range_max')}]，"
        f"Building为[{v(b10,'range_min')}, {v(b10,'range_max')}]、[{v(b30,'range_min')}, {v(b30,'range_max')}]。"
        "因此，单一总体速度方向不足以概括这些局部条件；方向保持的依据限于当前中位数和逐条有限记录剔除变体。")
    h20=orb("building",20);h20m=orb("building",20,"median")
    paragraph("P06","飞行条件与场景相关的表现差异",["C11_A"],["Q1"],
        f"Building的H20对照构成上述解释的边界：基线速度差为{v(h20,'baseline_value')}，改用序列内中位数后为{v(h20m)}，"
        f"已查范围跨越零至[{v(h20,'range_min')}, {v(h20,'range_max')}]。"
        "图中保留这一高度及全部中间速度点，不能把H10/H30的方向保持推广到所有高度或其它方法。"
        "相关四角差只描述两个高度下速度差的变化，既不是因果双重差分，也不证明显著交互；路线标签分层未消除实际路径或采集条件的全部差异。")
    base=sen("DPVO::mono|speed8_minus2|support_view|V1")
    for fld in ["n_F","low_n_retained","low_n_finite","high_n_retained","high_n_finite"]:
        value(base,fld,"d","fig:s11-dpvo-composition caption")
    pool=sen("DPVO::mono|speed8_minus2|scene_contribution|V1 pool")
    omit=sen("DPVO::mono|speed8_minus2|leave_one_scene_out|V1 minus pool")
    paragraph("P07","总体均值、覆盖和重复结果的敏感性",["C11_B"],["Q9_DPVO_CANCELLATION"],
        f"DPVO较小的总体速度差包含场景抵消。在完整F的{v(base,'n_F','d')}个名义条件块中，以块等权得到V8−V2均值差{v(base,'value','.6f')}。"
        f"Pool对这一总体差的代数贡献为{v(pool,'value','.6f')}，其余场景贡献均为正。"
        f"移去Pool后的同类差值为{v(omit,'value','.6f')}，但它只用于检验场景组成敏感性（图fig:s11-dpvo-composition），不替代完整集合基线。"
        "小总体差据此不能解释为对速度普遍不敏感；共享场景的条件块也不构成独立随机样本或显著性投票。")
    vg=desc("VGGT-SLAM::mono");av=select(A10,pair_id=" <> ".join(PAIRS[1]))
    paragraph("P08","总体均值、覆盖和重复结果的敏感性",["C11_COV"],["Q4","R10_P2"],
        f"可计算的误差均值只描述有限结果覆盖的部分条件。VGGT-SLAM单目有{v(vg,'n_finite_records','d')}/{v(vg,'n_retained_records','d')}条运行RMSE有限，"
        f"至少一次有限的sequence为{v(vg,'n_sequences_with_finite','d')}/{v(vg,'n_observed_sequences','d')}；"
        "Pool的H10/H20与V4/V8组合均有保留记录但全无有限RMSE，不能用其它格子的均值代替它们。"
        f"统计单位还会改变对覆盖的直观判断：ORB-SLAM2与ORB-SLAM3单目分别有{v(av,'A_any_finite_sequences_P','d')}/{v(av,'n_P','d')}、"
        f"{v(av,'B_any_finite_sequences_P','d')}/{v(av,'n_P','d')}条sequence至少一次有限，"
        f"但有限运行数分别为{v(av,'A_n_finite_P','d')}/{v(av,'A_n_retained_P','d')}和{v(av,'B_n_finite_P','d')}/{v(av,'B_n_retained_P','d')}（表tab:s11-coverage）。"
        "这两层描述回答不同问题，都不能据此判定完整轨迹成功或某版本更可靠。")
    lo=seq("ORB-SLAM3::rgbd","cross_building_low_low")
    bg=seq("ORB-SLAM3::rgbd","road2_medium_medium")
    rr=sen("ORB-SLAM3::rgbd|cross_building_low_low|sequence_variant_range|drop_one")
    rd=seq("ORB-SLAM3::rgbd","road2_medium_low")
    paragraph("P09","总体均值、覆盖和重复结果的敏感性",["C11_REPEAT"],["Q3"],
        f"ORB-SLAM3的彩色图像加深度（RGB-D）配置的重复值说明，较高均值还需结合具体运行解释。Building的H10V2三条有限值中，两条约为"
        f"{value(lo,'finite_values_json','.5f','draft',0)}与{value(lo,'finite_values_json','.5f','draft',1)}，另一条为"
        f"{value(lo,'finite_values_json','.4f','draft',2)}；均值为{v(lo,'mean')}，中位数为{v(lo,'median','.5f')}，"
        f"删一均值范围为[{v(rr,'range_min','.5f')}, {v(rr,'range_max')}]。"
        f"Road H10V4另有两条有限值与一条非有限记录，有限均值为{v(rd,'mean')}，不能将非有限值补0。"
        f"与此同时，Road H20V4的三条值为{value(bg,'finite_values_json','.4f','draft',0)}、"
        f"{value(bg,'finite_values_json','.4f','draft',1)}、{value(bg,'finite_values_json','.4f','draft',2)}，均值{v(bg,'mean')}，"
        "构成多个较高重复共同支持的背景。因此，单条记录敏感性不能解释所有高均值，较大影响也不自动证明记录错误。")
    f=within("hierslam::rgbd_whole","fps");t=within("hierslam::rgbd_whole","runtime");m=within("hierslam::rgbd_whole","memory")
    paragraph("P10","配置内部的计算负担与方法间难度模式",["C11_D"],["Q5","R10_T_hierslam::rgbd_whole"],
        "Hier-SLAM完整轨迹配置中的误差与资源描述呈现共同变化。对每条sequence，先取RMSE与相应效率指标同时有限的运行交集，并在同一交集上计算两个均值。"
        f"在各指标可用的{v(f,'n_sequences','d')}条sequence上，RMSE与FPS、runtime、memory的rho分别为"
        f"{v(f,'rho','.3f')}、{v(t,'rho','.3f')}、{v(m,'rho','.3f')}（图fig:s11-hier-association）。"+
        ("总体及五景均保持FPS负、runtime和memory正的方向。" if hier_relation_facts()[0] else "未满足原统一方向的指标/范围为："+ "、".join(hier_relation_facts()[1])+"；旧共同变化主张需重新审阅。")+
        "这一配置内关联不能解释成以更多计算换取更好精度，更不能归因于尚未检查的内部机制。")
    e=select(E9,row_id="runtime|overall")
    paragraph("P11","配置内部的计算负担与方法间难度模式",["C11_D"],["Q5"],
        f"上述序列关联与运行级效率筛选应分开阅读。Hier完整轨迹的runtime（s）在效率本身有限的A集合中有{v(e,'n_A','d')}条运行，"
        f"再要求RMSE有限后，B集合剩{v(e,'n_B','d')}条；两者均值分别为{v(e,'mean_A','.2f')}与{v(e,'mean_B','.2f')}，"
        f"B−A为{v(e,'overall_B_minus_A','.3f')}（s）。"
        "当前受筛选影响单元及各自方向见第9步runtime分解；整体筛选方向不能自动推广到每个单元，旧四单元方向不作为新版前提。"
        "A/B刻画不同保留集合，不选择其中一项作为唯一正确性能；完整轨迹是用户确认的配置范围，也不等于每条保留运行均完整完成。")
    p=pair(0);pp=pair(0,"scene_F_mean","pool");pr=pair(0,"scene_F_mean","road");hh=pair(5);hc=pair(5,"C_mean")
    paragraph("P12","配置内部的计算负担与方法间难度模式",["C11_P1","C11_P6"],["R10_P1","R10_P6"],
        "方法间关系作为对上述场景异质性的补充，而非论文主线的替代。"
        f"DPVO与DROID-SLAM单目在共同{v(p,'n_sequences','d')}条sequence上的总体rho为{v(p,'rho','.3f')}，"
        f"但Pool内为{v(pp,'rho','.3f')}（n={v(pp,'n_sequences','d')}），Road内为{v(pr,'rho','.3f')}（n={v(pr,'n_sequences','d')}），"
        "总体相似性不能概括每个场景的排序。"
        f"两种Hier 500帧配置在共同{v(hh,'n_sequences','d')}条sequence上的rho为{v(hh,'rho','.3f')}；"
        f"要求双方全部保留RMSE有限的C集合为{v(hc,'n_sequences','d')}条sequence，rho为{nullable_rho(hc)}；"
        "当前两配置的重复结构为："+repetition_summary(["hierslam::rgbd_500","hierslam::semantic_500"])+"。高秩关联不证明语义无收益、误差相等或独立重复稳定；均值/中位数与F/C按当前实际有限集合核对。六对关系与各自样本数集中列在补充表tab:s11-pair-patterns。")
    paragraph("P13","当前局限和适用范围",["C11_PROVENANCE","C11_AVAIL","C11_CONSTANT"],["Q2","R10_AVAILABILITY_COMPLEMENTARITY","R10_CONSTANT_MEMORY"],
        "上述结论限定于当前保留记录及其有限结果集合。DROID-SLAM RGB-D、ElasticFusion RGB-D、SLAM3R单目和VGGT-LONG单目存在序列内重复误差字段完全相同的特征，"
        "其生成来源和独立性尚未确认，既不删除这些记录，也不把相同值解释成复制、固定种子或确定性机制。"
        "跨方法比较中的同名sequence尚不能证明实际输入与历史评测协议完全相同；双方有有限值的子集也不代表全无效条件。"
        "双向数值可用性只提供后续系统验证线索，尚非实现过的融合收益；恒定输入的相关未定义，不能填零。")
    paragraph("P14","当前局限和适用范围",["C11_COV","C11_D","C11_EXCLUDED"],["Q3","Q4","Q5"],
        "当前四个更新配置的实际保留结构为："+repetition_summary(["hierslam::rgbd_500","hierslam::semantic_500","hierslam::rgbd_whole","SplaTAM::rgbd"])+"。三次保留不等于三次有限、完整完成或相互独立。"+
        "现有描述不补齐虚构运行，也不为统一次数删除其它方法的记录。"+current_measurement_note()+
        "材料继续作为独立审阅稿；本轮刷新数值不代表原论文已重写，不支持普遍机制或因果结论。")
    captions={}
    captions["fig:s11-orb-response"]="ORB-SLAM2单目的条件响应与所查重复敏感性。上排是road/building全部H10/20/30与V2/4/8组合的有限运行均值，每格一条sequence、3/3条保留RMSE有限。下排为固定H的V8−V2：圆点是均值基线、菱形是序列内中位数，线段涵盖基线、中位数和逐条有限记录剔除结果，不是置信区间（CI）。H/V为来源名义标签；名义完整轨迹范围已由用户确认；RMSE物理单位/历史对齐仍待核实。Building H20跨零反例保持可见。"
    captions["fig:s11-dpvo-composition"]="DPVO单目完整共同有限集合的场景抵消。F指同一名义场景/路线标签/H块的V2与V8两端均至少一次RMSE有限；原F共15块，各端合计45/45条运行有限。左侧为五场景对块等权总体差的有符号代数贡献；右侧同时保留完整F和每次移去一个场景的视图及各自块数n，不把剔除后结果替代基线。这些块非独立随机样本；名义完整轨迹范围已确认，物理单位和历史协议仍未闭合。"
    for fld in ["n_A","n_B"]:
        value(e,fld,"d","fig:s11-hier-association caption")
    for metric in ["fps","runtime","memory"]:
        cr=within("hierslam::rgbd_whole",metric)
        for fld in ["n_observed_sequences","n_sequences"]:
            value(cr,fld,"d","fig:s11-hier-association caption")
        DISPLAY.append({"source_ref":ref(cr),"fields":["n_observed_sequences","n_sequences"],
                        "operation":"observed minus usable","unrounded_value":int(cr["n_observed_sequences"])-int(cr["n_sequences"]),
                        "format":"d","display":str(int(cr["n_observed_sequences"])-int(cr["n_sequences"])),"use":"fig:s11-hier-association caption no-joint-finite sequence"})
    panel_counts=[]
    for metric in ["fps","runtime","memory"]:
        cr=within("hierslam::rgbd_whole",metric)
        panel_counts.append(metric+"有限/观测sequence="+value(cr,"n_sequences","d","fig:s11-hier-association caption")+"/"+value(cr,"n_observed_sequences","d","fig:s11-hier-association caption"))
    captions["fig:s11-hier-association"]=("Hier-SLAM完整轨迹配置内的同运行交集关联。每个点是一条sequence，横纵均值使用该sequence内RMSE与对应效率同时有限的相同运行；"+
        "；".join(panel_counts)+"。无共同有限运行不填0。颜色与形状共同区分场景，rho为sequence等权的Spearman。runtime单位为s（作者确认）；计时覆盖与内存单位/类型仍有相应限制；runtime运行级A/B="+
        value(e,"n_A","d","fig:s11-hier-association caption")+"/"+value(e,"n_B","d","fig:s11-hier-association caption")+"及筛选差异见正文。不能把共同有限子集当作唯一正确性能或解释成多用计算换精度。")
    md=["# 飞行条件、场景异质性与保留结果的敏感性\n",
        "独立中文审阅稿；内部段落和材料标签待与原稿对接。发布状态以结论清单为准，正文候选不等于可提交。\n"]
    tx=["% Independent Chinese insertion fragment; no document class, bibliography or assumed paper numbering.",
        "% Needs a host supporting UTF-8 Chinese and graphicx; compile from benchmark_analysis or adapt paths.",
        "% Paragraph IDs and local evidence are internal traceability, not public references.",
        r"\subsection*{飞行条件、场景异质性与保留结果的敏感性}",
        tex_escape(md[1].strip())+"\n"]
    last=None
    for p in PARAGRAPHS:
        if p["section"]!=last:
            md.append("## "+p["section"]+"\n")
            tx.append(r"\subsubsection*{"+tex_escape(p["section"])+"}")
            last=p["section"]
        md += ["**"+p["paragraph_id"]+"** "+p["text"]+"\n",
               "<!-- "+p["paragraph_id"]+"; claim_id="+",".join(p["claim_ids"])+"; evidence="+",".join(p["earlier_evidence_ids"])+" -->\n"]
        tx += ["% "+p["paragraph_id"]+"; claim_id="+",".join(p["claim_ids"])+"; evidence="+",".join(p["earlier_evidence_ids"]),
               tex_escape(p["text"])+"\n"]
    md += ["## 本材料包图表\n","以下仅为内部稳定标签，不预设论文图表编号。三图按暂定180 mm宽度制作；正式模板未提供。\n"]
    tx += [r"\subsubsection*{本材料包图表}",tex_escape(md[-1].strip())]
    for label,name in zip(captions,FIGS):
        md += ["### "+label+"\n",f"![{label}](../../figures/11_paper/{name}.png)\n",captions[label]+"\n"]
        tx += [r"\begin{figure}[htbp]",r"\centering",r"\includegraphics[width=\linewidth]{figures/11_paper/"+name+".png}",
               r"\caption{"+tex_escape(captions[label])+"}",r"\label{"+label+"}",r"\end{figure}"]
    for name,label,kind in [("analysis_coverage","tab:s11-coverage","正文候选表"),("six_pair_patterns","tab:s11-pair-patterns","补充表")]:
        md += [f"{kind} {label}：[CSV](../../tables/11_paper/{name}.csv) · [LaTeX片段](../../tables/11_paper/{name}.tex)。\n"]
        tx += [r"\input{tables/11_paper/"+name+".tex}"]
    # Turn only declared internal material labels into proper TeX references.
    tex="\n".join(tx)+"\n"
    for lab in list(captions)+["tab:s11-coverage","tab:s11-pair-patterns"]:
        escaped=tex_escape(lab)
        for p in PARAGRAPHS:
            original=tex_escape(p["text"])
            if escaped in original:
                tex=tex.replace(original,original.replace(escaped,r"\ref{"+lab+"}"))
    output_text("paper/11_draft/results_discussion.md","\n".join(md)+"\n")
    output_text("paper/11_draft/results_discussion.tex",tex)
    return captions

TARGETED = [
("A","C11_DROID_POOL/C11_PROVENANCE/C11_P3/C11_P4；补充关系表",
 "四配置DROID RGB-D、ElasticFusion RGB-D、SLAM3R mono、VGGT-LONG mono各48条sequence内的已提供误差字段重复相同；效率未必同",
 "所选配置的尝试标识→评估输出→导出行的最小关联记录，以及当时导出命令/版本；先核查已标记案例，非要求重跑全部",
 "当前保留数值及字段相等特征；保留所有行，不证明独立稳定",
 "复制、固定种子、确定性已证实；来源已闭合；独立重复方差很小",
 "requires_targeted_verification"),
("B","C11_A/B/REPEAT/D与跨方法C11_P1～P5；三张图及误差量化段落",
 "用户确认两种Hier 500帧，其余逐次配置为完整轨迹；MonoGS与当前新SplaTAM的Accuracy已有定点审计，旧阶段数值必须按所绑定版本解释；SR专题已完成并冻结",
 "拟引用配置的历史评估命令/版本、对齐选项、坐标单位与实际评估起止范围；逐配置绑定已保留CSV来源",
 "仅在明确配置、名义条件和来源单位下描述现有数值；不能称公开可比的绝对误差",
 "所有CSV历史同Sim(3)/同米单位/同完整轨迹；因果高度速度效应",
 "requires_targeted_verification"),
("C","C11_COV/C11_AVAIL；覆盖表及任何拟用SR",
 "有限运行/保留运行、至少一次有限sequence/实际sequence均可审计；作者定义的最终导出输出覆盖SR@80/90/95已在独立专题完成，不等于100%完整或在线连续定位",
 "使用冻结SR专题及对应稳定运行键；本组数值可用性不能代替SR，不再重复索求已确认阈值或重算SR",
 "数值可用性比例；无记录/无效/未补跑分开",
 "将有限RMSE比例或至少一次有限比例重命名为完整轨迹成功率、可靠性赢家",
 "current_numeric_availability_draft_supported; operational_SR_completed_and_frozen_separately"),
("D","C11_D、C11_T_DPVO、C11_T_ORB-SLAM3；资源关联图",
 "runtime单位秒已确认；reported FPS为主，计时阶段仍按具体配置限定。旧分析memory未接入独立有类型Table 2标准化，不将旧字段一律称GPU预留显存",
 "拟引用配置当时计时/内存计量定义、聚合方式和代表日志键到CSV的对应；只查直接影响所选材料的配置",
 "当前记录中同运行交集的关联，以及A/B集合改变后的均值差",
 "source units标签就等于核验解决；跨方法资源效率优劣；多算换精度；具体内部机制",
 "requires_targeted_verification"),
("E","C11_COV/REPEAT/P6/D；覆盖表、Hier500关系与重复稳定性措辞",
 "当前保留重复数与用户确认见更新版source_manifest及覆盖表；旧一次/两次说明仅保留在更新前快照",
 "仅当主张重复稳定性或更新输入时，核对新增实际运行及来源标识；当前描述不要求立即补跑",
 "按已保留次数和有限次数分别描述；仅一个有限值时重复SD未定义；500与完整轨迹分开",
 "历史尝试数等于当前保留数；补虚构记录；三次保留均成功或均独立",
 "current_retained_counts_draft_supported; stability_requires_targeted_verification"),
("F","所有配置显示名及原稿整合",
 "MonoGS显示名已由用户确认；MongGS仍保留为来源目录和configuration_id。未提供原论文编辑目标或期刊模板",
 "用户确认显示名映射及明确原稿/插入位置/模板；如需机制文献，另行授权定向补证",
 "独立中文审阅稿、内部稳定标签、暂定180 mm排版",
 "已经整合原稿/符合某期刊要求；未经来源支持新增文献事实或bibkey",
 "editorial_verification_pending")]
def target_table():
    out=["| 项 | 影响主张/材料 | 已知 | 最小新增证据（本轮未调查） | 当前可写 | 暂不能写 | 状态 |",
         "|---|---|---|---|---|---|---|"]
    out += ["| "+" | ".join(row)+" |" for row in TARGETED]
    return "\n".join(out)
def reproducibility(inputs,versions):
    commands=[]
    for n in [7,8,9]:
        path={7:"reports/07_exploration_spec.json",8:"reports/08_condition_analysis_spec.json",9:"reports/09_robustness_spec.json"}[n]
        d=json.loads(text_input(path));commands.append((str(n),d["command"],path))
    text10=text_input("reports/10_method_relationships.md")
    # Reports may quote the canonical command while running under an explicitly
    # validated staging workspace. Retain the exact frozen report command.
    allowed_roots={W,Path(__file__).resolve().parents[1],Path("/home/yuan/SLAM/codex_review/benchmark_analysis")}
    allowed_commands={PYTHON+" -B "+str(root/"scripts/analyze_method_relationships.py")+" --overwrite" for root in allowed_roots}
    matched=[cmd for cmd in allowed_commands if cmd in text10.splitlines()]
    if len(matched)!=1:
        raise ValueError(f"Expected one verified stage10 command in frozen report; found {len(matched)}")
    cmd10=matched[0]
    commands.append(("10",cmd10,"reports/10_method_relationships.md"))
    codefence=chr(96)*3
    lines=["# 第11步材料的复现与更新交接\n",
    "这是材料提取/排版交接，不是新机器上的独立复现证明。原始实验目录和原论文未修改；本次授权版本更新可重建工作区第6～11C步依赖，旧版本先备份；不重评轨迹或补跑。\n",
    "## 仅重建本轮材料\n",codefence+"bash",
    PYTHON+" -B "+str(W/SCRIPT)+" --overwrite",codefence,
    "\n默认不带--overwrite会拒绝已有材料。--overwrite只允许固定第11步输出清单，并先核对上次生成哈希；任何草稿或其它输出被人工修改、缺失、成为软/硬链接，都停止而不覆盖。"
    "若人工修稿与生成版本冲突，先由作者保留/合并修订，再授权更新生成内容；不要伪造旧哈希来绕过保护。\n",
    "只检查、不重建："+chr(96)+PYTHON+" -B "+str(W/SCRIPT)+" --verify"+chr(96)+"。\n",
    "构建入口只使用标准库和Matplotlib绘图；没有导入任何旧分析脚本或调用旧main。"
    "run_records.csv仅核对冻结字节哈希，不重新解析逐次值；选定成员通过已有序列表、端点表和关系证据表核验。\n",
    "## 冻结证据与变化停止\n",
    "artifact_manifest.json列出全部实际读取输入哈希、是否存在旧阶段快照、精确行键、行内容哈希、成员字段、显示前数值与格式、段落claim_id、材料来源和输出哈希。"
    "标准化三个文件与第10步快照逐项一致；其它派生产物只有实际存在的旧哈希才做历史比较，无旧哈希者标记本轮实际快照。清单自身不写自身最终哈希。\n",
    "构建前后均检查冻结输入。任一变化会报出具体路径并停止；按清单row_sources、displays和11_claim_registry.csv的evidence_rows_json定位受影响主张/图表。"
    "不要只刷新哈希后继续排版。先判断变更是否改变成员、配置范围或统计规则；数字与旧报告实质冲突时暂停该主张纳入，不修旧表配合叙事。\n",
    "每个数值的来源链：旧派生CSV精确行键→成员字段/同表baseline/variant键→source_relative_path、source_sha256与source_record_index。"
    "这些原始来源仅被引用，不由本脚本访问。显示舍入只作用于展示；绘图使用旧表未舍入值，不重新分组或检验。\n",
    "## 原始统计由哪些既有入口负责\n",
    "以下命令来自当前约定或报告；实际数据更新执行顺序与状态见本轮updates/rebuild_manifest。它们不是仅排版命令。\n",
    "| 阶段 | 已有命令 | 记录来源 |\n|---|---|---|"]
    lines += ["| "+n+" | "+chr(96)+cmd+chr(96)+" | "+path+" |" for n,cmd,path in commands]
    lines += ["\n第5步DPVO旧表复现由scripts/run_dpvo_pilot.py负责；第6步标准化由scripts/build_analysis_dataset.py负责。"
              "第6步是版本更新的上游标准化入口，第5步历史核对不重跑。第5步旧scene表的门控/ddof=0与旧高度/速度表独立有限集合/ddof=1保留；"
              "第7步以后sequence等权、repeat_sd与有限集合见原约定，本稿未偷偷替换旧总表。\n",
    "## 新重复记录到来之后\n",
    "未来新增真实实验先核对来源及配置身份，尤其区分Hier两种500帧与完整轨迹。"
    "按原阶段范围更新来源核验与第6步主表/manifest/schema/质量检查，重新核对第7步覆盖与重复、"
    "第8步条件单元、第9步支持集合与敏感性、第10步匹配集合及相关，再决定哪些主张仍成立。"
    "Hier新增记录会影响C11_COV/P6/D及相应图表，SplaTAM新增记录会影响覆盖和双向可用性；其它配置变化也沿精确成员映射追踪。"
    "版本更新由受控调度入口执行，实际完成状态见本轮updates记录；未保留记录不加入分母。\n",
    "## 本次实际依赖与排版\n",
    "| 项 | 本次实际值 |\n|---|---|"]
    lines += ["| "+k+" | "+str(v)+" |" for k,v in versions.items()]
    lines += ["\n依赖版本来自本次执行进程/包元数据，不把历史环境报告当作本次新验证；没有导出整个环境或安装锁定依赖。"
    "缓存仅存在工作区reports下本轮临时目录，退出清理；禁用字节码写入。\n",
    "图暂定宽180 mm，PNG/SVG成对；实际查看状态绑定图像哈希，后续图像字节改变需重新查看。"
    "results_discussion.tex是UTF-8中文插入片段，正文与Markdown由同一段落数据生成。"
    "宿主需支持中文及graphicx；图表路径相对于benchmark_analysis根。当前只做转义、label/ref、路径和内容对应检查，未安装或调用未知模板进行LaTeX编译。\n",
    "内部P01等段落ID、claim_id、fig:s11-*与tab:s11-*标签供审阅追溯，不是公开文献或原论文编号。"
    "未新增DOI、bibkey、参考文献、作者/资助声明或文献事实。MonoGS显示名已确认；原稿编号/插入位置仍待作者确认。"
    "四配置重复来源、误差历史、完成判据、效率测量仍按定向核验表处理；材料整理完成不等于论文已可提交。\n"]
    output_text("paper/11_draft/reproducibility.md","\n".join(lines)+"\n")
    return commands

def verify_materials(claims):
    md=outpath("paper/11_draft/results_discussion.md").read_text()
    tex=outpath("paper/11_draft/results_discussion.tex").read_text()
    labels=re.findall(r"\\label\{([^}]+)\}",tex)
    inputs=re.findall(r"\\input\{([^}]+)\}",tex)
    for f in inputs:
        assert f in OUTPUTS and outpath(f).is_file(),f
        labels+=re.findall(r"\\label\{([^}]+)\}",outpath(f).read_text())
    assert len(labels)==len(set(labels))==5
    refs=re.findall(r"\\ref\{([^}]+)\}",tex)
    assert set(refs)<=set(labels),(refs,labels)
    for f in re.findall(r"\\includegraphics\[[^\]]*\]\{([^}]+)\}",tex):
        assert f in OUTPUTS and outpath(f).is_file(),f
    for p in PARAGRAPHS:
        expected=tex_escape(p["text"])
        for lab in labels:expected=expected.replace(tex_escape(lab),r"\ref{"+lab+"}")
        assert expected in tex and p["text"] in md,p["paragraph_id"]
        assert set(p["claim_ids"])<={c["claim_id"] for c in claims}
    assert not re.search(r"\\(?:cite|bibliography|documentclass)\b",tex)
    for p in [outpath("paper/11_draft/results_discussion.tex")]+[outpath(x) for x in inputs]:
        s=p.read_text()
        depth=0
        for char in re.sub(r"\\[{}]","",s):
            if char=="{":depth+=1
            if char=="}":depth-=1
            assert depth>=0,p
        assert depth==0,p
    for c in claims:
        if c["placement"]=="main_text_candidate":
            assert json.loads(c["evidence_rows_json"]),c
        assert c["placement"] in ["main_text_candidate","supplementary","internal_only","excluded"]
        assert c["release_status"] in ["draft_supported_with_limits","requires_targeted_verification","unsupported","needs_reassessment"]
    # Existing independent tables must agree; never resolve conflicts by editing sources.
    av=select(A10,pair_id=" <> ".join(PAIRS[1]))
    for side,c in zip(["A","B"],PAIRS[1]):
        d=desc(c)
        assert av[side+"_n_finite_P"]==d["n_finite_records"]
        assert av[side+"_n_retained_P"]==d["n_retained_records"]
        assert av[side+"_any_finite_sequences_P"]==d["n_sequences_with_finite"]
    for s in ["road","building"]:
        for h in [10,20,30]:
            low=joint("ORB-SLAM2::mono",s,h,2);high=joint("ORB-SLAM2::mono",s,h,8)
            close(float(high["mean"])-float(low["mean"]),orb(s,h,"mean")["value"])
            assert all(r["n_observed_sequences"]=="1" and r["n_retained_records"]=="3" and r["n_finite_records"]=="3" for r in [low,high])
    assert float(orb("building",20)["range_min"])<0<float(orb("building",20)["range_max"])
    b=sen("DPVO::mono|speed8_minus2|support_view|V1")
    close(sum(float(sen(f"DPVO::mono|speed8_minus2|scene_contribution|V1 {s}")["value"]) for s in SCENES),b["value"])
    assert b["n_F"]=="15" and b["low_n_retained"]==b["low_n_finite"]==b["high_n_retained"]==b["high_n_finite"]=="45"
    for i in range(6):
        r=pair(i)
        evidence=chosen(Q10,lambda x:x["pair_id"]==r["pair_id"] and x["in_F"]=="True")
        assert {e["evidence_id"] for e in evidence}==set(json.loads(r["member_evidence_ids_json"]))
        assert len(evidence)==int(r["n_sequences"])
        for side in ["A","B"]:
            assert sum(int(e[side+"_n_retained"]) for e in evidence)==int(r[side+"_n_retained"])
            assert sum(int(e[side+"_n_finite"]) for e in evidence)==int(r[side+"_n_finite"])
    CHECKS.update(paragraphs_matched=len(PARAGRAPHS),labels_unique=len(labels),refs_resolved=len(refs),
        source_conflicts=0,selected_numeric_rows_reconciled=True,main_claims_have_evidence=True,
        no_fake_citations=True,display_values=len(DISPLAY),new_figures=3,main_tables=1,supplementary_tables=1,
        latex_compilation="not_run_unknown_host_template",raw_source_access=False)
    return CHECKS

def guard_tests():
    global W
    original=W
    passed=[]
    with tempfile.TemporaryDirectory(prefix=".step11_guard_",dir=original/"reports") as td:
        W=Path(td)
        try:
            for p in OUTPUTS:
                q=safe(p);q.parent.mkdir(parents=True,exist_ok=True);q.write_text("generated")
            mp=safe(MANIFEST);mp.parent.mkdir(parents=True,exist_ok=True)
            mp.write_text(js({"outputs":{p:{"sha256":sha(safe(p))} for p in OUTPUTS}}))
            try:preflight(False);raise AssertionError("default overwrite accepted")
            except ValueError:passed.append("default_refusal")
            preflight(True);passed.append("reviewed_generated_outputs_only")
            p=safe("paper/11_draft/results_discussion.md");p.write_text("human edit")
            before={n:sha(safe(n)) for n in OUTPUTS}
            try:preflight(True);raise AssertionError("human edit overwritten")
            except ValueError:passed.append("manual_draft_conflict")
            assert before=={n:sha(safe(n)) for n in OUTPUTS}
            try:safe("../outside");raise AssertionError("escape accepted")
            except ValueError:passed.append("scope_guard")
            l=W/"link";l.symlink_to(p)
            try:safe("link");raise AssertionError("link accepted")
            except ValueError:passed.append("symlink_guard")
            l.unlink()
            h=W/"hard";os.link(p,h)
            try:safe("hard");raise AssertionError("hardlink accepted")
            except ValueError:passed.append("hardlink_guard")
            h.unlink()
        finally:W=original
    return passed

def synthesis(claims,inputs,versions,review):
    claim_status={r["claim_id"]:r["release_status"] for r in claims}
    lines=[INITIAL_PLAN.split("## 论证与发布边界")[0],
        "## 实际论证取舍与关键修正\n",
        "本材料保留第11步历史案例组织的四条观察：C11_A；C11_B；C11_COV与C11_REPEAT组成同一观察；C11_D；不将其自动恢复为当前投稿主线。结论清单共"+str(len(claims))+"条，"
        "复用实际Q1～Q5、Q9_DPVO_CANCELLATION与R10_*，没有将同一现象的阶段展开算成多个独立发现。\n",
        "| 观察 | 纳入理由 | 已保留反例/边界 | 发布状态 |\n|---|---|---|---|",
        f"| O1 条件响应 | 同时有联合单元、固定端点和重复敏感性证据 | Building H20的基线正、中位数和删一可负；H10/H30仅所查方向保持；四角量非因果DID | C11_A {claim_status['C11_A']} |",
        f"| O2 场景抵消 | 完整F与所有单场景剔除、代数贡献相互核对 | 原始完整集合保持主结果，删Pool不替代基线 | C11_B {claim_status['C11_B']} |",
        f"| O3 覆盖和重复 | 将运行/序列分母与具体有限值放在一起解释 | VGGT全无效格、ORB3三高背景、ORB2/ORB3两个层级的不同印象 | C11_COV {claim_status['C11_COV']}；C11_REPEAT {claim_status['C11_REPEAT']} |",
        f"| O4 配置内关联 | 同运行交集、总体及各场景方向、A/B组成均有证据 | 共同恶化不解释为更多计算换精度；A/B不是唯一正确集合 | C11_D {claim_status['C11_D']} |\n",
        "四配置重复误差的来源限制保留在正文P13、补充表图注和定向核验表；不判断数据复制、固定种子或确定性。"
        "MonoGS使用用户确认显示名，MongGS来源键保持不变。"+current_measurement_note()+
        "现行资格见audits/accuracy_protocol/20261008_three_configurations/report.md；数值版本见reports/current_input_manifest.json。\n",
        "## 补充与排除\n",
        "- 六对方法总体/五场景rho、F/C/中位数与n提取为一张补充表。Hier500按当前实际重复与有限集合计算，rho高不等于语义无收益；VGGT只覆盖双方有限序列。其余剔除场景和秩散点沿旧路径登记，不重新绘全套图。\n"
        "- DROID Pool条件差及重复相同、ORB3四个案例的旧重复图、VGGT的旧覆盖/支持图，均保留为可追溯补充。DPVO/ORB3的配置内资源关系亦沿原表登记。\n"
        "- 当前双向可用性配置对在清单C11_AVAIL逐一列出精确pair_id及实际数量，来源是完整pairwise_availability表。六对覆盖图只描述六对，不代替完整集合。没有新增融合效果图。\n"
        "- 因果机制、显著交互、方法赢家、由有限RMSE直接推出完整成功或在线连续稳定、已实现融合和语义无效仍为C11_EXCLUDED/unsupported。独立冻结的输出覆盖SR@80/90/95已有明确操作定义及结果，不属于上述排除项，也不由本材料重新计算。\n",
        "## 定向提交前核验\n",target_table()+"\n",
        "本轮只记录以上最小证据需求，没有访问实验源目录、底层日志、轨迹、代码仓库或原论文，没有运行第12步调查。\n",
        "## 数字、成员与口径检查\n",
        "采用机器可读CSV精确行键，不以报告舍入数字作为计算输入。构建器核对ORB端点差、DPVO贡献和、"
        "覆盖数在序列与关系两表中的一致性，以及六对F成员、有限/保留运行数量。图表只改变表达，没有新分组、新假设检验或新支持集合。"
        "详细未舍入值/格式/use位置、成员字段与row_sha256在artifact_manifest.json；两张CSV保留读者表之外的证据键。\n",
        "标准化records/manifest/schema与第10步已存快照一致。其它28项输入范围内，旧spec存在哈希的逐一匹配；"
        "未有旧哈希的产物仅标本次实际快照，不虚构历史匹配。run_records仅核对哈希，本轮没有重新解析真实逐次指标。\n",
        "统计标准差、旧summary与新探索规则区别见正文P02/P04和交接说明。500帧独立列示；名义scope按当前用户确认登记，不据此确认逐运行完整完成。"
        "有限率/sequence数/运行数/条件块数分别标注；比例没有改写成成功率，Spearman未写成百分比，敏感性范围未写成CI。\n",
        "## 本轮产物与验证\n",
        "- 中文审阅稿与同内容TeX插入片段："+chr(96)+"paper/11_draft/results_discussion.md/.tex"+chr(96)+"；"+str(len(PARAGRAPHS))+"个稳定段落。\n"
        "- 结论登记："+chr(96)+"reports/11_claim_registry.csv"+chr(96)+"；来源、显示格式、输出哈希与命令："+chr(96)+"paper/11_draft/artifact_manifest.json"+chr(96)+"。\n"
        "- 表：analysis_coverage与six_pair_patterns，各CSV+TeX。图：三组PNG+SVG，均在本轮专属目录。本材料入口不复制整套上游图；上游更新状态由本轮rebuild_manifest登记。\n"
        "- 复现交接："+chr(96)+"paper/11_draft/reproducibility.md"+chr(96)+"；轻量入口："+chr(96)+SCRIPT+chr(96)+"。\n",
        "检查结果："+js(CHECKS)+"。\n",
        "视觉验收："+js(review)+"。暂定180 mm插入宽度；未知正式模板，未声称期刊合规。"
        "静态检查包含中文文本对应、TeX转义、唯一label、全部ref及图表路径；未编译未知宿主模板。\n",
        "覆盖保护已实际测试默认拒绝、仅当前固定输出、人工修稿冲突、路径越界和软/硬链接。"
        "输入在构建前后再次核对；哈希有变化就停止并列具体路径。第3～5步历史证据和原版本备份由受控更新清单保护；实际阶段更新见rebuild_manifest。\n",
        "本轮复用既有证据嵌入式材料结构，不安装或执行外部skills，不新增文献。旧缩略语检查属于历史生成版本，图稿变化后不能冒充本轮审查。\n",
        "第11步材料整理完成须以数值/静态检查及新PNG实际查看全部完成为准。材料整理完成不等于论文已可提交。停止在本阶段，不整合原稿，不自动补跑或启动第12步。\n"]
    if review.get("status")=="passed_actual_open":
        lines[-1]="第11步材料整理已完成：数值与静态检查通过，三张最终PNG已逐张实际查看。材料整理完成不等于论文已可提交；未整合原稿，停止在本阶段，不自动补跑或启动第12步。\n"
    if review.get("acronym_check"):
        lines += ["## 写作辅助检查\n",js(review["acronym_check"])+"\n"]
    reassess=[c["claim_id"] for c in claims if c.get("update_assessment_status")=="needs_reassessment"]
    if current_version(W):
        amendment = reviewed_patch(W)
        note = amendment.get("synthesis_review_note") or ("本轮保留原案例锚点，不重选论文主线。需重新审阅的主张："+("、".join(reassess) or "无")+
            "。各项旧statement、旧release_status和变动数值证据键见当前结论清单；旧版本内容保存在updates备份。")
        lines.insert(1,"## 数据版本更新后的主张检查\n"+note+"\n")
    output_text("reports/11_paper_synthesis.md","\n".join(lines))

STAGING=None
def outpath(rel):
    safe(rel)
    if rel not in OUTPUTS:raise ValueError("Output outside allowlist")
    return (STAGING/rel) if STAGING else safe(rel)

def main():
    global STAGING
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--overwrite",action="store_true")
    parser.add_argument("--verify",action="store_true",help="verify frozen inputs and generated output hashes only")
    parser.add_argument("--self-test",action="store_true",help="test output guards on self-created temporary files")
    args=parser.parse_args()
    if args.self_test:
        print(js({"guard_tests":guard_tests()}));return
    if args.verify:
        if not safe(MANIFEST).is_file():
            raise ValueError("No completed generation manifest; cannot verify outputs.")
        preflight(True);inputs=check_inputs()
        print(js({"inputs_verified":len(inputs),"outputs_verified":len(OUTPUTS),"no_writes":True}));return
    old=preflight(args.overwrite)
    inputs=check_inputs()
    CHECKS["guard_tests"]=guard_tests()
    for p in INPUT_HASHES:
        if p.endswith(".md"):text_input(p)
    schema=json.loads(text_input("derived_data/06_standardized/schema.json"))
    # Stage all new outputs inside this workspace; commit only after numerical and static checks pass.
    with tempfile.TemporaryDirectory(prefix=".step11_build_",dir=W/"reports") as td:
        STAGING=Path(td)/"outputs";STAGING.mkdir()
        cache=Path(td)/"cache";cache.mkdir()
        envkeys=["PYTHONDONTWRITEBYTECODE","MPLCONFIGDIR","XDG_CACHE_HOME"]
        saved_env={k:os.environ.get(k) for k in envkeys}
        os.environ.update(PYTHONDONTWRITEBYTECODE="1",MPLCONFIGDIR=str(cache),XDG_CACHE_HOME=str(cache))
        try:
            claims=build_claims()
            output_text("reports/11_claim_registry.csv",csv_string(claims))
            output_text("reports/11_paper_synthesis.md",INITIAL_PLAN)
            tcaps=tables_materials()
            captions=draft_materials()
            figures_materials()
            verify_materials(claims)
            versions={"sys.executable":sys.executable,"Python":sys.version.split()[0],
                      "matplotlib":metadata.version("matplotlib"),"numpy":metadata.version("numpy"),
                      "backend":"Agg","scope":"this process / installed package metadata; no fresh-machine replication"}
            commands=reproducibility(inputs,versions)
            review={"status":"pending_actual_open","width_mm":180,"figures":{}}
            newfigsha={f:sha(outpath(f)) for f in OUTPUTS if f.endswith(".png")}
            if old and old.get("visual_review",{}).get("figures")==newfigsha:
                review=dict(old["visual_review"])
                if review.get("acronym_check",{}).get("draft_sha256")!=sha(outpath("paper/11_draft/results_discussion.md")):
                    review.pop("acronym_check",None)
            synthesis(claims,inputs,versions,review)
            check_inputs()
            preflight(args.overwrite)
            output_info={p:{"sha256":sha(outpath(p)),"bytes":outpath(p).stat().st_size} for p in OUTPUTS}
            manifest={"stage":11,"schema_version":"1.0","command":PYTHON+" -B "+str(W/SCRIPT)+(" --overwrite" if args.overwrite else ""),
                "regenerate_command":PYTHON+" -B "+str(W/SCRIPT)+" --overwrite","script_sha256":sha(safe(SCRIPT)),
                "editorial_review_helper_sha256":sha(safe("scripts/claim_review_support.py")),
                "editorial_review_applied":bool(reviewed_patch(W)),
                "inputs":inputs,"claim_ids":[c["claim_id"] for c in claims],
                "adopted_main_claim_ids":[c["claim_id"] for c in claims if c["placement"]=="main_text_candidate"],
                "core_observation_groups":["O1","O2","O3","O4"],"row_sources":ROW_SOURCES,"displays":DISPLAY,
                "paragraphs":PARAGRAPHS,"figure_captions":captions,"table_captions":dict(zip(["tab:s11-coverage","tab:s11-pair-patterns"],tcaps)),
                "material_sources":{"fig:s11-orb-response":[J8,S9],"fig:s11-dpvo-composition":[S9,B9],
                                    "fig:s11-hier-association":[T10,E9],"tab:s11-coverage":[D7,S7,M6,A10],
                                    "tab:s11-pair-patterns":[P10,Q10]},
                "historical_commands":commands,"versions":versions,"checks":CHECKS,"visual_review":review,
                "initial_acceptance":old.get("initial_acceptance",{}) if old else {},
                "consulted_context_snapshots":old.get("consulted_context_snapshots",{}) if old else {},
                "outputs":output_info,"self_hash":"intentionally omitted; no self-referential final hash"}
            for p in OUTPUTS:
                dest=safe(p);dest.parent.mkdir(parents=True,exist_ok=True);os.replace(outpath(p),dest)
            mp=safe(MANIFEST);mp.parent.mkdir(parents=True,exist_ok=True)
            mp.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
            print(js({"claims":len(claims),"paragraphs":len(PARAGRAPHS),"source_rows":len(ROW_SOURCES),
                      "display_entries":len(DISPLAY),"outputs":len(OUTPUTS)+1,"checks":CHECKS,"visual_review":review}))
        finally:
            STAGING=None
            for k,v in saved_env.items():
                if v is None:os.environ.pop(k,None)
                else:os.environ[k]=v

if __name__=="__main__":
    try:main()
    except (ValueError,AssertionError,KeyError) as exc:
        print("STOP: "+str(exc),file=sys.stderr);sys.exit(1)
