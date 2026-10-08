"""Audited typed memory extraction; no research imports or experiment execution.

The 2026-10-08 audit distinguishes printed suffixes from verified producer
definitions. Binary exceptions to printed GB/MB labels have inspected producer
divisors of 1024**3 or 1024**2; DROID and author-confirmed SLAM3R use decimal MB.
No binary conversion is inferred merely from an old aggregation divisor.
See memory_gib_audit.md for provenance and missing-statistic limitations.

The author-confirmed CPU RSS policy keeps CPU_RSS separate from GPU_RESERVED.
Both use GiB; CPU RSS carries a display asterisk and never enters a reserved
column through the compatibility scalar API.
"""

import hashlib
import math
from pathlib import Path
import re


UNIT_FACTORS = {
    "bytes": 1 / 1024**3,
    "B": 1 / 1024**3,
    "KiB": 1 / 1024**2,
    "MiB": 1 / 1024,
    "GiB": 1.0,
    "KB": 1000 / 1024**3,
    "MB": 1000**2 / 1024**3,
    "GB": 1000**3 / 1024**3,
}

# method: (exact field, verified native unit, permitted printed suffix)
_RULES = {
    "DPVO": ("peak_reserved_GiB", "GiB", ""),
    "DROID-SLAM": ("peak_gpu_reserved_mb", "MB", ""),
    "MASt3R-SLAM": ("GPU_PeakReserved", "GiB", "GB"),
    "MongGS": ("Peak_reserved_by_process [GiB]", "GiB", ""),
    "Photo-slam": ("Peak reserved (MB)", "MiB", ""),
    "SGS-SLAM": ("PeakReservedGB", "GiB", ""),
    "SplaTAM": ("Peak GPU reserved", "MiB", "MB"),
    "TartanVO": ("peak_gpu_mem_reserved", "GiB", "GiB"),
    "VGGT-SLAM": ("Peak reserved  (PyTorch)", "GiB", "GB"),
    "VGGT-LONG": ("peak_gpu_gb", "GiB", ""),
    # user_confirmed 2026-10-08: stored value is reserved bytes / 1000**2.
    "SLAM3R": ("gpu_peak_reserved_mb", "MB", ""),
}
_CPU_RULES = {
    "DSO": ("PeakMemory (MB)", "MiB", ""),
    "ElasticFusion": ("peak_rss_mb", "MiB", ""),
    "ORB-SLAM2": ("memory", "MiB", "# MB (peak RSS)"),
    "ORB-SLAM3": ("memory_peak_MB", "MiB", ""),
    "SVO": ("peak_mem_mb", "MiB", ""),
}
_CPU_SOURCE_NAMES = {
    "DSO": "metric.txt",
    "ElasticFusion": "RunStats.txt",
    "ORB-SLAM2": "RunStats.txt",
    "ORB-SLAM3": "TimingResults.txt",
    "SVO": "metric.txt",
}
_MAX_BYTES = 1024 * 1024  # metric texts only; never consume a large run log


def convert_to_gib(value, unit):
    """Convert a nonnegative finite measurement using an explicit unit."""
    if unit not in UNIT_FACTORS:
        raise ValueError(f"Unverified memory unit: {unit!r}")
    value = float(value)
    if not math.isfinite(value) or value < 0:
        raise ValueError("Memory must be finite and nonnegative")
    result = value * UNIT_FACTORS[unit]
    if not math.isfinite(result):
        raise ValueError("Memory conversion overflow")
    return result


def _result(path, memory_type="GPU_RESERVED"):
    return {
        "status": "unverified",
        "value_gib": None,
        "source_path": str(path),
        "source_sha256": "",
        "source_field": "",
        "native_unit": "",
        "raw_value": None,
        "conversion": "",
        "memory_type": memory_type,
        "table_display_marker": "*" if memory_type == "CPU_RSS" else "",
    }


def _read_small_text(path, result):
    try:
        if path.stat().st_size > _MAX_BYTES:
            result["status"] = "source_too_large"
            return None
        data = path.read_bytes()
    except FileNotFoundError:
        result["status"] = "missing_file"
        return None
    except NotADirectoryError as error:
        result["status"] = "path_not_directory"
        result["detail"] = str(error)
        return None
    except (OSError, PermissionError) as error:
        result["status"] = "source_unreadable"
        result["detail"] = str(error)
        return None
    result["source_sha256"] = hashlib.sha256(data).hexdigest()
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        result["status"] = "source_not_text"
        return None


def read_memory(path, method):
    """Read one audited field, returning a value plus evidence or explicit gap.

    Hier semantic inputs always select the reserved-bytes sidecar. CPU RSS is
    read only by its separately audited method rule, never as a fallback for a
    missing GPU reserved measurement. Allocated/device-used/current-RSS fields
    and old CSV columns are never fallback sources.
    """
    if method not in _RULES and method not in _CPU_RULES and method != "hierslam":
        raise ValueError(f"Unknown audited memory method: {method!r}")
    path = Path(path)
    if method == "hierslam":
        semantic = "Airsim_semantic" in path.parts
        no_semantic = "Airsim_no_semantic" in path.parts
        if semantic == no_semantic:
            result = _result(path)
            result["status"] = "route_mismatch"
            result["detail"] = "Hier route must identify exactly one audited semantic branch"
            return result
        if semantic:
            path = path.with_name("gpu_peak_memory.txt")
            rule = ("peak_reserved_bytes", "bytes", "")
        else:
            rule = ("GPU Peak Memory (MB)", "MiB", "")
    else:
        rule = _RULES.get(method) or _CPU_RULES[method]

    result = _result(path, "CPU_RSS" if method in _CPU_RULES else "GPU_RESERVED")
    field, unit, suffix = rule
    result["source_field"] = field
    result["native_unit"] = unit or "unresolved"
    if method in _CPU_SOURCE_NAMES and path.name != _CPU_SOURCE_NAMES[method]:
        result["status"] = "route_mismatch"
        result["detail"] = f"{method} CPU RSS requires {_CPU_SOURCE_NAMES[method]}, not {path.name}"
        return result
    if method == "Photo-slam" and path.name != "GpuPeakUsageMB.txt":
        result["status"] = "route_mismatch"
        result["detail"] = "Photo requires GpuPeakUsageMB.txt, never ORB TimingResults.txt"
        return result
    if method == "hierslam" and "Airsim_no_semantic" in path.parts and path.name != "metric.txt":
        result["status"] = "route_mismatch"
        result["detail"] = "Hier no-semantic reserved source is metric.txt"
        return result
    text = _read_small_text(path, result)
    if text is None:
        return result
    # Whitespace between words is formatting, not a different measurement key.
    field_pattern = r"\s+".join(re.escape(word) for word in field.split())
    pattern = re.compile(r"^\s*" + field_pattern + r"(?:\s*:\s*|\s+)(.*?)\s*$")
    matches = [(line_number, match.group(1))
               for line_number, line in enumerate(text.splitlines(), 1)
               if (match := pattern.fullmatch(line)) is not None]
    if not matches:
        result["status"] = "missing_field"
        return result
    if len(matches) != 1:
        result["status"] = "ambiguous_field"
        result["detail"] = f"Target field occurs {len(matches)} times; no row selected"
        result["source_lines"] = [number for number, _ in matches]
        return result
    line_number, payload = matches[0]
    result["source_line"] = line_number
    parts = payload.split()
    if not parts:
        result["status"] = "invalid_value"
        return result
    try:
        value = float(parts[0])
    except ValueError:
        result["status"] = "invalid_value"
        result["raw_text"] = payload
        return result
    if not math.isfinite(value) or value < 0:
        result["status"] = "invalid_value"
        result["raw_text"] = payload
        return result
    result["raw_value"] = value
    if " ".join(parts[1:]) != suffix:
        result["status"] = "unit_conflict"
        result["detail"] = f"Expected printed suffix {suffix!r}; got {' '.join(parts[1:])!r}"
        return result
    if unit is None:
        result["status"] = "unit_unresolved"
        return result
    try:
        result["value_gib"] = convert_to_gib(value, unit)
    except ValueError as error:
        result["status"] = "invalid_value"
        result["detail"] = str(error)
        return result
    result["conversion"] = f"{unit} -> GiB; multiply by {UNIT_FACTORS[unit]:.17g}"
    result["status"] = "ok"
    return result


def parse_peak_reserved_gib(path, method):
    """Reserved-only compatibility scalar; CPU RSS must use the typed API."""
    result = read_memory(path, method)
    if result["status"] in {"ambiguous_field", "route_mismatch", "unit_conflict"}:
        raise ValueError(f"{method}: {result['status']}: {result.get('detail', '')}")
    return result["value_gib"] if result["status"] == "ok" and result["memory_type"] == "GPU_RESERVED" else "NA"
