#!/usr/bin/env python3
"""Read-only CSV structure inventory; no metric calculations or source imports."""

import argparse
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shlex
import stat
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone


WORKSPACE = Path('/home/yuan/SLAM/codex_review/benchmark_analysis')
INPUT_ROOT = Path('/home/yuan/SLAM/AirSim-Visual-SLAM-Research-Toolkit/Benchmark/experiment_data')
ROLES = ('run_metrics_candidate', 'aggregate_summary', 'other_csv', 'unknown')
FIELDS = (
    'source_relative_path', 'source_absolute_path', 'method_directory', 'file_role',
    'modality', 'semantic_usage', 'configuration_clues_json', 'evaluation_scope',
    'record_count', 'raw_columns_json', 'raw_header_text_json',
    'identifier_samples_json', 'configuration_samples_json', 'size_bytes',
    'mtime_utc', 'sha256', 'hash_status', 'read_status', 'encoding', 'delimiter',
    'empty_records_excluded', 'symlink_target', 'classification_rationale',
    'pending_notes',
)
# Exact names only: rgbd, semantic, results, and rgbd_whole_trajectory are NOT excluded.
# Skipping is a coverage gap, never evidence that a directory is obsolete.
REVIEW_BEFORE_ENTERING = {
    'rgb', 'depth', 'images', 'image', 'raw_images', 'raw_data', 'pointclouds',
    'trajectories', 'trajectory', 'models', 'checkpoints', 'weights', 'rosbags',
    '.git', '__pycache__', '.venv', 'venv',
}
IDENTIFIERS = {
    'dataset', 'dataset_name', 'sequence', 'sequence_name', 'seq', 'seq_name',
    'run', 'run_id', 'run_name', 'experiment', 'experiment_id', 'scene',
}
CONFIGURATION_FIELDS = {
    'mode', 'modality', 'config', 'configuration', 'semantic', 'use_semantic',
    'semantic_usage', 'calibration', 'calib', 'scope', 'evaluation_scope',
    'eval_scope', 'stage', 'method', 'algorithm', 'label', 'type',
    'altitude', 'speed', 'scene',
}


def js(value):
    return json.dumps(value, ensure_ascii=False)


def normalized(value):
    return re.sub(r'[\s-]+', '_', value.strip().lower())


def inspect_csv(data):
    """Strict UTF-8 CSV parsing; preserve cells; count nonempty CSV records."""
    text = data.decode('utf-8-sig', errors='strict')
    if not text:
        raise ValueError('Empty file: no header; record count is unknown')
    dialect = csv.Sniffer().sniff(text[:32768], delimiters=',;\t')
    stream = io.StringIO(text, newline='')
    reader = csv.reader(stream, dialect, strict=True)
    header = next(reader)
    raw_header = text[:stream.tell()]
    if not header or all(cell == '' for cell in header):
        raise ValueError('Empty header: cannot identify a table')
    ids = [(i, name) for i, name in enumerate(header) if normalized(name) in IDENTIFIERS]
    configs = [(i, name) for i, name in enumerate(header)
               if normalized(name) in CONFIGURATION_FIELDS]
    id_samples, config_samples = {}, {}
    config_values = {f'{i}:{name}': [] for i, name in configs}
    # Include index in the key to retain duplicate column names without overwriting.
    for dest, selected in [(id_samples, ids), (config_samples, configs)]:
        for i, name in selected:
            dest[f'{i}:{name}'] = []
    count, empty, ragged = 0, 0, []
    for row in reader:
        if not row or all(cell == '' for cell in row):
            empty += 1
            continue
        count += 1
        if len(row) != len(header):
            if len(ragged) < 3:
                ragged.append(f'data record {count}, ends at physical line {reader.line_num}: '
                              f'{len(row)} fields, header {len(header)}')
        for i, name in ids:
            if i < len(row) and row[i] != '':
                values = id_samples[f'{i}:{name}']
                # At most three examples, no whole-column uniqueness calculation.
                if len(values) < 3 and row[i] not in values:
                    values.append(row[i])
        for i, name in configs:
            if i < len(row) and row[i] != '':
                config_values[f'{i}:{name}'].append(row[i])
    # Group labels may embed configuration names. Take first/middle/last raw values;
    # do not split tokens or produce a full set of unique groups/configurations.
    for key, values in config_values.items():
        if values:
            for i in [0, (len(values) - 1) // 2, len(values) - 1]:
                if values[i] not in config_samples[key]:
                    config_samples[key].append(values[i])
    return {
        'record_count': count, 'raw_columns_json': js(header),
        'raw_header_text_json': js(raw_header),
        'identifier_samples_json': js(id_samples),
        'configuration_samples_json': js(config_samples),
        'empty_records_excluded': empty,
        'encoding': 'UTF-8 with BOM' if data.startswith(b'\xef\xbb\xbf') else 'UTF-8',
        'delimiter': dialect.delimiter,
        'read_status': 'parsed_with_structure_warning' if ragged else 'parsed',
        'pending_notes': '; '.join(ragged),
    }


def classify(row):
    rel = Path(row['source_relative_path'])
    name = rel.name.lower()
    header = json.loads(row['raw_columns_json'] or '[]')
    names = {normalized(x) for x in header}
    clues, reasons, pending = [], [], []
    row.update(file_role='unknown', modality='unknown', semantic_usage='unknown',
               evaluation_scope='unknown')
    if name.startswith('summary'):
        row['file_role'] = 'aggregate_summary'
        row['evaluation_scope'] = 'mixed/unknown'
        reasons.append('用户已确认：summary 开头为聚合派生表，不作为逐次运行输入')
        pending.append('记录级配置/范围待查；不根据父目录给整张 summary 指定范围')
    elif name in {'mono_metrics.csv', 'rgbd_metrics.csv', 'semantic_metrics.csv'}:
        row['file_role'] = 'run_metrics_candidate'
        reasons.append('用户已确认的逐次指标命名；本轮仅确认结构，口径尚未验证')
    elif names & IDENTIFIERS and any(
            re.search(r'(^|_)(rmse|ate|fps|runtime|memory)($|_)', c) for c in names):
        row['file_role'] = 'run_metrics_candidate'
        reasons.append('表头同时包含运行/数据标识与指标字段；暂列候选，来源待核验')
    else:
        reasons.append('现有文件名与结构证据不足，保留 unknown，不自动纳入或排除')
    tokens = re.split(r'[_\W]+', rel.as_posix().lower())
    for token in ['mono', 'rgbd', 'semantic', 'calib', 'nocalib', 'whole', 'trajectory']:
        if token in tokens:
            clues.append(f'path token: {token}')
    if row['file_role'] == 'run_metrics_candidate':
        if name == 'mono_metrics.csv':
            row['modality'] = 'mono'
        elif name == 'rgbd_metrics.csv':
            row['modality'] = 'RGB + Depth'
        elif name == 'semantic_metrics.csv':
            row['semantic_usage'] = 'yes'
        if rel.as_posix() in {'hierslam/rgbd_metrics.csv', 'hierslam/semantic_metrics.csv'}:
            row['evaluation_scope'] = '500 frames'
            reasons.append('评测范围：README 中用户已确认的 Hier-SLAM 外层配置')
            if name == 'rgbd_metrics.csv':
                row['semantic_usage'] = 'no'
        elif (rel.parent.as_posix() == 'hierslam/rgbd_whole_trajectory'
              and name == 'rgbd_metrics.csv'):
            row.update(modality='RGB + Depth', semantic_usage='no',
                       evaluation_scope='whole trajectory')
            reasons.append('用户已确认的 Hier-SLAM 完整轨迹配置；实际发现此逐次指标文件')
        if row['evaluation_scope'] == 'unknown':
            pending.append('评测范围 unknown；不自动认定完整轨迹')
        if row['semantic_usage'] == 'unknown':
            pending.append('语义使用情况 unknown；不从 mono/rgbd 推断无语义')
        if row['modality'] == 'unknown':
            pending.append('完整输入模态 unknown')
        if 'calib' in tokens or 'nocalib' in tokens:
            pending.append('calib/nocalib 分开保留；校准含义与输入模态待核验')
        if not names & IDENTIFIERS:
            pending.append('未找到已识别的运行标识字段，后续需人工核验')
    if row['method_directory'] == 'shared/ownership_pending':
        pending.append('根级 CSV，方法归属待确认')
    if row['pending_notes']:
        pending.insert(0, row['pending_notes'])
    row['configuration_clues_json'] = js(clues)
    row['classification_rationale'] = '；'.join(reasons)
    row['pending_notes'] = '；'.join(pending)


def file_record(path, root, max_bytes):
    rel = path.relative_to(root)
    row = dict.fromkeys(FIELDS, '')
    row.update(source_relative_path=rel.as_posix(), source_absolute_path=str(path),
               method_directory=rel.parts[0] if len(rel.parts) > 1 else 'shared/ownership_pending',
               hash_status='not computed: content not read')
    try:
        before = path.lstat()
        row.update(size_bytes=before.st_size,
                   mtime_utc=datetime.fromtimestamp(before.st_mtime, timezone.utc).isoformat())
        if stat.S_ISLNK(before.st_mode):
            row.update(symlink_target=os.readlink(path), read_status='symlink_not_followed',
                       pending_notes='符号链接不读取目标；size/mtime 是链接自身元数据')
        elif not stat.S_ISREG(before.st_mode):
            row.update(read_status='non_regular_not_read', pending_notes='非常规文件，未读取')
        elif before.st_size > max_bytes:
            row.update(read_status='size_limit', pending_notes=f'超过 {max_bytes} bytes 内容读取上限')
        else:
            # O_NOFOLLOW protects the final component if it changes after discovery.
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(fd, 'rb') as source:
                opened = os.fstat(source.fileno())
                if not stat.S_ISREG(opened.st_mode):
                    raise OSError('File is no longer a regular file')
                data = source.read(max_bytes + 1)
                after = os.fstat(source.fileno())
            current = path.lstat()
            signatures = [(s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns)
                          for s in (before, opened, after, current)]
            if len(set(signatures)) != 1 or len(data) != after.st_size:
                row.update(read_status='changed_during_read',
                           pending_notes='读取期间文件元数据或内容长度变化；不报告计数或哈希')
            elif len(data) > max_bytes:
                row.update(read_status='size_limit', pending_notes='读取时超过内容上限')
            else:
                row.update(sha256=hashlib.sha256(data).hexdigest(), hash_status='full byte snapshot')
                try:
                    row.update(inspect_csv(data))
                except (UnicodeError, csv.Error, ValueError, StopIteration) as exc:
                    row.update(read_status='parse_error', pending_notes=f'{type(exc).__name__}: {exc}')
    except OSError as exc:
        row.update(read_status='access_error', pending_notes=f'{type(exc).__name__}: {exc}')
    classify(row)
    return row


def discover(root):
    csv_paths, methods, visited, events, scripts, other_files = [], [], [], [], [], []

    def visit(directory):
        rel = directory.relative_to(root).as_posix()
        if directory.is_symlink():
            events.append((rel, 'symlink_not_followed', os.readlink(directory)))
            return
        try:
            with os.scandir(directory) as entries:
                entries = sorted(entries, key=lambda item: item.name)
        except OSError as exc:
            if directory == root:
                raise
            events.append((rel, 'directory_access_error', str(exc)))
            return
        visited.append(rel)
        for entry in entries:
            path = Path(entry.path)
            relative = path.relative_to(root).as_posix()
            try:
                if entry.is_symlink():
                    events.append((relative, 'symlink_not_followed', os.readlink(path)))
                    if path.suffix.lower() == '.csv':
                        csv_paths.append(path)
                elif entry.is_dir(follow_symlinks=False):
                    if directory == root:
                        methods.append(entry.name)
                    if entry.name.lower() in REVIEW_BEFORE_ENTERING:
                        events.append((relative, 'directory_needs_review',
                                       '目录名提示原始内容/模型/缓存；未进入，需核对覆盖范围'))
                    else:
                        visit(path)
                elif path.suffix.lower() == '.csv':
                    csv_paths.append(path)
                elif path.suffix.lower() == '.py':
                    scripts.append(relative)
                else:
                    other_files.append(relative)
            except OSError as exc:
                events.append((relative, 'entry_access_error', str(exc)))
                if path.suffix.lower() == '.csv':
                    csv_paths.append(path)

    visit(root)
    return sorted(set(csv_paths)), sorted(methods), visited, events, scripts, other_files


def md(value):
    return str(value).replace('|', '\\|').replace('\n', '<br>')


def report(rows, methods, visited, events, scripts, other_files, args):
    counts = Counter(row['file_role'] for row in rows)
    states = Counter(row['read_status'] for row in rows)
    lines = [
        '# 第 3 步：输入文件盘点', '',
        f'快照时间（UTC）：{datetime.now(timezone.utc).isoformat()}。', '',
        '## A．范围、方法与覆盖', '',
        f'- 输入根：`{args.input_root}`，只读。',
        f'- 输出目录：`{args.output_dir}`。',
        f'- 实际解释器：`{sys.executable}`；仅使用 Python 标准库，无安装。',
        '- 实际执行命令：', '', '```bash',
        shlex.join([sys.executable, '-B', str(Path(__file__).absolute()),
                    '--input-root', str(args.input_root), '--output-dir', str(args.output_dir),
                    '--max-bytes', str(args.max_bytes)]
                   + (['--overwrite'] if args.overwrite else [])), '```', '',
        f'第一层实际方法目录 {len(methods)} 个；CSV 文件 {len(rows)} 个（按完整路径逐文件记录）。', '',
        '| 暂定角色 | 文件数 |', '|---|---:|',
        *[f'| {role} | {counts[role]} |' for role in ROLES], '',
        '读取状态：' + '；'.join(f'{key}={value}' for key, value in sorted(states.items())) + '。', '',
        '记录数采用 CSV 解析器：首个 CSV 记录为表头；后续排除空记录 `[]` 及所有字段均为',
        '空字符串的记录。仅有空格的字段仍保留；缺失值、NA、0、重复记录、疑似失败记录均不删除。',
        '字段原文不 strip、不转数值；带引号换行仍算一个 CSV 记录。该计数不是成功次数、',
        '独立序列数或总实验数，不跨文件求和宣称总实验数。', '',
        '严格 UTF-8/UTF-8 BOM 解码，`csv.Sniffer` 仅在逗号、分号、制表符中识别分隔符，',
        '严格解析引号。失败记为未知计数，不跳坏行；字段数不一致保留记录并显式警告。',
        '原始列名（保留顺序、大小写及空格）和表头文本、少量原始标识/配置样例见 CSV 的 JSON 字段。',
        '每个标识字段最多三个原始样例；配置/分组标签取首、中、末最多三个非空值样例，',
        '不是完整配置列表。未拆解速度/高度/run token，未计算指标或状态。', '',
        f'单文件内容上限 {args.max_bytes} bytes（{args.max_bytes / 1048576:g} MiB）。',
        'SHA256 仅针对已完整读取的原始字节；未读取时为空并给出原因。mtime 仅表示快照，',
        '不能据此选择主版本。完整路径始终保留，不删除、合并或排除同名/同哈希文件。', '',
        '已遍历目录（全部，相对输入根）：', '',
        *[f'- `{p}`' for p in visited], '',
        '跳过、链接、访问失败与覆盖缺口：', '',
    ]
    problems = [r for r in rows if r['read_status'] != 'parsed']
    if not events and not problems:
        lines.append('无。全部发现的 CSV 均已读取并解析；没有超限文件、符号链接或未覆盖子目录。')
    else:
        lines.extend(f'- `{p}`：{kind}；{md(reason)}' for p, kind, reason in events)
        lines.extend(f"- `{r['source_relative_path']}`：{r['read_status']}；{md(r['pending_notes'])}"
                     for r in problems)
    root_rows = [r for r in rows if r['method_directory'] == 'shared/ownership_pending']
    lines.extend(['', f'根级共享/归属待定 CSV：{len(root_rows)} 个。', '',
                  '非 CSV 文件仅登记名称，不读取其内容：', '',
                  *[f'- `{p}`' for p in other_files], '',
                  '## B．按方法逐文件清单', '',
                  '以下路径均相对于输入根。所有角色/配置判断仅用于后续核验的分流，',
                  '不代表 ATE、SR、FPS、内存等统计口径已验证。语义 unknown 不等于“无语义”。', ''])
    for method in methods + (['shared/ownership_pending'] if root_rows else []):
        subset = [r for r in rows if r['method_directory'] == method]
        candidates = [r for r in subset if r['file_role'] == 'run_metrics_candidate']
        lines.extend([f'### `{method}`', '', f'逐次指标候选 {len(candidates)} 个。', '',
                      '| 候选路径 | 记录数 | 模态 | 语义 | 评测范围 | 配置线索 |',
                      '|---|---:|---|---|---|---|'])
        if not candidates:
            lines.append('| 无候选文件 | — | unknown | unknown | unknown | 待核验 |')
        for r in candidates:
            lines.append('| ' + ' | '.join(md(x) for x in [
                f"`{r['source_relative_path']}`", r['record_count'] if r['record_count'] != '' else 'unknown',
                r['modality'], r['semantic_usage'], r['evaluation_scope'],
                ', '.join(json.loads(r['configuration_clues_json'])) or 'unknown']) + ' |')
        others = [r for r in subset if r['file_role'] != 'run_metrics_candidate']
        lines.extend(['', '| 其它 CSV 路径 | 角色 | 记录数 |', '|---|---|---:|'])
        for r in others:
            lines.append(f"| `{r['source_relative_path']}` | {r['file_role']} | "
                         f"{r['record_count'] if r['record_count'] != '' else 'unknown'} |")
        lines.append('')
    lines.extend(['## C．配置区别与同名文件', '',
                  '### Hier-SLAM：分别定位', '',
                  '| 逐次候选实际路径 | 模态 | 语义 | 范围 | 记录数 |',
                  '|---|---|---|---|---:|'])
    for rel in ['hierslam/rgbd_metrics.csv', 'hierslam/semantic_metrics.csv',
                'hierslam/rgbd_whole_trajectory/rgbd_metrics.csv']:
        r = next((r for r in rows if r['source_relative_path'] == rel), None)
        if r:
            lines.append(f"| `{rel}` | {r['modality']} | {r['semantic_usage']} | "
                         f"{r['evaluation_scope']} | {r['record_count']} |")
        else:
            lines.append(f'| `{rel}` | 未定位 | unknown | unknown | unknown |')
    lines.extend(['', '上述配置依据 README 的用户已确认规则；500 帧不改写为固定距离。',
                  '外层与内层无语义 RGBD 分开保留，不混在一起排名。semantic 的完整模态仍待核验。',
                  'Hier-SLAM 的 summary 全部标为 mixed/unknown，不从目录继承整表范围。', '',
                  '### 其它配置线索与 summary 样例', '',
                  '- calib/nocalib 按实际路径分别登记；名称只提示校准配置差异，不推断传感器模态。',
                  '- mono/rgbd/semantic 依据已确认命名保留；除 Hier-SLAM 已确认配置外，',
                  '  没有证据的评测范围保持 unknown，不默认完整轨迹。', '',
                  '下表展示 MASt3R-SLAM、SGS-SLAM、Hier-SLAM 的 summary 分组标签样例；',
                  '其余文件的同类样例保存在逐文件清单中。分组标签不等于已核实配置。', '',
                  '| 文件 | 原始配置/分组标签样例（每列最多 3 个） |', '|---|---|'])
    for r in rows:
        if (r['method_directory'] in {'MASt3R-SLAM', 'SGS-SLAM', 'hierslam'}
                and json.loads(r['configuration_samples_json'] or '{}')):
            lines.append(f"| `{r['source_relative_path']}` | {md(r['configuration_samples_json'])} |")
    header_groups = defaultdict(list)
    for r in rows:
        if r['file_role'] == 'run_metrics_candidate':
            header_groups[r['raw_columns_json']].append(r['source_relative_path'])
    lines.extend(['', '### 逐次候选的原始表头差异', '',
                  '| 原始列名 | 文件数 | 定位 |', '|---|---:|---|'])
    for header, paths in sorted(header_groups.items()):
        location = '、'.join(f'`{p}`' for p in paths) if len(paths) <= 4 else '详见 CSV 清单逐文件表头'
        lines.append(f'| {md(header)} | {len(paths)} | {location} |')
    lines.extend(['', '- 相同字段名不代表测量与统计口径相同。',
                  '- 各候选文件的记录数见 B 节；原因与预期运行计划尚未核验，',
                  '  不据此推导缺失、失败或成功率。', ''])
    paths = {r['source_relative_path'] for r in rows}
    if {'SGS-SLAM/semantic_metrics.csv', 'SGS-SLAM/summary_metrics_by_scene_rgbd.csv'} <= paths:
        lines.extend(['- `SGS-SLAM/semantic_metrics.csv` 与',
                      '  `SGS-SLAM/summary_metrics_by_scene_rgbd.csv` 的名称线索不同；',
                      '  来源对应关系待第 4 步核验，不因此把 semantic 改判为 RGBD。', ''])
    names = defaultdict(list)
    hashes = defaultdict(list)
    for r in rows:
        names[Path(r['source_relative_path']).name].append(r['source_relative_path'])
        if r['sha256']:
            hashes[r['sha256']].append(r['source_relative_path'])
    lines.extend(['', '### 同名文件：只列路径分组，不判重复', '',
                  '| 文件名 | 独立来源路径 |', '|---|---|'])
    for name, paths in sorted(names.items()):
        if len(paths) > 1:
            lines.append(f"| `{name}` | " + '<br>'.join(f'`{p}`' for p in paths) + ' |')
    lines.extend(['', '### 相同 SHA256：仅内容相同快照', ''])
    same_hash = [(digest, paths) for digest, paths in sorted(hashes.items()) if len(paths) > 1]
    if not same_hash:
        lines.append('未发现相同 SHA256 的不同路径文件。')
    for digest, paths in same_hash:
        lines.append(f'- `{digest}`：' + '、'.join(f'`{p}`' for p in paths) + '。全部保留。')
    lines.extend(['', '## D．后续待核验问题', '',
                  '### 优先从指标、说明或统计代码核验（本轮不读取源 .py 实现）', '',
                  '- 表头中的 ATE/误差、FPS、runtime、内存字段的单位、对齐与计算口径；',
                  '  区分单次误差分布 std 和重复运行 RMSE 的 std。',
                  '- SR 的实际分子、分母与上游有效性；缺失、未运行、失败标记及覆盖范围。',
                  '- 标识 token 顺序、速度/高度映射和重复编号提取规则；当前只保留原始样例。',
                  '- calib/nocalib 的实际含义；semantic 的完整输入模态；各方法未知评测范围。',
                  '- summary 的配置标签、来源逐次文件和聚合粒度，尤其是 Hier-SLAM 的混合范围风险。',
                  '- 表头是否一致不等于测量口径一致；文件记录数差异不直接解释为成功率或失败数。', '',
                  '### 可能需要用户补充（先查已有依据，不重复询问已确认规则）', '',
                  '- 若目录内指标、说明与统计代码都未记录实际采集/评估配置、预期运行计划或',
                  '  summary 来源，则需用户补充当时配置和来源记录；本轮尚未认定这些资料缺失。',
                  '- 对无法从记录判别的“未运行／未导出／失败”以及是否另有未提供数据，',
                  '  后续再提出具体路径问题，不自行填补或猜测。', '',
                  '可供后续定位的源脚本名称（仅列名；未读取、导入或运行）：', '',
                  *[f'- `{p}`' for p in scripts], '',
                  '## E．进入第 4 步的条件', ''])
    ready = [r for r in rows if r['file_role'] == 'run_metrics_candidate'
             and r['read_status'] == 'parsed']
    pending = [r for r in rows if r['file_role'] in {'unknown', 'other_csv'}
               or r['read_status'] != 'parsed']
    lines.extend([
        f'- {len(ready)} 个已解析逐次候选可进入字段/口径核验（具体路径见 B 节及 CSV 清单）；',
        '  它们尚不是可直接合并、计算 SR 或排名的标准化输入。',
        f'- {counts["aggregate_summary"]} 个 summary 可作为后续旧表/来源核对材料，不作为逐次样本。',
        f'- 用途或读取状态需暂缓的文件 {len(pending)} 个。',
        *[f"  - `{r['source_relative_path']}`：{r['file_role']} / {r['read_status']}" for r in pending],
        '- 未知范围/模态属于下一步核验事项，不阻止其它可读候选进入核验。',
        '- 本轮未标准化、拼接、统计、绘图或重跑实验；derived_data 未写入数据。',
        '- 完成盘点后停止。第 4 步：确认字段与统计口径，等待用户下达任务。', '',
    ])
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-root', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--max-bytes', type=int, required=True)
    parser.add_argument('--overwrite', action='store_true',
                        help='Only after reviewing existing project-generated outputs')
    args = parser.parse_args()
    if args.input_root != INPUT_ROOT or args.input_root.is_symlink():
        parser.error('Only the exact project input root is allowed, without symlinks')
    if args.max_bytes <= 0:
        parser.error('--max-bytes must be positive')
    for path in [args.input_root, args.output_dir]:
        if any(p.is_symlink() for p in [path, *path.parents]):
            parser.error(f'Symlink path component is not allowed: {path}')
    if not args.input_root.is_dir():
        parser.error('Input root is missing or inaccessible; no fallback')
    if (not args.output_dir.is_dir()
            or not args.output_dir.resolve().is_relative_to(WORKSPACE.resolve())
            or args.output_dir.resolve().is_relative_to(INPUT_ROOT.resolve())):
        parser.error('Output must be an existing directory inside the project workspace')
    outputs = [args.output_dir / name for name in ['03_input_inventory.csv', '03_input_inventory.md']]
    if any(p.is_symlink() for p in outputs):
        parser.error('Output symlinks are never overwritten or followed')
    if any(p.exists() for p in outputs) and not args.overwrite:
        parser.error('Output already exists: review it before explicitly using --overwrite')
    csv.field_size_limit(args.max_bytes)
    paths, methods, visited, events, scripts, other_files = discover(args.input_root)
    rows = [file_record(path, args.input_root, args.max_bytes) for path in paths]
    mode = 'w' if args.overwrite else 'x'
    with outputs[0].open(mode, encoding='utf-8', newline='') as out:
        writer = csv.DictWriter(out, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    with outputs[1].open(mode, encoding='utf-8') as out:
        out.write(report(rows, methods, visited, events, scripts, other_files, args))
    print(js({'method_directories': methods, 'csv_files': len(rows),
              'roles': dict(Counter(r['file_role'] for r in rows)),
              'read_status': dict(Counter(r['read_status'] for r in rows)),
              'coverage_events': events, 'visited_directories': visited,
              'outputs': [str(p) for p in outputs]}))


if __name__ == '__main__':
    main()
