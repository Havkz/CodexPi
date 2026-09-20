import json
import os
from pathlib import Path
import secrets
import sys
import tempfile
import time
import unittest
import uuid

from app.windows_worker import Worker, execute, protect_secret, relative_path, validate_job


class WorkerTests(unittest.IsolatedAsyncioTestCase):
    async def test_native_execution_exit_output_timeout(self):
        with tempfile.TemporaryDirectory() as directory:
            result = await execute([sys.executable, '-c',
                'import sys; print("native-output"); print("native-error", file=sys.stderr); sys.exit(7)'], directory, 10)
            self.assertEqual(result['exit_code'], 7)
            self.assertIn('native-output', result['stdout'])
            self.assertIn('native-error', result['stderr'])
            result = await execute([sys.executable, '-c', 'import time; time.sleep(30)'], directory, 1)
            self.assertTrue(result['timed_out'])
            self.assertNotEqual(result['exit_code'], 0)

    def test_validation_and_restart_does_not_repeat(self):
        job = {'type': 'job', 'job_id': str(uuid.uuid4()), 'slug': 'test-project',
               'repo': 'test/test-project', 'commit': 'a' * 40, 'timeout': 10,
               'argv': ['python', '--version'], 'artifacts': ['dist/result.txt']}
        validate_job(job)
        for path in ('../outside', '..\\outside', 'C:\\outside', '\\outside', 'file:stream',
                     '//server/share', 'nested/../../outside', ''):
            with self.subTest(path=path), self.assertRaises(ValueError):
                relative_path(path)
        with tempfile.TemporaryDirectory() as directory:
            worker = Worker(directory, secrets.token_hex(32), 'http://unused')
            worker.db.execute('INSERT INTO jobs VALUES (?,?,?,?,?)',
                (job['job_id'], json.dumps(job), 'running', None, time.time()))
            worker.db.close()
            recovered = Worker(directory, secrets.token_hex(32), 'http://unused')
            row = recovered.db.execute('SELECT * FROM jobs').fetchone()
            self.assertEqual(row['status'], 'finished')
            self.assertTrue(json.loads(row['result'])['outcome_unknown'])
            self.assertIsNone(recovered.execution)
            recovered.db.close()

    @unittest.skipUnless(os.name == 'nt', 'Windows DPAPI only')
    def test_dpapi_current_user_roundtrip(self):
        secret = secrets.token_bytes(32)
        encrypted = protect_secret(secret)
        self.assertNotIn(secret, encrypted)
        self.assertEqual(protect_secret(encrypted, decrypt=True), secret)
        with self.assertRaises(OSError):
            protect_secret(b'not a DPAPI credential', decrypt=True)


if __name__ == '__main__':
    unittest.main()
