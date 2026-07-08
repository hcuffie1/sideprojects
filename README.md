# sideprojects
Data science, ML, and analytics projects — causal inference, LLM evaluation, geospatial simulation.

## Projects

### [Dixie Highway Traffic Impact Analysis](dixie-hwy-traffic-analysis/)
Multi-model corridor analysis of a proposed road diet on US-25 (Kenton County, KY). Built a custom discrete-event microsimulator that reveals an 83% per-vehicle delay increase — a finding completely hidden by the standard BPR capacity formula. Geospatial overlay using real OSM road network data (osmnx + folium) identifies mid-block commercial driveway conflicts as the actual bottleneck.
`Python` `NumPy` `Pandas` `Folium` `osmnx` `Jupyter`

---

### [Shopping Agent Eval Framework](shopping-eval-framework/)
Production-style evaluation framework for a multi-turn conversational shopping agent built with LangGraph + Gemini. Covers the full eval lifecycle: guardrail design, constraint checking, groundedness scoring, Langfuse prompt versioning, SQLite persistence, and drift detection.
`Python` `LangGraph` `Gemini` `Langfuse` `SQLite`

---

### [DS/Analytics Interview Case Prep](case_prep/)
Reusable notebooks for data scientist and analyst business case interviews. Includes worked case studies on conversion drop analysis (Instacart), A/B testing, and metric decomposition frameworks.
`Python` `Pandas` `SQL`
