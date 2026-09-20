import unittest

from Setup.build_audit import reconcile


class AuditTests(unittest.TestCase):
    def test_append_preserves_evidence_and_rejects_edits(self):
        initial = reconcile(b'# Original\n\nRequired\n')
        initial['requirements'][1].update(status='tested', evidence=['actual check'])
        appended = '# Original\n\nRequired\n\nErgänzende verbindliche Design-Anforderung\n1. DESIGN\n- Dark mode\n'.encode('cp1252')
        with self.assertRaises(ValueError):
            reconcile(appended, initial)
        updated = reconcile(appended, initial, True)
        self.assertEqual(updated['requirements'][1], initial['requirements'][1])
        self.assertEqual(updated['requirements'][-1]['status'], 'pending')
        self.assertEqual(updated['requirements'][-1]['section'], 'DESIGN: 1. DESIGN')
        self.assertEqual(len(updated['source_revisions']), 1)
        self.assertFalse(updated['complete'])
        for edited in (b'# Original\n\nChanged\n', b'# Original\n'):
            with self.assertRaises(ValueError):
                reconcile(edited, initial, True)


if __name__ == '__main__':
    unittest.main()
