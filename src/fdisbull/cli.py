"""One-shot JSON CLI and line-oriented agent protocol over stdin/stdout."""

import argparse
import json
from pathlib import Path
import sqlite3
import sys
from . import __version__
from .output_limits import (
    OutputPolicy,
    current_output_policy,
    output_policy_context,
    validate_request_id,
)

AGENT_SKILL_GUIDES = {
    "SKILL.md": "Start here: investigation technique, cost/reward/confidence and evidence boundaries",
    "references/scenes.md": "Define native scene objects, masks, recognition, readiness and named actions",
    "references/methodology.md": "Plan evidence, coordinate independent questions, trace causes and screen for interpreters",
    "references/runtime-navigation.md": "Choose movement, spatial policies, assistance and observation projections",
    "references/sweding.md": "Keep intent fixed while qualifying alternative implementations, timing, effects and hosting",
    "references/reconstruction.md": "First-use recovery recipe: original-to-UIL-to-target gates, discriminating probes and resumable evidence",
    "references/proofs.md": "Build explicit bounded Z3 models and report their assumptions and scope",
    "references/workflows.md": "Choose static analysis, native debugging, scene, media/ROM, guest-module or UIL/UDC entry points",
    "references/analysis-approach.md": "Choose what to analyze next using evidence, dependencies, information gain and cost",
    "references/udl-uil-udc.md": "Qualify memory/desktop/Win16/web shells, console replay/synthesis, direct AGI/Zork profiles and DOS block layers",
    "references/common-uil.md": "Compose indexed typed UIL, semantic catalogs, native modules/desktop shells and persistent packages",
    "references/recovery-research.md": "Qualify research, retain reusable meanings and compare recovery depth and cost",
    "references/semantic-contracts.md": "Recover complete intent contracts and compare facts, effects, time and projection losses",
    "references/media-modules.md": "Reuse shipped parser APIs, recover missing tooling, and extend bounded format specifications",
    "references/file-formats.md": "Identify file headers through SQLite format modules and frame native SMK2 with explicit decoder/runtime gates",
    "references/scene-recovery.md": "Recover UIL scenes from required elements, bounded source dependencies and explicit residuals",
    "references/source-and-concepts.md": "Intake pinned source, search concepts across editions, and preserve source/native claim boundaries",
    "references/formats-and-media.md": "Qualify containers, Mach-O/NE/LE/AIL/Cortex-M/ROM mappings, AVI capture audits and media reduction",
    "references/agi-scenes.md": "Inventory AGI scene elements, resolve typed references and retain unqualified IR",
    "references/binary-claim-verification.md": "Prove or falsify stored-value, writer and behavior claims against the decoded original binary",
    "references/dos-drivers-and-qemm.md": "Analyze DOS device roots and mixed LE objects; qualify a QEMM-configured full-machine guest",
    "references/desqview-and-memory-search.md": "Inspect DESQview interfaces/modules, cooperate through an authored helper, and run persistent memory searches with bounded guarded edits",
}
AGENT_SKILL_RESOURCES = tuple(AGENT_SKILL_GUIDES)
DEFAULT_AGENT_SKILL = "fdisbull-investigate"
AGENT_SKILLS = {
    DEFAULT_AGENT_SKILL: {
        "purpose": "Investigate programs, qualify evidence and recover game behavior",
        "guides": AGENT_SKILL_GUIDES,
    },
    "write-gamefaqs-guide": {
        "purpose": "Write a reversing-first game review covering mechanics, discoveries, routes, formats and engine reuse",
        "guides": {
            "SKILL.md": "Start here: scope, evidence and workflow for a readable game guide",
            "references/evidence-and-provenance.md": "Distinguish recovered facts, observations, external sources and unknowns",
            "references/guide-structure.md": "Organize routes, reference sections, navigation, spoilers and text exports",
            "references/technical-mechanics.md": "Explain algorithms, numeric semantics and worked examples with evidence",
            "references/routes-and-discoveries.md": "Cover unused code, bugs, cheats, alternate routes, speedrun rules and completion goals",
            "references/formats-and-engine-reuse.md": "Specify recovered files and media; qualify interpreters and cross-game reuse",
            "references/engine-source-examples.md": "External engine/layout examples: read only when the information policy permits game facts",
            "references/source-examples.md": "External guide examples and rationale: check the information policy before reading",
        },
    },
}

METHODS = {
    "debug-step": "Step native or engine instructions with the selected backend contract; run,[count,timeout_ms]",
    "debug-spectator": "Read or enable the owned watch-only Windows dot-mode viewer; run,[enabled]",
    "debug-spectator-frame": "Capture one native paused Windows frame for the watch-only viewer; run",
    "debug-engine-state": "Read paused engine VM state with its own address context; run",
    "debug-write-engine-state": "Apply a checked engine state edit; run,kind,index,value,[expected,width,signed,endian]",
    "debug-read-variable": "Read a typed engine variable at a byte offset; run,offset,[width,signed,endian]",
    "debug-write-variable": "Write a typed engine variable with an optional expected value; run,offset,value,[width,signed,endian,expected]",
    "debug-hotspot-events": "Read retained engine hotspot dispatch receipts; run",
    "debug-watchpoint": "Watch a typed engine state location; run,kind,index",
    "debug-delete-watchpoint": "Remove an engine watchpoint; run,watchpoint_id",
    "debug-resource": "Read an engine resource identity and original source extent; run,kind,number",
    "debug-read-resource": "Read source-bound loaded engine bytes; run,[logic,script,generation,offset,length] (parameters depend on backend)",
    "debug-patch-resource": "Apply a checked reversible loaded-logic edit; run,logic,offset,expected_hex,data_hex",
    "debug-engine-cycle": "Run to an explicit engine cycle boundary; run,[max_instructions,timeout_ms]",
    "debug-restore-resource": "Restore retained original loaded-logic bytes after checking current identity; run,logic,[expected_fnv1a64]",
    "debug-run-async": "Start one finite ScummVM run while keeping the foreground server responsive; run,[timeout_ms,guest_ms,max_instructions]",
    "debug-run-result": "Read the result of an explicitly started asynchronous run; run,operation,[wait_ms]",
    "uil-check": "Validate indexed common UIL or a complete package; program,[presentation,catalog,orchestration] or package; no execution",
    "uil-catalog": "Compile a list of UDL descriptors into exact semantic groups; blocks; unsupported languages remain explicit",
    "uil-run": "Execute bounded indexed UIL with typed copies and planned effects; program,presentation,[catalog,orchestration,inputs,max_steps]",
    "uil-compile": "Generate Python/JavaScript or build a typed native realization; program,presentation,catalog,orchestration,output,[target,arithmetic,module_requirements,c_compiler,source_only]",
    "uil-link": "Resolve native module/intrinsic requirements deterministically; program,presentation,catalog,orchestration,target,[arithmetic,module_requirements]",
    "uil-components": "Describe nested typed module/provider choices without execution; modules,providers,target,[pins]",
    "uil-build": "Compile and seal an existing native source realization; output,[c_compiler]",
    "uil-seal": "Seal externally compiled native artifacts against retained sources; output,[compiler_evidence]",
    "uil-desktop": "Emit or build a native window shell over fixed-arena common UIL; program,presentation,catalog,orchestration,plan,initial,output,[target,source_only,variants,c_compiler]; build is not runtime qualification",
    "uil-desktop-build": "Compile and seal an existing desktop source shell; output,[c_compiler]; no application execution",
    "uil-desktop-seal": "Seal externally compiled desktop artifacts against their sources; output; no application execution",
    "uil-fold": "Retain a function child graph in a recoverable higher-level block; program,function,semantic_id",
    "uil-expand": "Recover the exact lower-level program from a pinned fold receipt; program,recovery",
    "uil-store": "Persist an immutable common UIL package; project,name,package,[version,parent,author]",
    "uil-info": "Inspect an immutable common UIL package; project,revision,[full]",
    "uil-list": "List common UIL packages without payloads; project,[limit,offset]",
    "capture-audit": "Decode/hash finalized AVI segments and optionally sample frames; inputs,output,[every,html,timeout,max_frames,max_frame_bytes,max_input_bytes,max_metadata_bytes,max_output_bytes,ffmpeg,ffprobe]; no guest or project required",
    "macos-snapshot": "Inspect native macOS displays, target accessibility and menu state without input; bundle_id",
    "macos-session": "Capture a bounded reversible native session; bundle_id,output,[live,status_index,display_id,rect,keys,preference_changes,max_seconds]",
    "macos-session-recover": "Inspect and restore owned pending native session changes; output",
    "capabilities": "Read-only analysis capability/dependency catalog; [analyze_headless,lldb,java]; no project or tool execution",
    "media-modules": "Discover shipped media adapters, APIs, dependencies and limits; no project required",
    "format-modules": "Discover format signatures, header fields and linked reader capabilities; [catalog_path]; no project required",
    "intake-inventory": "Inventory one or many private input roots through the format catalog; paths,[catalog_path,max_files,max_read_bytes,max_binary_bytes]; no extraction or input execution",
    "file-identify": "Identify executable/media headers and nested views with a bounded format registry; path,[catalog_path,max_binary_bytes]; no input execution",
    "smk-frame": "Frame bounded SMK2 video with native holds and unchanged audio; path,output,[keep_frames,max_output_bytes,ffmpeg,ffprobe,timeout]; independent decoding required",
    "media-inspect": "Inventory bounded source members without execution; path,adapter,[volume_root,number,index_path]",
    "media-extract": "Copy one member to a new private directory outside Git; path,output,adapter,member,[volume_root,number,max_output_bytes]",
    "gog-list": "List local GOG Inno Setup payloads without Wine; path,[include,timeout]; no project required",
    "gog-unpack": "Unpack local GOG Inno Setup payloads into a new private directory; path,output,[include,timeout]; no project required",
    "output-info": "Inspect an immutable private output artifact; artifact",
    "output-read": "Read a bounded base64 byte range without executing the original operation; artifact,[offset,length]",
    "output-select": "Read a complete small JSON Pointer selection or an explicit incomplete descriptor; artifact,[pointer,max_bytes]",
    "output-export": "Export retained JSON to a new private file outside Git; artifact,output",
    "debug-save-spatial-map": "Save an immutable source-bound room map; name,document,[parent,version,author]",
    "debug-spatial-map-info": "Read a pinned room-map revision; revision,[version]",
    "debug-spatial-domain-audit": "Audit stored world/room/viewport extents without changing navigation; revision,[version,max_checks]",
    "debug-spatial-check": "Check actor footprint against known safe masks; revision,point,[conditions,version]",
    "debug-spatial-candidates": "Propose clear anchors in game units; revision,[zone,origin,limit,clearance,conditions,version]",
    "debug-spatial-route": "Plan a bounded cardinal route through known clear cells; revision,start,goal,[conditions,maxnodes,version]",
    "debug-spatial-overlay": "Export a stored game-unit map as PNG; revision,output,[conditions,version]",
    "debug-spatial-policy": "Inspect or select physical, assisted or story policy; run,[mode,fair_play]",
    "debug-spatial-action": "Run an original input under a qualified spatial policy; run,map_revision,definition,[room_field,conditions,zone,actor_recipe,travel_plan,timeout_ms]",
    "debug-save-workflow": "Save a resource-bound partial workflow; name,definition,resource_root,[parent,version,author]",
    "debug-workflow-info": "Read an immutable workflow revision; workflow,[version]",
    "debug-workflow-receipts": "Read persisted workflow attempts and outcomes; workflow,[version]",
    "debug-save-text-projection": "Save a public projection over a pinned workflow; name,definition,[parent,version]",
    "debug-text-projection-info": "Read a projection revision for authoring; name,[version]",
    "debug-workflow-observe": "Inspect qualified coverage and fresh action conditions; run,workflow,resource_root,[action,research_context]",
    "debug-workflow-act": "Dispatch a qualified scene action; run,workflow,action,resource_root,[timeout_ms]",
    "debug-text-observe": "Read the public text view without guest execution; run,projection,resource_root",
    "debug-text-act": "Dispatch a resolved public command; run,projection,request,resource_root",
    "debug-assisted-travel": "Apply qualified travel assistance and observe the original engine; run,plan,[timeout_ms]",
    "proof-check": "Check a bounded explicit bitvector model and persist assumptions/result; spec,[version,timeout_ms,author,evidence]",
    "proofs": "List source/version-bound proof results; [version]",
    "proof-info": "Read and authenticate a persisted bounded proof; proof,[version]",
    "debug-define-macros": "Save an immutable typed source-bound input vocabulary; definition,[version,author,parent]",
    "debug-macro-sets": "List exact-version input vocabularies; [version]",
    "debug-macro-info": "Inspect a saved vocabulary; macro_set,[version]",
    "debug-export-macros": "Return a metadata-only portable vocabulary envelope; macro_set,[version]",
    "debug-import-macros": "Import a matching source/version vocabulary envelope; envelope,[version,author]",
    "debug-macro": "Expand and execute a selected typed input macro; run,macro_set,name,[args,timeout_ms,allowed_authorities]",
    "debug-move": "Observe a bounded route with explicit controls, destination, progress and stop contracts; run,macro_set,start,stop,observations,until,progress,settle,[guest_ms,timeout_ms,scene,spatial_map,map_conditions,room_field,position,target,target_tolerance]",
    "debug-bind-runtime-memory": "Qualify explicit runtime RAM with a source witness and address context; run,name,address,length,expected_hex,provenance,[mask_hex,space]",
    "debug-runtime-memory": "Read a qualified runtime view; run,binding,[offset,length]",
    "debug-write-runtime-memory": "Guard and verify a live RAM edit without save/load; run,binding,data_hex,expected_hex,[offset]",
    "debug-proof-check": "Persist a bounded model check with live run provenance; run,spec,[timeout_ms,author,evidence]",
    "debug-keyboard-down": "Queue make and return an owned physical key lease; run,key",
    "debug-keyboard-up": "Consume an owned lease and queue physical break; run,lease",
    "debug-scene-navigation": "Check an actor footprint in explicit game-space geometry; run,scene,point,[footprint]",
    "agent-skill": "Discover or read bundled skills; [skill,list,index,reference]; no project required",
    "debug-save-scene": "Save a versioned scene manifest with persistent objects and screenshot evidence; name,definition,[parent,version,author]",
    "debug-scenes": "List current scene revisions; [version]",
    "debug-scene-info": "Read a scene manifest, evidence and persistent object identities; scene,[version]",
    "debug-scene-domain-audit": "Audit stored object extents and expected margins; scene,[version,max_checks]",
    "debug-scene-overlay": "Render shared masks with names or numbers and a legend; scene,[artifact,name,grid_step,version,labels]",
    "debug-scene-observation": "Read one retained full or compact historical observation; observation,[compact]",
    "debug-export-scenes": "Export compatible scene definitions and clean PNG evidence only; scenes,output,[version]",
    "debug-import-scenes": "Atomically import a portable scene bundle with new local IDs; bundle,[version]",
    "debug-scene-observations": "Read persisted checks, collisions and diagnostic captures; [revision,run,limit]",
    "debug-frame-probe": "Read at most 4096 RGB pixels from one native completed frame, without PNG transfer; run,points",
    "debug-scene-check": "Check scene identity and optional object availability; run,scene,[object,compact]",
    "debug-scene-assert": "Assert current scene/object or save a diagnostic snapshot; run,scene,[object,compact]",
    "debug-scene-click": "Perform checked real input and verify its bounded outcome; run,scene,object,[handle_popups,timeout_ms,slice_ms,compact]",
    "debug-scene-act": "Perform a named guest mouse/keyboard action and verify its outcome; run,scene,object,[handle_popups,timeout_ms,slice_ms,compact]",
    "debug-scene-wait": "Wait on authored scene/object conditions with explicit budgets; run,scene,[object,guest_ms,timeout_ms,slice_ms,compact]",
    "capture-signature": "Capture a named closed stored function for cross-project reuse; address,name,[version,cs,author,max_instructions]",
    "import-signatures": "Atomically import an explicit signature catalog; catalog,[version]",
    "export-signatures": "Export registered project identities as a reusable JSON catalog; [version]",
    "omf-catalog": "Extract fixup-free DOS16 public routines from an OMF library; path,[abi]",
    "dos-services": "List DOS/BIOS/audio contracts or describe a vector with pre-call registers",
    "debug-wait": "Poll explicit observations with separate guest/host budgets; run,observations,until,guest_ms,[slice_ms,timeout_ms,fast_forward,max_polls,timeout_screenshot]",
    "debug-trace-view": "Compare stored trace instruction bytes/context against a temporal interpretation; artifact,version",
    "doctor": "Run disposable authored debugger acceptance; backend,executable,[kernel,initramfs,output,boot_timeout_ms]",
    "debug-promote-code": "Analyze a qualified runtime code capture as a preserved temporal child; artifact,[label,max_instructions,defer]",
    "runtime-version-info": "Inspect temporal capture/edit provenance for a byte version; [version]",
    "debug-controls": "Inspect owned breakpoint/watch/hook definitions for experiment capture; run",
    "debug-save-experiment": "Capture a native checkpoint, controls, script and observations; run,name,[script,script_id,observations]",
    "debug-experiments": "List immutable saved experiments; [version]",
    "debug-experiment-info": "Inspect a saved experiment and verify its identities offline; artifact",
    "debug-restore-experiment": "Restore native state, layers, breakpoints, watches and hook hit counts; run,experiment",
    "debug-compare-experiment": "Run baseline and an explicit layer stack, save differences and restore baseline; run,experiment,layers,[timeout_ms]",
    "debug-contexts": "List explicit DOS/process and outer-machine execution contexts; run",
    "debug-pause": "Request a pause in a supported execution context; run,[context,timeout_ms]",
    "debug-resume": "Resume a supported execution context with its declared budgets; run,[context,timeout_ms,guest_ms,max_instructions]",
    "debug-launch": "Launch a project-bound DOS, Windows, machine or experimental ScummVM backend; executable,game_dir,[version,backend,guest_profile,game_id,language,platform,kernel,initramfs,files,boot_timeout_ms,state,remote_server,window,dot_mode,memory_mib,spatial_mode,fair_play]",
    "le-driver-inspect": "Inspect mixed-width LE driver objects and symbolic fixups without process loading; path",
    "le-driver-disasm": "Bounded object-relative LE driver view; path,object_number,[offset,max_instructions,abi]",
    "qemm-config": "Preview or validate an unconditional QEMM CONFIG.SYS without editing files; [config_file,config_sys,qemm_path,options,validate_only]",
    "qemm-profile": "Bind a QEMM guest profile to CONFIG.SYS and driver bytes in a caller-owned FAT12/16 boot image; boot_image,[config_sys,driver_path]",
    "qpi-probe": "Export an authored read-only DOS QPI observation helper; output,[mode]",
    "qpi-report": "Read a bounded guest-produced QPI report; path,[include_pages]",
    "debug-memory-translation": "Observe an x86 machine linear-to-physical page walk at the current stop; run,address,[context]",
    "debug-memory-snapshot": "Capture an immutable paused DOS memory range with run/task/mapping identity; run,address,length,[space,task_id,name,context]",
    "debug-memory-apply": "Apply one owned memory edit plan with fresh context/expected-byte guards and readback; run,plan,[context]",
    "memory-snapshot-info": "Inspect a retained private memory snapshot and capture provenance; snapshot",
    "memory-search-start": "Search a retained snapshot using unknown, exact or range values; snapshot,[width,signed,byteorder,stride,mode,value,minimum,maximum,bias,max_candidates]",
    "memory-search-refine": "Narrow only existing candidates against a compatible new snapshot; search,snapshot,mode,[value,delta,max_candidates]",
    "memory-search-results": "Page retained memory candidates with current/previous scalar values; search,[offset,limit]",
    "memory-edit-plan": "Plan a conditional guarded candidate edit without writing; search,offset,value,[condition,compare_value]",
    "memory-rule-create": "Create a finite conditional edit/freeze rule for an owned candidate; search,offset,value,[condition,compare_value,max_applications,max_ticks,name]",
    "memory-rule-info": "Read a stored memory rule and its durable execution budgets/progress; rule",
    "debug-memory-rule-tick": "Observe and conditionally edit one rule candidate at a qualified stop; run,rule,[context]",
    "debug-memory-rule-run": "Execute finite rule ticks with DOSBox guest-time intervals; run,rule,ticks,[interval_ms,timeout_ms]",
    "desqview-profile": "Pin a caller-owned DOS boot image and selected DESQview MZ/modules; boot_image,[program,modules,qemm,startup]",
    "desqview-probe": "Emit an authored presence-gated cooperative DESQview COM helper; output,[mode,yields,nonce]",
    "desqview-report": "Parse an exact guest-produced DESQview report without inferring freshness; path",
    "desqview-module-inspect": "Inspect raw DVdx or caller-described older DESQview modules; path,[expected_type,expected_version]",
    "debug-desqview-observe": "Read a stopped DESQview report, optionally verifying authored helper/nonce/ready PC; run,address,[space,probe_base,expected_nonce,context]",
    "debug-qemm-observe": "Read a QPI report from stopped machine memory; run,address,[length,context]",
    "debug-status": "Live debugger status and address mapping; run",
    "debug-registers": "Live CPU registers with project address mapping; run",
    "debug-layer": "Save an immutable guarded RAM or execution layer; name,kind,patches,[version]",
    "debug-layer-info": "Inspect an immutable layer definition; layer",
    "debug-layers": "List saved layers for a static version; [version]",
    "debug-events": "Read the persisted runtime event timeline; run,[after,limit]",
    "debug-layer-stack": "Inspect or replace the active ordered layer stack; run,[active]",
    "debug-layer-enable": "Enable or disable a saved layer; run,layer,[enabled]",
    "debug-layer-patch": "Create and optionally activate a guarded RAM/execute patch; run,name,address,expected_hex,data_hex,[kind,activate]",
    "debug-code": "Decode observed RAM or effective instruction-fetch bytes; run,address,[cs,length,view]",
    "debug-capture-code": "Save a temporal code view as an immutable project artifact; run,address,[cs,length,view,name]",
    "debug-branch": "Invert or force an observed 16-bit Jcc using an execution layer; run,name,address,[mode,activate]",
    "debug-cave": "Create an execution-only code cave with normalized far return; run,name,address,code_hex,return_to,[activate]",
    "debug-hook": "Attach bounded declarative actions to a breakpoint; run,address,actions,[once,max_hits,cs,access,length]",
    "debug-hooks": "Inspect active breakpoint actions and hit counts; run",
    "debug-delete-hook": "Remove an owned hook and its native breakpoints; run,hook",
    "debug-breakpoint": "Translate execution or data access breakpoint; run,address,[cs,access,length]",
    "debug-delete-breakpoint": "Delete a live breakpoint; run,breakpoint_id",
    "debug-run": "Run to a breakpoint or bounded guest time, pausing at host timeout; run,[timeout_ms,guest_ms,fast_forward]",
    "debug-click": "Queue a screenshot-pixel mouse click; run,x,y,[button,hold_ms,mode_id]",
    "debug-keyboard-press": "Queue a guest keyboard press/release; run,key,[modifiers,hold_ms,gap_ms]",
    "debug-keyboard-type": "Queue 1..64 US-layout ASCII characters; run,text,[hold_ms,gap_ms]",
    "debug-keyboard-state": "Inspect queued guest keyboard events and owned keys; run",
    "debug-click-frame": "Capture and label the chosen point, then queue its frame-mode-bound click; run,x,y,[name,grid_step,button,hold_ms,mode_id]",
    "debug-screenshot": "Store an actual guest PNG with optional grid, DOS hooks and negotiated native encoding; run,[name,grid,grid_step,hooks,encoding]",
    "debug-screenshot-hooks": "Inspect or persist DOS screenshot pre/post scripts and suspended layers; run,[configuration]",
    "debug-grid": "Derive a coordinate grid from a stored clean screenshot offline; artifact,[name,step,target]",
    "debug-trace": "Store bounded CPU trace with project address mappings; run,[name,count,timeout_ms,fast_forward]",
    "debug-memory": "Read project-mapped runtime bytes; run,address,[cs,length]",
    "debug-write-memory": "Guarded PE64 runtime edit with readback; run,address,data_hex,expected_hex",
    "debug-write-registers": "Guarded PE64 general-register edits; run,registers",
    "debug-save-state": "Compatibility name for saving a full native Anchor Stone; run,[name,max_bytes]",
    "debug-load-state": "Compatibility name for loading an Anchor Stone; run,artifact",
    "debug-rewind-start": "Start bounded native DOS Anchor Stone history; run,[max_steps,max_bytes]",
    "debug-rewind-status": "Inspect the live Anchor Stone history cursor, budgets and validity; run",
    "debug-rewind-record": "Capture an Anchor Stone before each bounded next-fetch interval and advance; run,[count,timeout_ms]",
    "debug-rewind": "Jump to an earlier full Anchor Stone in legacy history; run,[count]",
    "debug-save-anchor-stone": "Save a full native Anchor Stone; run,[name,max_bytes]",
    "debug-load-anchor-stone": "Jump directly to a compatible Anchor Stone; run,artifact",
    "debug-anchor-stone-info": "Inspect a saved Anchor Stone offline; artifact",
    "debug-delta-start": "Experimental delta rewind with one full native Anchor Stone; run,ranges,[max_steps,max_bytes]",
    "debug-delta-status": "Inspect selected-state delta scope, cursor, costs and execution guard; run",
    "debug-delta-record": "Record selected CPU/RAM changes at DOS next-fetch or Wine completed-instruction boundaries; run,[count,timeout_ms]",
    "debug-delta-rewind": "Undo selected CPU/RAM deltas; optional policy preserves declared state and explicitly permits experimental partial continuation; run,[count,policy]",
    "debug-delta-recover": "Load the recovery Anchor Stone and clear the partial-state guard; run",
    "debug-frame-advance": "Advance native DOS completed renderer frames without recording; run,[frames,timeout_ms]",
    "debug-frame-inputs": "Apply physical keyboard edges at a stopped frame boundary; run,edges",
    "debug-timeline-start": "Start bounded native frame/input history with full or lossless delta retention; run,[max_frames,max_bytes,max_state_bytes,max_image_bytes,max_captures,storage_mode,keyframe_interval]",
    "debug-timeline-status": "Inspect live frame history, cursor, input log, retained bytes and validity; run",
    "debug-timeline-advance": "Advance and automatically capture each native frame, with optional frame input edges; run,[frames,inputs,timeout_ms]",
    "debug-timeline-rewind": "Restore a recent full frame state; explicit policy can preserve declared runtime RAM as an experiment; run,[frames,policy]",
    "debug-timeline-stop": "Stop automatic recording and release its live cache; run",
    "debug-timeline-pin": "Persist the current cached frame as a durable Anchor Stone without recapture; run,[name]",
    "debug-timeline-image": "Export the current cached guest PNG, including after rewind; run,[name]",
    "debug-script": "Execute bounded menu/debug script; run,[script,script_id,timeout_ms]",
    "debug-save-script": "Save an immutable version-bound script; name,script,[version]",
    "debug-scripts": "List saved scripts; [version]",
    "debug-state-info": "Inspect native checkpoint metadata and component sizes offline; artifact",
    "debug-fork-state": "Restore, edit and recapture native state with target stopped; artifact,executable,game_dir,[name,memory,registers,backend,kernel,initramfs,window]",
    "debug-stop": "Stop and reap a live emulator; run",
    "debug-runs": "Saved runtime history for a static version; [version]",
    "debug-artifacts": "Saved screenshots and traces, available after restart; [version,run]",
    "debug-export": "Export a saved artifact without running an emulator; artifact,output",
    "label-links": "List shared label links and optional removal history; [version,include_removed,limit,offset]",
    "unlink-labels": "Retract a mistaken shared label link with provenance; link_id,reason,[version,author]",
    "link-labels": "Link corresponding native/file byte ranges; left,right,evidence,[size,name,version,author]",
    "rename-file": "Rename a file field and every linked identity; file,offset,name,[version,author]",
    "label-info": "Resolve a shared field label and its evidence chain; endpoint,[version]",
    "attach-file": "Snapshot an external data/save/resource file; path,[name,kind,version,author]",
    "files": "Attached file identities, hashes and type bindings; [version,limit,offset]",
    "file-bytes": "Read bounded attached-file hex and text; name,[offset,size,version]",
    "apply-file-type": "Bind a structural type in file-offset space; file,type_name,[offset,name,version,author]",
    "file-data": "Read an exact typed attached-file binding; file,[offset,version,max_items]",
    "file-reference": "Author an instruction-to-file relationship; address,file,evidence,[offset,width,count,stride,access,cs,version,author]",
    "file-xrefs": "Query authored references to attached-file bytes; file,[offset,size,version,limit,page_offset,include_stale]",
    "refresh-dos-state": "Rebuild legacy DOS states and dependent facts; [version,max_instructions]",
    "auto-analyze": "Run persistent native and derived analysis to a bounded fixed point; [version,start,cs,ds,es,ss,max_instructions,max_functions,max_steps,max_entries,max_rounds,abi]",
    "advanced-status": "Derived job states, pending entries and fixed point; [version]",
    "function-analysis": "Stored frame, indirect-target, signature and effect evidence; address,[version,cs]",
    "function-membership": "Shared instruction/block membership from candidate entries; [version,max_work,max_instructions]",
    "define-type": "Register scalar/pointer/array/struct/union/enum/bitfield/typedef/function; name,definition,[version,author]",
    "set-function-type": "Apply a declared function prototype and ABI; address,type_name,[version,cs,author]",
    "apply-type": "Bind a type to shared data identity; address,type_name,[name,version,author]",
    "types": "Registered layouts and data bindings; [version]",
    "export-types": "Export unbound structural interpretations with declared provenance; [version,names,output]",
    "import-types": "Atomically import structural definitions without bindings; catalog,[version,author]",
    "typed-data": "Interpret a bound data object; address,[version,max_items]",
    "set-summary": "Register a qualified function contract; address,name,[prototype,summary,abi,version,cs,author]",
    "summaries": "Registered and signature-qualified function contracts; [version]",
    "add-signature": "Register an exact or relocation-masked full-body signature; signature,[version]",
    "signatures": "Builtin and registered function signatures; [version]",
    "call-effects": "Qualified memory effects at call sites; [address,size,access,version,include_unresolved,limit,offset]",
    "libraries": "Declared dependency names and load ordinals; [version,limit,offset]",
    "relocations": "Static relocation records with symbol/addend provenance; [version,limit,offset]",
    "linkage": "GOT/PLT or dyld slot/stub metadata; [version]",
    "refresh-metadata": "Reinspect retained ELF/Mach-O/PE bytes and invalidate consumers; [version]",
    "analyze-module": "Offline DLL/shared-library analysis; path,project,[export,entry,max_instructions,slice_arch,image]",
    "analysis-status": "Current persisted queues, seed states and fixed-point status; [version]",
    "cfg": "Reachable stored CFG from exact entry; address,[version,cs,max_instructions,highlights]",
    "code-backings": "Exact entry-qualified native encodings and source occurrences (x86 and Mach-O ARM64); entries,[version,cs,max_instructions]",
    "ghidra-arm64": "Cross-check selected source-bound Mach-O ARM64 instructions with optional Ghidra; project,path,addresses,analyze_headless,[decompile_entry,version]",
    "macos-observe": "Launch one exact source-bound Mach-O ARM64 executable to a named LLDB breakpoint; project,executable,symbol,[version,argv]",
    "code-blocks": "Logical entry-qualified code blocks without source layout changes; entries,[version,cs,max_instructions,split_at]",
    "code-layout": "Bounded raw x86 layout with explicit jumps and caller assumptions; entries,assumptions,[version,cs,max_instructions,order,base,entry_references]",
    "udc-native-capture": "Persist native UDL blocks for direct UDC pass-through; name,entries,[version,cs,max_instructions,split_at,parent,author]",
    "udc-native-info": "Read an immutable native UDC definition; definition,[include_blocks]",
    "udc-native-compile": "Exact original-layout pass-through or explicit raw relayout; definition,[mode,assumptions,base,order,block_order,entry_references]",
    "render-cfg": "Export reachable basic-block CFG as SVG; address,output,[version,cs,max_instructions,highlights]",
    "memory-accesses": "Read/write/overlap and unresolved memory evidence; address,[size,version,access,limit,offset,include_unresolved]",
    "refresh-facts": "Backfill persisted fallthrough and memory-access facts from stored instructions; [version]",
    "calls": "Grouped native function/library calls with incoming xrefs; [version,limit,offset,kind]",
    "locate": "Byte position in stored instructions/data and unexplored memory; address,[version,cs]",
    "function-patterns": "Candidate prologue/epilogue evidence; [version,limit,offset,scan_unexplored]",
    "managed": "Inspect .NET metadata or disassemble one CIL method; path or project,[token,max_instructions,version]",
    "agi-logic": "Read-only partial AGI 2.917 logic decoding; logdir, volume_dir, logic, profile, [max_instructions]",
    "agi-scenes": "Read-only AGI scene census, not executable UIL; game_dir, profile, [stage,include_ir,include_text,max_updates,max_instructions,max_code_bytes]",
    "kq1-bow-intents": "Export one source-bound court intent with UDL and retained IR; game_dir,output,[uil,udl]",
    "kq1-bow-evaluate": "Evaluate court intent rules and engine requests; package,state or state_file,[event,event_file]; no native guest",
    "decoder-modules": "List explicitly registered trusted source decoder modules; no project required",
    "module-analyze": "Direct source analysis without native ASM; module,path,[volume_dir,logic,profile,address,max_instructions]",
    "module-lift": "Direct source-to-UDL/UIL projection; module,path,initial_state,[volume_dir,logic,profile,entry_offset,stop_offsets,stop_points,callee_entries,max_instructions,max_call_depth,control_flow,allow_opaque,effect_profile]",
    "zmachine-disasm": "Read-only Z-machine v3 instruction slice; path,[address,max_instructions]",
    "zmachine-analyze": "Bounded recursive Z-machine v3 processor analysis; path,[entry_points,max_instructions]",
    "decoder-check": "Compare x86 iced/Capstone proposals without execution; data,[bits,address,scan_offsets,max_candidates]",
    "import": "Create a new project from binary; params: project, path, [arch,bits,base,entry,load_segment,slice_arch,image]",
    "segments": "DOS inferred segment inventory; [version]",
    "code-regions": "DOS decoded instruction runs by CS; [version]",
    "identify": "Identify file header from bytes; path; no project required",
    "inspect": "Parse file metadata; path; no project required",
    "rom-inspect": "Parse console cartridge or Sega data-track descriptor; path; no project required",
    "console-udc": "Compile bounded UIL to a new private NES/Genesis cartridge directory; path,target,output,[display_variable,scene_path]",
    "console-udc-targets": "List native console compiler targets and accepted UIL operations; no project required",
    "rom-game-lift": "Export the reviewed full Miniplanets game/audio UIL to a new private directory; path,output",
    "genesis-replay-profiles": "List registered Genesis-source UIL/replay profiles and explicit target limits",
    "genesis-replay-source": "Preflight original ROM parsing and registered semantic-profile eligibility; path",
    "genesis-replay-export": "Capture semantic UIL and a locked NES or Genesis build in a new private bundle; path,output,[target,cc65_root,m68k_root,variant,procedures]",
    "genesis-replay-inspect": "Check private replay payload integrity without executing tools or trusting qualification claims; path",
    "genesis-replay-build": "Replay a registered bundle with exact original ROM and explicit trusted target compiler; path,output,rom_path,[target,cc65_root,m68k_root]",
    'shadowrun-systems': 'List recovered Shadowrun procedural components and whole-game gaps; no parameters',
    'shadowrun-play-build': 'Build the bounded scene-2 NES play profile; path,rom_path,capture,cc65_root,output',
    'shadowrun-ai-profiles': 'List source-bound Shadowrun actor/combat profiles and their limits',
    'shadowrun-ai-build': 'Build a private Shadowrun AI NES or native macOS ARM64 profile; path,rom_path,capture,output,[cc65_root,profile,preset,target]',
    'shadowrun-snes-build': 'Build the private prepared SNES opening scene as a native ARM64 movement study; rom_path,ram,save_ram,output',
    'shadowrun-city-export': 'Export a private investigator city snapshot as JSON, text and interactive HTML; rom_path,snapshot,output',
    'shadowrun-system-export': 'Export one registered source-bound component as UIL; rom_path,system,output',
    'shadowrun-system-inspect': 'Validate a private Shadowrun component bundle; path',
    'shadowrun-system-build-check': 'Compile finite scalar UIL cases to a headless NES check cartridge; path,rom_path,procedure,cases_path,cc65_root,output',
    'shadowrun-opening-profiles': 'List the bounded Shadowrun Genesis opening and Stoker projection profile; no parameters',
    'shadowrun-opening-export': 'Export a source-bound Shadowrun opening GameIL and private capture/atlas bundle; rom_path,snapshot,atlas,output',
    'shadowrun-opening-inspect': 'Verify a private Shadowrun opening bundle integrity without executing tools; path',
    'shadowrun-opening-build': 'Build a registered Shadowrun opening bundle for NES with exact ROM and explicit cc65 root; path,rom_path,cc65_root,output',
    'shadowrun-opening-animation-build': 'Build the separate right-only animated NES probe; path,rom_path,capture,cc65_root,output',
    "nes-multicart-profiles": "List bounded NES packaging UDC profiles and compatibility requirements",
    "nes-multicart-inspect": "Inspect NES cartridge mapper and bank geometry without assuming a game count; path",
    "nes-multicart-build": "Package two compatible authored NROM cartridges behind a bank-switching menu; inputs,output,authored_compatible",
    "rom-disasm": "Decode bounded, explicitly mapped SH-2 bytes with interchangeable engines; path,base_address,[backend,offset,length,max_instructions,mode,ghidra_home,saturn_recomp_root,timeout]",
    "disc-inspect": "Parse bounded CUE/BIN or ISO primary filesystem metadata; path,[mode,max_entries,max_directory_bytes,max_depth]",
    "info": "Parsed container summary; [version]",
    "header": "Parsed header fields; [version]",
    "sections": "Disk and virtual section layout; [version,limit,offset]",
    "imports": "Static imports and persisted IAT recovery; [version,limit,offset]",
    "exports": "Export addresses, ordinals and forwarders; [version,limit,offset]",
    "strings": "File-backed ASCII/UTF16 strings; [version,limit,offset]",
    "items": "Investigated memory locations; [version,limit,offset]",
    "queue": "Code/data investigation work; [version,limit,offset]",
    "represent": "Shared data/code/unexplored definition; address,representation,[size,author,version,max_instructions,defer]",
    "recover-imports": "Offline CHimpREC-derived recovery; module_exports or export_map,[candidate_slots,version,max_slots,gap_limit]",
    "status": "Image mappings, hashes, counts and remaining work; [version]",
    "analyze": "Recursive code/data analysis; [version,start,max_instructions,cs,ds,es,ss]",
    "functions": "Candidate function entries; [version,limit,offset]",
    "disasm": "Stored decoded rows; [version,address,lines,cs]",
    "xrefs": "Direct control/data references; address, [version,direction,limit,cs]",
    "rename": "Persistent address label; address,name,[version,author]",
    "comment": "Persistent evidence note; address,text,[version,author]",
    "versions": "Immutable mapped-byte snapshots and provenance",
    "patch": "Create a new snapshot, preserve parent; address,data,[version,label,origin]",
    "issues": "Pending/rejected/unresolved work; [version,limit]",
    "render": "Export stored rows as SVG/PNG; output,[version,address,lines,format,cs]",
    "storage-info": "Read-only storage inventory; project",
    "migrate-external": "Explicitly create an external-storage derivative; project,destination",
    "source-info": "Recorded target size/SHA-256, loader provenance and current availability; [version]",
    "source-candidate": "Inspect candidate identity without attaching; path,[version]",
    "bind-source": "Bind exact source or explicitly approved divergent layer; path,[version,approval]",
    "new-source-analysis": "Explicitly create a separate analysis without changing this one; path,destination,[version]",
    "help": "List methods; all project operations require project path",
}

from .udc_api import METHODS as BLOCK_METHODS
METHODS.update(BLOCK_METHODS)
from .source_api import METHODS as SOURCE_METHODS
METHODS.update(SOURCE_METHODS)
METHODS["source-info"] = (
    "Recorded target size/SHA-256, loader provenance and current availability; [version]; "
    "or source-catalog counts and scope with catalog"
)


def source_catalog_request(method, params):
    """Select the source-catalog API only when its catalog argument is present."""
    return (
        method in SOURCE_METHODS
        and isinstance(params, dict)
        and (method != "source-info" or "catalog" in params)
    )


def invoke(method, params, debugger=None):
    if method not in METHODS:
        raise ValueError(f"unknown method: {method}")
    if not isinstance(params, dict):
        raise ValueError("params must be an object")
    p = dict(params)
    if source_catalog_request(method, p):
        from .source_api import invoke as source_invoke
        return source_invoke(method, p)
    if method.startswith("uil-"):
        from .uil_api import invoke_common

        return invoke_common(method, p)
    if method in ("output-info", "output-read", "output-select", "output-export"):
        policy = current_output_policy()
        artifact = p.pop("artifact")
        store = policy.store()
        if method == "output-info":
            if p:
                raise ValueError("output-info accepts only artifact")
            return store.info(artifact)
        if method == "output-read":
            offset = p.pop("offset", 0)
            length = p.pop("length", 1024)
            if p:
                raise ValueError("unknown output-read parameter")
            if (
                type(length) is not int
                or length < 1
                or ((length + 2) // 3) * 4 + 2048 > policy.max_inline_bytes
            ):
                raise ValueError("requested range exceeds the inline output budget")
            return store.read(artifact, offset=offset, length=length)
        if method == "output-select":
            pointer = p.pop("pointer", "")
            maximum = p.pop("max_bytes", 16384)
            if p:
                raise ValueError("unknown output-select parameter")
            if (
                not isinstance(pointer, str)
                or len(json.dumps(pointer, ensure_ascii=True))
                > policy.max_inline_bytes - 2048
            ):
                raise ValueError("pointer exceeds the inline output budget")
            result = store.select(artifact, pointer=pointer, max_bytes=maximum)
            if (
                len(
                    json.dumps(
                        result, ensure_ascii=True, separators=(",", ":")
                    ).encode()
                )
                + 1024
                > policy.max_inline_bytes
            ):
                result = {
                    k: v
                    for k, v in result.items()
                    if k not in ("value", "selected_bytes")
                }
                result.update(complete=False, reason="selection_too_large")
            return result
        output = p.pop("output")
        if p:
            raise ValueError("unknown output-export parameter")
        return store.export(artifact, output)
    if method == "agent-skill":
        skill_supplied = "skill" in p
        skill = p.pop("skill", DEFAULT_AGENT_SKILL)
        listing = p.pop("list", False)
        reference = p.pop("reference", None)
        index = p.pop("index", False)
        if p:
            raise ValueError("agent-skill accepts only skill, list, index or reference")
        if not isinstance(skill, str) or skill not in AGENT_SKILLS:
            raise ValueError("unknown bundled skill name")
        if type(listing) is not bool:
            raise ValueError("list must be boolean")
        if type(index) is not bool:
            raise ValueError("index must be boolean")
        if listing and (skill_supplied or index or reference is not None):
            raise ValueError("list cannot be combined with skill, index or reference")
        if index and reference is not None:
            raise ValueError("index and reference are mutually exclusive")
        if listing:
            return {
                "format": "fdisbull-skill-catalog-1",
                "default_skill": DEFAULT_AGENT_SKILL,
                "skills": [
                    {"name": name, "purpose": item["purpose"], "entrypoint": "SKILL.md"}
                    for name, item in AGENT_SKILLS.items()
                ],
            }
        guides = AGENT_SKILLS[skill]["guides"]
        if index:
            return {
                "name": skill,
                "format": "fdisbull-skill-index-1",
                "entrypoint": "SKILL.md",
                "guides": [
                    {"reference": name, "purpose": purpose}
                    for name, purpose in guides.items()
                ],
            }
        if reference is not None and (
            not isinstance(reference, str) or reference not in guides
        ):
            raise ValueError("unknown bundled skill reference")
        from importlib.resources import files

        root = files("fdisbull").joinpath("skills", skill)
        resources = (reference,) if reference is not None else tuple(guides)
        return {
            "name": skill,
            "files": {
                n: root.joinpath(n).read_text(encoding="utf-8") for n in resources
            },
        }
    if method == "media-modules":
        from .media import media_modules

        if p:
            raise ValueError("media-modules takes no parameters")
        return media_modules()
    if method == "intake-inventory":
        from .intake import intake_inventory

        return intake_inventory(**p)
    if method in ("format-modules", "file-identify"):
        from .format_registry import format_catalog, identify_file

        return (format_catalog if method == "format-modules" else identify_file)(**p)
    if method == "smk-frame":
        from .smacker import frame_smk

        return frame_smk(**p)
    if method == "capture-audit":
        from .capture_audit import audit_capture

        return audit_capture(**p)
    if method in ("media-inspect", "media-extract"):
        from .media import inspect_media, extract_media

        return (inspect_media if method == "media-inspect" else extract_media)(**p)
    if method in ("gog-list", "gog-unpack"):
        from .gog_unpack import list_gog, unpack_gog

        return (list_gog if method == "gog-list" else unpack_gog)(**p)
    if method == "omf-catalog":
        from .omf_catalog import omf_signatures

        path = Path(p.pop("path"))
        if not path.is_file() or path.stat().st_size > 16 * 1024 * 1024:
            raise ValueError("OMF library must be at most 16 MiB")
        return omf_signatures(path.read_bytes(), source=str(path), **p)
    if method == "dos-services":
        from .dos_services import service_catalog, describe_interrupt

        vector = p.pop("vector", None)
        registers = p.pop("registers", {})
        ax = p.pop("ax", None)
        if p or not isinstance(registers, dict):
            raise ValueError("dos-services expects vector, registers and optional ax")
        if vector is None:
            if registers or ax is not None:
                raise ValueError("registers/ax require a vector")
            return service_catalog()
        from .project import integer

        vector = integer(vector, "vector", 0, 255)
        if ax is not None:
            ax = integer(ax, "ax", 0, 65535)
            if "ax" in registers and registers["ax"] != ax:
                raise ValueError("conflicting AX selectors")
            registers = {**registers, "ax": ax}
        return describe_interrupt(vector, registers)
    if method == "doctor":
        from .doctor import doctor

        return doctor(**p)
    if method == "capabilities":
        from .capabilities import capabilities

        return capabilities(**p)
    if method in ("macos-snapshot", "macos-session", "macos-session-recover"):
        from .macos_capture import NativeCapture
        native = NativeCapture()
        if method == "macos-snapshot":
            if set(p) != {"bundle_id"} or not isinstance(p["bundle_id"], str):
                raise ValueError("macos-snapshot requires only bundle_id")
            return native("snapshot", **p)
        from .macos_session import run_session, recover_session
        return (run_session if method == "macos-session" else recover_session)(native=native, **p)
    if method in ("decoder-modules", "module-analyze", "module-lift"):
        from .decoder_modules import analyze_input, builtin_registry, lift_input
        registry = builtin_registry()
        if method == "decoder-modules":
            if p:
                raise ValueError("decoder-modules takes no parameters")
            return {"format": "fdisbull-decoder-modules-1", "modules": registry.catalog(),
                    "registration": "explicit trusted in-process objects; no automatic imports"}
        identity, path = p.pop("module"), p.pop("path")
        limit = p.pop("max_instructions", 40 if method == "module-analyze" else 128)
        if method == "module-analyze":
            address = p.pop("address", None)
            if p.get("function_index") is None:
                p.pop("function_index", None)
            return analyze_input(registry.open(identity, path, **p),
                                 address=address, max_instructions=limit)
        state_file = p.pop("state_file", None)
        if state_file is not None:
            if "initial_state" in p:
                raise ValueError("supply initial_state or state_file, not both")
            with Path(state_file).open("rb") as handle:
                raw = handle.read(65537)
            if len(raw) > 65536:
                raise ValueError("initial state exceeds 64 KiB")
            p["initial_state"] = json.loads(raw)
        initial_state = p.pop("initial_state")
        call_depth = p.pop("max_call_depth", None)
        control_flow, allow_opaque = p.pop("control_flow", None), p.pop("allow_opaque", None)
        effect_profile = p.pop("effect_profile", None)
        return lift_input(registry.open(identity, path, **p),
                          initial_state=initial_state, max_instructions=limit,
                          max_call_depth=call_depth, control_flow=control_flow,
                          allow_opaque=allow_opaque, effect_profile=effect_profile)
    if method in ("zmachine-disasm", "zmachine-analyze"):
        from .zmachine_analysis import analyze_story, disassemble_story

        operation = disassemble_story if method == "zmachine-disasm" else analyze_story
        return operation(**p)
    if method in ("le-driver-inspect", "le-driver-disasm", "qemm-config", "qemm-profile", "qpi-probe", "qpi-report"):
        from .qemm_tools import invoke as qemm_invoke

        return qemm_invoke(method, p)
    if method in ('desqview-profile','desqview-probe','desqview-report','desqview-module-inspect'):
        from .desqview_runtime import invoke as desqview_invoke
        return desqview_invoke(method, p)
    from .project import Project, number

    for field in ("base", "entry"):
        if field in p and p[field] is not None:
            p[field] = number(p[field])
    if method == "help":
        return {
            "application": "fDisBull",
            "version": __version__,
            "protocol": "JSON lines, one response per request; not MCP/JSON-RPC",
            "methods": METHODS,
        }
    if method == "analyze-module":
        from .modules import analyze_module

        return analyze_module(**p)
    if method == "decoder-check":
        from .decoder_check import compare_decoders

        data = p.pop("data")
        if not isinstance(data, str):
            raise ValueError("data must be hexadecimal bytes")
        return compare_decoders(bytes.fromhex(data), **p)
    if method in ("ghidra-arm64", "macos-observe"):
        import hashlib

        project = p.pop("project", None)
        version = p.pop("version", 1)
        if not project:
            raise ValueError("project path is required")
        if type(version) is not int or version != 1:
            raise ValueError(
                "macOS native probes currently require the original byte version 1"
            )
        path = Path(p.pop("path" if method == "ghidra-arm64" else "executable"))
        if not path.is_file() or not 0 < path.stat().st_size <= 64 * 1024 * 1024:
            raise ValueError("expected a nonempty Mach-O source file at most 64 MiB")
        with path.open("rb") as stream:
            checked_bytes = stream.read(64 * 1024 * 1024 + 1)
        if not 0 < len(checked_bytes) <= 64 * 1024 * 1024:
            raise ValueError("Mach-O source grew beyond the 64 MiB probe limit")
        with Project(project) as db:
            state = db.status(version=version)
            source = db.source_info(version=version)
        if (
            state["format"] != "Mach-O"
            or state["arch"] != "arm64"
            or state["bits"] != 64
        ):
            raise ValueError("project must contain a Mach-O ARM64 image")
        identity = source["identity"]
        if not source["verified"] or path.stat().st_size != identity["size"]:
            raise ValueError(
                "original source identity is unavailable or does not match this file"
            )
        if hashlib.sha256(checked_bytes).hexdigest() != identity["sha256"]:
            raise ValueError(
                "probe file does not match the recorded original source hash"
            )
        if method == "ghidra-arm64":
            from .ghidra_arm64 import probe_macho_arm64

            try:
                result = probe_macho_arm64(path, p.pop("addresses"), **p)
            except RuntimeError as error:
                raise ValueError(str(error)) from error
        else:
            from .macos_lldb import observe_macos_arm64_launch

            result = observe_macos_arm64_launch(path, **p)
        observed_hash = (
            result.get("source_sha256")
            if method == "ghidra-arm64"
            else (result.get("source") or {}).get("sha256")
        )
        if observed_hash != identity["sha256"]:
            raise ValueError(
                "native probe source changed or could not be verified against the project"
            )
        result["fdisbull_project"] = {
            "version": version,
            "mapped_sha256": state["version"]["sha256"],
            "source_sha256": identity["sha256"],
        }
        return result
    if method == "managed" and "path" in p:
        from .managed import inspect_managed, disassemble_managed

        path = Path(p.pop("path"))
        if not path.is_file() or not 0 < path.stat().st_size <= 64 * 1024 * 1024:
            raise ValueError("expected one nonempty input file at most 64 MiB")
        with path.open("rb") as stream:
            data = stream.read(64 * 1024 * 1024 + 1)
        token = p.pop("token", None)
        if token is not None:
            return disassemble_managed(data, token, **p)
        if p:
            raise ValueError("unexpected managed inspection options")
        return inspect_managed(data)
    if method == "agi-logic":
        from .agi import inspect_logic

        return inspect_logic(**p)
    if method == "agi-scenes":
        from .agi_scenes import inspect_scenes
        return inspect_scenes(**p)
    if method == "kq1-bow-intents":
        from .kq1_bow import export_bow
        return export_bow(**p)
    if method == "kq1-bow-evaluate":
        from .court_adapter import evaluate_bow
        return evaluate_bow(**p)
    if method=='disc-inspect':
        from .disc import inspect_disc_path
        return inspect_disc_path(**p)
    if method=='console-udc':
        from .console_udc import compile_console_path
        return compile_console_path(**p)
    if method=='rom-game-lift':
        from .udl_miniplanets_full import lift_game_path
        return lift_game_path(**p)
    if method.startswith('nes-multicart-'):
        from . import nes_multicart
        if method=='nes-multicart-profiles':
            if p:raise ValueError('nes-multicart-profiles accepts no parameters')
            return nes_multicart.multicart_profiles()
        handler={'nes-multicart-inspect':nes_multicart.inspect_multicart_path,
                 'nes-multicart-build':nes_multicart.build_multicart}.get(method)
        if handler is not None:return handler(**p)
    if method.startswith('genesis-replay-'):
        from . import udc_genesis
        if method=='genesis-replay-profiles':
            if p:raise ValueError('genesis-replay-profiles accepts no parameters')
            return udc_genesis.translation_profiles()
        handler={'genesis-replay-source':udc_genesis.inspect_translation_source,
                 'genesis-replay-export':udc_genesis.write_translation,
                 'genesis-replay-inspect':udc_genesis.inspect_translation_bundle,
                 'genesis-replay-build':udc_genesis.replay_translation}.get(method)
        if handler is not None:return handler(**p)
    if method=='shadowrun-snes-build':
        from .shadowrun_snes_macos import build
        return build(**p)
    if method.startswith('shadowrun-ai-'):
        from . import shadowrun_ai
        if method=='shadowrun-ai-profiles':
            if p:raise ValueError('shadowrun-ai-profiles accepts no parameters')
            return shadowrun_ai.profiles()
        if method=='shadowrun-ai-build':return shadowrun_ai.build(**p)
    if method=='shadowrun-play-build':
        from .shadowrun_nes_play import build_play
        path=p.pop('path')
        return build_play(path,**p)
    if method=='shadowrun-city-export':
        from .shadowrun_city_view import export_city
        return export_city(**p)
    if method=='shadowrun-systems' or method.startswith('shadowrun-system-'):
        from . import shadowrun_systems
        if method=='shadowrun-systems':
            if p:raise ValueError('shadowrun-systems accepts no parameters')
            return shadowrun_systems.catalog()
        if method=='shadowrun-system-export':return shadowrun_systems.export_system(**p)
        if method=='shadowrun-system-inspect':
            path=p.pop('path')
            if p:raise ValueError('shadowrun-system-inspect accepts only path')
            return shadowrun_systems.inspect_system(path)
        if method=='shadowrun-system-build-check':
            path=p.pop('path')
            return shadowrun_systems.build_system_check(path,**p)
    if method.startswith('shadowrun-opening-'):
        from . import shadowrun_replay
        if method=='shadowrun-opening-profiles':
            if p:raise ValueError('shadowrun-opening-profiles accepts no parameters')
            return shadowrun_replay.profiles()
        if method=='shadowrun-opening-export':
            return shadowrun_replay.export_opening(**p)
        if method=='shadowrun-opening-inspect':
            path=p.pop('path')
            if p:raise ValueError('shadowrun-opening-inspect accepts only path')
            return shadowrun_replay.inspect_opening(path)
        if method=='shadowrun-opening-build':
            path=p.pop('path')
            return shadowrun_replay.build_opening(path,**p)
        if method=='shadowrun-opening-animation-build':
            path=p.pop('path')
            return shadowrun_replay.build_animated_opening(path,**p)
    if method=='console-udc-targets':
        from .console_udc import console_targets
        if p:raise ValueError('console-udc-targets accepts no parameters')
        return console_targets()
    if method=='rom-disasm':
        from .rom_asm import disassemble_rom_path
        return disassemble_rom_path(**p)
    if method=='rom-inspect':
        from .roms import inspect_rom_path
        path=p.pop('path')
        if p:raise ValueError('rom-inspect accepts only path')
        return inspect_rom_path(path)
    if method in ("identify", "inspect"):
        from .inspection import identify_header, inspect_binary

        path = Path(p.pop("path"))
        slice_arch = p.pop("slice_arch", None)
        image = p.pop("image", None)
        if (
            p
            or (method == "identify" and (slice_arch is not None or image is not None))
            or not path.is_file()
            or path.stat().st_size > 64 * 1024 * 1024
        ):
            raise ValueError("expected one regular input file at most 64 MiB")
        with path.open("rb") as stream:
            data = stream.read(64 * 1024 * 1024 + 1)
        return (
            identify_header(data)
            if method == "identify"
            else inspect_binary(data, slice_arch=slice_arch, image=image)
        )
    project = p.pop("project", None)
    if not project:
        raise ValueError("project path is required")
    if method == "storage-info":
        from .target_storage import storage_report

        return storage_report(project)
    if method == "migrate-external":
        return Project.migrate_external(project, p["destination"])
    scene_offline = (
        "debug-save-scene",
        "debug-scenes",
        "debug-scene-info",
        "debug-scene-domain-audit",
        "debug-scene-overlay",
        "debug-scene-observations",
        "debug-scene-observation",
        "debug-export-scenes",
        "debug-import-scenes",
        "debug-save-workflow",
        "debug-workflow-info",
        "debug-workflow-receipts",
        "debug-save-text-projection",
        "debug-text-projection-info",
        "debug-save-spatial-map",
        "debug-spatial-map-info",
        "debug-spatial-domain-audit",
        "debug-spatial-check",
        "debug-spatial-candidates",
        "debug-spatial-route",
        "debug-spatial-overlay",
    )
    macro_offline = (
        "debug-define-macros",
        "debug-macro-sets",
        "debug-macro-info",
        "debug-export-macros",
        "debug-import-macros",
    )
    if method in scene_offline + macro_offline:
        if "definition_file" in p:
            file = Path(p.pop("definition_file"))
            if (
                method != "debug-save-scene"
                or "definition" in p
                or not file.is_file()
                or file.stat().st_size > 1024 * 1024
            ):
                raise ValueError(
                    "Expected one scene definition JSON file at most 1 MiB"
                )
            p["definition"] = json.loads(file.read_text())
        with Project(project) as db:
            return getattr(db, method.replace("-", "_"))(**p)
    if method.startswith("debug-") and method not in (
        "debug-runs",
        "debug-artifacts",
        "debug-export",
        "debug-grid",
        "debug-save-script",
        "debug-scripts",
        "debug-state-info",
        "debug-anchor-stone-info",
        "debug-fork-state",
        "debug-layer",
        "debug-layer-info",
        "debug-layers",
        "debug-events",
        "debug-experiments",
        "debug-experiment-info",
        "debug-promote-code",
        "debug-trace-view",
    ):
        if debugger is None:
            raise ValueError(
                "Live debugger commands require fdisbull serve or fdisbull debug; sessions close on server exit"
            )
        return debugger.invoke(method, project, p)
    if method == "import":
        binary = p.pop("path", None)
        if binary is None:
            raise ValueError("path is required for import")
        with Project.create(project, binary, **p) as db:
            return db.status()
    with Project(project) as db:
        if method in ('memory-snapshot-info', 'memory-search-start', 'memory-search-refine',
                      'memory-search-results', 'memory-edit-plan', 'memory-rule-create', 'memory-rule-info'):
            return getattr(db, method.replace('-', '_'))(**p)
        if method in (
            "code-backings",
            "code-blocks",
            "code-layout",
            "udc-native-capture",
            "udc-native-info",
            "udc-native-compile",
        ):
            for field in ("assumptions", "order", "block_order", "entry_references"):
                filename = p.pop(field + "_file", None)
                if filename is not None:
                    path = Path(filename)
                    if (
                        field in p
                        or not path.is_file()
                        or path.stat().st_size > 4 * 1024 * 1024
                    ):
                        raise ValueError(
                            "expected one JSON argument file at most 4 MiB"
                        )
                    p[field] = json.loads(path.read_text())
            return getattr(db, method.replace("-", "_"))(**p)
        if method in BLOCK_METHODS:
            from .udc_api import invoke as invoke_block
            return invoke_block(db,method,p)
        if method in ("source-info", "source-candidate", "bind-source"):
            return getattr(db, method.replace("-", "_"))(**p)
        if method == "new-source-analysis":
            p["project"] = p.pop("destination")
            return db.new_source_analysis(**p)
        if method in ("proof-check", "proofs", "proof-info"):
            return getattr(db, method.replace("-", "_"))(**p)
        if method in (
            "debug-runs",
            "debug-artifacts",
            "debug-export",
            "debug-grid",
            "debug-save-script",
            "debug-scripts",
            "debug-state-info",
            "debug-anchor-stone-info",
            "debug-fork-state",
            "debug-layer",
            "debug-layer-info",
            "debug-layers",
            "debug-events",
            "debug-experiments",
            "debug-experiment-info",
            "debug-promote-code",
            "debug-trace-view",
            "runtime-version-info",
        ):
            return getattr(db, method.replace("-", "_"))(**p)
        if method in (
            "link-labels",
            "rename-file",
            "label-info",
            "label-links",
            "unlink-labels",
        ):
            return getattr(db, method.replace("-", "_"))(**p)
        if method == "refresh-dos-state":
            return db.refresh_dos_state(**p)
        file_methods = {
            "attach-file": "attach_file",
            "files": "external_files",
            "file-bytes": "file_bytes",
            "apply-file-type": "apply_file_type",
            "file-data": "typed_file",
            "file-reference": "file_reference",
            "file-xrefs": "file_xrefs",
        }
        if method in file_methods:
            return getattr(db, file_methods[method])(**p)
        if method == "export-types":
            output = p.pop("output", None)
            catalog = db.export_types(**p)
            if output is None:
                return catalog
            from .type_catalog import _json as catalog_json

            raw = catalog_json(catalog).encode("utf-8")
            if len(raw) > 4 * 1024 * 1024:
                raise ValueError("Type catalog exceeds 4 MiB")
            destination = Path(output).expanduser()
            with destination.open("xb") as stream:
                stream.write(raw)
            import hashlib

            return dict(
                output=str(destination),
                bytes=len(raw),
                sha256=hashlib.sha256(raw).hexdigest(),
                exported=len(catalog["types"]),
                version=catalog["source"]["version"],
            )
        if method in (
            "define-type",
            "add-signature",
            "set-summary",
            "import-signatures",
            "import-types",
        ):
            for field in ("definition", "signature", "prototype", "summary", "catalog"):
                filename = p.pop(field + "_file", None)
                if filename is not None:
                    path = Path(filename)
                    if not path.is_file() or path.stat().st_size > 4 * 1024 * 1024:
                        raise ValueError("expected a JSON file at most 4 MiB")
                    if method == "import-types":
                        with path.open("rb") as stream:
                            raw = stream.read(4 * 1024 * 1024 + 1)
                        if len(raw) > 4 * 1024 * 1024:
                            raise ValueError("expected a JSON file at most 4 MiB")
                        p[field] = json.loads(raw)
                    else:
                        p[field] = json.loads(path.read_text())
        if method in (
            "auto-analyze",
            "advanced-status",
            "function-analysis",
            "function-membership",
            "define-type",
            "apply-type",
            "types",
            "export-types",
            "import-types",
            "typed-data",
            "set-summary",
            "set-function-type",
            "capture-signature",
            "import-signatures",
            "export-signatures",
            "summaries",
            "add-signature",
            "signatures",
            "call-effects",
        ):
            return getattr(db, method.replace("-", "_"))(**p)
        if method == "memory-accesses":
            return db.memory_accesses(**p)
        if method == "refresh-facts":
            return db.refresh_facts(**p)
        if method == "render-cfg":
            from .cfg_render import render_cfg

            destination = Path(p.pop("output")).expanduser().resolve()
            protected = [
                db.path,
                Path(str(db.path) + "-wal"),
                Path(str(db.path) + "-shm"),
            ]
            if any(
                destination == item
                or (
                    destination.exists()
                    and item.exists()
                    and destination.samefile(item)
                )
                for item in protected
            ):
                raise ValueError(
                    "render output cannot overwrite a project database or SQLite sidecar"
                )
            return render_cfg(db.cfg(**p), destination)
        if method == "code-regions":
            return db.code_regions(**p)
        if method == "function-patterns":
            return db.function_patterns(**p)
        if method == "analysis-status":
            return db.analysis_status(**p)
        if method == "refresh-metadata":
            return db.refresh_metadata(**p)
        if method in (
            "info",
            "header",
            "sections",
            "imports",
            "exports",
            "strings",
            "libraries",
            "relocations",
            "linkage",
        ):
            return db.information(topic="summary" if method == "info" else method, **p)
        if method == "recover-imports":
            return db.recover_imports(**p)
        if method == "rename":
            p["text"] = p.pop("name")
            return db.annotate(kind="name", **p)
        if method == "comment":
            return db.annotate(kind="comment", **p)
        if method == "disasm":
            return db.disassembly(**p)
        if method == "render":
            from .render import render_snapshot

            output = p.pop("output")
            fmt = p.pop("format", None)
            if fmt is not None and (
                not isinstance(fmt, str) or fmt not in ("svg", "png")
            ):
                raise ValueError("format must be svg or png")
            destination = Path(output).expanduser().resolve()
            protected = [
                db.path,
                Path(str(db.path) + "-wal"),
                Path(str(db.path) + "-shm"),
            ]
            if any(
                destination == item
                or (
                    destination.exists()
                    and item.exists()
                    and destination.samefile(item)
                )
                for item in protected
            ):
                raise ValueError(
                    "render output cannot overwrite a project database or SQLite sidecar"
                )
            snapshot = db.disassembly(**p)
            if not snapshot["instructions"]:
                raise ValueError(
                    "no stored instructions at this address; run analyze first"
                )
            return render_snapshot(snapshot, destination, fmt)
        return getattr(db, method)(**p)


def public_addresses(value, field=None):
    address_fields = {
        "address",
        "virtual_address",
        "entrypoint",
        "imagebase",
        "target",
        "start",
        "end",
        "source",
        "concrete_target",
        "interval_start",
        "interval_end",
        "possible_start",
        "possible_end",
        "slot",
        "stub",
        "slot_address",
        "stub_address",
        "storage_address",
        "resolver_address",
        "source_address",
        "target_address",
        "next_address",
    }
    if isinstance(value, dict):
        return {key: public_addresses(item, key) for key, item in value.items()}
    if isinstance(value, list):
        return [
            public_addresses(
                item, "address" if field in ("addresses", "stub_addresses") else None
            )
            for item in value
        ]
    if (
        field in address_fields
        and isinstance(value, int)
        and not isinstance(value, bool)
    ):
        return hex(value)
    return value


def respond(request, default_project=None, debugger=None):
    request_id = None
    policy = None
    try:
        policy = current_output_policy()
        if not isinstance(request, dict) or not isinstance(request.get("method"), str):
            raise ValueError(
                "request must be an object with method and optional params/id"
            )
        request_id = validate_request_id(request.get("id"))
        params = request.get("params", {})
        standalone = source_catalog_request(request["method"], params) or (
            request["method"]
            in (
                "uil-check",
                "uil-catalog",
                "uil-run",
                "uil-compile",
                "uil-link",
                "uil-components",
                "uil-build",
                "uil-seal",
                "uil-desktop",
                "uil-desktop-build",
                "uil-desktop-seal",
                "uil-fold",
                "uil-expand",
                "capture-audit",
                "macos-snapshot",
                "macos-session",
                "macos-session-recover",
                "capabilities",
                "media-modules",
                "format-modules",
                "intake-inventory",
                "file-identify",
                "smk-frame",
                "media-inspect",
                "media-extract",
                "agent-skill",
                "identify",
                "inspect",
                "help",
                "decoder-check",
                "doctor",
                "dos-services",
                "omf-catalog",
                "gog-list",
                "gog-unpack",
                "agi-logic",
                "decoder-modules",
                "module-analyze",
                "module-lift",
                "zmachine-disasm",
                "zmachine-analyze",
                "le-driver-inspect",
                "le-driver-disasm",
                "qemm-config",
                "qemm-profile",
                "qpi-probe",
                "qpi-report",
                "desqview-profile",
                "desqview-probe",
                "desqview-report",
                "desqview-module-inspect",
                "output-info",
                "output-read",
                "output-select",
                "output-export",
            )
            or request["method"] == "managed"
            and isinstance(params, dict)
            and "path" in params
        )
        standalone = standalone or request["method"] in {
            'console-udc',
            'console-udc-targets',
            'disc-inspect',
            'genesis-replay-build',
            'genesis-replay-export',
            'genesis-replay-inspect',
            'genesis-replay-profiles',
            'genesis-replay-source',
            'nes-multicart-build',
            'nes-multicart-inspect',
            'nes-multicart-profiles',
            'rom-disasm',
            'rom-game-lift',
            'rom-inspect',
            'shadowrun-ai-build',
            'shadowrun-ai-profiles',
            'shadowrun-city-export',
            'shadowrun-opening-animation-build',
            'shadowrun-opening-build',
            'shadowrun-opening-export',
            'shadowrun-opening-inspect',
            'shadowrun-opening-profiles',
            'shadowrun-play-build',
            'shadowrun-snes-build',
            'shadowrun-system-build-check',
            'shadowrun-system-export',
            'shadowrun-system-inspect',
            'shadowrun-systems',
        }
        standalone = standalone or request["method"] in {"agi-scenes", "kq1-bow-intents", "kq1-bow-evaluate"}
        if default_project is not None and isinstance(params, dict) and not standalone:
            params = {"project": default_project, **params}
        result = invoke(request["method"], params, debugger)
        # Catalog definitions can contain enum members named "address" or
        # "target". Preserve their numeric values for exact round trips.
        if (
            request["method"] not in BLOCK_METHODS
            and request["method"] not in SOURCE_METHODS
            and request["method"] != "export-types"
            and not request["method"].startswith("uil-")
        ):
            result = public_addresses(result)
        value = {"id": request_id, "ok": True, "result": result}
    except (
        ValueError,
        TypeError,
        KeyError,
        OSError,
        sqlite3.Error,
        OverflowError,
        AttributeError,
        RecursionError,
    ) as e:
        value = {
            "id": request_id,
            "ok": False,
            "error": {"type": type(e).__name__, "message": str(e)},
        }
        from .udc_layers import LayerQualificationError
        if isinstance(e, LayerQualificationError):
            value["error"]["qualification"] = e.receipt
    return (policy or OutputPolicy()).bound(value)


def load_request(value):
    def invalid_constant(value):
        raise ValueError(f"non-finite JSON number is not supported: {value}")

    return json.loads(value, parse_constant=invalid_constant)


def emit(value):
    line = current_output_policy().render(value) + "\n"
    binary = getattr(sys.stdout, "buffer", None)
    if binary is not None:
        # Keep the promised wire budget even if the text stream translates LF.
        sys.stdout.flush()
        binary.write(line.encode("ascii"))
        binary.flush()
    else:
        sys.stdout.write(line)
        sys.stdout.flush()


def serve(default_project=None, debug_launch=None):
    from .debugger import DebugWorkspace

    debugger = DebugWorkspace()
    try:
        if debug_launch is not None:
            result = respond(
                {"id": "launch", "method": "debug-launch", "params": debug_launch},
                default_project,
                debugger,
            )
            emit(result)
            if not result["ok"]:
                return 1
        while True:
            line = sys.stdin.buffer.readline(1024 * 1024 + 1)
            if not line:
                return 0
            if len(line) > 1024 * 1024:
                emit(
                    {
                        "id": None,
                        "ok": False,
                        "error": {
                            "type": "ValueError",
                            "message": "request exceeds 1 MiB; stream closed",
                        },
                    }
                )
                return 1
            try:
                request = load_request(line)
            except (ValueError, UnicodeDecodeError, RecursionError) as e:
                emit(
                    {
                        "id": None,
                        "ok": False,
                        "error": {"type": "InvalidJSON", "message": str(e)},
                    }
                )
                continue
            emit(respond(request, default_project, debugger))
    finally:
        debugger.close()


def parser():
    root = argparse.ArgumentParser(
        prog="fdisbull",
        description="Agent-first disassembly with SQLite persistence and headless image export",
    )
    root.add_argument("--version", action="version", version=__version__)
    root.add_argument(
        "--max-output-bytes",
        type=int,
        help="Core JSON reply budget including newline (4096..1048576; default 65536)",
    )
    root.add_argument(
        "--output-artifact-dir", help="Private output-artifact directory outside Git"
    )
    sub = root.add_subparsers(dest="command", required=True)
    for name in ("output-info", "output-read", "output-select", "output-export"):
        c = sub.add_parser(name, help=METHODS[name])
        c.add_argument("artifact")
        if name == "output-read":
            c.add_argument("--offset", type=int, default=0)
            c.add_argument("--length", type=int, default=1024)
        elif name == "output-select":
            c.add_argument("pointer", nargs="?", default="")
            c.add_argument("--max-bytes", type=int, default=16384)
        elif name == "output-export":
            c.add_argument("output")
    c = sub.add_parser(
        "text-host",
        help="Serve one local text player over a qualified original-game projection",
    )
    c.add_argument(
        "configuration",
        help="Private JSON configuration; game, state and project paths remain local",
    )
    c.add_argument(
        "--fair-play",
        action="store_true",
        help="Disable assisted within-room teleports and room jumps for this host",
    )
    c.add_argument(
        "--spatial-mode",
        choices=["physical", "assisted", "story"],
        help="Choose ordinary movement, qualified placement or source-identified proximity waivers",
    )
    c = sub.add_parser(
        "zork",
        help="Bounded original-story JSON-lines harness with an explicitly selected Jericho Python",
    )
    c.add_argument("story")
    c.add_argument("--python", required=True)
    c.add_argument("--seed", type=int, default=123)
    c.add_argument("--timeout-ms", type=int, default=10000)
    c.add_argument("--resume")
    c.add_argument(
        "--checkpoint",
        help="Private checkpoint updated atomically after each completed command",
    )
    c.add_argument("--scenes", help="Private qualified named-scene/action JSON mapping")
    c = sub.add_parser(
        "story-info",
        help="Recognize raw Z-machine v3 by structure, independent of extension",
    )
    c.add_argument("story")
    c = sub.add_parser(
        "zork-recover",
        help="Recover the qualified R88 mailbox action into shared source-backed IL",
    )
    c.add_argument("story")
    c = sub.add_parser(
        "zork-uil",
        help="Convert a complete v3 story to executable word16 IR (legacy command name)",
    )
    c.add_argument("story")
    c.add_argument("--output", required=True)
    c.add_argument(
        "--mapping", help="Optional private UDL source mapping (.json or .json.gz)"
    )
    c.add_argument("--world", help="Optional private initial Z object/state projection")
    c = sub.add_parser(
        "zork-intents",
        help="Recover bounded game-intent UIL with UDL definitions and retained low-level IR",
    )
    c.add_argument("story")
    c.add_argument(
        "--output", required=True, help="New private runnable intent/IR package"
    )
    c.add_argument(
        "--ir", help="Preserved word16 IR; compiled from the story when omitted"
    )
    c.add_argument("--uil", help="Optional private address-free game-intent definition")
    c.add_argument(
        "--udl",
        help="Optional private source bindings, evidence and residual definitions",
    )
    c = sub.add_parser(
        "zork-scenes",
        help="Recover named scene rules and direct handler links with explicit residual IR",
    )
    c.add_argument("story")
    c.add_argument("--output", required=True, help="New private runnable scene package")
    c.add_argument("--intents", help="Existing intent/IR package to preserve exactly")
    c.add_argument("--uil", help="Optional private address-free scene definitions")
    c.add_argument(
        "--dispatch",
        help="Optional private named rule links with explicit residual bodies",
    )
    c.add_argument("--udl", help="Optional private source correspondence and witnesses")
    for name in ("il-check", "il-run"):
        c = sub.add_parser(
            name,
            help="Validate or evaluate the shared UDL/UIL primitive block representation",
        )
        c.add_argument("program")
        c.add_argument("--state")
        c.add_argument(
            "--capability",
            action="append",
            choices=("graphics", "audio", "input"),
            default=[],
        )
        if name == "il-run":
            c.add_argument("--effect-context", help="Private explicit object/resource model context")
            c.add_argument("--checkpoint", help="Private suspended model invocation")
            c.add_argument("--host-result", help="Matching explicit host completion result")
            c.add_argument("--max-steps", type=int, default=1024)
            c.add_argument("--max-call-depth", type=int, default=8)
    c = sub.add_parser(
        "il-store",
        help="Store an immutable source-checked shared IL revision with a project",
    )
    c.add_argument("project")
    c.add_argument("name")
    c.add_argument("program")
    c.add_argument("--version", type=int)
    c.add_argument("--parent")
    c.add_argument("--source")
    c.add_argument("--source-name", default="story")
    c = sub.add_parser(
        "il-info",
        help="Read an immutable IL revision and verify its attached source evidence",
    )
    c.add_argument("project")
    c.add_argument("revision")
    c.add_argument("--version", type=int)
    for name in ("uil-check", "uil-run", "uil-compile", "uil-link"):
        c = sub.add_parser(name, help=METHODS[name])
        c.add_argument("program")
        c.add_argument("--presentation", required=name != "uil-check")
        c.add_argument("--catalog", required=name in ("uil-compile", "uil-link"))
        c.add_argument("--orchestration", required=name in ("uil-compile", "uil-link"))
        if name == "uil-run":
            c.add_argument(
                "--inputs", help="JSON file with the indexed entry input list"
            )
            c.add_argument("--max-steps", type=int, default=4000000)
        if name == "uil-compile":
            c.add_argument("--output", required=True)
            c.add_argument("--c-compiler")
            c.add_argument("--source-only", action="store_true")
        if name in ("uil-compile", "uil-link"):
            c.add_argument(
                "--target",
                choices=(
                    "python",
                    "javascript",
                    "macos-arm64",
                    "linux-x64",
                    "windows-x64",
                )
                if name == "uil-compile"
                else ("macos-arm64", "linux-x64", "windows-x64"),
                required=name == "uil-link",
                default="python" if name == "uil-compile" else None,
            )
            c.add_argument(
                "--arithmetic",
                choices=("portable-c", "native-asm"),
                default="portable-c",
            )
            c.add_argument(
                "--module-requirements",
                help="JSON file of exact per-module intrinsic/component requirements",
            )
    c = sub.add_parser("uil-build", help=METHODS["uil-build"])
    c.add_argument("output")
    c.add_argument("--c-compiler")
    c = sub.add_parser("uil-seal", help=METHODS["uil-seal"])
    c.add_argument("output")
    c.add_argument("--compiler-evidence")
    c = sub.add_parser("uil-desktop", help=METHODS["uil-desktop"])
    for field in (
        "program",
        "presentation",
        "catalog",
        "orchestration",
        "plan",
        "initial",
        "output",
    ):
        c.add_argument(field)
    c.add_argument(
        "--target",
        choices=("macos-arm64", "linux-x64", "windows-x64"),
        default="macos-arm64",
    )
    c.add_argument("--source-only", action="store_true")
    c.add_argument(
        "--variants",
        help="JSON file containing declared sealed implementation variants",
    )
    c.add_argument("--c-compiler")
    c = sub.add_parser("uil-desktop-build", help=METHODS["uil-desktop-build"])
    c.add_argument("output")
    c.add_argument("--c-compiler")
    c = sub.add_parser("uil-desktop-seal", help=METHODS["uil-desktop-seal"])
    c.add_argument("output")
    c = sub.add_parser("uil-components", help=METHODS["uil-components"])
    c.add_argument("modules")
    c.add_argument("providers")
    c.add_argument(
        "--target", required=True, choices=("macos-arm64", "linux-x64", "windows-x64")
    )
    c.add_argument("--pins")
    c = sub.add_parser("uil-catalog", help=METHODS["uil-catalog"])
    c.add_argument("blocks")
    c = sub.add_parser("uil-fold", help=METHODS["uil-fold"])
    c.add_argument("program")
    c.add_argument("function", type=int)
    c.add_argument("semantic_id")
    c = sub.add_parser("uil-expand", help=METHODS["uil-expand"])
    c.add_argument("program")
    c.add_argument("recovery")
    c = sub.add_parser("uil-store", help=METHODS["uil-store"])
    c.add_argument("project")
    c.add_argument("name")
    c.add_argument("package")
    c.add_argument("--version", type=int)
    c.add_argument("--parent")
    c.add_argument("--author", default="agent")
    c = sub.add_parser("uil-info", help=METHODS["uil-info"])
    c.add_argument("project")
    c.add_argument("revision")
    c.add_argument("--full", action="store_true")
    c = sub.add_parser("uil-list", help=METHODS["uil-list"])
    c.add_argument("project")
    c.add_argument("--limit", type=int, default=100)
    c.add_argument("--offset", type=int, default=0)
    for name in ("udc-capture", "udc-info", "udc-programs", "udc-compile"):
        c = sub.add_parser(
            name,
            help="Original-backed DOS block definitions and private byte-preserving compilation",
        )
        c.add_argument("project")
        c.add_argument("name" if name == "udc-capture" else "definition")
        if name == "udc-capture":
            c.add_argument("--resources")
            c.add_argument("--blocks")
            c.add_argument("--version", type=int, default=1)
            c.add_argument("--parent")
            c.add_argument("--author", default="agent")
            c.add_argument("--main-name")
        elif name == "udc-info":
            c.add_argument("--full", action="store_true")
        elif name == "udc-programs":
            c.add_argument("--role", choices=("udl", "uil"), default="uil")
            c.add_argument("--output", required=True)
        else:
            c.add_argument("output")
            c.add_argument("--programs")
    for name in ("udl-lift-asm", "udl-lift-c"):
        c = sub.add_parser(
            name, help="Lift only the declared straight-line u16 register subset"
        )
        c.add_argument("source")
        c.add_argument("--bindings", required=True)
        c.add_argument("--input", action="append", default=[])
        c.add_argument("--output-register", action="append", required=True)
        c.add_argument("--output", required=True)
    c = sub.add_parser(
        "udl-verify",
        help="Z3 comparison of a source block and candidate UIL under explicit assumptions",
    )
    c.add_argument("lift")
    c.add_argument("program")
    c.add_argument("--timeout-ms", type=int, default=1000)
    c.add_argument(
        "--output", help="Save the full proof specifications; stdout stays compact"
    )
    c = sub.add_parser("agent-skill", help=METHODS["agent-skill"])
    c.add_argument(
        "--skill",
        choices=tuple(AGENT_SKILLS),
        help="Select a bundled skill (default: fdisbull-investigate)",
    )
    g = c.add_mutually_exclusive_group()
    g.add_argument(
        "--reference",
        help="Read one allowlisted file from the selected skill; use --index for paths",
    )
    g.add_argument(
        "--index",
        action="store_true",
        help="List guide purposes without fetching any guide contents",
    )
    g.add_argument(
        "--list",
        action="store_true",
        help="List bundled skills without fetching their contents",
    )
    for name in (
        "debug-save-scene",
        "debug-scenes",
        "debug-scene-info",
        "debug-scene-domain-audit",
        "debug-scene-overlay",
        "debug-scene-observations",
        "debug-scene-observation",
        "debug-export-scenes",
        "debug-import-scenes",
    ):
        c = sub.add_parser(name, help=METHODS[name])
        c.add_argument("project")
        if name not in ("debug-scene-observations", "debug-scene-observation"):
            c.add_argument("--version", type=int)
        if name == "debug-save-scene":
            c.add_argument("name")
            c.add_argument("definition_file")
            c.add_argument("--parent")
            c.add_argument("--author", default="agent")
        elif name in ("debug-scene-info", "debug-scene-domain-audit", "debug-scene-overlay"):
            c.add_argument("scene")
            if name == "debug-scene-domain-audit":
                c.add_argument("--max-checks", type=int, default=4096)
            if name == "debug-scene-overlay":
                c.add_argument("--artifact")
                c.add_argument("--name", default="scene-overlay.png")
                c.add_argument("--grid-step", type=int, default=8)
                c.add_argument(
                    "--labels", choices=["names", "numbers"], default="names"
                )
        elif name == "debug-scene-observations":
            c.add_argument("--revision")
            c.add_argument("--run")
            c.add_argument("--limit", type=int, default=100)
        elif name == "debug-scene-observation":
            c.add_argument("observation")
            c.add_argument("--compact", action="store_true")
        elif name == "debug-export-scenes":
            c.add_argument("output")
            c.add_argument("scenes", nargs="+")
        elif name == "debug-import-scenes":
            c.add_argument("bundle")
    c = sub.add_parser("dos-services", help=METHODS["dos-services"])
    c.add_argument("--vector", type=lambda s: int(s, 0))
    c.add_argument("--ax", type=lambda s: int(s, 0))
    c.add_argument("--registers", type=json.loads, default={})
    c = sub.add_parser("omf-catalog", help=METHODS["omf-catalog"])
    c.add_argument("path")
    c.add_argument("--abi", default="x86_16_cdecl_near")
    c = sub.add_parser("capabilities", help=METHODS["capabilities"])
    c.add_argument("--analyze-headless")
    c.add_argument("--lldb")
    c.add_argument("--java")
    c = sub.add_parser("macos-snapshot", help=METHODS["macos-snapshot"])
    c.add_argument("bundle_id")
    c = sub.add_parser("macos-session", help=METHODS["macos-session"])
    c.add_argument("bundle_id")
    c.add_argument("output")
    c.add_argument("--live", action="store_true", help="Explicitly permit the selected status-menu action and declared preference changes")
    c.add_argument("--status-index", type=int)
    c.add_argument("--display-id", type=int)
    c.add_argument("--rect", type=json.loads, help="Global CoreGraphics logical rectangle as JSON {x,y,width,height}")
    c.add_argument("--keys", action="append", default=[])
    c.add_argument("--preference-changes", type=json.loads, help="Explicit key-to-binary-plist values as JSON; null removes a key")
    c.add_argument("--max-seconds", type=float, default=30)
    c = sub.add_parser("macos-session-recover", help=METHODS["macos-session-recover"])
    c.add_argument("output")
    c=sub.add_parser('rom-inspect',help=METHODS['rom-inspect'])
    c.add_argument('path')
    sub.add_parser('console-udc-targets',help=METHODS['console-udc-targets'])
    c=sub.add_parser('console-udc',help=METHODS['console-udc'])
    c.add_argument('path')
    c.add_argument('--target',choices=['nes','genesis'],required=True)
    c.add_argument('--output',required=True)
    c.add_argument('--display-variable')
    c.add_argument('--scene',dest='scene_path',help='optional NES level scene JSON')
    c.add_argument('--region',dest='region_path',help='original immutable ROM region for a procedural game profile')
    c.add_argument('--cc65-root',help='prepared external cc65 toolchain for the banked procedural game profile')
    c.add_argument('--m68k-root',help='prepared external m68k-elf toolchain for the full Genesis procedural profile')
    c=sub.add_parser('rom-game-lift',help=METHODS['rom-game-lift'])
    c.add_argument('path');c.add_argument('--output',required=True)
    c.add_argument('--variant',choices=['efficient','baseline'],default='efficient')
    sub.add_parser('genesis-replay-profiles',help=METHODS['genesis-replay-profiles'])
    for name in ('genesis-replay-source','genesis-replay-inspect'):
        c=sub.add_parser(name,help=METHODS[name]);c.add_argument('path')
    c=sub.add_parser('genesis-replay-export',help=METHODS['genesis-replay-export'])
    c.add_argument('path');c.add_argument('--output',required=True)
    c.add_argument('--target',choices=['nes','genesis'],default='nes')
    c.add_argument('--cc65-root');c.add_argument('--m68k-root')
    c.add_argument('--variant',choices=['efficient','baseline'],default='efficient')
    c.add_argument('--procedures',type=json.loads,help='JSON map of reviewed procedure names to baseline/efficient')
    c=sub.add_parser('genesis-replay-build',help=METHODS['genesis-replay-build'])
    c.add_argument('path');c.add_argument('--output',required=True)
    c.add_argument('--rom',dest='rom_path',required=True)
    c.add_argument('--target',choices=['nes','genesis'],default='nes')
    c.add_argument('--cc65-root');c.add_argument('--m68k-root')
    sub.add_parser('shadowrun-systems',help=METHODS['shadowrun-systems'])
    c=sub.add_parser('shadowrun-play-build',help=METHODS['shadowrun-play-build'])
    c.add_argument('path');c.add_argument('--rom',dest='rom_path',required=True);c.add_argument('--capture',required=True)
    c.add_argument('--cc65-root',required=True);c.add_argument('--output',required=True)
    sub.add_parser('shadowrun-ai-profiles',help=METHODS['shadowrun-ai-profiles'])
    c=sub.add_parser('shadowrun-snes-build',help=METHODS['shadowrun-snes-build'])
    c.add_argument('--rom',dest='rom_path',required=True)
    c.add_argument('--ram',required=True);c.add_argument('--save-ram',required=True)
    c.add_argument('--output',required=True)
    c=sub.add_parser('shadowrun-ai-build',help=METHODS['shadowrun-ai-build'])
    c.add_argument('path');c.add_argument('--rom',dest='rom_path',required=True);c.add_argument('--capture',required=True)
    c.add_argument('--cc65-root');c.add_argument('--output',required=True)
    c.add_argument('--profile',choices=['assisted-arena','captured-courtyard'],default='assisted-arena')
    c.add_argument('--preset',choices=['stationary','moving','courtyard'])
    c.add_argument('--target',choices=['nes','macos-arm64'])
    c=sub.add_parser('shadowrun-city-export',help=METHODS['shadowrun-city-export'])
    c.add_argument('rom_path');c.add_argument('--snapshot',required=True);c.add_argument('--output',required=True)
    c.add_argument('--profile',choices=['static','assisted-arena'],default='static')
    c.add_argument('--preset',choices=['stationary','moving'],default='stationary')
    c=sub.add_parser('shadowrun-z',help='Serve a prepared Shadowrun model through the text-player protocol')
    c.add_argument('rom_path');c.add_argument('--snapshot',required=True);c.add_argument('--policy',choices=['physical','assisted'],default='physical')
    c.add_argument('--profile',choices=['static','assisted-arena'],default='static')
    c.add_argument('--preset',choices=['stationary','moving'],default='stationary')
    c=sub.add_parser('shadowrun-system-export',help=METHODS['shadowrun-system-export'])
    c.add_argument('rom_path');c.add_argument('--system',required=True);c.add_argument('--output',required=True)
    c=sub.add_parser('shadowrun-system-inspect',help=METHODS['shadowrun-system-inspect'])
    c.add_argument('path')
    c=sub.add_parser('shadowrun-system-build-check',help=METHODS['shadowrun-system-build-check'])
    c.add_argument('path');c.add_argument('--rom',dest='rom_path',required=True);c.add_argument('--procedure',required=True)
    c.add_argument('--cases',dest='cases_path',required=True);c.add_argument('--cc65-root',required=True);c.add_argument('--output',required=True)
    sub.add_parser('shadowrun-opening-profiles',help=METHODS['shadowrun-opening-profiles'])
    c=sub.add_parser('shadowrun-opening-export',help=METHODS['shadowrun-opening-export'])
    c.add_argument('rom_path');c.add_argument('--snapshot',required=True);c.add_argument('--atlas',required=True);c.add_argument('--output',required=True)
    c=sub.add_parser('shadowrun-opening-inspect',help=METHODS['shadowrun-opening-inspect'])
    c.add_argument('path')
    c=sub.add_parser('shadowrun-opening-build',help=METHODS['shadowrun-opening-build'])
    c.add_argument('path');c.add_argument('--rom',dest='rom_path',required=True);c.add_argument('--cc65-root',required=True);c.add_argument('--output',required=True)
    c=sub.add_parser('shadowrun-opening-animation-build',help=METHODS['shadowrun-opening-animation-build'])
    c.add_argument('path');c.add_argument('--rom',dest='rom_path',required=True);c.add_argument('--capture',required=True)
    c.add_argument('--cc65-root',required=True);c.add_argument('--output',required=True)
    sub.add_parser('nes-multicart-profiles',help=METHODS['nes-multicart-profiles'])
    c=sub.add_parser('nes-multicart-inspect',help=METHODS['nes-multicart-inspect'])
    c.add_argument('path')
    c=sub.add_parser('nes-multicart-build',help=METHODS['nes-multicart-build'])
    c.add_argument('inputs',nargs='+')
    c.add_argument('--output',required=True)
    c.add_argument('--authored-compatible',action='store_true',
                   help='assert these authored NROM games use no PRG-ROM writes or cartridge RAM')
    c=sub.add_parser('rom-disasm',help=METHODS['rom-disasm'])
    c.add_argument('path')
    c.add_argument('--base-address',type=lambda s:int(s,0),required=True,help='explicit address mapping source file offset zero')
    c.add_argument('--backend',choices=['capstone','ghidra','saturn-recomp'],default='capstone')
    c.add_argument('--offset',type=lambda s:int(s,0),default=0)
    c.add_argument('--length',type=lambda s:int(s,0))
    c.add_argument('--max-instructions',type=int,default=256)
    c.add_argument('--mode',choices=['linear','word-scan'],default='linear')
    c.add_argument('--ghidra-home');c.add_argument('--saturn-recomp-root')
    c.add_argument('--timeout',type=float,default=60.0)
    c=sub.add_parser('disc-inspect',help=METHODS['disc-inspect'])
    c.add_argument('path')
    c.add_argument('--mode',choices=['MODE1/2048','MODE1/2352'])
    c.add_argument('--max-entries',type=int,default=10000)
    c.add_argument('--max-directory-bytes',type=int,default=8*1024*1024)
    c.add_argument('--max-depth',type=int,default=32)
    c = sub.add_parser("doctor", help=METHODS["doctor"])
    c.add_argument(
        "--backend", choices=["dosbox", "dosbox-qemu", "wine-qemu"], required=True
    )
    c.add_argument("--executable", required=True)
    c.add_argument("--kernel")
    c.add_argument("--initramfs")
    c.add_argument("--output")
    c.add_argument("--boot-timeout-ms", type=int, default=240000)
    for name in ("le-driver-inspect", "le-driver-disasm"):
        c = sub.add_parser(name, help=METHODS[name])
        c.add_argument("path")
        if name == "le-driver-disasm":
            c.add_argument("object_number", type=lambda s: int(s, 0))
            c.add_argument("--offset", type=lambda s: int(s, 0), default=0)
            c.add_argument("--max-instructions", type=int, default=32)
            c.add_argument("--abi", choices=["unknown", "windows-vxd"], default="unknown")
    c = sub.add_parser("qemm-config", help=METHODS["qemm-config"])
    c.add_argument("--config-file")
    c.add_argument("--qemm-path", default=r"C:\QEMM\QEMM386.SYS")
    c.add_argument("--options", default="RAM")
    c.add_argument("--validate-only", action="store_true")
    c = sub.add_parser("qemm-profile", help=METHODS["qemm-profile"])
    c.add_argument("boot_image")
    c.add_argument("--config-sys", help="Optional host file to compare with the image's CONFIG.SYS")
    c.add_argument("--driver-path", help="Optional host file to compare with the image's QEMM386.SYS")
    c = sub.add_parser("qpi-probe", help=METHODS["qpi-probe"])
    c.add_argument("output")
    c.add_argument("--mode", choices=["breakpoint", "file"], default="breakpoint")
    c = sub.add_parser("qpi-report", help=METHODS["qpi-report"])
    c.add_argument("path")
    c.add_argument("--include-pages", action="store_true")
    c = sub.add_parser('desqview-profile', help=METHODS['desqview-profile'])
    c.add_argument('boot_image')
    c.add_argument('--program', default=r'\DV\DV.EXE')
    c.add_argument('--module', dest='modules', action='append')
    c.add_argument('--qemm', action='store_true')
    c.add_argument('--startup')
    c = sub.add_parser('desqview-probe', help=METHODS['desqview-probe'])
    c.add_argument('output')
    c.add_argument('--mode', choices=['file','breakpoint'], default='file')
    c.add_argument('--yields', type=int, default=0)
    c.add_argument('--nonce')
    c = sub.add_parser('desqview-report', help=METHODS['desqview-report'])
    c.add_argument('path')
    c = sub.add_parser('desqview-module-inspect', help=METHODS['desqview-module-inspect'])
    c.add_argument('path')
    c.add_argument('--expected-type')
    c.add_argument('--expected-version', type=lambda value: int(value,0))
    for name in ('memory-snapshot-info','memory-search-start','memory-search-refine','memory-search-results','memory-edit-plan','memory-rule-create','memory-rule-info'):
        c = sub.add_parser(name, help=METHODS[name])
        c.add_argument('project')
        c.add_argument('snapshot' if name in ('memory-snapshot-info','memory-search-start') else 'rule' if name == 'memory-rule-info' else 'search')
        if name == 'memory-search-refine':
            c.add_argument('snapshot')
            c.add_argument('--mode', required=True, choices=['equal','not_equal','changed','unchanged','increased','decreased','delta'])
            c.add_argument('--value', type=int)
            c.add_argument('--delta', type=int)
            c.add_argument('--max-candidates', type=int, default=1048576)
        elif name == 'memory-search-start':
            c.add_argument('--mode', choices=['unknown','equal','range'], default='unknown')
            c.add_argument('--width', type=int, choices=[1,2,4,8], default=1)
            c.add_argument('--signed', action='store_true')
            c.add_argument('--byteorder', choices=['little','big'], default='little')
            c.add_argument('--stride', type=int, default=1)
            c.add_argument('--bias', type=int, default=0)
            c.add_argument('--value', type=int)
            c.add_argument('--minimum', type=int)
            c.add_argument('--maximum', type=int)
            c.add_argument('--max-candidates', type=int, default=1048576)
        elif name == 'memory-search-results':
            c.add_argument('--offset', type=int, default=0)
            c.add_argument('--limit', type=int, default=64)
        elif name in ('memory-edit-plan','memory-rule-create'):
            c.add_argument('--offset', type=int, required=True)
            c.add_argument('--value', type=int, required=True)
            c.add_argument('--condition', choices=['equal','not_equal','greater','greater_equal','less','less_equal','always'], default='always' if name == 'memory-rule-create' else 'equal')
            c.add_argument('--compare-value', type=int)
            if name == 'memory-rule-create':
                c.add_argument('--max-applications', type=int, default=128)
                c.add_argument('--max-ticks', type=int, default=4096)
                c.add_argument('--name', default='memory-rule')
    c = sub.add_parser(
        "debug",
        help="Launch a project execution backend and accept live debugger JSON commands on stdin",
    )
    c.add_argument("project")
    c.add_argument("--executable", required=True)
    c.add_argument("--game-dir", required=True)
    c.add_argument("--memory-mib", type=int, help="Owned Windows guest RAM, up to 8192 MiB")
    c.add_argument("--version", type=int)
    c.add_argument("--guest-profile", choices=["qemm", "qemm-386-v1", "desqview", "desqview-386-v1"],
                   help="Admit and pin a QEMM/DESQview raw DOS boot image (qemu-machine only; JSON accepts an explicit prepared profile)")
    c.add_argument(
        "--backend",
        choices=["dosbox", "dosbox-qemu", "wine-qemu", "ida-wine-qemu", "qemu-machine", "wine-ne",
                 "scummvm-agi", "scummvm-gob", "scummvm-kyra"],
    )
    c.add_argument("--game-id", help="Explicit ScummVM engine/game ID, for example agi:kq1, gob:lit, kyra:kyra1 or kyra:lol")
    c.add_argument("--language", help="Explicit Gob language code, for example us (English US) or it")
    c.add_argument("--platform", help="Explicit Gob game platform, for example dos")
    c.add_argument(
        "--remote-server",
        help="User-supplied IDA 9.4 win64_remote.exe (IDA backend only)",
    )
    c.add_argument("--kernel")
    c.add_argument("--initramfs")
    c.add_argument("--files", type=json.loads)
    c.add_argument("--boot-timeout-ms", type=int, default=240000)
    c.add_argument(
        "--state", help="PE64 native checkpoint artifact to restore without cold launch"
    )
    c.add_argument(
        "--dot-mode",
        "--window",
        dest="window",
        action="store_true",
        help="Request dot-mode: a watch-only DOSBox window or Windows spectator viewer; host input stays outside the guest",
    )
    c.add_argument("--spatial-mode", choices=["physical", "assisted", "story"])
    c.add_argument(
        "--fair-play", action="store_true", help="Lock this session to physical mode"
    )
    for name in (
        "debug-runs",
        "debug-artifacts",
        "debug-export",
        "debug-grid",
        "debug-save-script",
        "debug-scripts",
        "debug-state-info",
        "debug-anchor-stone-info",
        "debug-fork-state",
        "debug-experiments",
        "debug-experiment-info",
        "debug-promote-code",
        "debug-trace-view",
        "runtime-version-info",
    ):
        c = sub.add_parser(name, help=METHODS[name])
        c.add_argument("project")
        if name in ("debug-state-info", "debug-anchor-stone-info", "debug-experiment-info"):
            c.add_argument("artifact")
        elif name == "debug-trace-view":
            c.add_argument("artifact")
            c.add_argument("--version", type=int, required=True)
        elif name == "debug-promote-code":
            c.add_argument("artifact")
            c.add_argument("--label", default="runtime interpretation")
            c.add_argument("--max-instructions", type=int, default=128)
            c.add_argument("--defer", action="store_true")
        elif name == "debug-fork-state":
            c.add_argument("artifact")
            c.add_argument("--executable", required=True)
            c.add_argument("--game-dir", required=True)
            c.add_argument("--name", default="derived.sav")
            c.add_argument("--memory", type=json.loads, default=[])
            c.add_argument("--registers", type=json.loads, default={})
            c.add_argument("--backend", choices=["dosbox", "dosbox-qemu", "wine-qemu"])
            c.add_argument("--kernel")
            c.add_argument("--initramfs")
            c.add_argument(
                "--dot-mode",
                "--window",
                dest="window",
                action="store_true",
                help="Request dot-mode: a watch-only native DOSBox window",
            )
        elif name == "debug-export":
            c.add_argument("artifact")
            c.add_argument("output")
        elif name == "debug-grid":
            c.add_argument("artifact")
            c.add_argument("--name", default="coordinate-grid.png")
            c.add_argument("--step", type=int, default=32)
            c.add_argument(
                "--target",
                type=json.loads,
                help="Optional native [x,y] coordinate marker",
            )
        else:
            c.add_argument("--version", type=int)
            if name == "debug-artifacts":
                c.add_argument("--run")
            if name == "debug-save-script":
                c.add_argument("name")
                c.add_argument("script", type=json.loads, help="JSON script object")
    sub.add_parser("media-modules", help=METHODS["media-modules"])
    c = sub.add_parser("format-modules", help=METHODS["format-modules"])
    c.add_argument("--catalog", dest="catalog_path", help="Persist/reopen metadata-only SQLite format catalog")
    c = sub.add_parser("intake-inventory", help=METHODS["intake-inventory"])
    c.add_argument("paths", nargs="+", help="Explicit game/collection file or directory roots")
    c.add_argument("--catalog", dest="catalog_path")
    c.add_argument("--max-files", type=int, default=10000)
    c.add_argument("--max-read-bytes", type=int, default=256 * 1024 * 1024)
    c.add_argument("--max-binary-bytes", type=int, default=64 * 1024 * 1024)
    c = sub.add_parser("file-identify", help=METHODS["file-identify"])
    c.add_argument("path")
    c.add_argument("--catalog", dest="catalog_path")
    c.add_argument("--max-binary-bytes", type=int, default=64 * 1024 * 1024)
    c.add_argument("--max-read-bytes", type=int)
    c = sub.add_parser("smk-frame", help=METHODS["smk-frame"])
    c.add_argument("path")
    c.add_argument("output", help="New directory beneath an existing private parent outside Git")
    c.add_argument("--keep-frames", type=int, default=32, help="Retain this many opening and ending images")
    c.add_argument("--max-movie-bytes", dest="smk_max_output_bytes", type=int, default=64 * 1024 * 1024)
    c.add_argument("--ffmpeg", default="ffmpeg")
    c.add_argument("--ffprobe", default="ffprobe")
    c.add_argument("--timeout", type=float, default=120)
    c = sub.add_parser("capture-audit", help=METHODS["capture-audit"])
    c.add_argument(
        "inputs", nargs="+", help="Finalized AVI files; each keeps its own clock"
    )
    c.add_argument(
        "--output",
        required=True,
        help="New directory beneath an existing private parent outside Git",
    )
    c.add_argument(
        "--every",
        type=int,
        default=0,
        help="Export frames 0,N,2N,...; 0 hashes all without PNG export",
    )
    c.add_argument(
        "--html",
        action="store_true",
        help="Self-contained sampled-frame viewer; requires --every",
    )
    c.add_argument(
        "--timeout", type=float, default=120, help="Host seconds per reader process"
    )
    c.add_argument("--max-frames", type=int, default=10000)
    c.add_argument("--max-frame-bytes", type=int, default=16 * 1024 * 1024)
    c.add_argument("--max-input-bytes", type=int, default=512 * 1024 * 1024)
    c.add_argument("--max-metadata-bytes", type=int, default=32 * 1024 * 1024)
    c.add_argument(
        "--audit-output-bytes",
        dest="capture_max_output_bytes",
        type=int,
        default=512 * 1024 * 1024,
        help="Audit file budget, separate from the global JSON reply budget",
    )
    c.add_argument("--ffmpeg", default="ffmpeg")
    c.add_argument("--ffprobe", default="ffprobe")
    for name in ("media-inspect", "media-extract"):
        c = sub.add_parser(name, help=METHODS[name])
        c.add_argument("path")
        choices = ("mz-envelope", "agi-v2", "westwood-pak", "westwood-cps", "westwood-wsa", "westwood-emc2")
        if name == "media-inspect":
            choices = choices + ("smacker", "flic")
        c.add_argument("--adapter", required=True, choices=choices)
        c.add_argument("--volume-root")
        c.add_argument("--number", type=int)
        if name == "media-inspect":
            c.add_argument("--index-path", help="Explicit TFTD VID companion IDX for structural cross-check")
        if name == "media-extract":
            c.add_argument("output")
            c.add_argument("--member", required=True)
            c.add_argument(
                "--max-payload-bytes",
                dest="media_max_output_bytes",
                type=int,
                default=64 * 1024 * 1024,
                help="Extracted member byte limit (1..67108864); separate from global JSON reply budget",
            )
    for name in ("gog-list", "gog-unpack"):
        c = sub.add_parser(name, help=METHODS[name])
        c.add_argument("path", help="local GOG Inno Setup offline installer")
        if name == "gog-unpack":
            c.add_argument("output", help="new private directory outside the checkout")
        c.add_argument(
            "--include",
            action="append",
            help="repeatable native Inno 5.6.2 member filter; list first",
        )
        c.add_argument(
            "--library-config",
            help="libraries.json to check registered SHA-256 identities (read-only)",
        )
        c.add_argument(
            "--timeout",
            type=int,
            default=300,
            help="bounded native decoding deadline in seconds (1..3600)",
        )
    for name in ("identify", "inspect"):
        c = sub.add_parser(name, help=METHODS[name])
        c.add_argument("path")
        if name == "inspect":
            c.add_argument("--slice-arch", choices=["x86", "x86_64", "arm64"])
            c.add_argument(
                "--image", choices=["auto", "pe", "le", "ne", "mz", "sys", "com", "ail"]
            )
    c = sub.add_parser("ghidra-arm64", help=METHODS["ghidra-arm64"])
    c.add_argument("project")
    c.add_argument("path")
    c.add_argument(
        "--address",
        dest="addresses",
        action="append",
        type=lambda s: int(s, 0),
        required=True,
    )
    c.add_argument(
        "--analyze-headless",
        required=True,
        help="Ghidra support/analyzeHeadless executable",
    )
    c.add_argument("--java-home", help="JDK home used by Ghidra")
    c.add_argument("--max-instructions", type=int, default=64)
    c.add_argument("--timeout-s", type=float, default=120)
    c.add_argument("--decompile-entry", type=lambda s: int(s, 0))
    c.add_argument("--decompile-timeout-s", type=int, default=10)
    c.add_argument("--version", type=int, default=1)
    c = sub.add_parser("macos-observe", help=METHODS["macos-observe"])
    c.add_argument("project")
    c.add_argument("executable")
    c.add_argument("--symbol", required=True)
    c.add_argument("--arg", dest="argv", action="append", default=[])
    c.add_argument("--timeout-seconds", type=float, default=20)
    c.add_argument("--memory-bytes", type=int, default=32)
    c.add_argument("--instruction-count", type=int, default=8)
    c.add_argument("--lldb-path")
    c.add_argument("--version", type=int, default=1)
    for name in (
        "storage-info",
        "migrate-external",
        "source-info",
        "source-candidate",
        "bind-source",
        "new-source-analysis",
    ):
        c = sub.add_parser(name, help=METHODS[name])
        if name == "source-info":
            c.add_argument("project", nargs="?")
            c.add_argument("--catalog")
        else:
            c.add_argument("project")
        if name in ("source-candidate", "bind-source", "new-source-analysis"):
            c.add_argument("path")
        if name in ("migrate-external", "new-source-analysis"):
            c.add_argument("destination")
        if name not in ("storage-info", "migrate-external"):
            c.add_argument("--version", type=int)
        if name == "bind-source":
            c.add_argument(
                "--approval",
                type=json.loads,
                help="Exact source-candidate receipt, only after user approval of this base and candidate",
            )
    c = sub.add_parser(
        "import", help="create project from executable or explicit raw code"
    )
    c.add_argument("path")
    c.add_argument("project")
    c.add_argument(
        "--profile",
        choices=["cortex-m"],
        help="explicit Cortex-M flash with Armv7-M vectors (not Armv8-M Security)",
    )
    c.add_argument(
        "--vector-count",
        type=int,
        help="declared number of vector words (16..256)",
    )
    c.add_argument(
        "--arch",
        choices=["x86", "arm64", "thumb"],
        help="explicit raw mode (bypasses executable loader)",
    )
    c.add_argument("--bits", type=int, choices=[16, 32, 64])
    c.add_argument("--base", default=None, type=lambda s: int(s, 0))
    c.add_argument("--entry", type=lambda s: int(s, 0))
    c.add_argument("--load-segment", type=lambda s: int(s, 0), default=0x1000)
    c.add_argument(
        "--image",
        choices=["auto", "pe", "le", "ne", "mz", "sys", "com", "ail"],
        help="select PE, DOS/4GW LE, Win16 NE, MZ, declared DOS COM or AIL driver",
    )
    c.add_argument(
        "--slice-arch",
        choices=["x86", "x86_64", "arm64"],
        help="select a thin/universal Mach-O CPU slice",
    )
    c.add_argument(
        "--module",
        action="store_true",
        help="allow a library without an executable entry",
    )
    c = sub.add_parser("analyze-module", help=METHODS["analyze-module"])
    c.add_argument("path")
    c.add_argument("project")
    c.add_argument("--image", choices=["auto", "pe", "le", "ne", "mz", "sys", "ail"])
    c.add_argument("--slice-arch", choices=["x86", "x86_64", "arm64"])
    c.add_argument("--export")
    c.add_argument("--entry", type=lambda s: int(s, 0))
    c.add_argument("--max-instructions", type=int, default=10000)
    c = sub.add_parser("managed", help=METHODS["managed"])
    c.add_argument("path")
    c.add_argument("--token", type=lambda s: int(s, 0))
    c.add_argument("--max-instructions", type=int)
    c = sub.add_parser("agi-logic", help=METHODS["agi-logic"])
    c.add_argument("logdir")
    c.add_argument("volume_dir")
    c.add_argument("logic", type=int)
    c.add_argument("--profile", required=True, choices=["2.917"])
    c.add_argument("--max-instructions", type=int, default=1000)
    c = sub.add_parser("agi-scenes", help=METHODS["agi-scenes"])
    c.add_argument("game_dir")
    c.add_argument("--profile", required=True, choices=["2.917"])
    c.add_argument("--stage", choices=["outline", "resolve"], default="resolve")
    c.add_argument("--include-ir", action="store_true")
    c.add_argument("--include-text", action="store_true")
    c.add_argument("--max-updates", type=int, default=200000)
    c.add_argument("--max-instructions", type=int, default=100000)
    c.add_argument("--max-code-bytes", type=int, default=1048576)
    c = sub.add_parser("kq1-bow-intents", help=METHODS["kq1-bow-intents"])
    c.add_argument("game_dir")
    c.add_argument("--output", required=True)
    c.add_argument("--uil")
    c.add_argument("--udl")
    c = sub.add_parser("kq1-bow-evaluate", help=METHODS["kq1-bow-evaluate"])
    c.add_argument("package")
    c.add_argument("--state-file", required=True)
    c.add_argument("--event-file")
    c = sub.add_parser("debug-spatial-domain-audit", help=METHODS["debug-spatial-domain-audit"])
    c.add_argument("project")
    c.add_argument("revision")
    c.add_argument("--version", type=int)
    c.add_argument("--max-checks", type=int, default=4096)
    sub.add_parser("decoder-modules", help=METHODS["decoder-modules"])
    for name in ("module-analyze", "module-lift"):
        c = sub.add_parser(name, help=METHODS[name])
        c.add_argument("module")
        c.add_argument("path")
        c.add_argument("--volume-dir")
        c.add_argument("--logic", type=int)
        c.add_argument("--profile", choices=["2.917", "kyrandia1-dos", "lol1-dos"])
        c.add_argument("--max-instructions", type=int, default=40 if name == "module-analyze" else 128)
        if name == "module-analyze":
            c.add_argument("--address", type=lambda s: int(s, 0))
            c.add_argument("--function-index", type=int)
        else:
            c.add_argument("--state-file", required=True)
            c.add_argument("--entry-offset", type=lambda s: int(s, 0), default=0)
            c.add_argument("--stop-offset", dest="stop_offsets", action="append", type=lambda s: int(s, 0))
            c.add_argument("--stop-point", dest="stop_points", action="append", help="LOGIC:OFFSET component boundary")
            c.add_argument("--callee-entry", dest="callee_entries", action="append", help="LOGIC:OFFSET cached scan-entry witness")
            c.add_argument("--max-call-depth", type=int)
            c.add_argument("--control-flow", choices=["tree", "compact"])
            c.add_argument("--allow-opaque", action="store_const", const=True, default=None,
                           help="Retain known unmodeled actions in a non-executable compact graph")
            c.add_argument("--effect-profile", choices=["agi-2.917"], help="Explicit object/resource effect contract")
    c = sub.add_parser("zmachine-disasm", help=METHODS["zmachine-disasm"])
    c.add_argument("path")
    c.add_argument("--address", type=lambda s: int(s, 0))
    c.add_argument("--max-instructions", type=int, default=40)
    c = sub.add_parser("zmachine-analyze", help=METHODS["zmachine-analyze"])
    c.add_argument("path")
    c.add_argument(
        "--entry", dest="entry_points", action="append", type=lambda s: int(s, 0)
    )
    c.add_argument("--max-instructions", type=int, default=10000)
    c = sub.add_parser("decoder-check", help=METHODS["decoder-check"])
    c.add_argument("data")
    c.add_argument("--bits", type=int, choices=[16, 32, 64], default=64)
    c.add_argument("--address", type=lambda s: int(s, 0), default=0)
    c.add_argument("--scan-offsets", action="store_true")
    c.add_argument("--max-candidates", type=int, default=16)
    for name in ("code-backings", "code-blocks", "code-layout"):
        c = sub.add_parser(name, help=METHODS[name])
        c.add_argument("project")
        c.add_argument("--entry", dest="entries", action="append", required=True)
        c.add_argument("--version", type=int)
        c.add_argument("--cs", type=lambda s: int(s, 0))
        c.add_argument("--max-instructions", type=int, default=10000)
        if name == "code-blocks":
            c.add_argument("--split-at", dest="split_at", action="append")
        if name == "code-layout":
            c.add_argument("--assumptions", dest="assumptions_file", required=True)
            c.add_argument("--order", dest="order_file")
            c.add_argument("--entry-references", dest="entry_references_file")
            c.add_argument("--base", type=lambda s: int(s, 0), default=0)
    for name in ("udc-native-capture", "udc-native-info", "udc-native-compile"):
        c = sub.add_parser(name, help=METHODS[name])
        c.add_argument("project")
        if name == "udc-native-capture":
            c.add_argument("name")
            c.add_argument("--entry", dest="entries", action="append", required=True)
            c.add_argument("--version", type=int)
            c.add_argument("--cs", type=lambda s: int(s, 0))
            c.add_argument("--max-instructions", type=int, default=10000)
            c.add_argument("--split-at", dest="split_at", action="append")
            c.add_argument("--parent")
            c.add_argument("--author", default="agent")
        else:
            c.add_argument("definition")
            if name == "udc-native-info":
                c.add_argument("--full", dest="include_blocks", action="store_true")
            else:
                c.add_argument(
                    "--mode",
                    choices=("original-layout", "relayout"),
                    default="original-layout",
                )
                c.add_argument("--assumptions", dest="assumptions_file")
                c.add_argument("--base", type=lambda s: int(s, 0), default=0)
                c.add_argument("--order", dest="order_file")
                c.add_argument("--block-order", dest="block_order_file")
                c.add_argument("--entry-references", dest="entry_references_file")
    for name in [
        "status",
        "analyze",
        "functions",
        "disasm",
        "xrefs",
        "rename",
        "comment",
        "versions",
        "patch",
        "issues",
        "render",
        "info",
        "header",
        "sections",
        "imports",
        "exports",
        "strings",
        "items",
        "queue",
        "represent",
        "recover-imports",
        "segments",
        "code-regions",
        "locate",
        "function-patterns",
        "analysis-status",
        "calls",
        "cfg",
        "render-cfg",
        "memory-accesses",
        "refresh-facts",
        "libraries",
        "relocations",
        "linkage",
        "refresh-metadata",
        "refresh-dos-state",
    ]:
        c = sub.add_parser(name, help=METHODS[name])
        c.add_argument("project")
        if name != "versions":
            c.add_argument("--version", type=int)
        if name in (
            "xrefs",
            "rename",
            "comment",
            "patch",
            "represent",
            "locate",
            "cfg",
            "render-cfg",
            "memory-accesses",
        ):
            c.add_argument("address")
        if name in (
            "analyze",
            "disasm",
            "xrefs",
            "render",
            "locate",
            "cfg",
            "render-cfg",
        ):
            c.add_argument("--cs", type=lambda s: int(s, 0))
        if name == "analyze":
            for register in ("ds", "es", "ss"):
                c.add_argument("--" + register, type=lambda s: int(s, 0))
        if name in ("analyze", "represent", "cfg", "render-cfg", "refresh-dos-state"):
            if name == "analyze":
                c.add_argument("--start")
            c.add_argument("--max-instructions", type=int, default=10000)
        if name in (
            "functions",
            "xrefs",
            "issues",
            "sections",
            "imports",
            "exports",
            "strings",
            "items",
            "queue",
            "function-patterns",
            "calls",
            "memory-accesses",
            "libraries",
            "relocations",
        ):
            c.add_argument("--limit", type=int, default=200)
        if name in (
            "functions",
            "sections",
            "imports",
            "exports",
            "strings",
            "items",
            "queue",
            "function-patterns",
            "calls",
            "memory-accesses",
            "libraries",
            "relocations",
        ):
            c.add_argument("--offset", type=int, default=0)
        if name in ("disasm", "render"):
            c.add_argument("--address")
            c.add_argument("--lines", type=int, default=40)
        if name == "xrefs":
            c.add_argument("--direction", choices=["to", "from"], default="to")
        if name == "rename":
            c.add_argument("name")
        if name == "comment":
            c.add_argument("text")
        if name in ("rename", "comment", "represent"):
            c.add_argument("--author", default="agent")
        if name == "represent":
            c.add_argument(
                "representation",
                choices=[
                    "code",
                    "byte",
                    "word",
                    "dword",
                    "qword",
                    "pointer",
                    "ascii",
                    "utf-16le",
                    "unexplored",
                ],
            )
            c.add_argument("--size", type=int)
            c.add_argument(
                "--defer",
                action="store_true",
                help="change representation and leave reanalysis queued",
            )
        if name in ("cfg", "render-cfg"):
            c.add_argument("--highlight", dest="highlights", action="append")
        if name == "render-cfg":
            c.add_argument("output")
        if name == "memory-accesses":
            c.add_argument("--size", type=int, default=1)
            c.add_argument("--access", choices=["all", "read", "write"], default="all")
            c.add_argument(
                "--no-unresolved", dest="include_unresolved", action="store_false"
            )
        if name == "function-patterns":
            c.add_argument("--scan-unexplored", action="store_true")
        if name == "calls":
            c.add_argument(
                "--kind",
                choices=["all", "function", "library", "unresolved"],
                default="all",
            )
        if name == "recover-imports":
            c.add_argument(
                "export_map", help="JSON list of runtime module export addresses"
            )
            c.add_argument("--max-slots", type=int, default=4096)
            c.add_argument("--gap-limit", type=int, default=10)
        if name == "patch":
            c.add_argument("data", help="replacement hex bytes; creates child version")
            c.add_argument("--label", default="patch")
            c.add_argument("--origin", default="agent supplied bytes")
        if name == "render":
            c.add_argument("output")
            c.add_argument("--format", choices=["svg", "png"])
    for name in (
        "auto-analyze",
        "advanced-status",
        "function-analysis",
        "function-membership",
        "define-type",
        "apply-type",
        "types",
        "export-types",
        "import-types",
        "typed-data",
        "set-summary",
        "set-function-type",
        "capture-signature",
        "import-signatures",
        "export-signatures",
        "summaries",
        "add-signature",
        "signatures",
        "call-effects",
    ):
        c = sub.add_parser(name, help=METHODS[name])
        c.add_argument("project")
        c.add_argument("--version", type=int)
        if name in (
            "function-analysis",
            "apply-type",
            "typed-data",
            "set-summary",
            "set-function-type",
            "capture-signature",
        ):
            c.add_argument("address")
        if name in (
            "function-analysis",
            "set-summary",
            "auto-analyze",
            "set-function-type",
            "capture-signature",
        ):
            c.add_argument("--cs", type=lambda s: int(s, 0))
        if name == "auto-analyze":
            c.add_argument("--start")
            c.add_argument("--abi")
            for field, default in [
                ("max-instructions", 10000),
                ("max-functions", 200),
                ("max-steps", 100000),
                ("max-entries", 256),
                ("max-rounds", 8),
            ]:
                c.add_argument("--" + field, type=int, default=default)
            for register in ("ds", "es", "ss"):
                c.add_argument("--" + register, type=lambda s: int(s, 0))
        if name == "function-membership":
            c.add_argument("--max-work", type=int, default=1000000)
            c.add_argument("--max-instructions", type=int, default=100000)
        if name == "define-type":
            c.add_argument("name")
            c.add_argument("definition_file")
        if name == "apply-type":
            c.add_argument("type_name")
            c.add_argument("--name")
        if name == "set-function-type":
            c.add_argument("type_name")
        if name == "typed-data":
            c.add_argument("--max-items", type=int, default=256)
        if name == "set-summary":
            c.add_argument("name")
            c.add_argument("--abi")
            c.add_argument("--prototype-file")
            c.add_argument("--summary-file")
        if name == "capture-signature":
            c.add_argument("name")
            c.add_argument("--max-instructions", type=int, default=4096)
        if name in ("import-signatures", "import-types"):
            c.add_argument("catalog_file")
        if name == "export-types":
            c.add_argument("--output", help="write the raw catalog to a new file")
            c.add_argument(
                "--name",
                dest="names",
                action="append",
                help="select a type and its dependencies; repeat to select more",
            )
        if name == "add-signature":
            c.add_argument("signature_file")
        if name in (
            "define-type",
            "apply-type",
            "set-summary",
            "set-function-type",
            "capture-signature",
            "import-types",
        ):
            c.add_argument("--author", default="agent")
        if name == "call-effects":
            c.add_argument("--address")
            c.add_argument("--size", type=int, default=1)
            c.add_argument("--access", choices=["all", "read", "write"], default="all")
            c.add_argument(
                "--no-unresolved", dest="include_unresolved", action="store_false"
            )
            c.add_argument("--limit", type=int, default=200)
            c.add_argument("--offset", type=int, default=0)
    for name in (
        "attach-file",
        "files",
        "file-bytes",
        "apply-file-type",
        "file-data",
        "file-reference",
        "file-xrefs",
    ):
        c = sub.add_parser(name, help=METHODS[name])
        c.add_argument("project")
        c.add_argument("--version", type=int)
        if name == "attach-file":
            c.add_argument("path")
            c.add_argument("--name")
            c.add_argument("--kind", default="data")
        elif name == "files":
            c.add_argument("--limit", type=int, default=200)
            c.add_argument("--offset", type=int, default=0)
        elif name == "file-bytes":
            c.add_argument("name")
            c.add_argument("--offset", type=lambda s: int(s, 0), default=0)
            c.add_argument("--size", type=lambda s: int(s, 0), default=64)
        else:
            if name == "file-reference":
                c.add_argument("address")
            c.add_argument("file")
            if name in ("file-reference", "file-xrefs"):
                c.add_argument("offset", type=lambda s: int(s, 0))
            else:
                c.add_argument("--offset", type=lambda s: int(s, 0), default=0)
            if name == "apply-file-type":
                c.add_argument("type_name")
                c.add_argument("--name")
            if name == "file-data":
                c.add_argument("--max-items", type=int, default=256)
            if name == "file-reference":
                c.add_argument("--width", type=lambda s: int(s, 0), default=1)
                c.add_argument("--count", type=int, default=1)
                c.add_argument("--stride", type=lambda s: int(s, 0))
                c.add_argument(
                    "--access",
                    choices=["read", "write", "read_write", "address", "unknown"],
                    default="unknown",
                )
                c.add_argument("--evidence", required=True)
                c.add_argument("--cs", type=lambda s: int(s, 0))
            if name == "file-xrefs":
                c.add_argument("--size", type=lambda s: int(s, 0), default=1)
                c.add_argument("--limit", type=int, default=200)
                c.add_argument("--page-offset", type=int, default=0)
                c.add_argument(
                    "--active-only", dest="include_stale", action="store_false"
                )
        if name in ("attach-file", "apply-file-type", "file-reference"):
            c.add_argument("--author", default="agent")
    for name in (
        "link-labels",
        "rename-file",
        "label-info",
        "label-links",
        "unlink-labels",
    ):
        c = sub.add_parser(name, help=METHODS[name])
        c.add_argument("project")
        c.add_argument("--version", type=int)
        if name == "link-labels":
            c.add_argument("left", type=json.loads)
            c.add_argument("right", type=json.loads)
            c.add_argument("--size", type=lambda s: int(s, 0), default=1)
            c.add_argument("--evidence", required=True)
            c.add_argument("--name")
            c.add_argument("--author", default="agent")
        elif name == "label-links":
            c.add_argument("--include-removed", action="store_true")
            c.add_argument("--limit", type=int, default=200)
            c.add_argument("--offset", type=int, default=0)
        elif name == "unlink-labels":
            c.add_argument("link_id", type=int)
            c.add_argument("--reason", required=True)
            c.add_argument("--author", default="agent")
        elif name == "rename-file":
            c.add_argument("file")
            c.add_argument("offset", type=lambda s: int(s, 0))
            c.add_argument("name")
            c.add_argument("--author", default="agent")
        else:
            c.add_argument("endpoint", type=json.loads)
    c = sub.add_parser(
        "serve", help="JSON-lines stdin/stdout protocol; no listening socket"
    )
    c.add_argument("--project")
    c = sub.add_parser("request", help="one JSON request")
    c.add_argument("json")
    sub.add_parser("methods", help="describe JSON methods")
    return root


def _udc_command(command, args):
    """Bounded metadata replies; original binary and lifted source stay in files."""
    import hashlib
    from .udc import (
        capture_dos_definition,
        definition_info,
        shared_programs,
        compile_dos,
        UDCQualificationError,
    )

    def read(path, limit=4 * 1024 * 1024):
        with open(path, "rb") as stream:
            raw = stream.read(limit + 1)
        if len(raw) > limit:
            raise ValueError("input exceeds its size budget")
        return raw

    def read_json(path):
        def pairs(values):
            result = {}
            for key, value in values:
                if key in result:
                    raise ValueError("duplicate JSON field")
                result[key] = value
            return result

        return json.loads(read(path), object_pairs_hook=pairs)

    def write_json(path, value):
        raw = (
            json.dumps(
                value, sort_keys=True, separators=(",", ":"), allow_nan=False
            ).encode()
            + b"\n"
        )
        with open(path, "xb") as stream:
            stream.write(raw)
        return {
            "output": str(Path(path).resolve()),
            "size": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
        }

    def compact_verification(value):
        return {k: v for k, v in value.items() if k != "outputs"} | {
            "outputs": {
                name: {k: v for k, v in result.items() if k != "spec"}
                for name, result in value.get("outputs", {}).items()
            }
        }

    try:
        if command.startswith("udl-"):
            from .udl_blocks import lift_asm_block, lift_c_block, verify_block

            if command == "udl-verify":
                result = verify_block(
                    read_json(args["lift"]),
                    read_json(args["program"]),
                    timeout_ms=args["timeout_ms"],
                )
                exported = write_json(args["output"], result) if args["output"] else {}
                emit({**compact_verification(result), **exported})
                return 0 if result["status"] == "equivalent_under_assumptions" else 1
            bindings = read_json(args["bindings"])
            raw = read(args["source"], 1024)
            lift = (lift_asm_block if command == "udl-lift-asm" else lift_c_block)(
                raw if command == "udl-lift-asm" else raw.decode("utf-8"),
                bindings,
                inputs=args["input"],
                outputs=args["output_register"],
            )
            emit(
                {
                    "status": "lifted",
                    "scope": lift["scope"],
                    **write_json(args["output"], lift),
                }
            )
            return 0
        from .project import Project

        with Project(args["project"]) as project:
            if command == "udc-capture":
                result = capture_dos_definition(
                    project,
                    args["name"],
                    resources=read_json(args["resources"])
                    if args["resources"]
                    else None,
                    semantic_blocks=read_json(args["blocks"])
                    if args["blocks"]
                    else None,
                    version=args["version"],
                    parent=args["parent"],
                    author=args["author"],
                    main_name=args["main_name"],
                )
            elif command == "udc-info":
                result = definition_info(
                    project, args["definition"], include_blocks=args["full"]
                )
            elif command == "udc-programs":
                programs = shared_programs(
                    project, args["definition"], role=args["role"]
                )
                result = {
                    "definition": args["definition"],
                    "role": args["role"],
                    "program_count": len(programs),
                    **write_json(args["output"], programs),
                }
            else:
                result = compile_dos(
                    project,
                    args["definition"],
                    args["output"],
                    programs=read_json(args["programs"]) if args["programs"] else None,
                )
                # Full artifact/proof receipts are saved alongside emitted files.
                result = {
                    k: result[k]
                    for k in (
                        "output",
                        "definition",
                        "definition_sha256",
                        "primary",
                        "scope",
                        "generated_dos_lowering",
                        "native_execution",
                    )
                } | {
                    "artifact_count": len(result["artifacts"]),
                    "qualification": {
                        k: v
                        for k, v in result["qualification"].items()
                        if k != "proofs"
                    },
                    "manifest": str(Path(result["output"]) / "udc-manifest.json"),
                }
            if "artifacts" in result and not args.get("full"):
                result = {k: v for k, v in result.items() if k != "artifacts"} | {
                    "artifact_count": len(result["artifacts"])
                }
            emit(result)
            return 0
    except UDCQualificationError as error:
        emit(
            {
                "complete": False,
                "status": "refused",
                "error": str(error),
                "verification": compact_verification(error.verification),
            }
        )
        return 1
    except (
        ValueError,
        OSError,
        KeyError,
        TypeError,
        RecursionError,
        sqlite3.Error,
    ) as error:
        emit({"complete": False, "status": "refused", "error": str(error)})
        return 1


def _language_command(command, args):
    """Local language/harness entry points; user stories and states stay external."""

    def read_json(path, limit=65536):
        with open(path, "rb") as stream:
            raw = stream.read(limit + 1)
        if len(raw) > limit:
            raise ValueError("JSON input exceeds its size budget")
        return json.loads(raw)

    try:
        if command == "story-info":
            from .zmachine import inspect_story

            emit(inspect_story(args["story"]))
            return 0
        if command == "zork-recover":
            from .zork_recovery import recover_mailbox

            emit(recover_mailbox(args["story"]))
            return 0
        if command == "zork-uil":
            from .zork_uil import convert_story

            emit(
                convert_story(
                    args["story"],
                    output=args["output"],
                    mapping=args["mapping"],
                    world=args["world"],
                )
            )
            return 0
        if command == "zork-intents":
            from .zork_intent_export import export_intents

            emit(
                export_intents(
                    args["story"],
                    output=args["output"],
                    ir=args["ir"],
                    uil=args["uil"],
                    udl=args["udl"],
                )
            )
            return 0
        if command == "zork-scenes":
            from .zork_scene_export import export_scenes

            emit(
                export_scenes(
                    args["story"],
                    output=args["output"],
                    intents=args["intents"],
                    uil=args["uil"],
                    udl=args["udl"],
                    dispatch=args["dispatch"],
                )
            )
            return 0
        if command.startswith("il-"):
            from .interaction_il import execute_il, validate_il
            from .il_recovery import save_il, load_il

            if command in ("il-check", "il-run"):
                program = read_json(args["program"])
                validate_il(program)
                result = (
                    {"complete": True, "status": "valid", "role": program["role"]}
                    if command == "il-check"
                    else execute_il(
                        program,
                        state=read_json(args["state"]) if args["state"] else None,
                        capabilities=args["capability"],
                        max_steps=args["max_steps"],
                        max_call_depth=args["max_call_depth"],
                        effect_context=read_json(args["effect_context"]) if args["effect_context"] else None,
                        checkpoint=read_json(args["checkpoint"]) if args["checkpoint"] else None,
                        host_result=read_json(args["host_result"]) if args["host_result"] else None,
                    )
                )
                emit(result)
                return 0 if result["complete"] else 1
            from .project import Project

            with Project(args["project"]) as project:
                if command == "il-info":
                    result = load_il(project, args["revision"], version=args["version"])
                else:
                    if args["source"]:
                        project.attach_file(
                            args["source"],
                            name=args["source_name"],
                            version=args["version"],
                        )
                    result = save_il(
                        project,
                        args["name"],
                        read_json(args["program"]),
                        version=args["version"],
                        parent=args["parent"],
                    )
                emit(result)
            return 0
        from .zork import ZorkSession, NamedZorkHarness, ZorkError

        with ZorkSession(
            args["story"],
            python=args["python"],
            seed=args["seed"],
            timeout_ms=args["timeout_ms"],
        ) as session:
            if args["resume"]:
                session.restore_checkpoint(args["resume"])
            harness = (
                NamedZorkHarness(session, read_json(args["scenes"]))
                if args["scenes"]
                else None
            )
            emit(
                {
                    "status": "ready",
                    **session.observe(),
                    "story": session.story_info,
                    "policy": {"assisted_travel": False},
                }
            )
            while True:
                line = sys.stdin.readline(1024 * 1024 + 1)
                if not line:
                    break
                if len(line.encode()) > 1024 * 1024 or not line.endswith("\n"):
                    raise ValueError("Incomplete or excessive request line")
                request = json.loads(line)
                if not isinstance(request, dict):
                    raise ValueError("Expected request object")
                op = request.get("op")
                executed = False
                if op == "observe" and set(request) == {"op"}:
                    result = session.observe()
                elif op == "command" and set(request) == {"op", "text"}:
                    result = session.command(request["text"])
                    executed = True
                elif op in ("save", "restore") and set(request) == {"op", "path"}:
                    result = (
                        session.save_checkpoint
                        if op == "save"
                        else session.restore_checkpoint
                    )(request["path"])
                elif (
                    harness
                    and op in ("scene", "reacquire")
                    and set(request) == {"op", "scene"}
                ):
                    result = (harness.observe if op == "scene" else harness.reacquire)(
                        request["scene"]
                    )
                elif (
                    harness
                    and op == "act"
                    and set(request) == {"op", "scene", "action", "token"}
                ):
                    result = harness.act(
                        request["scene"], request["action"], request["token"]
                    )
                    executed = True
                else:
                    raise ValueError("Unsupported request or fields")
                if executed and args["checkpoint"]:
                    result["checkpoint"] = session.save_checkpoint(args["checkpoint"])
                emit(result)
                if result.get("outcome") == "unexpected":
                    return 1
        return 0
    except (ValueError, OSError, RuntimeError, EOFError, KeyError, TypeError) as error:
        emit({"complete": False, "status": "stopped", "error": str(error)})
        return 1


def main(argv=None):
    args = vars(parser().parse_args(argv))
    try:
        policy = OutputPolicy.from_environment(
            max_inline_bytes=args.pop("max_output_bytes"),
            artifact_dir=args.pop("output_artifact_dir"),
        )
    except ValueError as error:
        print(
            json.dumps(
                {"complete": False, "status": "refused", "error": str(error)},
                separators=(",", ":"),
            ),
            flush=True,
        )
        return 1
    with output_policy_context(policy):
        code = _dispatch(args)
        return 2 if code == 0 and policy.delivery_failed else code


def _dispatch(args):
    command = args.pop("command")
    if command.startswith("uil-"):
        try:
            from .uil_api import invoke_common

            result = invoke_common(
                command, {k: v for k, v in args.items() if v is not None}
            )
            emit(result)
            return (
                1
                if isinstance(result, dict)
                and result.get("status") in ("refused", "pending_host")
                else 0
            )
        except (
            ValueError,
            TypeError,
            KeyError,
            OSError,
            sqlite3.Error,
            RecursionError,
        ) as error:
            emit({"status": "refused", "error": str(error)})
            return 1
    if command == 'shadowrun-z':
        from .shadowrun_city_view import open_runtime
        from .shadowrun_z import ShadowrunZBackend
        from .text_projection import serve_stream
        try:
            backend=ShadowrunZBackend(open_runtime(args['rom_path'],snapshot=args['snapshot'],profile=args['profile'],preset=args['preset']),policy=args['policy'])
            serve_stream(backend,sys.stdin,sys.stdout)
            return 0
        except (ValueError,OSError,KeyError,TypeError) as error:
            print(json.dumps({'complete':False,'status':'refused','reason':str(error)}),flush=True)
            return 1
    if command == "media-extract":
        args["max_output_bytes"] = args.pop("media_max_output_bytes")
    if command == "smk-frame":
        args["max_output_bytes"] = args.pop("smk_max_output_bytes")
    if command == "capture-audit":
        args["max_output_bytes"] = args.pop("capture_max_output_bytes")
    if command.startswith(("udc-", "udl-")) and not command.startswith("udc-native-"):
        return _udc_command(command, args)
    if command in (
        "story-info",
        "zork",
        "zork-recover",
        "zork-uil",
        "zork-intents",
        "zork-scenes",
        "il-check",
        "il-run",
        "il-store",
        "il-info",
    ):
        return _language_command(command, args)
    if command == "text-host":
        from .text_host import host

        try:
            path = Path(args["configuration"])
            if not path.is_file() or path.stat().st_size > 1024 * 1024:
                raise ValueError("Expected a text host configuration at most 1 MiB")
            configuration = json.loads(path.read_text())
            if args["fair_play"]:
                configuration = dict(
                    configuration, fair_play=True, spatial_mode="physical"
                )
            if args["spatial_mode"] is not None:
                configuration = dict(configuration, spatial_mode=args["spatial_mode"])
            emit(
                host(
                    configuration,
                    on_listen=lambda address: emit({"text_player_endpoint": address}),
                )
            )
            return 0
        except (ValueError, OSError) as error:
            emit({"ok": False, "error": str(error)})
            return 1
    if command == "serve":
        return serve(args["project"])
    if command == "debug":
        project = args.pop("project")
        return serve(project, {k: v for k, v in args.items() if v is not None})
    if command == "request":
        try:
            request = load_request(args["json"])
        except (ValueError, RecursionError) as e:
            emit(
                {
                    "id": None,
                    "ok": False,
                    "error": {"type": "InvalidJSON", "message": str(e)},
                }
            )
            return 1
    else:
        request = {
            "method": "help" if command == "methods" else command,
            "params": {k: v for k, v in args.items() if v is not None},
        }
    result = respond(request)
    emit(result)
    if command in ("doctor", "capture-audit") and result["ok"]:
        body = result["result"]
        status = body["execution"]["status"] if body.get("format") == "fdisbull-output-ref-1" else body["status"]
        if status != "passed":
            return 1
    if command in ("macos-session", "macos-session-recover") and result["ok"]:
        body = result["result"]
        status = body["execution"]["status"] if body.get("format") == "fdisbull-output-ref-1" else body["status"]
        if status != "confirmed":
            return 1
    return 0 if result["ok"] else 1
