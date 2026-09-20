#!/usr/bin/env python3
"""Classify portrait transfer failures and redact incident envelopes.

This does not generate images, call connectors, or rewrite file bytes.
BLOCKED_FILE_REFERENCE is recorded honestly: one success is not a root-cause fix.
"""
from __future__ import annotations
import json
import re
from typing import Any
from urllib.parse import parse_qsl, urlsplit, urlunsplit

SECRET_QUERY_KEYS = {
    'access_token', 'api_key', 'auth', 'expires', 'key', 'se', 'sig', 'signature',
    'sk', 'sp', 'spr', 'sr', 'st', 'sv', 'token', 'x-amz-credential',
    'x-amz-security-token', 'x-amz-signature',
}
SECRET_HEADER_KEYS = {
    'authorization', 'cookie', 'set-cookie', 'x-api-key', 'x-goog-api-key',
    'x-access-token',
}
URL_IN_TEXT = re.compile(r'https?://[^\s\"\'<>]+', re.I)
FILE_REF = re.compile(r'\bfile_[0-9a-f]{8,}\b', re.I)
MOUNTED_PATH = re.compile(r'(?:/mnt/data|/mnt/user-data)[^\s\"\'<>]*')
SIGNED_QUERY = re.compile(r'(?i)([?&](?:sig|signature|token|access_token|sv|se|sp|spr|sr|st|sk)=)[^&\s\"\']+')


def classify_reference_form(value: Any) -> str:
    if value is None or value == '':
        return 'missing'
    text = value if isinstance(value, str) else json.dumps(value, sort_keys=True)
    if text.startswith('file_'):
        return 'runtime_file_reference'
    if text.startswith('/mnt/data') or text.startswith('/mnt/user-data') or text.startswith('/mnt/'):
        return 'mounted_path'
    if text.startswith('https://') or text.startswith('http://'):
        return 'https_url'
    if isinstance(value, dict):
        keys = {str(k).lower() for k in value}
        if {'id', 'mime_type', 'download_link'} <= keys or 'openaifileidrefs' in keys:
            return 'structured_file_object'
    return 'other'


def classify_blocked_file_reference(
    *,
    reference_form: str,
    schema_expected: str | None = None,
    provider_contacted: bool | None = None,
    provider_http_status: int | None = None,
    same_runtime_reference_already_tried: bool = False,
) -> dict:
    """Return a classification. Confidence is explicit; unknown layers stay unknown.

    Proven:
      - A mounted-path / wrong-form call can produce BLOCKED_FILE_REFERENCE and
        later succeed with the runtime file_... form (Aneesah Morrow).
      - The exact runtime file_... form can still be rejected by Drive and Docs
        in the same run (Awa Fam, Ashten Prechtel).
      - The same form can fail, then succeed later without regeneration
        (Ashlon Jackson). That does not identify which layer recovered.

    Not proven from saved incidents:
      - runtime attachment resolution vs connector rewrite vs auth/egress vs
        upstream Google. Raw envelopes were not stored.
    """
    if reference_form in {'mounted_path', 'other'} and schema_expected == 'runtime_file_reference':
        return {
            'class': 'schema_mismatch',
            'confidence': 'observed',
            'retry_same_reference': False,
            'schedule_retry': False,
            'next_action': 'retry_once_with_runtime_file_reference',
            'disable_hourly_task': False,
        }
    if provider_contacted is True and provider_http_status and provider_http_status >= 500:
        return {
            'class': 'upstream_provider_unavailable',
            'confidence': 'observed',
            'retry_same_reference': False,
            'schedule_retry': True,
            'next_action': 'bounded_backoff_then_fresh_handoff',
            'disable_hourly_task': False,
        }
    if provider_contacted is True and provider_http_status in {401, 403}:
        return {
            'class': 'upstream_authorization',
            'confidence': 'observed',
            'retry_same_reference': False,
            'schedule_retry': False,
            'next_action': 'report_smallest_owner_authorization_action',
            'disable_hourly_task': False,
        }
    if reference_form == 'runtime_file_reference':
        layer = 'unknown'
        if provider_contacted is False:
            layer = 'runtime_or_connector_before_provider'
        elif provider_contacted is True:
            layer = 'provider_or_connector_after_dispatch'
        return {
            'class': 'connector_file_binding_denied',
            'confidence': 'hypothesis' if provider_contacted is None else 'observed_layer_incomplete',
            'denied_layer': layer,
            'retry_same_reference': False,
            'schedule_retry': False,
            'next_action': 'google_independent_github_handoff',
            'disable_hourly_task': False,
            'do_not_regenerate': True,
            'already_retried_same_reference': same_runtime_reference_already_tried,
        }
    return {
        'class': 'unknown',
        'confidence': 'unknown',
        'retry_same_reference': False,
        'schedule_retry': False,
        'next_action': 'capture_redacted_envelope_then_classify',
        'disable_hourly_task': False,
    }


def should_retry_runtime_reference(classification: dict) -> bool:
    return bool(classification.get('retry_same_reference'))


def should_schedule_capability_retry(classification: dict) -> bool:
    return bool(classification.get('schedule_retry'))


def _redact_url(url: str) -> str:
    parts = urlsplit(url)
    query = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        if key.lower() in SECRET_QUERY_KEYS:
            query.append((key, '[redacted]'))
        else:
            query.append((key, value))
    host = parts.hostname or ''
    redacted_query = '&'.join(f'{k}={v}' for k, v in query)
    return urlunsplit((parts.scheme, host, '[path-redacted]', redacted_query, ''))


def _redact_text(value: str) -> str:
    value = URL_IN_TEXT.sub(lambda m: _redact_url(m.group(0)), value)
    value = SIGNED_QUERY.sub(r'\1[redacted]', value)
    value = FILE_REF.sub('file_[redacted]', value)
    value = MOUNTED_PATH.sub('/mnt/data/[redacted]', value)
    return value


def redact_envelope(envelope: Any) -> Any:
    """Keep action/error/correlation evidence; strip tokens, signed URLs, file ids."""
    if envelope is None:
        return None
    if isinstance(envelope, str):
        return _redact_text(envelope)
    if isinstance(envelope, (int, float, bool)):
        return envelope
    if isinstance(envelope, list):
        return [redact_envelope(item) for item in envelope]
    if not isinstance(envelope, dict):
        return _redact_text(str(envelope))
    redacted = {}
    for key, value in envelope.items():
        lowered = str(key).lower()
        if lowered in SECRET_HEADER_KEYS or lowered in SECRET_QUERY_KEYS:
            redacted[key] = '[redacted]'
        elif lowered in {'download_url', 'sourceuri', 'contenturi', 'uri', 'url', 'signed_url'}:
            if isinstance(value, str) and value.startswith('http'):
                redacted[key] = _redact_url(value)
            else:
                redacted[key] = classify_reference_form(value)
        elif lowered in {'file_uri', 'file_id', 'runtime_file_reference', 'image_uris'}:
            if isinstance(value, list):
                redacted[key] = [classify_reference_form(item) for item in value]
            else:
                redacted[key] = classify_reference_form(value)
        else:
            redacted[key] = redact_envelope(value)
    return redacted


def incident_record(
    *,
    player_id: int,
    player_name: str,
    slug: str,
    stage: str,
    error_code: str,
    reference_form: str,
    action_name: str | None,
    envelope,
    provider_contacted: bool | None,
    provider_http_status: int | None = None,
    correlation_id: str | None = None,
    execution_context: str = 'unknown',
    schema_expected: str | None = None,
    same_runtime_reference_already_tried: bool = False,
    bytes_preserved: bool,
    preserved_master_id: str | None,
    source_sha256: str | None,
    **extra,
) -> dict:
    classification = classify_blocked_file_reference(
        reference_form=reference_form,
        schema_expected=schema_expected,
        provider_contacted=provider_contacted,
        provider_http_status=provider_http_status,
        same_runtime_reference_already_tried=same_runtime_reference_already_tried,
    )
    record = {
        'player_id': player_id,
        'player_name': player_name,
        'slug': slug,
        'stage': stage,
        'error_code': error_code,
        'action_name': action_name,
        'reference_form': reference_form,
        'provider_contacted': provider_contacted,
        'provider_http_status': provider_http_status,
        'correlation_id': correlation_id,
        'execution_context': execution_context,
        'error_envelope_redacted': redact_envelope(envelope),
        'raw_error_envelope_captured': envelope is not None,
        'classification': classification,
        'bytes_preserved': bytes_preserved,
        'preserved_master_id': preserved_master_id,
        'source_sha256': source_sha256,
        'next_retry_at': None if not classification.get('schedule_retry') else extra.get('next_retry_at'),
        'help_needed': classification['next_action'] in {
            'google_independent_github_handoff',
            'report_smallest_owner_authorization_action',
        } and not bytes_preserved,
        'disable_hourly_task': False,
    }
    record.update(extra)
    return record
