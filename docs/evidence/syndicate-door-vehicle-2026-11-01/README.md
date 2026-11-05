# Door and vehicle research verification

These source-free receipts describe the original-game experiments in the linked
[report](https://chatgpt.com/library?file_id=libfile_c143c9db8ea08191ab6c2c5defc04630&account_id=personal). They are not raw
game bytes or a native checkpoint. Native execution was completed during the
investigation, and its guest is closed.

From a repository with the proposed example applied and fdisbull_player installed:

```sh
python -B docs/evidence/syndicate-door-vehicle-2026-11-01/verify_slice.py \
  --scene-root examples/syndicate_z_scene \
  --evidence docs/evidence/syndicate-door-vehicle-2026-11-01 \
  --output /path/to/new-private-verification.json
```

The checker runs the current authored suite and validates the recorded numerical witnesses.
It does not start DOSBox, recreate native observations, contact a server, install
anything or read original game files. The output must not already exist.

`player-native.json` binds the four final runtime modules used by the native
15-command matrix. The binder CLI opt-in flag was checked separately; it was
not silently included in that runtime qualification. Earlier failed preparations
remain in `friction.json`. Historical native results must not become fresh tests
of a future rebase.

The original D003 suite contained 103 cases. The cumulative scene has additional
tests, so the checker reports its actual count. Historical runtime-file hashes
are compared with current files and reported separately; a difference is not a
fresh native failure or proof that current code was native-tested. Pass
`--require-historical-sources` only when verifying the exact D003 source snapshot.
