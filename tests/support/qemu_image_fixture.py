"""Explicit OS-image boundary for host tests that already replace the native VM.

The real executable/owner checks live in test_qemu_image and native witnesses;
checkpoint tests retain the production require/compare/cleanup routes.
"""
from copy import deepcopy
from types import SimpleNamespace

from fdisbull.qemu_image import FORMAT, ImageProof


class AuthoredImageProof(ImageProof):
    def __init__(self, vm):
        self.owner = vm.process
        self.identity = dict(format=FORMAT, path='/authored/native-qemu',
            sha256='9' * 64, size=12345, version='10.0.13')
        self.closed = False

    def verify(self, vm, deadline):
        assert vm.process is self.owner, 'authored native owner changed'
        assert vm.inputs['qemu_image'] == self.identity, 'authored native image changed'
        assert not self.closed

    def close(self):
        self.closed = True


def attach_image(vm):
    if not hasattr(vm, 'process'):
        vm.process = SimpleNamespace(poll=lambda: None)
    if not hasattr(vm, 'inputs'):
        vm.inputs = {}
    vm._qemu_image_proof = AuthoredImageProof(vm)
    vm.inputs['qemu_image'] = deepcopy(vm._qemu_image_proof.identity)
    return vm._qemu_image_proof
