"""One-time, hash-bounded quarantine of the already-audited corrupt Aja asset.
Never substitutes artwork, changes statistics or weakens validation for new files.
"""
import hashlib
import json
from pathlib import Path

BAD='/images/players/aja-wilson-portrait-v1.webp'
BAD_HASH='be8434386e754bc5a1375b69a147a253076285e851a5d01307eb765cd1afb5b2'

def write(path,value):
    content=json.dumps(value,ensure_ascii=False,indent=2)+'\n'
    if not path.exists() or path.read_text()!=content:
        path.parent.mkdir(parents=True,exist_ok=True); path.write_text(content)

def migrate(root):
    manifest_path=root/'content/player-illustrations.json'
    policy_path=root/'content/portrait-quality.json'
    manifest=json.loads(manifest_path.read_text()); policy=json.loads(policy_path.read_text())
    legacy=policy.get('unchanged_legacy_assets',{})
    # Bind existing legacy records to their previously recorded byte hashes only.
    for r in manifest['portraits']:
        if 'asset_sha256' not in r:
            digest=hashlib.sha256((root/r['src'].lstrip('/')).read_bytes()).hexdigest()
            if legacy.get(r['src'])!=digest:
                raise ValueError('Unrecorded artwork needs explicit approval and checksum: '+r['slug'])
            r['asset_sha256']=digest
    bad=[r for r in manifest['portraits'] if r['player_id']==535 and r['src']==BAD]
    if bad:
        if len(bad)!=1 or bad[0]['asset_sha256']!=BAD_HASH:
            raise ValueError('Unexpected Aja asset; refusing to overwrite a different replacement')
        manifest['portraits'].remove(bad[0])
        qpath=root/'content/portrait-quarantine.json'
        quarantine=json.loads(qpath.read_text()) if qpath.exists() else {'schema_version':1,'portraits':[]}
        quarantine['portraits']=[r for r in quarantine['portraits'] if r['player_id']!=535]
        quarantine['portraits'].append(dict(bad[0],status='quarantined_corrupt_file',live_verified=False,
            reason='Live HTTP 200 response cannot be decoded. Chromium desktop and mobile both report naturalWidth=0; Pillow also rejects repository bytes.',
            audit_run_id=35142043492,
            replacement_source_status='Exact owner-approved Aja replacement master is unavailable in active runtime after a subsequent image reused its filename. Await original file. Do not substitute or regenerate.'))
        write(qpath,quarantine)
        legacy.pop(BAD,None)
        policy['legacy_note']='Legacy size exemptions never bypass decoding, checksum, player-ID or live-browser checks.'
        progress_path=root/'content/portrait-rollout.json'
        progress=json.loads(progress_path.read_text())
        for item in progress.get('published',[]):
            if item['player_id']==535:
                item.update(live_verified=False,status='invalidated_corrupt_image',verification_invalidated_by_audit_run=35142043492)
        progress.update(status='paused_for_individual_approval_and_repair',current_batch=None,
                        approval_mode='owner_approves_each_image_then_publish_verify_then_show_next')
        progress['verified_published_count']=sum(r.get('live_verified') is True for r in progress.get('published',[]))
        progress['remaining_count']=progress.get('initial_profile_count',562)-progress['verified_published_count']
        write(progress_path,progress)
    write(manifest_path,manifest); write(policy_path,policy)

if __name__=='__main__':migrate(Path(__file__).resolve().parents[1])
