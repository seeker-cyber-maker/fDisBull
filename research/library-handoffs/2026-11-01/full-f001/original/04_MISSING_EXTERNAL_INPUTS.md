# External inputs deliberately not bundled

## fDisBull v0.29 runtime

The requested package was not downloaded through the side browser. Both browser
attempts failed before tab access with:

> Browser access requires the originating browser context. Open ChatGPT in the browser with the connected extension and try again.

This is a connector failure, not evidence that the signed-in GitLab session is
invalid. The authorized GitLab repository reads worked. Its exposed download
action accepts existing Markdown-upload references, not package-registry links.
No credentials were copied or requested in chat.

Expected package:

```text
fdisbull-0.29.0-linux-x86_64-offline.tar.gz
bytes: 103013282
sha256: b6f43aa6933c8e4e12b643f1dead105d96e5ac0a0bb6c9671032c31fffd97a3f
```

The release tag is `09a820952ad3f54d0d0707db0515a8010f7eceb1`;
the publisher identifies package-build source
`c03dc4f9d4b5b9d0b374f6423e21962bfb0b07c9`.
Repository source access, download verification, installation and native
acceptance are distinct states. Only the scoped Player-source check is included.

## Original research inputs

Private original game installers/media, DOS runtime dependencies and byte-bearing
project/checkpoint stores must be retained separately. This ZIP contains public
research and authored tools, not replacement original assets. Authored tests and
recorded read-only scene observations work without a running native game; live
actions require a newly verified native session and the user's private inputs.

This baseline does not claim an exhaustive backup of private files from every
historical chat, nor an entire fDisBull repository export. It includes the retained
Syndicate authored-work deliveries and their available research context.
