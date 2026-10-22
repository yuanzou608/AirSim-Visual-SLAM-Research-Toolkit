"""Step 11C taxonomy: a pure display/metadata mapping, never a source-data edit.

Only build_taxonomy(manifest_rows) is needed by the entry point.  The explicit
method taxonomy and two semantic RGB-D configurations come from the user's
11C instructions; historical audit fields are kept alongside current labels.
No file I/O, network, statistical aggregation, or family performance ranking.
"""
import json
from collections import Counter

INPUT_GROUP_ORDER = ("Mono", "RGB-D", "RGB-D + Semantic", "Unknown")
FAMILY_ORDER = (
    "Traditional", "Learning-based", "3DGS", "Feedforward",
    "3DGS & Semantic-enhanced", "Semantic-enhanced",
)
INPUT_GROUP_CODES = {"Mono": "M", "RGB-D": "D", "RGB-D + Semantic": "DS", "Unknown": "U"}
FAMILY_CODES = {
    "Traditional": "TRAD", "Learning-based": "LEARN", "3DGS": "3DGS",
    "Feedforward": "FF", "3DGS & Semantic-enhanced": "3DGS+SEM",
    "Semantic-enhanced": "SEM",
}
# Keys are unchanged source method directories, not inferred algorithm families.
METHOD_FAMILY = {
    "ORB-SLAM2": "Traditional", "ORB-SLAM3": "Traditional",
    "ElasticFusion": "Traditional", "SVO": "Traditional", "DSO": "Traditional",
    "DROID-SLAM": "Learning-based", "DPVO": "Learning-based", "TartanVO": "Learning-based",
    "Photo-slam": "3DGS", "MongGS": "3DGS", "SplaTAM": "3DGS",
    "hierslam": "3DGS & Semantic-enhanced",
    "MASt3R-SLAM": "Feedforward", "VGGT-SLAM": "Feedforward",
    "VGGT-LONG": "Feedforward", "SLAM3R": "Feedforward",
    "SGS-SLAM": "Semantic-enhanced",
}
# MongGS spelling is explicitly corrected for NEW displays by the user.
# README maps the Hier-SLAM name to the hierslam directory and the stage-11
# figure already uses Hier-SLAM.  No equivalent formal Photo-slam display
# mapping was found in the bounded inspection; its source spelling is retained.
METHOD_DISPLAY_NAMES = {"MongGS": "MonoGS", "hierslam": "Hier-SLAM"}
SEMANTIC_CONFIGURATIONS = frozenset(("SGS-SLAM::semantic", "hierslam::semantic_500"))
USER_RGBD_NO_SEMANTIC_CONFIGURATIONS = frozenset(("hierslam::rgbd_500", "hierslam::rgbd_whole"))
MAST3R_CONFIGURATIONS = frozenset(("MASt3R-SLAM::mono_calib", "MASt3R-SLAM::mono_nocalib"))
MANIFEST = "derived_data/06_standardized/source_manifest.csv"
TASK_EVIDENCE = (
    "/home/yuan/.codex/attachments/72319604-42f1-4cca-abd6-d598a6b94640/"
    "Pasted text.txt"
)
LATEST_SEMANTIC_EVIDENCE = "user_confirmed:11C_latest_semantic_input_clarification"
LATEST_MAST3R_EVIDENCE = "user_confirmed:11C_MASt3R_mono_clarification"
BASE_MODALITY_MAP = {"mono": "mono", "RGB + Depth": "rgbd", "unknown": "unknown"}
VARIANT_LABELS = {
    "mono": ("Mono", "Mono"),
    "rgbd": ("RGB-D", "RGB-D"),
    "mono_calib": ("Mono calib", "Mono calib"),
    "mono_nocalib": ("Mono nocalib", "Mono nocalib"),
    "rgbd_500": ("RGB-D 500 frames", "RGB-D 500"),
    "rgbd_whole": ("RGB-D whole trajectory", "RGB-D whole"),
    "semantic": ("RGB-D + Semantic", "D+S"),
    "semantic_500": ("RGB-D + Semantic 500 frames", "D+S 500"),
}

def _js(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False, separators=(",", ":"))

def _display_name_evidence(method):
    if method == "MongGS":
        return "user_confirmed:11C explicit MongGS -> MonoGS display-only spelling correction"
    if method == "hierslam":
        return (
            "existing_project_mapping: README.md#固定路径与读写边界 identifies the Hier-SLAM method directory as hierslam; "
            "scripts/build_paper_materials.py figure title: Hier-SLAM whole trajectory"
        )
    return "source_method_directory preserved; no additional display rename asserted"

def build_taxonomy(manifest_rows):
    """Return exactly 24 rows sorted by declared metadata, with row_order 1..24.

    The rows contain both the source-audit values and the latest user-confirmed
    semantic and MASt3R modality confirmations.  Historical source values remain
    separate; the explicit user confirmation supplies the current plot group.
    """
    if len(manifest_rows) != 24:
        raise ValueError("Step 11C expects the frozen manifest's 24 configurations")
    ids = [m["configuration_id"] for m in manifest_rows]
    if len(set(ids)) != 24:
        raise ValueError("Duplicate configuration_id in taxonomy input")
    methods = {m["method_directory"] for m in manifest_rows}
    if methods != set(METHOD_FAMILY):
        raise ValueError("Source methods differ from the explicit 17-method taxonomy")
    if not SEMANTIC_CONFIGURATIONS | USER_RGBD_NO_SEMANTIC_CONFIGURATIONS | MAST3R_CONFIGURATIONS <= set(ids):
        raise ValueError("Required user-confirmed configurations are absent")

    rows = []
    for m in manifest_rows:
        c, source_method, variant = m["configuration_id"], m["method_directory"], m["configuration"]
        if c != source_method + "::" + variant:
            raise ValueError("Source configuration identity mismatch: " + c)
        if variant not in VARIANT_LABELS:
            raise ValueError("Unreviewed configuration variant: " + variant)
        old_modality = m["modality_declared"]
        if old_modality not in BASE_MODALITY_MAP:
            raise ValueError("Unreviewed source modality label: " + old_modality)
        base = BASE_MODALITY_MAP[old_modality]
        semantic = "yes" if c in SEMANTIC_CONFIGURATIONS else "no"
        ref = MANIFEST + "#configuration_id=" + c
        modality_evidence = m["modality_evidence"] + ": " + ref + ".modality_declared"
        modality_status = "source_audit_unresolved" if base == "unknown" else m["modality_evidence"]
        notes = [
            "Display mapping does not edit source IDs or bytes; paths, scope and retained-run metadata follow the supplied current frozen manifest. Prior versions remain in their version archive.",
            "Method-level family is user-provided taxonomy for ordering/annotation, not independent support votes or a family performance result.",
        ]
        if c in SEMANTIC_CONFIGURATIONS:
            base = "rgbd"
            modality_evidence = LATEST_SEMANTIC_EVIDENCE + ": RGB-D inputs with semantic information, explicitly confirmed for this configuration"
            modality_status = "user_confirmed"
            notes.append("RGB-D + Semantic preserves the depth input; semantic use is not a depth-absence claim.")
        elif c in USER_RGBD_NO_SEMANTIC_CONFIGURATIONS:
            base = "rgbd"
            modality_evidence = LATEST_SEMANTIC_EVIDENCE + ": Hier-SLAM rgbd_500/rgbd_whole are RGB-D without semantic information; matches " + ref
            modality_status = "user_confirmed"
        if c in MAST3R_CONFIGURATIONS:
            base = "mono"
            modality_evidence = LATEST_MAST3R_EVIDENCE + ": MASt3R-SLAM input is mono; applies to current calib and nocalib configurations; historical source audit retained separately"
            modality_status = "user_confirmed"
        group = "RGB-D + Semantic" if semantic == "yes" else "Mono" if base == "mono" else "RGB-D" if base == "rgbd" else "Unknown"
        method_display = METHOD_DISPLAY_NAMES.get(source_method, source_method)
        full_variant, short_variant = VARIANT_LABELS[variant]
        paper_modality = "mono" if c in MAST3R_CONFIGURATIONS else "not_separately_asserted"
        paper_evidence = (
            "user-provided 11C expected display order places MASt3R calib/nocalib under MONO; "
            "method-level paper capability only, not source/configuration verification"
            if c in MAST3R_CONFIGURATIONS else "not_used_to_fill_source_metadata"
        )
        calibration = "calib" if c == "MASt3R-SLAM::mono_calib" else "nocalib" if c == "MASt3R-SLAM::mono_nocalib" else "not_applicable"
        if c in MAST3R_CONFIGURATIONS:
            notes.append("Current Mono input is explicitly user-confirmed for both variants. source_modality_declared records the supplied manifest value; earlier unknown audit values remain in the version archive. Plot grouping follows the explicit confirmation, not paper capability alone.")
            notes.append("calib/nocalib are retained configuration labels; actual upstream calibration details remain unresolved.")
        if source_method == "Photo-slam":
            notes.append("Photo-slam spelling retained: bounded checks of README and stage-11 display code found no explicit formal display-name mapping; family assignment is the user's Photo-SLAM taxonomy entry.")
        if source_method == "MongGS":
            notes.append("Display MonoGS is user-confirmed; source_method_directory/configuration_id/source_relative_path retain MongGS.")
        if source_method == "hierslam":
            notes.append("500-frame and whole-trajectory configurations remain separate; scope labels do not assert that every retained run completed the full configured trajectory.")
        if m["evaluation_scope"] == "unknown":
            notes.append("Evaluation scope remains unknown; neither scope nor historical units/alignment are inferred from the family.")
        row = {
            "configuration_id": c,
            "source_method_directory": source_method,
            "source_configuration": variant,
            "source_relative_path": m["source_relative_path"],
            "source_sha256": m["source_sha256"],
            "method_display_name": method_display,
            "configuration_display_name": method_display + " " + full_variant,
            "caption_short_name": method_display + " " + short_variant,
            "configuration_variant": variant,
            "base_modality": base,
            "semantic_usage": semantic,
            "display_input_group": group,
            "input_group_code": INPUT_GROUP_CODES[group],
            "algorithm_family": METHOD_FAMILY[source_method],
            "family_code": FAMILY_CODES[METHOD_FAMILY[source_method]],
            "evaluation_scope": m["evaluation_scope"],
            "evaluation_scope_evidence": m["evaluation_scope_evidence"] + ": " + ref + ".evaluation_scope",
            "calibration_variant": calibration,
            "calibration_evidence": ref + ".configuration (label only)" if c in MAST3R_CONFIGURATIONS else "not_applicable",
            "taxonomy_evidence": "user_provided_method_level_taxonomy: " + TASK_EVIDENCE + "#3.3; inherited by configurations of the same unchanged source method",
            "modality_evidence": modality_evidence,
            "modality_evidence_status": modality_status,
            "semantic_evidence": LATEST_SEMANTIC_EVIDENCE + ": only SGS-SLAM::semantic and hierslam::semantic_500 use semantic information; all other 22 configurations do not",
            "semantic_evidence_status": "user_confirmed",
            "display_name_evidence": _display_name_evidence(source_method),
            "paper_reported_modality": paper_modality,
            "paper_reported_modality_evidence": paper_evidence,
            "paper_reported_modality_used_for_sorting": False,
            "display_qualifier": "*" if base == "unknown" else "",
            "source_modality_declared": old_modality,
            "source_modality_evidence": m["modality_evidence"],
            "source_semantic_usage": m["semantic_usage"],
            "source_semantic_evidence": m["semantic_evidence"],
            "source_evaluation_scope": m["evaluation_scope"],
            "source_evidence_reference": m["source_evidence_reference"],
            "metadata_evidence_json": _js({
                "source": {"table": MANIFEST, "key": {"configuration_id": c},
                           "fields": ["method_directory", "configuration", "modality_declared", "modality_evidence",
                                      "semantic_usage", "semantic_evidence", "evaluation_scope", "source_relative_path"]},
                "new_user_confirmation": LATEST_SEMANTIC_EVIDENCE,
                "modality_user_confirmation": LATEST_MAST3R_EVIDENCE if c in MAST3R_CONFIGURATIONS else LATEST_SEMANTIC_EVIDENCE if c in SEMANTIC_CONFIGURATIONS | USER_RGBD_NO_SEMANTIC_CONFIGURATIONS else "not_separately_asserted",
                "method_taxonomy": TASK_EVIDENCE + "#3.3",
                "display_name": _display_name_evidence(source_method),
            }),
            "notes": " ".join(notes),
        }
        rows.append(row)
    rows.sort(key=lambda r: (INPUT_GROUP_ORDER.index(r["display_input_group"]),
                            FAMILY_ORDER.index(r["algorithm_family"]),
                            r["method_display_name"].casefold(), r["configuration_variant"]))
    for order, r in enumerate(rows, 1):
        r["row_order"] = order
        r["row_order_basis"] = "input_group_order;family_order;method_display_name.casefold;configuration_variant;never performance values"
    counts = Counter(r["display_input_group"] for r in rows)
    if counts != {"Mono": 14, "RGB-D": 8, "RGB-D + Semantic": 2}:
        raise ValueError("Unexpected frozen taxonomy group counts: " + repr(counts))
    if {r["configuration_id"] for r in rows if r["semantic_usage"] == "yes"} != SEMANTIC_CONFIGURATIONS:
        raise ValueError("Semantic configuration set changed")
    if any(r["source_evaluation_scope"] != r["evaluation_scope"] for r in rows):
        raise ValueError("Scope altered")
    return rows
