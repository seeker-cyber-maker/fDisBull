# Collected authored source fixtures

These C sources were independently authored by three fresh-context workers for
the documented collect-coins contract. Each worker received the same common
README, ABI and tool interface, plus its assigned mode and private work folder.
The workers received no parent conversation or coordinator reference C.
Reading boundaries on the shared filesystem were instructions, not a sandbox.

The directories preserve the original source bytes returned by those workers:

| Directory | Shape |
|---|---|
| singles | Three separate function bodies, each in its own source file. |
| pair | The first two function bodies and a pair entry that calls them in order. |
| triple | All three function bodies and a turn entry that calls them in order. |

They are small arithmetic fixtures written for this experiment, with no
original game source or assets. Treat their provenance as an authorship record,
and their behavior as subject to the supplied bounded checks.

To replay a collected candidate, copy only its source files to a new private
directory outside the checkout and use the ordinary experiment tool. For
example, from the repository root with dependencies and GCC available:

```sh
trial_work=$(mktemp -d)
cp examples/swede_trial/candidates/pair/pair.c "$trial_work/"
PYTHONPATH=src python examples/swede_trial/trial.py --mode pair --work "$trial_work" doctor
PYTHONPATH=src python examples/swede_trial/trial.py --mode pair --work "$trial_work" task
PYTHONPATH=src python examples/swede_trial/trial.py --mode pair --work "$trial_work" check
PYTHONPATH=src python examples/swede_trial/trial.py --mode pair --work "$trial_work" register
PYTHONPATH=src python examples/swede_trial/trial.py --mode pair --work "$trial_work" lookup
```

Use `singles` or `triple` and copy that directory's C files for the other modes.
Receipts and binary identities are generated for the current build; historical
execution evidence is not transferred merely by copying source.
