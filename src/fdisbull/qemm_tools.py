"""Projectless file/API adapters for bounded DOS driver and QEMM operations."""
from pathlib import Path


def _read(path, maximum, label):
    selected = Path(path).expanduser().resolve(strict=True)
    if not selected.is_file() or selected.stat().st_size > maximum:
        raise ValueError(f'{label} must be a regular file no larger than {maximum} bytes')
    with selected.open('rb') as stream:
        data = stream.read(maximum + 1)
    if len(data) > maximum:
        raise ValueError(f'{label} changed beyond its read budget')
    return selected, data


def invoke(method, params):
    p = dict(params)
    if method in ('le-driver-inspect', 'le-driver-disasm'):
        from .le_driver import inspect_le_driver, disassemble_le_driver
        path, data = _read(p.pop('path'), 64 * 1024 * 1024, 'LE driver')
        operation = inspect_le_driver if method == 'le-driver-inspect' else disassemble_le_driver
        return {**operation(data, **p), 'source_path': str(path)}
    if method == 'qemm-profile':
        from .qemm_runtime import prepare_qemm_profile
        return prepare_qemm_profile(**p)
    if method == 'qemm-config':
        from .qemm_runtime import prepare_qemm_config, validate_qemm_config
        file = p.pop('config_file', None)
        if file is not None and 'config_sys' in p:
            raise ValueError('Supply config_file or config_sys, not both')
        text = _read(file, 65536, 'CONFIG.SYS')[1].decode('cp437') if file is not None else p.pop('config_sys', '')
        validate = p.pop('validate_only', False)
        if type(validate) is not bool:
            raise ValueError('validate_only must be boolean')
        if validate:
            # The CLI includes these defaults even for validation. Non-default
            # preparation options must not be silently ignored.
            if p.pop('qemm_path', r'C:\QEMM\QEMM386.SYS') != r'C:\QEMM\QEMM386.SYS' or p.pop('options', 'RAM') != 'RAM' or p:
                raise ValueError('Validation does not accept preparation options')
            return dict(validation=validate_qemm_config(text), applied_to_image=False)
        return prepare_qemm_config(text, **p)
    if method == 'qpi-probe':
        from .qpi import write_qpi_probe
        return write_qpi_probe(**p)
    if method == 'qpi-report':
        from .qpi import parse_qpi_report, REPORT_SIZE
        path, data = _read(p.pop('path'), REPORT_SIZE, 'QPI report')
        return {**parse_qpi_report(data, **p), 'source_path': str(path)}
    raise ValueError('Unknown QEMM tool method')
