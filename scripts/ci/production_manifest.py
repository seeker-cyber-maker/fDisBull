"""Exact reviewed installed CI-control source set; not a release manifest."""

MODULES = frozenset({
    'ci_status.py', 'execution_identity.py', 'export-local-artifacts.py',
    'github-bootstrap.py', 'github-once.py', 'offline-qualification.py',
    'ovh-export.py', 'production-ci.py', 'production-qualification.py',
    'production_control.py', 'production_evidence.py', 'production_github_host.py',
    'production_intake.py', 'production_manifest.py', 'production_policy.py',
    'production_runtime.py', 'production_source_publish.py',
    'production_source_transport.py', 'production_transport.py', 'recovery.py',
    'recovery_github.py', 'recovery_gitlab_production.py', 'recovery_production.py',
    'recovery_source.py', 'recovery_source_production.py',
})
