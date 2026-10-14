"""Isolated regression for both verbosity transcript readers; no live state writes."""
import importlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parent / 'upstream/token-optimizer/skills/token-optimizer/scripts'
sys.path.insert(0, str(SCRIPTS))
SID = '0e37aafe-6625-457c-9d94-68e7ea73e45c'


class VerbosityMemoryTests(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory(prefix='codexpi-verbosity-')
        self.addCleanup(self.scratch.cleanup)
        self.root = Path(self.scratch.name)
        env = patch.dict(os.environ, TOKEN_OPTIMIZER_RUNTIME='codex',
                         TOKEN_OPTIMIZER_SNAPSHOT_DIR=str(self.root))
        env.start()
        self.addCleanup(env.stop)
        self.m = importlib.reload(importlib.import_module('measure'))
        self.cache = self.root / f'quality-cache-{SID}.json'
        self.m._quality_cache_path_for = lambda filepath=None: self.cache
        self.cache.write_text(json.dumps({
            'fill_pct': 47, 'score': 73, 'session_efficiency': 60,
            'nudge_count': 0, 'last_nudge_time': 0}), encoding='utf-8')
        self.transcript = self.root / 'transcript.jsonl'

    def transcript_with_noise(self, outputs):
        assistant = lambda value: json.dumps({
            'type': 'assistant', 'message': {'usage': {'output_tokens': value}}})
        # Invalid, non-object and oversized records must not change turn indexes.
        self.transcript.write_text('\n'.join([
            assistant(outputs[0]), '{invalid', '[]',
            json.dumps({'ignored': '\u00e4' * 1000}, ensure_ascii=False),
            *(assistant(value) for value in outputs[1:])]), encoding='utf-8')
        original = Path.read_text

        def no_whole_read(path, *args, **kwargs):
            if path == self.transcript:
                raise AssertionError('transcript must be streamed')
            return original(path, *args, **kwargs)

        guard = patch.object(Path, 'read_text', no_whole_read)
        guard.start()
        self.addCleanup(guard.stop)
        import codex_session
        # Even above the file cap, calibration needs the whole timeline, not a tail.
        limits = patch.multiple(codex_session, MAX_PARSE_FILE_BYTES=1,
                                LARGE_FILE_TAIL_BYTES=1, MAX_JSONL_LINE_CHARS=128)
        limits.start()
        self.addCleanup(limits.stop)

    def test_pre_nudge_baseline_streams_and_keeps_early_turns(self):
        self.transcript_with_noise([800, 600, 400])
        logged = []
        self.m._log_savings_event = lambda *args, **kwargs: logged.append((args, kwargs))
        result = self.m.run_verbosity_steer(str(self.transcript), session_id=SID)
        self.assertTrue(result)
        details = [kwargs['detail'] for args, kwargs in logged if args[0] == 'verbosity_steer']
        self.assertEqual(len(details), 1)
        self.assertIn('pre_avg_out=600 pre_turns=3', details[0])

    def test_prior_nudge_calibration_streams_and_stays_idempotent(self):
        self.m._log_savings_event('verbosity_steer', 0, session_id=SID,
                                 detail='pre_avg_out=800 pre_turns=2')
        self.transcript_with_noise([800, 800, 400, 500])
        self.assertEqual(self.m._calibrate_prior_verbosity_nudges(SID, self.transcript), 700)
        self.assertEqual(self.m._calibrate_prior_verbosity_nudges(SID, self.transcript), 0)
        conn = self.m._init_trends_db()
        try:
            rows = conn.execute("SELECT tokens_saved FROM savings_events "
                                "WHERE event_type='verbosity_steer_measured'").fetchall()
        finally:
            conn.close()
        self.assertEqual(rows, [(700,)])


if __name__ == '__main__':
    unittest.main()
