"""Conservative low PC RAM bounds for admitted machine configurations."""


def low_ram_end(configuration):
    """Return the exclusive low-RAM end, excluding the legacy PCI aperture."""
    memory_mib = configuration.get('memory_mib', 0)
    if 'max_ram_below_4g_mib' not in configuration:
        return min(memory_mib << 20, 0xc0000000)
    split = configuration['max_ram_below_4g_mib']
    if (type(split) is not int or split != 32 or type(memory_mib) is not int
            or memory_mib != 64 or configuration.get('cpu') != 'max'):
        raise ValueError('Unknown split guest RAM configuration')
    return split << 20


def high_ram_end(configuration):
    """Return the exclusive admitted high-bank end, or None for ordinary PC RAM."""
    if 'max_ram_below_4g_mib' not in configuration:
        return None
    low_end = low_ram_end(configuration)
    return (1 << 32) + (configuration['memory_mib'] << 20) - low_end
