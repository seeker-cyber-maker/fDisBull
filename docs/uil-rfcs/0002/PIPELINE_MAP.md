# Branches and confluences: the UIL route map

**REVISION IN PROGRESS. Conceptual map, not a capability or performance claim.**

[Architecture and provider details](AGENT_FIRST_TOPOLOGY.md) | [Research and verification](RESEARCH_AND_VERIFICATION.md) | [Editable Mermaid source](pipeline-map.mmd)

The thick amber line is the architectural reference route, not a prescribed
implementation or a claim that every proposed contract is implemented. Dashed
paths are optional or proposed integrations. Blue routes gather source-bound
facts; purple routes qualify relationships; green routes realize targets.
The map is inspired by branching/rejoining timelines, not an actual chronology.
There is no measured cost/elevation scale and no "best decompiler" claim.

```mermaid
flowchart LR
    S["Pinned program + resources"] ==> N["Native facts<br/>fDisBull / Capstone"]
    N ==> U["Executable UDL<br/>backings + adapters"]
    U ==>|"shared syntax and contracts"| I["UIL blueprint<br/>values / state / effects / regions"]
    I ==> D["UDC plan<br/>choose implementations + connections"]
    D ==> O["Retained native output"]

    S -.-> G["Ghidra<br/>raw / high p-code"]
    S -.-> B["Binary Ninja<br/>LLIL / MLIL / SSA"]
    S -.-> X["IDA + Hex-Rays<br/>microcode / ctree"]
    S -.-> H["Hopper<br/>ASM / pseudocode"]
    S -.-> V["Guest VM / resource adapter"]
    S -.-> T["Native execution history<br/>context-qualified witnesses"]

    G -.-> F["Evidence confluence<br/>typed facts + dependencies + conflicts"]
    B -.-> F
    X -.-> F
    H -.-> F
    V -.-> F
    T -.-> F
    N -.-> F
    F -.-> U

    N -.-> C["Optional C-like view"]
    G -.-> C
    B -.-> C
    X -.-> C
    H -.-> C
    C -.->|"qualified mapping, not proof by appearance"| U
    L["Guides / agent hypotheses"] -.-> F
    A["Authored behavior definitions"] -.-> I
    P["Guarded patch"] -.->|"replace backing; invalidate dependents"| U

    I -.-> Z["Z / HUD / visual editor<br/>projections, not sole authority"]
    Z -.->|"edits or requests through contracts"| I
    I -.-> Q["Relational checks + invariants<br/>H-Houdini-inspired research"]
    U -.-> Q
    Q -.->|"receipts / counterexamples"| F

    D -.-> M["Mixed ASM / C / Rust / JS<br/>qualified adapters"]
    D -.-> K["Optional graph / tensor lowering"]
    M -.-> R["Target recipe + linker / runtime<br/>ISA + ABI + services"]
    K -.-> R
    R -.-> E["ELF / PE / DOS profiles"]
    R -.-> W["JS / Wasm / other target packages"]
    O -.-> Y["Compare declared behavior<br/>and exact bytes where required"]
    E -.-> Y
    W -.-> Y
    Y -.-> Q

    classDef spine fill:#fff2d5,stroke:#a76a0a,color:#1c2026,stroke-width:2px;
    classDef route fill:#e8f4fa,stroke:#397694,color:#182c38;
    classDef check fill:#eeebfa,stroke:#6a59a0,color:#292138;
    classDef output fill:#e8f5ee,stroke:#3c8062,color:#183329;
    class S,N,U,I,D,O spine;
    class G,B,X,H,V,T,F,C,L,A,P,Z route;
    class Q,Y check;
    class M,K,R,E,W output;
```

## Convergence rules

- Tool facts meet in an evidence graph with identity and scope intact. Conflicts
  do not disappear merely because the arrows converge.
- Executable UDL retains the source backings. UIL shares its vocabulary; neither
  C nor a text-adventure projection is compulsory.
- An opaque original-backed block may remain usable in its admitted context.
  A missing abstract explanation is not permission to invent behavior.
- Qualification is beside the route and incremental. The arrows are not circular
  proof: source correspondence, contracts and target adapters have distinct checks.
- Target scaffolds are profiles with loaders, ABI and runtime requirements, not
  empty byte containers. A route is executable only for its supported capabilities.

Any decorative rendering of this topology is illustrative. The Mermaid source,
companion definitions and recorded evidence are the reviewable specification.
