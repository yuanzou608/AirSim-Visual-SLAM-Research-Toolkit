"""Step 11B rendering only: consume frozen existing numerical rows.

No source-directory access, no analysis entry point, no recomputation of
statistical estimates. The caller owns snapshots, output guards and caches.
"""
from pathlib import Path
import json
import math

SCENES = ("building", "houses", "pool", "road", "roundabout")
HEIGHTS = (10, 20, 30)
SPEEDS = (2, 4, 8)
SCENE_SHORT = ("bld", "house", "pool", "road", "round")
SPECIAL = {
    "DROID-SLAM::rgbd", "ElasticFusion::rgbd",
    "SLAM3R::mono", "VGGT-LONG::mono",
}
COLORS = ("#0072B2", "#D55E00", "#009E73")
MARKERS = ("o", "s", "^")
STYLES = ("-", "--", ":")


def _number(row, key):
    value = row.get(key, "") if row else ""
    try:
        v = float(value)
        return v if math.isfinite(v) else math.nan
    except (TypeError, ValueError):
        return math.nan


def _count(row, key):
    v = _number(row, key)
    return str(int(v)) if math.isfinite(v) else "?"


def _fmt(value, digits=3):
    return format(value, "." + str(digits) + "g") if math.isfinite(value) else "NA"


def _scope(config, manifests):
    return manifests[config].get("evaluation_scope", "unknown")


def _splatam_external_m(config, manifests):
    row = manifests[config]
    return ((config == "SGS-SLAM::semantic" and __import__("version_support").sgs_external_ape_verified(row)) or (config == "SplaTAM::rgbd" and
            row.get("source_sha256") == "337a4d462b9d238681be52284017b3e3ef445130303911de1cc1601a6d9c8f7b" and
            "Sim(3)" in row.get("alignment_status", "") and
            "/100" not in row.get("rmse_unit_status", "") and
            "unverified" not in row.get("rmse_unit_status", "").lower()))


def _limits(values, zero=True):
    finite = [x for x in values if math.isfinite(x)]
    if not finite:
        return (0.0, 1.0)
    low, high = min(finite), max(finite)
    if zero:
        low, high = min(0.0, low), max(0.0, high)
    width = high - low
    if width == 0:
        width = max(abs(high) * .05, 1e-8)
    return low - .045 * width, high + .10 * width


def _save(fig, output_dir, basename, configurations, topics, caption, results, plt):
    png, svg = basename + ".png", basename + ".svg"
    fig.savefig(output_dir / png, dpi=105, facecolor="white",
                metadata={"Software": "benchmark_analysis step11b"})
    fig.savefig(output_dir / svg, facecolor="white",
                metadata={"Date": None})
    plt.close(fig)
    results.append({"basename": basename, "png": png, "svg": svg,
                    "configuration_ids": list(configurations),
                    "topics": list(topics), "caption": caption})


def render_all(output_dir, configs, manifests, joint, summaries, sequences,
               sequence_order, sensitivity, within_rows):
    """Render 48 condition pages and 12 four-configuration topic pages.

    sequence_order is a stable list of (scene, H, V, sequence_raw), and indices
    displayed here are 1-based, matching the caller's sequence_index.csv.
    """
    import numpy as np
    import matplotlib
    matplotlib.use("Agg", force=True)
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle
    from matplotlib.lines import Line2D

    output_dir = Path(output_dir)
    if len(configs) != 24 or len(set(configs)) != 24:
        raise ValueError("The atlas requires exactly 24 distinct configurations")
    if not output_dir.is_dir():
        raise ValueError("Caller must create the guarded output directory")
    for idx in range(1, 25):
        for suffix in ("grid", "response"):
            for ext in ("png", "svg"):
                if (output_dir / f"c{idx:02d}_{suffix}.{ext}").exists():
                    raise FileExistsError("Renderer never overwrites existing images")
    for idx in range(1, 7):
        for prefix in ("distribution_repeat", "composition_efficiency"):
            for ext in ("png", "svg"):
                if (output_dir / f"{prefix}_p{idx:02d}.{ext}").exists():
                    raise FileExistsError("Renderer never overwrites existing images")

    names = [r[3] for r in sequence_order]
    if len(names) != 44 or len(set(names)) != 44:
        raise ValueError("Stable primary sequence index must contain 44 unique names")
    xs = np.arange(1, len(names) + 1)
    rho_rows = {(r["configuration_id"], r["efficiency_metric"], r["scene"]): r
                for r in within_rows if r["row_type"] == "rank_correlation"}
    results = []
    with plt.rc_context({"font.size": 9, "axes.titlesize": 10,
                         "axes.labelsize": 9, "xtick.labelsize": 8,
                         "ytick.labelsize": 8, "legend.fontsize": 8,
                         "svg.hashsalt": "benchmark-analysis-11b",
                         "axes.spines.top": False,
                         "axes.spines.right": False}):
        for ci, config in enumerate(configs, 1):
            rows = [joint[(config, s, h, v)]
                    for s in SCENES for h in HEIGHTS for v in SPEEDS]
            values = [_number(r, "mean") for r in rows]
            finite = [v for v in values if math.isfinite(v)]
            vmax = max(finite) if finite else 1.0
            vmax = vmax if vmax > 0 else 1.0
            vmin = min(0.0, min(finite)) if finite else 0.0
            scope = _scope(config, manifests)
            splatam_m = _splatam_external_m(config, manifests)
            rmse_axis = "RMSE (m)" if splatam_m else "RMSE source units"

            fig, axes = plt.subplots(2, 5, figsize=(16, 6.4))
            fig.subplots_adjust(left=.047, right=.926, top=.82,
                                bottom=.15, wspace=.29, hspace=.40)
            fig.suptitle(f"{ci:02d}  {config}  |  scope={scope}\n"
                         "Five-scene condition grids | RMSE sequence means and finite-record coverage",
                         fontsize=13, y=.968)
            mappables = []
            for ri, field in enumerate(("mean", "finite_fraction")):
                image = None
                for sj, scene in enumerate(SCENES):
                    ax = axes[ri, sj]
                    array = np.array([[_number(joint[(config, scene, h, v)], field)
                                       for v in SPEEDS] for h in HEIGHTS])
                    cmap = plt.get_cmap("viridis" if ri == 0 else "Blues").copy()
                    cmap.set_bad("#fff2df")
                    image = ax.imshow(np.ma.masked_invalid(array), aspect="auto",
                                      origin="lower", cmap=cmap,
                                      vmin=vmin if ri == 0 else 0,
                                      vmax=vmax if ri == 0 else 1)
                    for hi, h in enumerate(HEIGHTS):
                        for vi, v in enumerate(SPEEDS):
                            row = joint[(config, scene, h, v)]
                            state = row["cell_state"]
                            value = _number(row, field)
                            label = _fmt(value)
                            if state == "no_retained_records":
                                ax.add_patch(Rectangle((vi - .5, hi - .5), 1, 1,
                                                       facecolor="#dddddd", edgecolor="#777777",
                                                       hatch="///", lw=.4))
                                label = "NR"
                            elif state == "observed_all_nonfinite":
                                label = "NA" if ri == 0 else "0 (NA)"
                                ax.add_patch(Rectangle((vi - .5, hi - .5), 1, 1,
                                                       fill=False, edgecolor="#b54b00",
                                                       lw=1.3, hatch="xx"))
                            text = (label + "\nR " + _count(row, "n_finite_records") + "/" +
                                    _count(row, "n_retained_records") + "\nS " +
                                    _count(row, "n_sequences_with_finite") + "/" +
                                    _count(row, "n_observed_sequences"))
                            fraction = ((value - vmin) / (vmax - vmin)
                                        if ri == 0 and math.isfinite(value) else value)
                            white = (math.isfinite(fraction) and
                                     (fraction < .36 if ri == 0 else fraction > .58))
                            color = "white" if white and state not in (
                                "no_retained_records", "observed_all_nonfinite") else "#171717"
                            ax.text(vi, hi, text, ha="center", va="center",
                                    fontsize=7.4, color=color, linespacing=1.04)
                    ax.set_xticks(range(3), SPEEDS)
                    ax.set_yticks(range(3), HEIGHTS)
                    ax.set_title(scene + (" | RMSE" if ri == 0 else " | finite fraction"))
                    ax.set_xlabel("Nominal speed (m/s)")
                    if sj == 0:
                        ax.set_ylabel("Nominal height (m)")
                mappables.append(image)
            for ri, image in enumerate(mappables):
                cax = fig.add_axes([.943, .515 if ri == 0 else .153, .013, .295])
                fig.colorbar(image, cax=cax)
                cax.set_ylabel(rmse_axis if ri == 0 else "Finite / retained runs",
                               fontsize=8)
            fig.text(.05, .062,
                     "R = finite / retained runs; S = sequences with finite RMSE / observed sequences. "
                     "NR = no records; NA = records but no finite RMSE.\n"
                     "Within this configuration only: shared RMSE color scale across five scenes. "
                     "Finite fractions use [0, 1]; no trajectory-success interpretation. " +
                     ("Audited external evo APE RMSE (m), Sim(3)." if splatam_m else
                      "Units / historical protocol not harmonized."),
                     fontsize=8, va="center")
            _save(fig, output_dir, f"c{ci:02d}_grid", [config],
                  ["condition_grid", "finite_coverage"],
                  "Five scenes × nominal H10/20/30 and V2/4/8. Existing equal-sequence means; "
                  "R and S retain original denominators. NR differs from all-nonfinite NA. "
                  f"scope={scope}; {rmse_axis}, no cross-configuration color ranking.",
                  results, plt)

            fig, axes = plt.subplots(2, 5, figsize=(16, 6.4), sharey=True)
            fig.subplots_adjust(left=.06, right=.985, top=.77,
                                bottom=.19, wspace=.23, hspace=.46)
            fig.suptitle(f"{ci:02d}  {config}  |  scope={scope}\n"
                         "Condition responses: all intermediate levels retained", fontsize=13, y=.97)
            for sj, scene in enumerate(SCENES):
                for k, h in enumerate(HEIGHTS):
                    ys = [_number(joint[(config, scene, h, v)], "mean") for v in SPEEDS]
                    axes[0, sj].plot(SPEEDS, ys, color=COLORS[k], marker=MARKERS[k],
                                     ls=STYLES[k], ms=4, lw=1.3)
                for k, v in enumerate(SPEEDS):
                    ys = [_number(joint[(config, scene, h, v)], "mean") for h in HEIGHTS]
                    axes[1, sj].plot(HEIGHTS, ys, color=COLORS[k], marker=MARKERS[k],
                                     ls=STYLES[k], ms=4, lw=1.3)
                for ri in (0, 1):
                    ax = axes[ri, sj]
                    ax.set_title(scene)
                    ax.set_ylim(*_limits(values))
                    ax.grid(alpha=.22)
                    ax.set_xticks(SPEEDS if ri == 0 else HEIGHTS)
                    ax.set_xlabel("Nominal speed (m/s)" if ri == 0 else "Nominal height (m)")
                if sj == 0:
                    axes[0, sj].set_ylabel(rmse_axis)
                    axes[1, sj].set_ylabel(rmse_axis)
            handles = [Line2D([0], [0], color=COLORS[k], marker=MARKERS[k],
                              ls=STYLES[k], label=f"Upper: H{HEIGHTS[k]} m; lower: V{SPEEDS[k]} m/s")
                       for k in range(3)]
            fig.legend(handles=handles, loc="upper center", bbox_to_anchor=(.52, .865),
                       ncol=3, frameon=False)
            fig.text(.06, .047,
                     "Existing sequence-equal RMSE means; same full-range y-axis for all five scenes. "
                     "Missing values break lines, with no interpolation or zero filling.\n" +
                     ("Nominal mapping follows metadata; audited external evo APE RMSE (m), Sim(3). " if splatam_m else
                      "Nominal condition mapping follows existing metadata; source units / historical protocol unresolved. ") +
                     "See companion grid for every run and sequence denominator.",
                     fontsize=8)
            _save(fig, output_dir, f"c{ci:02d}_response", [config],
                  ["speed_response", "altitude_response"],
                  "All five scenes, three heights and three speeds. Existing mean values, "
                  "missing points interrupt lines. One configuration-wide y range; no endpoint-only monotonicity claim. "
                  f"scope={scope}; " + ("ATE RMSE (m), external evo Sim(3)." if splatam_m else "source units."),
                  results, plt)

        for page in range(6):
            group = configs[4 * page:4 * page + 4]
            fig, axes = plt.subplots(4, 3, figsize=(16, 12.5))
            fig.subplots_adjust(left=.057, right=.985, top=.928,
                                bottom=.15, wspace=.26, hspace=.68)
            fig.suptitle(f"Sequence distributions and retained repeats | page {page + 1}/6",
                         fontsize=14, y=.984)
            for ri, config in enumerate(group):
                summary = summaries[(config, "__all__")]
                scope = _scope(config, manifests)
                splatam_m = _splatam_external_m(config, manifests)
                vals = sorted(_number(sequences.get((config, name)), "mean") for name in names
                              if math.isfinite(_number(sequences.get((config, name)), "mean")))
                ax = axes[ri, 0]
                if vals:
                    ax.step([vals[0]] + vals, [0] + [(i + 1) / len(vals) for i in range(len(vals))],
                            where="post", color="#333333", lw=1.5)
                for key, color, style in (("mean", COLORS[0], "-"),
                                          ("median", COLORS[1], "--"), ("p90", COLORS[2], ":")):
                    value = _number(summary, key)
                    if math.isfinite(value):
                        ax.axvline(value, color=color, ls=style, lw=1.2,
                                   label=key + "=" + _fmt(value))
                ax.legend(loc="lower right", fontsize=7, framealpha=.85)
                ax.set_ylim(0, 1.04)
                ax.set_xlabel("Sequence-mean RMSE (m)" if splatam_m else "Sequence-mean RMSE (source units)")
                ax.set_ylabel("Empirical fraction")
                ax.set_title(config + " | " + scope + "\nS " +
                             _count(summary, "n_sequences_with_finite") + "/" +
                             _count(summary, "n_observed_sequences"), fontsize=9)
                ax.grid(alpha=.2)
                ax = axes[ri, 1]
                means, sd_values = [], []
                absent, all_na, sd_undefined, sd_estimable = [], [], 0, 0
                for ix, name in zip(xs, names):
                    row = sequences.get((config, name))
                    if row is None:
                        absent.append(ix)
                        means.append(math.nan)
                        sd_values.append(math.nan)
                        continue
                    finite_values = json.loads(row["finite_values_json"])
                    if finite_values:
                        shifts = np.linspace(-.17, .17, len(finite_values)) if len(finite_values) > 1 else [0]
                        ax.scatter([ix + d for d in shifts], finite_values,
                                   s=10, marker="o", color="#777777", alpha=.74, zorder=3)
                    else:
                        all_na.append(ix)
                    means.append(_number(row, "mean"))
                    sd = _number(row, "repeat_sd")
                    sd_values.append(sd)
                    sd_estimable += int(math.isfinite(sd))
                    sd_undefined += int(not math.isfinite(sd))
                    sr = sensitivity.get(config + "|" + name + "|sequence_variant_range|drop_one")
                    if sr and math.isfinite(_number(sr, "range_min")):
                        ax.vlines(ix, _number(sr, "range_min"), _number(sr, "range_max"),
                                  color=COLORS[1], lw=1.5, zorder=2)
                ax.plot(xs, means, ls="none", marker="_", ms=7, color=COLORS[0], zorder=4)
                for positions, marker, color in ((absent, "|", "#222222"),
                                                 (all_na, "x", "#b54b00")):
                    if positions:
                        ax.scatter(positions, [.025] * len(positions), transform=ax.get_xaxis_transform(),
                                   marker=marker, color=color, s=25, clip_on=False)
                ax.set_title("All finite runs / mean / leave-one mean range", fontsize=9)
                ax.set_xlim(.25, 44.75)
                ax.set_xticks([1, 9, 18, 27, 36, 44])
                ax.set_xlabel("Sequence index (sequence_index.csv)")
                ax.set_ylabel("RMSE (m)" if splatam_m else "RMSE source units")
                ax.grid(alpha=.18)
                ax = axes[ri, 2]
                finite_sd_x = [x for x, v in zip(xs, sd_values) if math.isfinite(v)]
                finite_sd_y = [v for v in sd_values if math.isfinite(v)]
                if finite_sd_y:
                    ax.scatter(finite_sd_x, finite_sd_y, s=16, marker="s", color=COLORS[2])
                for x, row_sd, name in zip(xs, sd_values, names):
                    if not math.isfinite(row_sd) and (config, name) in sequences:
                        ax.plot(x, .035, marker="x", color="#b54b00", ms=4,
                                transform=ax.get_xaxis_transform())
                if absent:
                    ax.scatter(absent, [.025] * len(absent), marker="|", color="#222222",
                               transform=ax.get_xaxis_transform(), s=25)
                ax.set_title(f"Repeat SD: defined {sd_estimable}; undefined {sd_undefined}; "
                             f"no record {len(absent)}", fontsize=9)
                ax.set_xlim(.25, 44.75)
                ax.set_xticks([1, 9, 18, 27, 36, 44])
                ax.set_xlabel("Sequence index")
                ax.set_ylabel("Within-sequence SD (m; ddof=1)" if splatam_m else "Within-sequence SD (ddof=1)")
                if not finite_sd_y or max(finite_sd_y) == 0:
                    ax.set_ylim(-.02, .12)
                    ax.text(.02, .9, "No positive estimated repeat SD",
                            transform=ax.transAxes, fontsize=7)
                ax.grid(alpha=.18)
                if config in SPECIAL:
                    ax.text(.02, .83, "Identical error repeats; tiny stored SD = roundoff",
                            transform=ax.transAxes, fontsize=7, color="#8b3100")
                    ax.text(.02, .72, "Numerical residue is not observed repeat variation",
                            transform=ax.transAxes, fontsize=7, color="#8b3100")
                    ax.text(.02, .61, "Repeat provenance remains unresolved",
                            transform=ax.transAxes, fontsize=7, color="#8b3100")
            fig.text(.057, .027,
                     "Middle: gray dots = actual finite retained runs; blue ticks = existing sequence means; "
                     "orange vertical ranges = checked leave-one means (not CI).\n"
                     "Right: crosses in the bottom status band = undefined SD (<2 finite runs), not zero; "
                     "vertical status marks = no records. Middle crosses = all-nonfinite sequence.\n"
                     "Condition-labelled records only. Repeated equal error values do not prove independent stability. "
                     "Each configuration has its own RMSE/source scale; no absolute ranking.",
                     fontsize=8)
            _save(fig, output_dir, f"distribution_repeat_p{page + 1:02d}", group,
                  ["distribution", "actual_repeats", "repeat_sd", "sequence_leave_one"],
                  "Four configurations per page, stable 44-sequence index. ECDF of existing means with stored "
                  "mean/median/p90; every finite repeat; original mean, original leave-one range and ddof=1 SD. "
                  "Undefined SD/status marks are not numeric zeros. For four flagged equal-error configurations, "
                  "tiny stored SD roundoff is numerical residue, not observed repeat variation; provenance unresolved.",
                  results, plt)

            fig, axes = plt.subplots(4, 3, figsize=(16, 13))
            fig.subplots_adjust(left=.058, right=.97, top=.925,
                                bottom=.15, wspace=.31, hspace=.88)
            fig.suptitle(f"Composition sensitivity and within-configuration relations | page {page + 1}/6",
                         fontsize=14, y=.984)
            for ri, config in enumerate(group):
                ax = axes[ri, 0]
                labels = ["V0", "V1", "V2", "V3", "V4"] + ["-" + s for s in SCENE_SHORT]
                title_counts = []
                for k, comparison in enumerate(("speed8_minus2", "altitude30_minus10")):
                    view_rows = [sensitivity.get(config + "|" + comparison + "|support_view|V" + str(v))
                                 for v in range(5)]
                    view_rows += [sensitivity.get(config + "|" + comparison +
                                  "|leave_one_scene_out|V1 minus " + scene) for scene in SCENES]
                    y = [_number(row, "value") for row in view_rows]
                    ax.plot(range(10), y, color=COLORS[k], marker=MARKERS[k],
                            ls=STYLES[k], lw=1.2, ms=4,
                            label="Speed 8-2" if k == 0 else "Height 30-10")
                    baseline = view_rows[1]
                    title_counts.append(("speed" if k == 0 else "height") + " F=" +
                                        _count(baseline, "n_F"))
                    for xx, yy in enumerate(y):
                        if not math.isfinite(yy):
                            ax.text(xx, .02 + .09 * k, "NA", fontsize=6, rotation=90,
                                    transform=ax.get_xaxis_transform(), ha="center")
                ax.axhline(0, color="#666666", lw=.7)
                ax.set_xticks(range(10), labels, rotation=40, ha="right")
                ax.set_ylabel("RMSE difference (m)" if _splatam_external_m(config, manifests) else "RMSE difference (source units)")
                ax.set_title(config + " | " + _scope(config, manifests) + "\n" +
                             "; ".join(title_counts) + " blocks", fontsize=9)
                ax.legend(loc="best", fontsize=7, framealpha=.7)
                ax.grid(alpha=.2)
                ax = axes[ri, 1]
                for k, comparison in enumerate(("speed8_minus2", "altitude30_minus10")):
                    rows = [sensitivity.get(config + "|" + comparison +
                            "|scene_contribution|V1 " + scene) for scene in SCENES]
                    ys = [_number(row, "value") for row in rows]
                    x = np.arange(5) + (-.2 if k == 0 else .2)
                    ax.bar(x, ys, width=.36, color=COLORS[k], alpha=.78,
                           hatch="//" if k == 0 else "..",
                           label="Speed" if k == 0 else "Height")
                    for xx, yy, row in zip(x, ys, rows):
                        if math.isfinite(yy):
                            ax.annotate("n=" + _count(row, "n_blocks"), (xx, yy),
                                        xytext=(0, 3 if yy >= 0 else -3),
                                        textcoords="offset points", ha="center",
                                        va="bottom" if yy >= 0 else "top", fontsize=6.3)
                        else:
                            ax.text(xx, .02 + .075 * k, "NA", fontsize=6,
                                    transform=ax.get_xaxis_transform(), ha="center")
                ax.axhline(0, color="#666666", lw=.7)
                ax.set_xticks(range(5), SCENE_SHORT)
                ax.set_title("Five scene contributions to full-F V1", fontsize=9)
                ax.set_ylabel("Additive RMSE contribution")
                ax.margins(y=.24)
                ax.legend(loc="best", fontsize=7, framealpha=.75)
                ax.grid(axis="y", alpha=.2)
                ax = axes[ri, 2]
                rho_scenes = ("__all_scenes__",) + SCENES
                matrix = np.array([[_number(rho_rows.get((config, metric, scene)), "rho")
                                    for scene in rho_scenes] for metric in ("fps", "runtime", "memory")])
                cmap = plt.get_cmap("RdBu_r").copy()
                cmap.set_bad("#dddddd")
                img = ax.imshow(np.ma.masked_invalid(matrix), vmin=-1, vmax=1,
                                aspect="auto", cmap=cmap)
                for mi, metric in enumerate(("fps", "runtime", "memory")):
                    for si, scene in enumerate(rho_scenes):
                        row = rho_rows.get((config, metric, scene))
                        rho = _number(row, "rho")
                        if math.isfinite(rho):
                            text = f"{rho:.2f}\nn={_count(row, 'n_sequences')}"
                        else:
                            reason = "const" if row and row.get("status") == "constant_input" else "insuff"
                            text = "NA:" + reason + "\nn=" + _count(row, "n_sequences")
                        ax.text(si, mi, text, ha="center", va="center", fontsize=6.9,
                                color="white" if math.isfinite(rho) and abs(rho) > .65 else "#171717")
                ax.set_xticks(range(6), ["all"] + list(SCENE_SHORT))
                ax.set_yticks(range(3), ["FPS", "runtime", "memory"])
                ax.set_title("RMSE–efficiency Spearman rho [-1, 1]", fontsize=9)
                fig.colorbar(img, ax=ax, fraction=.025, pad=.018, ticks=[-1, 0, 1])
            fig.text(.058, .025,
                     "Left: V0 two marginal supports; V1 full F block-equal (baseline); V2 F scene-equal; "
                     "V3 all-retained-finite C; V4 F sequence medians. '-scene' = fixed-F V1 scene deletion.\n"
                     "Middle: signed existing scene terms sum to the full-F baseline; n denotes contributing blocks, "
                     "not independent observations. No scene is deleted from the main result.\n"
                     "Right: paired RMSE and each efficiency mean use exactly the same finite runs within each sequence. "
                     "n = sequences; constant/insufficient correlations are undefined, not zero.\n"
                     "Scope remains configuration-specific; source units/protocols unresolved. No causal, frame-count, "
                     "cross-method performance or computation-for-accuracy claim.",
                     fontsize=7.8)
            _save(fig, output_dir, f"composition_efficiency_p{page + 1:02d}", group,
                  ["V0_V4", "scene_leave_one", "scene_contributions", "within_efficiency"],
                  "Existing speed/height support views and fixed-F V1 scene deletion, scene additive terms with "
                  "block counts, and same-finite-run RMSE/efficiency Spearman rho across all and five scenes. "
                  "Undefined constant/insufficient views retained; rho scale [-1,1].",
                  results, plt)
    if len(results) != 60:
        raise AssertionError("Expected exactly 60 PNG/SVG page pairs")
    return results
