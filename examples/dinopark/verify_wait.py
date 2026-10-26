#!/usr/bin/env python3
"""Verify saved observation waits alongside the real DinoPark matched trial.

Outputs to a NEW directory outside Git. Only evidence/ is shareable; private/
contains copied game inputs, native states and a project database.
"""
from verify_experiments import main

if __name__=='__main__':main(observation_wait=True)
