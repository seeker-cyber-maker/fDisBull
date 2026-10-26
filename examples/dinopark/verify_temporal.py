#!/usr/bin/env python3
"""Run the fresh DinoPark experiment plus offline temporal promotion.

Accepts --executable, --game-dir and a NEW --output directory outside Git.
Replays navigation and captures new native states in that private output;
never edits an earlier experiment or attempts to bypass state compatibility.
Only evidence/ is shareable. The lookup test is not a complete purchase.
"""
from verify_experiments import main

if __name__=='__main__':main(temporal=True)
