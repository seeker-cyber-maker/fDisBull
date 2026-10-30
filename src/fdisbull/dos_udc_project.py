"""Project entry points for the bounded standard DOS compiler target."""


class DOSUDCProjectMixin:
    def udc_dos_define(self, name, native_definition, data=None, references=None,
                       parent=None, author='agent'):
        from .dos_udc import define_dos_udc
        return define_dos_udc(self, name, native_definition, data=data,
                              references=references, parent=parent, author=author)

    def udc_dos_info(self, definition, include_blocks=False):
        from .dos_udc import dos_udc_info
        return dos_udc_info(self, definition, include_blocks=include_blocks)

    def udc_dos_implementation(self, definition, block, code, expected_block_revision,
                               purpose='experiment', projection=None, references=None,
                               parent=None, author='agent'):
        from .dos_udc import register_dos_implementation
        return register_dos_implementation(self, definition, block, code,
                                           expected_block_revision=expected_block_revision,
                                           purpose=purpose, projection=projection,
                                           references=references, parent=parent, author=author)

    def udc_dos_implementation_info(self, implementation):
        from .dos_udc import dos_implementation_info
        return dos_implementation_info(self, implementation)

    def udc_dos_compile(self, definition, implementations=None, entry=None,
                        block_order=None, assumptions=None, code_base=None):
        from .dos_udc import compile_dos_udc
        return compile_dos_udc(self, definition, implementations=implementations,
                               entry=entry, block_order=block_order,
                               assumptions=assumptions, code_base=code_base)
