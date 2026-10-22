"""Render the five Step 11C overviews from supplied, previously checked rows.

This module does not read CSVs, regroup runs, infer taxonomy, or call prior
analysis entry points. The caller owns input snapshots and output protection.
"""
from pathlib import Path
import io
import json
import math
import textwrap
import xml.etree.ElementTree as ET

SCENES = ("building", "houses", "pool", "road", "roundabout")
HEIGHTS = (10, 20, 30)
SPEEDS = (2, 4, 8)
FIGURE_SIZE = (26, 34)
PNG_DPI = 110
TOP, BOTTOM = .902, .155
LEFT, ANNOTATION_WIDTH, PLOT_LEFT, PLOT_RIGHT = .052, .298, .374, .958
BASENAMES = (
    "01_distribution_atlas", "02_speed_response_matrix",
    "03_altitude_response_matrix", "04_finite_coverage_matrix",
    "05_precision_efficiency_matrix",
)
GROUP_COLORS = {"Mono": "#d8eaf4", "RGB-D": "#e5ecd2",
                "RGB-D + Semantic": "#eadcf0", "Unknown": "#e2e2e2"}
FAMILY_COLORS = {"Traditional": "#c5d8ea", "Learning-based": "#f6dcc1",
                 "3DGS": "#d6e8ca", "Feedforward": "#dfd4ed",
                 "3DGS & Semantic-enhanced": "#efd1db",
                 "Semantic-enhanced": "#f2e5b3"}
STATE_COLORS = {"positive": "#e6a283", "negative": "#83b4d8",
                "numeric_zero": "#f6f6e8", "unavailable": "#c7c7c7",
                "no_retained_records": "#efefef",
                "observed_all_nonfinite": "#e0c9e8"}
STATE_SYMBOLS = {"positive": "+", "negative": "-", "numeric_zero": "0",
                 "unavailable": "NA", "no_retained_records": "NR",
                 "observed_all_nonfinite": "AF"}
SHAPES = {"nondecreasing": "UP", "nonincreasing": "DN",
          "nonmonotonic": "NM", "numeric_flat": "FL", "unavailable": "?"}


def _num(value):
    if value is None or value == "":
        return math.nan
    try:
        value = float(value)
        return value if math.isfinite(value) else math.nan
    except (TypeError, ValueError):
        return math.nan


def _fmt(value, precision=4):
    value = _num(value)
    return format(value, "." + str(precision) + "g") if math.isfinite(value) else "NA"


def _list(value):
    return json.loads(value) if isinstance(value, str) else value


def _index(rows, fields):
    result = {}
    for row in rows:
        key = tuple(row[field] for field in fields)
        if key in result:
            raise ValueError("Duplicate rendering key: " + repr(key))
        result[key] = row
    return result


def _header(fig, title, subtitle):
    fig.text(.51, .968, title, ha="center", va="top", fontsize=23, weight="bold")
    fig.text(.51, .948, subtitle, ha="center", va="top", fontsize=13)


def _footer(fig, lines):
    expanded = []
    for line in lines:
        expanded.extend(textwrap.wrap(line, width=182, break_long_words=False,
                                      break_on_hyphens=False) or [""])
    fig.text(.052, .118, "\n".join(expanded), ha="left", va="top",
             fontsize=11.5, linespacing=1.45)


def _taxonomy_legend(taxonomy):
    # Show only current input groups; historical source-audit uncertainty is not
    # reintroduced after a user's explicit configuration-level confirmation.
    input_codes = (("Mono", "M"), ("RGB-D", "D"),
                   ("RGB-D + Semantic", "DS"), ("Unknown", "U"))
    present = {row["display_input_group"] for row in taxonomy}
    input_text = "; ".join(code + " = " + group for group, code in input_codes if group in present)
    lines = [
        "Input: " + input_text + ". "
        "Input information and algorithm family are separate annotations.",
        "Family: TRAD = Traditional; LEARN = Learning-based; 3DGS = 3DGS; "
        "FF = Feedforward; 3DGS+SEM = 3DGS & Semantic-enhanced; SEM = Semantic-enhanced.",
        "Fixed taxonomy order, never a numerical performance ranking. Family labels are user-provided "
        "method-level taxonomy, not independent configuration votes or evidence of mechanism.",
    ]
    if any(row.get("base_modality", "unknown") == "unknown" for row in taxonomy):
        lines.append("* Input-audit unresolved labels preserve current source/configuration uncertainty; "
                     "taxonomy is annotation only.")
    return lines


def _annotation(fig, taxonomy, plt, Rectangle, matrix_axes=()):
    ax = fig.add_axes([LEFT, BOTTOM, ANNOTATION_WIDTH, TOP - BOTTOM])
    ax.set_xlim(0, 8)
    ax.set_ylim(23.5, -.5)
    ax.axis("off")
    fig.text(LEFT + ANNOTATION_WIDTH * .035, TOP + .0075, "Input", fontsize=12, weight="bold")
    fig.text(LEFT + ANNOTATION_WIDTH * .135, TOP + .0075, "Family", fontsize=12, weight="bold")
    fig.text(LEFT + ANNOTATION_WIDTH * .275, TOP + .0075, "Configuration / evaluation scope",
             fontsize=12, weight="bold")
    boundaries = []
    previous_group = previous_family = None
    for ri, row in enumerate(taxonomy):
        group = row["display_input_group"]
        family = row["algorithm_family"]
        ax.add_patch(Rectangle((.015, ri - .46), .65, .92,
                               facecolor=GROUP_COLORS.get(group, "#e2e2e2"),
                               edgecolor="#999999", linewidth=.5))
        ax.add_patch(Rectangle((.72, ri - .46), 1.31, .92,
                               facecolor=FAMILY_COLORS.get(family, "#e2e2e2"),
                               edgecolor="#999999", linewidth=.5))
        ax.text(.34, ri, row["input_group_code"], ha="center", va="center",
                fontsize=12, weight="bold")
        ax.text(1.375, ri, row["family_code"], ha="center", va="center",
                fontsize=9.5, weight="bold")
        display = row["configuration_display_name"]
        display_lines = textwrap.wrap(display, 38, break_long_words=False,
                                      break_on_hyphens=False)
        scope = row.get("evaluation_scope", "unknown")
        scope_display = {"whole_trajectory": "whole trajectory",
                         "500_frames": "500 frames", "500_frame": "500 frames"}.get(scope, scope)
        label = "\n".join(display_lines) + "\nscope: " + scope_display
        unresolved = row.get("base_modality", "unknown") == "unknown"
        if unresolved:
            label += "; input audit unresolved*"
        ax.text(2.2, ri, label, ha="left", va="center", fontsize=10.3, linespacing=1.25)
        if ri and (group != previous_group or family != previous_family):
            major = group != previous_group
            boundaries.append((ri - .5, major))
            ax.axhline(ri - .5, color="#444444" if major else "#999999",
                       lw=1.8 if major else .7, ls="-" if major else "--")
        previous_group, previous_family = group, family
    for maxis in matrix_axes:
        for y, major in boundaries:
            maxis.axhline(y, color="#333333" if major else "#aaaaaa",
                         lw=1.8 if major else .65, ls="-" if major else "--")
    start = 0
    while start < 24:
        end = start + 1
        group = taxonomy[start]["display_input_group"]
        while end < 24 and taxonomy[end]["display_input_group"] == group:
            end += 1
        center = TOP - (start + end) / 48 * (TOP - BOTTOM)
        fig.text(.024, center, group, rotation=90, va="center", ha="center",
                 fontsize=14, weight="bold", color="#303030")
        start = end
    return boundaries


def _matrix_axis(fig, ncols, left=PLOT_LEFT, width=None):
    if width is None:
        width = PLOT_RIGHT - left
    ax = fig.add_axes([left, BOTTOM, width, TOP - BOTTOM])
    ax.set_xlim(-.5, ncols - .5)
    ax.set_ylim(23.5, -.5)
    ax.set_yticks([])
    ax.tick_params(axis="x", bottom=False, top=True, labelbottom=False,
                   labeltop=True, length=0, pad=6)
    for spine in ax.spines.values():
        spine.set_visible(False)
    return ax


def _save_checked(fig, out, basename, ids, caption, plt):
    """Write an actual SVG using its native renderer, check visible text boxes."""
    from matplotlib.backends.backend_svg import RendererSVG
    from matplotlib.text import Text
    original_dpi = fig.dpi
    fig.set_dpi(72)
    width, height = [float(x) * 72 for x in fig.get_size_inches()]
    svg_buffer = io.StringIO()
    renderer = RendererSVG(width, height, svg_buffer, image_dpi=PNG_DPI,
                           metadata={"Date": None,
                                     "Creator": "benchmark_analysis Step 11C"})
    fig.draw(renderer)
    checked, outside = [], []
    for artist in fig.findobj(match=Text):
        if not artist.get_visible() or not artist.get_text().strip():
            continue
        bbox = artist.get_window_extent(renderer)
        if not all(math.isfinite(x) for x in (bbox.x0, bbox.y0, bbox.x1, bbox.y1)):
            raise ValueError("Nonfinite text bbox in " + basename)
        record = {"text": artist.get_text(), "bbox_pt":
                  [round(bbox.x0, 3), round(bbox.y0, 3), round(bbox.x1, 3), round(bbox.y1, 3)]}
        checked.append(record)
        if bbox.x0 < -.1 or bbox.y0 < -.1 or bbox.x1 > width + .1 or bbox.y1 > height + .1:
            outside.append(record)
    renderer.finalize()
    svg_text = svg_buffer.getvalue()
    root = ET.fromstring(svg_text)
    viewbox = [float(x) for x in root.attrib["viewBox"].split()]
    svg_text_count = sum(node.tag.endswith("}text") for node in root.iter())
    if outside:
        raise ValueError("SVG text outside canvas in " + basename + ": " +
                         json.dumps(outside, ensure_ascii=False))
    if viewbox != [0.0, 0.0, width, height] or svg_text_count == 0:
        raise ValueError("SVG viewBox/text-preservation check failed")
    (out / (basename + ".svg")).write_text(svg_text, encoding="utf-8")
    fig.set_dpi(original_dpi)
    fig.savefig(out / (basename + ".png"), dpi=PNG_DPI, facecolor="white",
                metadata={"Software": "benchmark_analysis Step 11C"})
    plt.close(fig)
    return {"basename": basename, "png": basename + ".png", "svg": basename + ".svg",
            "configuration_ids": ids, "row_order": ids, "caption": caption,
            "figure_inches": list(FIGURE_SIZE), "png_dpi": PNG_DPI,
            "png_dimensions": [round(FIGURE_SIZE[0] * PNG_DPI), round(FIGURE_SIZE[1] * PNG_DPI)],
            "svg_clipping_check": {"renderer": "native RendererSVG at 72 pt/in",
                                   "viewBox": viewbox, "text_elements": svg_text_count,
                                   "visible_text_bboxes_checked": len(checked),
                                   "outside_canvas": outside,
                                   "status": "passed_no_visible_text_bbox_outside_viewBox",
                                   "checked_text_boxes": checked}}


def render_overviews(out, taxonomy, distribution, speed, altitude, coverage, efficiency):
    """Render five full 24-configuration overviews, without statistical aggregation."""
    import numpy as np
    import matplotlib
    matplotlib.use("Agg", force=True)
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle, Patch
    from matplotlib.lines import Line2D
    from matplotlib.colors import Normalize

    out = Path(out)
    if not out.is_dir():
        raise ValueError("Caller must create the guarded staging directory")
    if len(taxonomy) != 24 or len({r["configuration_id"] for r in taxonomy}) != 24:
        raise ValueError("Exactly 24 unique taxonomy rows are required")
    if any(r["display_input_group"] not in GROUP_COLORS for r in taxonomy):
        raise ValueError("Input groups must use Mono/RGB-D/RGB-D + Semantic/Unknown")
    row_orders = [int(r["row_order"]) for r in taxonomy]
    if row_orders != sorted(row_orders) or len(set(row_orders)) != 24:
        raise ValueError("Taxonomy must be supplied in its unique fixed row order")
    for base in BASENAMES:
        for ext in ("png", "svg"):
            if (out / (base + "." + ext)).exists():
                raise FileExistsError("Rendering helper never overwrites existing files")
    ids = [r["configuration_id"] for r in taxonomy]
    dist = _index(distribution, ("configuration_id",))
    speeds = _index(speed, ("configuration_id", "scene", "fixed_value"))
    altitudes = _index(altitude, ("configuration_id", "scene", "fixed_value"))
    cover = _index(coverage, ("configuration_id", "scene", "altitude_m", "speed_mps"))
    efficiencies = _index(efficiency, ("configuration_id", "efficiency_metric", "scene"))
    if (len(dist), len(speeds), len(altitudes), len(cover), len(efficiencies)) != (24, 360, 360, 1080, 432):
        raise ValueError("Rendering tables have unexpected key counts")
    results = []
    with plt.rc_context({"font.family": "DejaVu Sans", "font.size": 11,
                         "svg.fonttype": "none", "svg.hashsalt": "benchmark-11c",
                         "axes.spines.top": False, "axes.spines.right": False,
                         "axes.titlesize": 12, "axes.labelsize": 11,
                         "xtick.labelsize": 9, "ytick.labelsize": 9,
                         "legend.fontsize": 10}):
        fig = plt.figure(figsize=FIGURE_SIZE)
        _header(fig, "RMSE distribution atlas: all 24 configurations",
                "Condition-labelled, equal-weight sequence means | independent x scales; common ECDF 0-1")
        _annotation(fig, taxonomy, plt, Rectangle)
        row_height = (TOP - BOTTOM) / 24
        for ri, config in enumerate(ids):
            row = dist[(config,)]
            bottom = TOP - (ri + 1) * row_height + row_height * .19
            ax = fig.add_axes([PLOT_LEFT, bottom, .371, row_height * .65])
            vals = sorted(float(v) for v in _list(row["finite_sequence_values_json"]))
            if any(not math.isfinite(v) for v in vals):
                raise ValueError("ECDF input contains nonfinite values")
            if vals:
                ax.step([vals[0]] + vals, [0] + [(k + 1) / len(vals) for k in range(len(vals))],
                        where="post", color="#252525", lw=1.3)
                for key, color, linestyle in (("mean", "#0072B2", "-"),
                                               ("median", "#D55E00", "--"),
                                               ("p90", "#009E73", ":")):
                    v = _num(row[key])
                    if math.isfinite(v):
                        ax.axvline(v, color=color, ls=linestyle, lw=1.2)
                ax.margins(x=.025)
            else:
                ax.text(.5, .5, row["status"], transform=ax.transAxes,
                        ha="center", va="center", fontsize=10)
            ax.set_ylim(0, 1)
            ax.set_yticks([0, 1], ["0", "1"])
            ax.tick_params(axis="both", length=2, pad=2)
            ax.xaxis.set_major_locator(plt.MaxNLocator(5))
            ax.grid(alpha=.18)
            center = TOP - (ri + .5) * row_height
            summary = (f"Finite / observed: {row['n_finite_sequences']}/{row['n_observed_sequences']}\n"
                       f"mean {_fmt(row['mean'])}; median {_fmt(row['median'])}\n"
                       f"p90 {_fmt(row['p90'])}; status: {row['status']}")
            fig.text(.765, center, summary, fontsize=10.5, va="center", linespacing=1.35)
        fig.text(PLOT_LEFT, TOP + .008, "ECDF; RMSE x axis in each configuration's source units",
                 fontsize=12, weight="bold")
        fig.text(.765, TOP + .008, "Stored statistics / numeric coverage",
                 fontsize=12, weight="bold")
        handles = [Line2D([0], [0], color="#252525", label="ECDF"),
                   Line2D([0], [0], color="#0072B2", label="mean"),
                   Line2D([0], [0], color="#D55E00", ls="--", label="median"),
                   Line2D([0], [0], color="#009E73", ls=":", label="p90")]
        fig.legend(handles=handles, loc="upper center", bbox_to_anchor=(.65, .141),
                   ncol=4, frameon=False)
        _footer(fig, [
            "x scales are configuration-specific: compare shape, tails and mean/median relation, "
            "not cross-method absolute error. All finite values retained; no trimming or winsorization.",
            "Each sequence supplies one existing finite-run mean. Finite-sequence coverage is not trajectory success. "
            "Repeat SD requires at least two finite runs; scope labels follow explicit current evidence, not numeric validity.",
        ] + _taxonomy_legend(taxonomy))
        results.append(_save_checked(fig, out, BASENAMES[0], ids,
                       "All 24 configurations; existing sequence-mean ECDFs with independent x scales and common y=0-1, "
                       "stored mean/median/p90 and finite/observed sequence counts. No absolute RMSE ranking.", plt))

        for which, data, levels, symbol, base in (
                ("Speed", speeds, HEIGHTS, "H", BASENAMES[1]),
                ("Altitude", altitudes, SPEEDS, "V", BASENAMES[2])):
            fig = plt.figure(figsize=FIGURE_SIZE)
            difference = "RMSE(V8) - RMSE(V2)" if which == "Speed" else "RMSE(H30) - RMSE(H10)"
            _header(fig, which + " response across all configurations",
                    difference + " | discrete endpoint direction and separate three-level shape")
            ax = _matrix_axis(fig, 15)
            _annotation(fig, taxonomy, plt, Rectangle, [ax])
            for ri, config in enumerate(ids):
                for si, scene in enumerate(SCENES):
                    for li, level in enumerate(levels):
                        ci = si * 3 + li
                        row = data[(config, scene, level)]
                        state = row["display_status"]
                        if state not in STATE_COLORS:
                            raise ValueError("Unknown matrix display status " + state)
                        hatch = "///" if state == "no_retained_records" else (
                            "xx" if state == "observed_all_nonfinite" else None)
                        ax.add_patch(Rectangle((ci - .5, ri - .5), 1, 1,
                                               facecolor=STATE_COLORS[state], edgecolor="#ffffff",
                                               linewidth=.8, hatch=hatch))
                        if hatch:
                            ax.add_patch(Rectangle((ci - .5, ri - .5), 1, 1,
                                                   fill=False, edgecolor="#777777", linewidth=.4, hatch=hatch))
                        reasons = _list(row.get("missing_reasons_json", "[]"))
                        combined = state == "no_retained_records" and any(
                            "observed_all_nonfinite" in str(x) for x in reasons)
                        sign = "NR/AF" if combined else STATE_SYMBOLS[state]
                        shape = SHAPES[row["triple_shape"]]
                        ax.text(ci, ri - .12, sign, ha="center", va="center",
                                fontsize=13 if len(sign) <= 2 else 10, weight="bold")
                        ax.text(ci, ri + .20, shape, ha="center", va="center",
                                fontsize=8.5, color="#353535")
            ax.set_xticks(range(15), [symbol + str(level) for _ in SCENES for level in levels])
            for si, scene in enumerate(SCENES):
                ax.text(si * 3 + 1, 1.026, scene.title(), transform=ax.get_xaxis_transform(),
                        ha="center", va="bottom", fontsize=12, weight="bold")
                if si:
                    ax.axvline(si * 3 - .5, color="#303030", lw=1.8)
            handles = [Patch(facecolor=STATE_COLORS[s], edgecolor="#777777",
                             hatch="///" if s == "no_retained_records" else
                             ("xx" if s == "observed_all_nonfinite" else None),
                             label=STATE_SYMBOLS[s] + " " + s)
                       for s in STATE_COLORS]
            fig.legend(handles=handles, loc="upper center", bbox_to_anchor=(.66, .144),
                       ncol=3, frameon=False, fontsize=9)
            _footer(fig, [
                "Large token: endpoint direction only. Small shape code: UP = nondecreasing; DN = nonincreasing; "
                "NM = nonmonotonic; FL = numerical flat; ? = one or more of the three levels unavailable.",
                "NR = no retained records at a required endpoint; AF = observed endpoint but all RMSE nonfinite; "
                "NA = other unavailable. NR/AF retains both endpoint reasons. Exact differences and all reasons are in CSV.",
                "Numerical zero follows the fixed floating-point tolerance, not practical insensitivity. "
                "An endpoint increase does not establish three-level monotonicity, causality or significance.",
            ] + _taxonomy_legend(taxonomy))
            results.append(_save_checked(fig, out, base, ids,
                           difference + "; 24 fixed rows × five scenes × three fixed levels. "
                           "Discrete sign avoids cross-method absolute magnitude color ranking; "
                           "three-level shape and missing states separately displayed.", plt))

        fig = plt.figure(figsize=FIGURE_SIZE)
        _header(fig, "Finite RMSE coverage: all observed condition cells",
                "24 configurations × 5 scenes × 9 nominal height/speed cells | actual retained-run denominators")
        ax = _matrix_axis(fig, 45)
        _annotation(fig, taxonomy, plt, Rectangle, [ax])
        cmap = plt.get_cmap("Blues")
        norm = Normalize(0, 1)
        for ri, config in enumerate(ids):
            for si, scene in enumerate(SCENES):
                for hi, height in enumerate(HEIGHTS):
                    for vi, velocity in enumerate(SPEEDS):
                        ci = si * 9 + hi * 3 + vi
                        row = cover[(config, scene, height, velocity)]
                        state = row["cell_state"]
                        fraction = _num(row["finite_fraction"])
                        if state == "no_retained_records":
                            color, hatch, text = "#dddddd", "///", "NR"
                        else:
                            if not math.isfinite(fraction) or not 0 <= fraction <= 1:
                                raise ValueError("Observed cell requires finite coverage in [0,1]")
                            color, hatch = cmap(norm(fraction)), ("xx" if state == "observed_all_nonfinite" else None)
                            text = str(row["n_finite_records"]) + "/" + str(row["n_retained_records"])
                        ax.add_patch(Rectangle((ci - .5, ri - .5), 1, 1, facecolor=color,
                                               edgecolor="#dddddd", linewidth=.4))
                        if hatch:
                            ax.add_patch(Rectangle((ci - .5, ri - .5), 1, 1, fill=False,
                                                   edgecolor="#888888", linewidth=.4, hatch=hatch))
                        text_color = "white" if math.isfinite(fraction) and fraction > .58 else "#111111"
                        ax.text(ci, ri, text, ha="center", va="center", fontsize=7.5, color=text_color)
        ax.set_xticks(range(45),
                      [f"{h}/{v}" for _ in SCENES for h in HEIGHTS for v in SPEEDS],
                      rotation=90)
        for si, scene in enumerate(SCENES):
            ax.text(si * 9 + 4, 1.04, scene.title(), transform=ax.get_xaxis_transform(),
                    ha="center", va="bottom", fontsize=12, weight="bold")
            if si:
                ax.axvline(si * 9 - .5, color="#222222", lw=2)
            for hi in (1, 2):
                ax.axvline(si * 9 + hi * 3 - .5, color="#777777", lw=.7)
        cax = fig.add_axes([PLOT_LEFT + .09, .129, .32, .007])
        plt.colorbar(plt.cm.ScalarMappable(norm=norm, cmap=cmap), cax=cax, orientation="horizontal",
                     ticks=[0, .25, .5, .75, 1])
        cax.tick_params(labelsize=8, pad=2, length=2)
        fig.text(PLOT_LEFT + .255, .143, "Finite RMSE fraction [0, 1]", ha="center", fontsize=10)
        _footer(fig, [
            "Column labels are nominal H(m)/V(m/s), ordered H10/20/30 then V2/4/8 within each scene. "
            "Every cell prints finite/retained runs using its actual observed denominator, not planned repeats.",
            "NR with gray diagonal hatching means no records and is not a zero fraction. "
            "Cross-hatched 0/n means observed but all RMSE nonfinite. These are numeric-availability states, not success or failure labels.",
            "All 24 configurations and all 45 display cells retained. The observed-sequence and retained-run counts remain distinct in the CSV.",
        ] + _taxonomy_legend(taxonomy))
        results.append(_save_checked(fig, out, BASENAMES[3], ids,
                       "Fixed 24-row order; five scenes × H10/20/30 × V2/4/8. "
                       "Coverage uses actual finite/retained-run counts; no records separately hatched from observed zero coverage. "
                       "Fraction scale [0,1] is numeric availability, not success.", plt))

        fig = plt.figure(figsize=FIGURE_SIZE)
        _header(fig, "Within-configuration precision-efficiency associations",
                "Same-finite-run sequence means | overall and five scenes | Spearman rho in [-1, 1]")
        width = (PLOT_RIGHT - PLOT_LEFT - .035) / 3
        axes = [_matrix_axis(fig, 6, PLOT_LEFT + k * (width + .0175), width)
                for k in range(3)]
        _annotation(fig, taxonomy, plt, Rectangle, axes)
        rho_scenes = ("__all_scenes__",) + SCENES
        cmap = plt.get_cmap("RdBu_r")
        norm = Normalize(-1, 1)
        undefined = {"constant_input": ("C", "#e1d2ed", "xx"),
                     "insufficient_sequences": ("I", "#e0e0e0", ".."),
                     "unavailable": ("NA", "#bcbcbc", "///"),
                     "incompatible": ("X", "#efe1c6", "++")}
        for mi, (ax, metric) in enumerate(zip(axes, ("fps", "runtime", "memory"))):
            for ri, config in enumerate(ids):
                for si, scene in enumerate(rho_scenes):
                    row = efficiencies[(config, metric, scene)]
                    status = row["status"]
                    rho = _num(row["rho"])
                    if status == "computed":
                        if not math.isfinite(rho) or not -1.0000000001 <= rho <= 1.0000000001:
                            raise ValueError("Invalid computed rho")
                        color, hatch, token = cmap(norm(rho)), None, format(rho, ".2f")
                    else:
                        if status not in undefined:
                            raise ValueError("Unknown efficiency status " + status)
                        token, color, hatch = undefined[status]
                    ax.add_patch(Rectangle((si - .5, ri - .5), 1, 1, facecolor=color,
                                           edgecolor="white", linewidth=.6))
                    if hatch:
                        ax.add_patch(Rectangle((si - .5, ri - .5), 1, 1, fill=False,
                                               edgecolor="#888888", linewidth=.4, hatch=hatch))
                    text_color = "white" if status == "computed" and abs(rho) > .66 else "#111111"
                    ax.text(si, ri - .10, token, ha="center", va="center",
                            fontsize=8.8, color=text_color)
                    ax.text(si, ri + .20, "n=" + str(row["n_sequences"]), ha="center", va="center",
                            fontsize=6.8, color=text_color)
            ax.set_xticks(range(6), ["all", "bld", "house", "pool", "road", "round"],
                          rotation=0)
            ax.text(2.5, 1.025, "RMSE vs " + ("FPS" if metric == "fps" else metric),
                    transform=ax.get_xaxis_transform(), ha="center", va="bottom",
                    fontsize=13, weight="bold")
        cax = fig.add_axes([PLOT_LEFT + .09, .129, .32, .007])
        plt.colorbar(plt.cm.ScalarMappable(norm=norm, cmap=cmap), cax=cax, orientation="horizontal",
                     ticks=[-1, -.5, 0, .5, 1])
        cax.tick_params(labelsize=8, pad=2, length=2)
        fig.text(PLOT_LEFT + .255, .143, "Spearman rho [-1, 1]", ha="center", fontsize=10)
        _footer(fig, [
            "Each sequence's RMSE and efficiency means use the same finite-run intersection; "
            "n is the number of contributing sequences. Overall and each scene re-rank their own members.",
            "Undefined cells are separate states: C = constant input; I = insufficient sequences; "
            "NA = unavailable; X = incompatible. They are not zero correlation.",
            "Configuration-internal associations only: not cross-method resource efficiency or causality. "
            "Memory types are not harmonized; FPS/runtime timing protocols remain limited. FPS/runtime does not verify evaluated frame count.",
        ] + _taxonomy_legend(taxonomy))
        results.append(_save_checked(fig, out, BASENAMES[4], ids,
                       "Three parallel 24×6 matrices, same row order. Existing same-finite-run-intersection sequence-mean "
                       "Spearman rho across all and five scenes; fixed [-1,1] scale, explicit undefined states, n=sequences.", plt))
    if len(results) != 5:
        raise AssertionError("Five overview figures are required")
    return results
