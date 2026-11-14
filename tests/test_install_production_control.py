import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


CI = Path(__file__).resolve().parents[1] / 'scripts' / 'ci'
spec = importlib.util.spec_from_file_location('production_installer', CI / 'install-production-control.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


def _bundle(root):
    root.mkdir()
    contents = {name: ('# authenticated ' + name + '\n').encode()
                for name in installer.MODULES}
    unit = (CI / installer.UNIT_NAME).read_bytes()
    policy = b'fixed-test-policy'
    policy_hash = hashlib.sha256(policy).hexdigest()
    installer.POLICY_SHA256 = policy_hash
    hashes = {name: hashlib.sha256(data).hexdigest() for name, data in contents.items()}
    manifest = {'schema': installer.BUNDLE_SCHEMA, 'control_sha': 'a' * 40,
                'control_ref': installer.CONTROL_REF, 'module_sha256': hashes,
                'entrypoint_sha256': hashes['production-ci.py'],
                'unit_sha256': hashlib.sha256(unit).hexdigest(), 'policy_sha256': policy_hash}
    (root / 'manifest.json').write_text(json.dumps(manifest))
    for name, data in contents.items():
        (root / name).write_bytes(data)
    (root / installer.UNIT_NAME).write_bytes(unit)
    (root / installer.POLICY_NAME).write_bytes(policy)
    return root


def _pins(bundle):
    manifest = json.loads((bundle / 'manifest.json').read_text())
    return {'expected_control_sha': manifest['control_sha'],
            'expected_manifest_sha256': hashlib.sha256((bundle / 'manifest.json').read_bytes()).hexdigest()}


def test_plan_is_fixed_read_only_and_source_activation_is_opt_in(tmp_path, monkeypatch):
    bundle = _bundle(tmp_path / 'bundle')
    monkeypatch.setattr(installer, 'MAC_CODE', Path('/Volumes/CODEX/fixed/bridge'))
    monkeypatch.setattr(installer, 'MAC_PROVIDER_STATE', Path('/Volumes/CODEX/fixed/state'))
    monkeypatch.setattr(installer, 'MAC_SOURCE_STATE', Path('/Volumes/CODEX/fixed/source-state'))
    monkeypatch.setattr(installer, 'MAC_ANCHOR', Path('/Users/tiga/.local/state/fixed/anchor.json'))
    plan = installer.plan('mac', bundle, **_pins(bundle))
    assert plan['source_activation'] is False
    assert len([item for item in plan['files'] if item['path'].endswith('.py')]) == 25
    assert not (Path('/Volumes/CODEX/fixed')).exists()
    enabled = installer.plan('mac', bundle, **_pins(bundle), enable_source_review_approved=True)
    activation = [item for item in enabled['files'] if item.get('kind') == 'explicitly-approved-activation']
    assert len(activation) == 1
    assert set(activation[0]['module_sha256']) == set(installer.ACTIVATION_MODULES)


def test_vps_plan_keeps_service_disabled_and_active_policy_withheld_by_default(tmp_path, monkeypatch):
    bundle = _bundle(tmp_path / 'bundle')
    monkeypatch.setattr(installer, 'VPS_ENTRY', Path('/usr/local/libexec/fixed-entry.py'))
    monkeypatch.setattr(installer, 'VPS_MODULES', Path('/usr/local/libexec/fixed-modules'))
    monkeypatch.setattr(installer, 'VPS_CONFIG', Path('/etc/fixed/config.json'))
    monkeypatch.setattr(installer, 'VPS_UNIT', Path('/etc/systemd/system/fixed.service'))
    monkeypatch.setattr(installer, 'VPS_CONTROL', Path('/var/lib/fixed/production'))
    monkeypatch.setattr(installer, 'VPS_STATE', Path('/var/lib/fixed/recovery'))
    monkeypatch.setattr(installer, 'VPS_EXPORTS', Path('/var/lib/fixed/results'))
    monkeypatch.setattr(installer, 'VPS_EXECUTOR_LOCK', Path('/var/lib/fixed/lock'))
    monkeypatch.setattr(installer, 'VPS_BRIDGE', Path('/Volumes/CODEX/fixed/bridge/production_transport.py'))
    withheld = installer.plan('vps', bundle, **_pins(bundle))
    assert withheld['active_policy_input'] is False
    assert all(item['path'] != str(installer.VPS_ACTIVE_POLICY) for item in withheld['files'])
    enabled = installer.plan('vps', bundle, **_pins(bundle), install_active_policy_input=True)
    assert enabled['active_policy_input'] is True
    assert any(item.get('kind') == 'explicitly-installed-qualification-input' for item in enabled['files'])
    config = installer._vps_config(installer.validate_bundle(bundle)['manifest'])
    assert config['enabled'] is False
    assert config['github']['control_sha'] == 'a' * 40


def test_bundle_rejects_hash_drift_symlinks_and_extra_files(tmp_path):
    bundle = _bundle(tmp_path / 'bundle')
    installer.validate_bundle(bundle)
    target = bundle / 'production_control.py'
    target.write_bytes(target.read_bytes() + b'# drift\n')
    with pytest.raises(ValueError, match='digest mismatch'):
        installer.validate_bundle(bundle)

    clean = _bundle(tmp_path / 'clean')
    (clean / 'surprise').write_text('unexpected')
    with pytest.raises(ValueError, match='unexpected entry'):
        installer.validate_bundle(clean)


def test_bundle_rejects_missing_module_and_wrong_ref(tmp_path):
    bundle = _bundle(tmp_path / 'bundle')
    (bundle / 'production_control.py').unlink()
    with pytest.raises(ValueError, match='file set is incomplete'):
        installer.validate_bundle(bundle)

    other = _bundle(tmp_path / 'other')
    manifest_path = other / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    manifest['control_ref'] = 'moving-branch'
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match='source identity'):
        installer.validate_bundle(other)


def test_apply_entrypoints_refuse_without_touching_fixed_targets(tmp_path, monkeypatch):
    bundle = _bundle(tmp_path / 'bundle')
    monkeypatch.setattr(installer.platform, 'system', lambda: 'Darwin')
    monkeypatch.setattr(installer.os, 'geteuid', lambda: 501)
    monkeypatch.setattr(installer, '_disk_uuid', lambda: 'wrong-volume')
    monkeypatch.setattr(installer, 'MAC_CODE', tmp_path / 'CODEX' / 'bridge')
    with pytest.raises(RuntimeError, match='UUID mismatch'):
        installer.apply_mac(bundle, **_pins(bundle))
    assert not (tmp_path / 'CODEX').exists()

    monkeypatch.setattr(installer.platform, 'system', lambda: 'Linux')
    monkeypatch.setattr(installer.os, 'geteuid', lambda: 0)
    fake_root = tmp_path / 'vps'
    (fake_root / 'libexec').mkdir(parents=True)
    (fake_root / 'etc' / 'conf').mkdir(parents=True)
    (fake_root / 'etc' / 'systemd').mkdir(parents=True)
    (fake_root / 'var' / 'control' / 'production').mkdir(parents=True)
    (fake_root / 'var' / 'control' / 'recovery').mkdir(parents=True)
    (fake_root / 'var' / 'results').mkdir(parents=True)
    monkeypatch.setattr(installer, 'VPS_ENTRY', fake_root / 'libexec' / 'entry.py')
    monkeypatch.setattr(installer, 'VPS_MODULES', fake_root / 'libexec' / 'modules')
    monkeypatch.setattr(installer, 'VPS_CONFIG', fake_root / 'etc' / 'conf' / 'config.json')
    monkeypatch.setattr(installer, 'VPS_UNIT', fake_root / 'etc' / 'systemd' / 'fixed.service')
    monkeypatch.setattr(installer, 'VPS_CONTROL', fake_root / 'var' / 'control' / 'production')
    monkeypatch.setattr(installer, 'VPS_POLICY', fake_root / 'var' / 'control' / 'production' / 'canonical.json')
    monkeypatch.setattr(installer, 'VPS_JOB_INPUTS', fake_root / 'var' / 'control' / 'production' / 'job-inputs')
    monkeypatch.setattr(installer, 'VPS_ACTIVE_POLICY', fake_root / 'var' / 'control' / 'production' / 'job-inputs' / 'policy.json')
    monkeypatch.setattr(installer, 'VPS_STATE', fake_root / 'var' / 'control' / 'recovery' / 'production')
    monkeypatch.setattr(installer, 'VPS_EXPORTS', fake_root / 'var' / 'results')
    monkeypatch.setattr(installer, 'VPS_EXECUTOR_LOCK', fake_root / 'var' / 'control' / 'executor.lock')
    monkeypatch.setattr(installer, 'VPS_BRIDGE', fake_root / 'bridge' / 'production_transport.py')
    with pytest.raises(RuntimeError, match='preinstalled shared executor lock missing'):
        installer.apply_vps(bundle, **_pins(bundle))
    assert not (fake_root / 'libexec' / 'entry.py').exists()
