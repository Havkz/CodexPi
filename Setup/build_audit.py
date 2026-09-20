"""Create a lossless, line-addressed audit from the user's specification.

Every nonempty source line remains represented, including prose and examples.
The dashboard password is redacted; the source is never copied into Git.
Re-running preserves recorded evidence and fails if the specification changed.
"""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path('C:/CODEXPI_GOAL.md')


def main():
    raw = SOURCE.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    path = ROOT / 'docs' / 'requirement-audit.json'
    if path.exists():
        audit = json.loads(path.read_text(encoding='utf-8'))
        if audit['source_sha256'] != digest:
            raise SystemExit('Specification changed: audit needs explicit reconciliation')
    else:
        lines = raw.decode('cp1252').splitlines()
        section = ''
        entries = []
        for number, line in enumerate(lines, 1):
            if not line.strip():
                continue
            if line.startswith('# '):
                section = line[2:]
            entries.append({'id': f'L{number:04}', 'section': section,
                            'text': '[dashboard password redacted]' if number == 122 else line,
                            'status': 'pending', 'evidence': []})
        audit = {'source': str(SOURCE), 'source_sha256': digest,
                 'source_lines': len(lines), 'complete': False, 'requirements': entries}
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    counts = {}
    for row in audit['requirements']:
        counts[row['status']] = counts.get(row['status'], 0) + 1
    print(json.dumps({'source_sha256': digest, 'entries': len(audit['requirements']),
                      'states': counts}, indent=2))


if __name__ == '__main__':
    main()
