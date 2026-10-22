"""Read a version-bound editorial amendment; never recompute analysis or write files."""
from functools import lru_cache
import json

from version_support import CANONICAL, current_version, digest, local


@lru_cache(maxsize=4)
def reviewed_patch(root):
    version = current_version(root)
    if version is None:
        return {}
    rel = 'updates/' + version['current_version'] + '/claim_review/editorial_patch.json'
    path = local(CANONICAL, rel)
    if not path.is_file():
        return {}
    patch = json.loads(path.read_text(encoding='utf-8'))
    if patch['current_version'] != version['current_version']:
        raise ValueError('Editorial review belongs to a different data version')
    for evidence, expected in patch['evidence_hashes'].items():
        if digest(local(root, evidence)) != expected:
            raise ValueError('Reviewed evidence changed; reassess before applying wording: ' + evidence)
    return patch


def apply_reviewed_rows(root, kind, rows):
    """Apply only explicitly reviewed registration fields, on unchanged evidence."""
    patch = reviewed_patch(root)
    edits = patch.get(kind, {})
    key = {'claims': 'claim_id', 'cases': 'case_review_id'}[kind]
    by_id = {row[key]: row for row in rows}
    if set(edits) - set(by_id):
        raise ValueError('Reviewed registration missing from current build')
    for identity, fields in edits.items():
        by_id[identity].update(fields)
    return rows


def reviewed_paragraph(root, paragraph_id, text):
    return reviewed_patch(root).get('paragraphs', {}).get(paragraph_id, text)
