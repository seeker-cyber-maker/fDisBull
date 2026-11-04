---
name: tell-story-ai
description: Condense debugging evidence into a short plain-language story explaining what an object is, where it was found, and why it exists. Use when the user asks for a story, concise explanation, provenance summary, or role/usage of a string, function, API call, selector, symbol, address, or other debug object; also use after FindStringAI or debugger investigations before giving the final answer.
---
# TellStoryAI

TellStoryAI turns raw debugging evidence into the short useful story the user actually needs. It should answer: **what is this object, where did it come from, why is it there, and what role does it play?**

Use it for strings, functions, API calls, selectors, symbols, addresses, files, mapped regions, and trace events.

## Output shape

Default to 3-6 short bullets or one compact paragraph. Avoid long reports unless the user asks for evidence details.

```text
Story: <plain-language explanation>
What: <object type and exact value/name>
Where: <target/app/module/file/region/function/menu/API area>
Why/role: <what it is used for>
Confidence: <confirmed | likely | static-only | blocked> because <one short evidence phrase>
```

If evidence is strong and simple, collapse to one paragraph:

```text
The string "..." is part of the larger text "..." in <target>. It lives in <file/section/region> and is used for <UI/API/function purpose>. I know this because <short evidence>.
```

## Story rules

- Prefer the user's language. Explain like a software maintainer, not a forensic report.
- Keep exact object names intact: string literal, function name, API call, selector, symbol, address.
- For strings, identify the larger containing string or nearby sentence when available.
- For strings, explain whether it is UI text, metadata, configuration, log text, error text, translation/localization text, receipt/app-store data, terminal/session text, or a heap/runtime copy.
- For functions/API calls/selectors, explain what subsystem they belong to, what they call or are called by, and what user-visible behavior they likely support.
- Function names, selector names, framework/API names, symbol names, and nearby constants are high-value clues. Use them to infer purpose, but label the inference if not proven.
- Do not carry filters, exclusions, or assumptions from a previous search into a new search unless the user explicitly asks for comparison, filtering, or continuation. Each object search starts independent by default.
- Do not say an object is used for something only because the text resembles it. Ground the role in region/module/source/callsite/API/menu/resource evidence.
- If the best result is negative or blocked, still tell the story: what was checked, why it did not prove runtime usage, and the next useful branch.

## Evidence compression

Keep the final answer short, but preserve the strongest evidence:

- exact target name/path/PID when live-debugging mattered
- module/section/region or source/resource file
- containing string or surrounding UI/API context
- key function/API/selector names
- one address or file offset only if it helps future work
- attach failure reason if live runtime proof was blocked

Do not dump scanner JSON, long memory contexts, or every false lead. Put those in target records or handoff files, not the story.

## Examples

### App version string

Raw evidence: `3.7.0` appears in `Info.plist`, receipt data, and LaunchServices mapped cache near `CFBundleShortVersionString`, `net.notepadx.editor`, and build `12656`.

Story:

```text
The string "3.7.0" is NotepadX's published app version. It comes from the bundle metadata/receipt and is copied into LaunchServices' app metadata cache. Its job is to identify or display the app version, such as in About/version UI or system app metadata. Confidence: confirmed by Info.plist, receipt, and mapped LaunchServices context.
```

### UI sentence fragment

Raw evidence: `curated fallback chain` appears in `NotepadX.__TEXT.__cstring` inside a longer sentence about non-Latin scripts and font fallback.

Story:

```text
The string "curated fallback chain" is part of a larger NotepadX preferences/settings explanation about how non-Latin scripts choose fallback fonts. It lives in the app executable's `__TEXT.__cstring` section, so it is shipped UI copy, not a generated skill name. Its role is to explain a font-rendering preference to the user. Confidence: confirmed by live memory address and static executable offset.
```

### API or selector

Story template:

```text
`-[NSBundle infoDictionary]` is an Apple framework call used to read an app bundle's metadata. In this investigation it would explain how a version string moves from `Info.plist` into runtime UI or metadata. Confidence: likely unless a breakpoint/callsite proves this exact app calls it on the path being traced.
```

## Relationship to other skills

- Use `debug-ready-ai` before claiming live process evidence.
- Use `find-string-ai` to locate and classify string hits, then use TellStoryAI to write the short final story.
- Use `debug-decision-tree-ai` when multiple explanations remain. TellStoryAI summarizes the current best branch, not every branch.
