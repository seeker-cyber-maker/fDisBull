#!/usr/bin/env python3
"""Source-checkout wrapper for the installed, independently usable MADS validator."""
from fdisbull.mads_validation import companion, validate, main

if __name__ == '__main__':
    raise SystemExit(main())
