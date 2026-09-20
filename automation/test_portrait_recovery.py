"""Incident classification and envelope redaction for portrait transfer failures."""
from __future__ import annotations
import json
from pathlib import Path
import unittest
import portrait_recovery as recovery


class PortraitRecoveryTests(unittest.TestCase):
    def test_mounted_path_is_schema_mismatch_not_security_denial(self):
        result = recovery.classify_blocked_file_reference(
            reference_form='mounted_path',
            schema_expected='runtime_file_reference',
        )
        self.assertEqual(result['class'], 'schema_mismatch')
        self.assertEqual(result['confidence'], 'observed')
        self.assertFalse(result['retry_same_reference'])
        self.assertEqual(result['next_action'], 'retry_once_with_runtime_file_reference')
        self.assertFalse(result['disable_hourly_task'])

    def test_runtime_file_reference_is_not_automatically_retried(self):
        result = recovery.classify_blocked_file_reference(
            reference_form='runtime_file_reference',
            provider_contacted=None,
            same_runtime_reference_already_tried=True,
        )
        self.assertEqual(result['class'], 'connector_file_binding_denied')
        self.assertEqual(result['confidence'], 'hypothesis')
        self.assertEqual(result['denied_layer'], 'unknown')
        self.assertFalse(recovery.should_retry_runtime_reference(result))
        self.assertFalse(recovery.should_schedule_capability_retry(result))
        self.assertEqual(result['next_action'], 'google_independent_github_handoff')
        self.assertTrue(result['do_not_regenerate'])
        self.assertFalse(result['disable_hourly_task'])

    def test_provider_not_contacted_narrows_layer_but_does_not_claim_root_cause(self):
        result = recovery.classify_blocked_file_reference(
            reference_form='runtime_file_reference',
            provider_contacted=False,
        )
        self.assertEqual(result['denied_layer'], 'runtime_or_connector_before_provider')
        self.assertEqual(result['confidence'], 'observed_layer_incomplete')
        self.assertNotEqual(result['class'], 'fixed')

    def test_redacts_signed_urls_tokens_and_file_ids(self):
        envelope = {
            'action': 'batch_update_document',
            'error': 'BLOCKED_FILE_REFERENCE',
            'uri': 'https://files.oaiusercontent.com/private/abc.png?sv=2026&sig=supersecret',
            'file_uri': 'file_000000007b8481f88be021d71ff42316',
            'image_uris': ['file_000000007b8481f88be021d71ff42316'],
            'authorization': 'Bearer tok_live_secret',
            'message': 'failed https://example.blob.core.windows.net/x?sig=abc123 for /mnt/data/file-abc.png',
            'correlation_id': 'req_123',
            'http_status': None,
        }
        redacted = recovery.redact_envelope(envelope)
        dumped = json.dumps(redacted)
        self.assertNotIn('supersecret', dumped)
        self.assertNotIn('tok_live_secret', dumped)
        self.assertNotIn('file_000000007b8481f88be021d71ff42316', dumped)
        self.assertNotIn('/mnt/data/file-abc.png', dumped)
        self.assertEqual(redacted['action'], 'batch_update_document')
        self.assertEqual(redacted['error'], 'BLOCKED_FILE_REFERENCE')
        self.assertEqual(redacted['correlation_id'], 'req_123')
        self.assertEqual(redacted['file_uri'], 'runtime_file_reference')
        self.assertEqual(redacted['image_uris'], ['runtime_file_reference'])
        self.assertIn('[redacted]', redacted['uri'])
        self.assertEqual(redacted['authorization'], '[redacted]')

    def test_incident_sets_help_needed_when_bytes_are_not_preserved(self):
        record = recovery.incident_record(
            player_id=67076,
            player_name='Awa Fam',
            slug='awa-fam',
            stage='master_preservation_and_temporary_doc_handoff',
            error_code='BLOCKED_FILE_REFERENCE',
            reference_form='runtime_file_reference',
            action_name='upload_file',
            envelope={'error': 'BLOCKED_FILE_REFERENCE', 'file_uri': 'file_abc'},
            provider_contacted=None,
            execution_context='scheduled',
            bytes_preserved=False,
            preserved_master_id=None,
            source_sha256='abc',
        )
        self.assertTrue(record['help_needed'])
        self.assertIsNone(record['next_retry_at'])
        self.assertTrue(record['raw_error_envelope_captured'])
        self.assertEqual(record['error_envelope_redacted']['file_uri'], 'runtime_file_reference')
        self.assertFalse(record['disable_hourly_task'])

    def test_current_awa_and_ashten_incidents_remain_binding_denials_after_byte_preservation(self):
        root = Path(__file__).resolve().parents[1]
        for slug in ('awa-fam', 'ashten-prechtel'):
            incident = json.loads((root / 'content/portrait-recovery-incidents' / f'{slug}.json').read_text())
            classification = recovery.classify_blocked_file_reference(
                reference_form='runtime_file_reference',
                provider_contacted=incident.get('provider_contacted'),
                same_runtime_reference_already_tried=incident.get('attempt_count', 0) > 1,
            )
            self.assertEqual(classification['class'], 'connector_file_binding_denied')
            self.assertNotEqual(classification['class'], 'fixed')
            self.assertFalse(classification['schedule_retry'])
            self.assertTrue(incident['bytes_preserved'])
            self.assertTrue(incident['preserved_master_id'])
            self.assertEqual(incident['error_code'], 'BLOCKED_FILE_REFERENCE')
            self.assertFalse(incident['raw_error_envelope_captured'])
            self.assertIsNone(incident['next_retry_at'])
            self.assertFalse(incident['help_needed'])
            self.assertFalse(incident['disable_hourly_task'])
            self.assertEqual(incident['classification']['class'], 'connector_file_binding_denied')
            self.assertIn(
                incident['classification']['next_action'],
                ('await_cursor_publication_and_live_verification', 'google_independent_github_handoff'),
            )


if __name__ == '__main__':
    unittest.main()
