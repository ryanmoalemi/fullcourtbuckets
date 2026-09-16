#!/usr/bin/env python3
"""Read the next approved rollout batch; this does NOT generate or publish images."""
from __future__ import annotations
import argparse
import json
from pathlib import Path

FIRST_ACTIVE = ('angel-reese','aja-wilson','breanna-stewart','sabrina-ionescu',
                'napheesa-collier','paige-bueckers','kelsey-plum','aliyah-boston',
                'arike-ogunbowale','kelsey-mitchell')
FIRST_ARCHIVE = ('sue-bird','diana-taurasi','candace-parker','maya-moore',
                 'tamika-catchings','sylvia-fowles','lauren-jackson',
                 'tina-thompson','becky-hammon','seimone-augustus',
                 'cappie-pondexter','sheryl-swoopes','lisa-leslie')


def plan(index: dict, manifest: dict, progress: dict, limit: int = 10) -> dict:
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 10:
        raise ValueError('Batch limit must be from one to ten.')
    players = index.get('players', [])
    if not players or len({p['id'] for p in players}) != len(players):
        raise ValueError('A nonempty player index with unique permanent IDs is required.')
    by_id = {p['id']: p for p in players}
    approved = {p['player_id'] for p in manifest.get('portraits', []) if p.get('approved') is True}
    verified = {p['player_id'] for p in progress.get('published', []) if p.get('live_verified') is True}
    in_flight = (progress.get('current_batch') or {}).get('player_ids', [])
    parked = {p['player_id'] for p in progress.get('blocked', []) if p.get('retryable') is False}
    # A committed image is not a completed deployment. Reconcile it before
    # spending generation effort or starting a new batch.
    awaiting = sorted((approved - verified) & set(by_id))
    def rank(p):
        active = p.get('active_in_provider_feed') is True
        priority = FIRST_ACTIVE if active else FIRST_ARCHIVE
        position = priority.index(p['slug']) if p['slug'] in priority else len(priority)
        return (0 if active else 1, position, p['name'].casefold(), p['id'])
    candidates = sorted([p for p in players if p['id'] not in approved | verified | parked], key=rank)
    resume = [by_id[pid] for pid in in_flight if pid in by_id and pid not in verified | parked]
    selected = resume[:limit] if resume else candidates[:limit]
    return {'total_profiles': len(players), 'verified_published': len(verified & set(by_id)),
            'approved_images': len(approved & set(by_id)), 'remaining': len(set(by_id) - verified),
            'awaiting_live_verification': [by_id[pid] for pid in awaiting],
            'next_batch': selected, 'resuming': bool(resume),
            'blocked_player_ids': sorted(parked & set(by_id)),
            'complete': set(by_id).issubset(verified)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--limit', type=int, default=10)
    args = parser.parse_args()
    def read(relative, default=None):
        file = args.root / relative
        return json.loads(file.read_text(encoding='utf-8')) if file.exists() else default
    result = plan(read('data/wnba/players-index.json'),
                  read('content/player-illustrations.json', {'portraits': []}),
                  read('content/portrait-rollout.json', {}), args.limit)
    print(json.dumps(result, ensure_ascii=False, indent=2))
