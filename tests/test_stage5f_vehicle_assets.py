"""Synthetic archives and export records; never production geometry evidence."""
import copy
import hashlib
import json
from dataclasses import replace
from pathlib import Path
import zipfile
import subprocess

import pytest

from core.vehicle_assets import AssetResolver, Package, asset_path, extractor_command
from core.asset_profile_compiler import compile_candidate, transform_points, ProfileCache
from core.navigation.production_evidence import canonical
from core.navigation.profile_catalog import validate_profile_payload
from core.swept_envelope import EnvelopeError
from core.vehicle_profile import configuration_fingerprint, fixed_axle_geometry
from tests.test_stage5b1_vehicle_profile import observation, entry


def fixture(tmp_path, trailers=0):
    o = observation(trailers)
    path = tmp_path / 'base.zip'
    with zipfile.ZipFile(path, 'w') as z:
        z.writestr('def/cab.sii', 'SiiNunit { accessory_cabin_data : cab { collision: "/cab.pmc" variant: default } }')
        z.writestr('cab.pmc', b'not-a-real-PMC-decoder-fixture')
    resolver = AssetResolver([Package('base', path)])
    manifest = {'schema_version': 1, 'inventory_complete': True,
        'configuration_fingerprint': configuration_fingerprint(o),
        'game_build': 'synthetic', 'load_order': ['base'],
        'dlc': [], 'source': 'test configuration export', 'articles': []}
    exports = []
    for a in (a for a in o.articles if a.attached):
        axle = fixed_axle_geometry(a)
        manifest['articles'].append({'slot': a.slot, 'vehicle_id': a.vehicle_id,
            'cabin': 'test.cabin', 'chassis': 'test.chassis',
            'definitions': ['def/cab.sii'], 'accessories_complete': True})
        exports.append({'slot': a.slot, 'asset': 'cab.pmc',
            'asset_sha256': resolver.resolve('cab.pmc').sha256,
            'kind': 'collision', 'variant': 'default', 'all_parts': True,
            'transform': identity_transform(), 'uncertainty_m': .002,
            'motion_bound_m': .01, 'motion_bound_proven': True,
            'vertices': [[x,y,z] for x in (-1.3,1.3) for y in (0.,3.)
                         for z in (-7. if a.slot >= 0 else -3.,4.)],
            'wheel_anchors': [list(w.position_m) for w in a.wheels],
            'hook_local_m': list(a.hook_local_m),
            'outgoing_hook_local_m': [0.,1.,3.] if a.slot >= 0 else list(a.hook_local_m),
            'axle_local_m': list(axle.axle_local_m),
            'source': 'synthetic normalized collision export'})
    return o, manifest, resolver, exports


def identity_transform():
    return {'units': 'm', 'source_axes': 'X_RIGHT_Y_UP_Z_BACK',
        'target_axes': 'X_RIGHT_Y_UP_Z_BACK', 'handedness': 'right',
        'scale': 1., 'rotation': [[1.,0.,0.],[0.,1.,0.],[0.,0.,1.]],
        'pivot': [0.,0.,0.], 'translation': [0.,0.,0.],
        'uncertainty_m': .001, 'provenance_sha256': 'a'*64}


def test_ordered_override_and_include_graph(tmp_path):
    low, high = tmp_path/'low.zip', tmp_path/'high.zip'
    with zipfile.ZipFile(low,'w') as z:
        z.writestr('def/main.sii', 'SiiNunit { @include "part.sui" }')
        z.writestr('def/part.sui', 'accessory_cabin_data : low { collision: "/low.pmc" }')
    with zipfile.ZipFile(high,'w') as z:
        z.writestr('def/part.sui', 'accessory_cabin_data : high { collision: "/high.pmc" }')
    with AssetResolver([Package('low',low),Package('high',high)]) as r:
        g=r.definition_graph(['def/main.sii'])
        assert g['collision_assets'] == ['high.pmc']
        a=r.resolve('def/part.sui')
        assert a.package == 'high' and [x['package'] for x in a.chain] == ['low','high']


@pytest.mark.parametrize('name', ['../x', '/../../x', 'C:/x', 'a\\b', 'a//b', 'a/../b'])
def test_paths_cannot_escape(name):
    with pytest.raises(EnvelopeError): asset_path(name)


@pytest.mark.parametrize('change', ['cabin','chassis','accessory','game','asset'])
def test_configuration_or_asset_change_invalidates_key(tmp_path, change):
    o,m,r,e=fixture(tmp_path)
    a=compile_candidate(o,m,r,e,entry(o)['limits'])
    m2=copy.deepcopy(m)
    e2=copy.deepcopy(e)
    if change in ('cabin','chassis'): m2['articles'][0][change]='other'
    elif change=='accessory': m2['articles'][0]['accessory_ids']=['wider']
    elif change=='game': m2['game_build']='new'
    else: e2[0]['asset_sha256']='b'*64
    b=compile_candidate(o,m2,r,e2,entry(o)['limits'])
    assert a['asset_fingerprint'] != b['asset_fingerprint']
    r.close()


@pytest.mark.parametrize('trailers', [0,1,2,4])
def test_collision_candidate_deterministic_and_never_authorizes(tmp_path, trailers):
    o,m,r,e=fixture(tmp_path,trailers)
    a=compile_candidate(o,m,r,e,entry(o)['limits'])
    b=compile_candidate(o,m,r,e,entry(o)['limits'])
    assert canonical(a)==canonical(b)
    assert len(a['catalog_entry']['bodies'])==1+trailers
    assert a['catalog_entry']['bodies'][0]['width_m'] >= 2.6
    assert a['status']=='candidate' and not a['confirmed'] and not a['runtime_authorized']
    assert 'MISSING_VERIFIED_COLLISION_DECODER' in a['blockers']
    r.close()


@pytest.mark.parametrize('fault', ['missing','render','asset_hash','wheel','hook','inventory','detach','lift','rearsteer'])
def test_incomplete_or_conflicting_inputs_fail_closed(tmp_path, fault):
    o,m,r,e=fixture(tmp_path,1)
    if fault=='missing': e=[]
    elif fault=='render': e[0]['kind']='render_bbox'
    elif fault=='asset_hash': e[0]['asset_sha256']='b'*64
    elif fault=='wheel': e[0]['wheel_anchors'][0][2]+=1
    elif fault=='hook': e[0]['hook_local_m'][2]+=1
    elif fault=='inventory': m['inventory_complete']=False
    elif fault=='detach': o=observation(0)
    else:
        a=o.articles[1]
        w=replace(a.wheels[0], **({'liftable':True} if fault=='lift' else {'steerable':True}))
        o=replace(o, articles=(o.articles[0],replace(a,wheels=(w,)+a.wheels[1:]))+o.articles[2:])
        m['configuration_fingerprint']=configuration_fingerprint(o)
    p=compile_candidate(o,m,r,e,entry(o)['limits'])
    assert not p['geometry_complete'] and p['status']=='candidate'
    assert not p['confirmed'] and not p['runtime_authorized']
    r.close()


@pytest.mark.parametrize(('key','value'), [('units','cm'),('source_axes','XYZ_UNKNOWN'),
    ('handedness','left'),('scale',0),('scale',-1),('pivot',[float('nan'),0,0]),
    ('rotation',[[1,0,0],[0,1,0],[0,0,-1]])])
def test_bad_transforms_rejected(key,value):
    t=identity_transform();t[key]=value
    with pytest.raises(EnvelopeError): transform_points([[1.,2.,3.]],t)


def test_explicit_rotation_scale_pivot_translation():
    t=identity_transform();t.update(scale=2.,pivot=[1.,0.,0.],translation=[4.,5.,6.],
        rotation=[[0.,0.,1.],[0.,1.,0.],[-1.,0.,0.]])
    assert transform_points([[2.,1.,3.]],t)==[[10.,7.,4.]]


def test_cache_transfer_stale_and_tampering(tmp_path):
    o,m,r,e=fixture(tmp_path)
    p=compile_candidate(o,m,r,e,entry(o)['limits']);r.close()
    cache=ProfileCache(tmp_path/'cache', b'k'*32)
    path=cache.put(p)
    assert cache.get(p['asset_fingerprint'])==p
    with pytest.raises(EnvelopeError): cache.get('f'*64)
    doc=json.loads(path.read_text());doc['profile']['confirmed']=True
    path.write_text(json.dumps(doc))
    with pytest.raises(EnvelopeError): cache.get(p['asset_fingerprint'])


def test_extractor_requires_pinned_binary_and_hashfs(tmp_path):
    exe=tmp_path/'extractor.exe';exe.write_bytes(b'not executable')
    archive=tmp_path/'base.scs';archive.write_bytes(b'SCS#'+b'\x02\x00'+b'\x00'*10)
    sha=hashlib.sha256(exe.read_bytes()).hexdigest()
    cmd=extractor_command(exe,sha,archive,tmp_path/'new')
    assert cmd==[str(exe.resolve()),str(archive.resolve()),str((tmp_path/'new').resolve())]
    with pytest.raises(EnvelopeError): extractor_command(exe,'0'*64,archive,tmp_path/'new')


def test_extracted_tree_and_zip_resolve_same_bytes(tmp_path):
    root=tmp_path/'extracted';root.mkdir()
    (root/'cab.pmc').write_bytes(b'collision bytes')
    with AssetResolver([Package('base',root)]) as r:
        assert r.resolve('cab.pmc').data == b'collision bytes'
        before=r.receipts[0]['sha256']
        (root/'cab.pmc').write_bytes(b'changed')
        with pytest.raises(EnvelopeError, match='ASSET_CHANGED'): r.resolve('cab.pmc')
    with AssetResolver([Package('base',root)]) as r:
        assert before != r.receipts[0]['sha256']


def test_same_name_two_mods_and_reversed_priority(tmp_path):
    paths=[]
    for name in ('one','two'):
        p=tmp_path/(name+'.zip');paths.append(Package(name,p))
        with zipfile.ZipFile(p,'w') as z: z.writestr('cab.pmc',name)
    with AssetResolver(paths) as r:
        assert r.resolve('cab.pmc').data == b'two'
    with AssetResolver(paths[::-1]) as r:
        assert r.resolve('cab.pmc').data == b'one'


def test_include_cycle_and_unknown_directive_are_rejected(tmp_path):
    p=tmp_path/'cycle.zip'
    with zipfile.ZipFile(p,'w') as z:
        z.writestr('a.sii','@include "b.sui"');z.writestr('b.sui','@include "a.sii"')
        z.writestr('c.sii','@unknown "x"')
    with AssetResolver([Package('x',p)]) as r:
        with pytest.raises(EnvelopeError, match='CYCLIC'): r.definition_graph(['a.sii'])
        with pytest.raises(EnvelopeError, match='UNSUPPORTED_SII'): r.definition_graph(['c.sii'])


def test_candidate_cannot_enter_existing_runtime_catalog(tmp_path):
    o,m,r,e=fixture(tmp_path)
    p=compile_candidate(o,m,r,e,entry(o)['limits']);r.close()
    with pytest.raises(EnvelopeError, match='BODY_PROFILE_NOT_CONFIRMED'):
        validate_profile_payload(p,o,usable=True)


def test_changed_collision_vertices_expand_accessory_envelope(tmp_path):
    o,m,r,e=fixture(tmp_path)
    a=compile_candidate(o,m,r,e,entry(o)['limits'])
    e[0]['vertices'].append([1.8,1.,0.])
    b=compile_candidate(o,m,r,e,entry(o)['limits']);r.close()
    assert b['catalog_entry']['bodies'][0]['width_m'] == 3.6
    assert a['asset_fingerprint'] != b['asset_fingerprint']


def test_transfer_cache_requires_same_key_and_fresh_exact_fingerprint(tmp_path):
    o,m,r,e=fixture(tmp_path)
    p=compile_candidate(o,m,r,e,entry(o)['limits']);r.close()
    first=ProfileCache(tmp_path/'pc1',b'k'*32)
    blob=first.put(p).read_bytes()
    second=ProfileCache(tmp_path/'pc2',b'k'*32)
    second.directory.mkdir();second._path(p['asset_fingerprint']).write_bytes(blob)
    assert second.get(p['asset_fingerprint']) == p
    with pytest.raises(EnvelopeError): ProfileCache(second.directory,b'x'*32).get(p['asset_fingerprint'])
    doc=json.loads(blob);doc['profile']['catalog_entry']['bodies'][0]['width_m']=1.
    doc['sha256']=hashlib.sha256(canonical(doc['profile'])).hexdigest()
    second._path(p['asset_fingerprint']).write_bytes(canonical(doc))
    with pytest.raises(EnvelopeError,match='AUTHENTICATION'): second.get(p['asset_fingerprint'])


def test_build_has_no_raw_session_data(tmp_path):
    o,m,r,e=fixture(tmp_path)
    a=compile_candidate(o,m,r,e,entry(o)['limits'])
    later=replace(o,captured_at=12.,sdk_frame_us=2222222,
                  articles=tuple(replace(x,position_m=(999.,999.,999.)) for x in o.articles))
    b=compile_candidate(later,m,r,e,entry(o)['limits']);r.close()
    assert canonical(a)==canonical(b)
    assert b'sdk_frame_us' not in canonical(a) and b'position_m' not in canonical(a)


@pytest.mark.parametrize('fault', ['scale','pivot','motion','narrow','partial','variant','timeout'])
def test_geometric_conflicts_never_produce_complete_candidate(tmp_path,fault):
    o,m,r,e=fixture(tmp_path)
    if fault=='scale': e[0]['transform']['scale']=2.
    elif fault=='pivot': e[0]['transform']['pivot'][0]=1.
    elif fault=='motion': e[0]['motion_bound_proven']=False
    elif fault=='narrow':
        for v in e[0]['vertices']: v[0]*=.1
    elif fault=='partial': e[0]['all_parts']=False
    elif fault=='variant': e[0]['variant']=''
    else: r.deadline=0.
    p=compile_candidate(o,m,r,e,entry(o)['limits']);r.close()
    assert not p['geometry_complete'] and not p['confirmed']


def test_actual_package_update_changes_fingerprint(tmp_path):
    o,m,r,e=fixture(tmp_path)
    before=compile_candidate(o,m,r,e,entry(o)['limits']);r.close()
    with zipfile.ZipFile(tmp_path/'base.zip','a') as z: z.writestr('new_accessory.sii','new')
    with AssetResolver([Package('base',tmp_path/'base.zip')]) as r:
        after=compile_candidate(o,m,r,e,entry(o)['limits'])
    assert before['asset_fingerprint'] != after['asset_fingerprint']


def test_extractor_timeout_is_fail_closed(tmp_path,monkeypatch):
    from core.vehicle_assets import extract_hashfs
    exe=tmp_path/'extractor.exe';exe.write_bytes(b'pinned-fixture')
    archive=tmp_path/'base.scs';archive.write_bytes(b'SCS#\x02\x00')
    def timeout(command,**kwargs):
        assert kwargs['shell'] is False and kwargs['timeout']==1.
        raise subprocess.TimeoutExpired(command,1.)
    monkeypatch.setattr('core.vehicle_assets.subprocess.run',timeout)
    with pytest.raises(subprocess.TimeoutExpired):
        extract_hashfs(exe,hashlib.sha256(exe.read_bytes()).hexdigest(),archive,tmp_path/'output',timeout_s=1.)


def test_cli_build_repeats_canonical_output_without_installing(tmp_path,monkeypatch):
    from dataclasses import asdict
    from tools import build_vehicle_profile as cli
    o,m,r,e=fixture(tmp_path);r.close()
    obs=tmp_path/'observation.json';obs.write_bytes(canonical(asdict(o)))
    job=tmp_path/'job.json'
    job.write_bytes(canonical({'observation_file':str(obs),
        'packages_low_to_high':[{'id':'base','path':str(tmp_path/'base.zip')}],
        'configuration':m,'collision_exports':e,'limits':entry(o)['limits']}))
    monkeypatch.setattr(cli,'ROOT',tmp_path)
    outputs=[]
    for name in ('first','second'):
        output=tmp_path/'docs'/'steering-audit'/(name+'.json')
        monkeypatch.setattr('sys.argv',['build_vehicle_profile','build','--job',str(job),'--output',str(output)])
        cli.main();outputs.append(output.read_bytes())
    assert outputs[0]==outputs[1]


def test_offline_pipeline_is_not_imported_by_engine_or_controller():
    root=Path(__file__).resolve().parents[1]
    for filename in ('core/engine.py','core/navigation/route.py','core/lateral_controller.py',
                     'core/steering_dynamics.py','core/steering_executor.py'):
        text=(root/filename).read_text(encoding='utf-8')
        assert 'import core.vehicle_assets' not in text
        assert 'from core.asset_profile_compiler' not in text
