"""Create a lossless, line-addressed audit from the user's specification.

Every nonempty source line remains represented, including prose and examples.
The dashboard password is redacted; the source is never copied into Git.
Re-running preserves recorded evidence. Explicit append acceptance reconciles
new requirements without accepting edits or losing evidence for existing lines.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path('C:/CODEXPI_GOAL.md')
sys.path.insert(0, str(ROOT))
from app.common import atomic_write


def reconcile(raw, previous=None, accept_append=False):
    digest = hashlib.sha256(raw).hexdigest()
    lines = raw.decode('cp1252').splitlines()
    changed = previous and previous['source_sha256'] != digest
    if changed and not accept_append:
        raise ValueError('Specification changed: audit needs explicit reconciliation')
    previous_rows = {entry['id']: entry for entry in previous['requirements']} if previous else {}
    section, design = '', False
    entries = []
    for number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        if line.startswith('Ergänzende verbindliche Design-Anforderung'):
            design = True
            section = 'DESIGN: introduction'
        if line.startswith('# '):
            section = line[2:]
        elif design and re.match(r'^\d+\. [A-ZÄÖÜ]', line):
            section = 'DESIGN: ' + line
        text = '[dashboard password redacted]' if number == 122 else line
        ident = f'L{number:04}'
        old = previous_rows.get(ident)
        if previous and number <= previous['source_lines'] and (old is None or old['text'] != text):
            raise ValueError('Existing requirement changed at ' + ident + '; explicit edit reconciliation required')
        entries.append({**old, 'section': section} if old else {
            'id': ident, 'section': section, 'text': text, 'status': 'pending', 'evidence': []})
    if previous and (len(lines) < previous['source_lines'] or not set(previous_rows) <= {r['id'] for r in entries}):
        raise ValueError('Existing requirements were removed; refusing evidence loss')
    revisions = list(previous.get('source_revisions', [])) if previous else []
    if changed:
        revisions.append({'source_sha256': previous['source_sha256'], 'source_lines': previous['source_lines']})
    return {**(previous or {}), 'source': str(SOURCE), 'source_sha256': digest, 'source_lines': len(lines),
            'source_revisions': revisions, 'complete': False, 'requirements': entries}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--accept-append', action='store_true', help='Accept only appended specification requirements')
    args = parser.parse_args()
    raw = SOURCE.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    path = ROOT / 'docs' / 'requirement-audit.json'
    previous = json.loads(path.read_text(encoding='utf-8')) if path.exists() else None
    audit = reconcile(raw, previous, args.accept_append)
    atomic_write(path, json.dumps(audit, ensure_ascii=False, indent=2) + '\n', 0o644)
    counts = {}
    for row in audit['requirements']:
        counts[row['status']] = counts.get(row['status'], 0) + 1
    print(json.dumps({'source_sha256': digest, 'entries': len(audit['requirements']),
                      'states': counts}, indent=2))


if __name__ == '__main__':
    main()
