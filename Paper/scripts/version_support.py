"""Explicit, frozen data-version context for the existing analysis entry points."""
import hashlib
import json
import os
from pathlib import Path

CANONICAL = Path('/home/yuan/SLAM/codex_review/benchmark_analysis')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def workspace(default_path=CANONICAL):
    p = Path(os.environ.get('BENCHMARK_ANALYSIS_WORKSPACE', str(default_path)))
    if p.is_symlink() or any(x.is_symlink() for x in p.parents):
        raise ValueError('Linked workspace rejected')
    p = p.resolve()
    if p != CANONICAL and not (p.is_relative_to(CANONICAL / 'updates') and p.name == 'staging'):
        raise ValueError('Workspace override must be this project or an update staging directory')
    return p


def local(root, rel):
    p = Path(root) / rel
    if Path(rel).is_absolute() or not p.resolve().is_relative_to(Path(root).resolve()):
        raise ValueError('Out-of-workspace version path: ' + str(rel))
    if p.is_symlink() or any(x.is_symlink() for x in p.parents):
        raise ValueError('Linked version path rejected')
    return p


def current_version(root=None):
    root = workspace() if root is None else Path(root)
    p = root / 'reports/current_input_manifest.json'
    if not p.exists():
        return None
    info = json.loads(p.read_text())
    manifest = local(root, info['manifest']['path'])
    if digest(manifest) != info['manifest']['sha256']:
        raise ValueError('Current input manifest hash mismatch')
    return info


def source_read_path(root, relative, context=None):
    """Read a bound source snapshot without changing its original provenance path."""
    context = current_version(root) if context is None else context
    relative = Path(relative)
    if relative.is_absolute() or '..' in relative.parts:
        raise ValueError('Invalid source-relative path')
    frozen = (context or {}).get('frozen_source_root')
    if frozen:
        expected = 'updates/' + context['current_version'] + '/current_sources'
        if frozen != expected:
            raise ValueError('Frozen source root does not belong to the selected version')
        return local(CANONICAL, str(Path(frozen) / relative))
    return Path((context or {}).get('source_input_root',
        '/home/yuan/SLAM/AirSim-Visual-SLAM-Research-Toolkit/Benchmark/experiment_data')) / relative


def expected_inputs(stage, fallback, workspace=None):
    root = Path(workspace) if workspace is not None else globals()['workspace']()
    version = current_version(root)
    if version is None:
        return fallback
    context = json.loads(local(root, 'reports/current_build_context.json').read_text())
    if context['current_version'] != version['current_version'] or context['input_manifest_sha256'] != version['manifest']['sha256']:
        raise ValueError('Build context belongs to a different input version')
    item = context['stages'][str(stage)]
    expected = item['inputs']
    if set(expected) != set(fallback):
        raise ValueError('Stage input allowlist changed: ' + str(stage))
    for rel, sha in expected.items():
        if digest(local(root, rel)) != sha:
            raise ValueError('Frozen dependency changed: ' + rel)
    return expected


def check_version_history(root=None):
    root = workspace() if root is None else Path(root)
    v = current_version(root)
    if v is None:
        return False
    archive = local(CANONICAL, v['backup_manifest']['path'])
    if digest(archive) != v['backup_manifest']['sha256']:
        raise ValueError('Backup manifest changed')
    entries = json.loads(archive.read_text())['files']
    for entry in entries:
        if digest(local(archive.parent, entry['backup_path'])) != entry['sha256']:
            raise ValueError('Old-version backup changed: ' + entry['path'])
    for rel, sha in v['protected_history'].items():
        if digest(local(root, rel)) != sha:
            raise ValueError('Protected historical evidence changed: ' + rel)
    return True


def sgs_external_ape_verified(row):
    """Version-bound SGS run4/5/6 audit; never relabel historical native bytes."""
    return (row.get('source_sha256') == '1958020f0083595119c105ab76c5895be4560cdbd14b7cb56f6bbdcea5e7f6ac'
            and 'Sim(3)' in row.get('alignment_status', '')
            and row.get('rmse_unit_status', '').startswith('m;'))


def sgs_accuracy_note(row):
    if sgs_external_ape_verified(row):
        return ('本版SGS接入新run 4/5/6，采用C2W全帧、整数帧索引精确关联、Sim(3)对齐的外部evo平移APE RMSE(m)。'
                '旧run 1/2/3的W2C刚体对齐mean translation error与本版定义和批次不同，不能据数值差宣称精度提升。'
                '新SGS原生完成信号与GPU_RESERVED GiB组件由本次运行单独提取，不继承旧批次；原生完成信号不是SR@80/90/95。'
                '全17方法/24配置继续参与分析；本轮论文未同步。')
    return ('SGS旧native为W2C平移列经Horn刚体R+t对齐的mean translation error，非camera-center APE RMSE。'
            '作者已恢复17方法/24配置主线，SGS可用于真实定义下的配置内趋势，不并入不兼容的绝对误差排名。')
