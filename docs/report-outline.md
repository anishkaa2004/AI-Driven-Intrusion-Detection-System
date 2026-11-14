# Final report outline (blueprint §27) — with pointers into this repo

1. **Introduction** — motivation (blueprint §3).
2. **Literature review** — IDS types (signature vs anomaly), flow-based detection, CICIDS2017/UNSW-NB15 critiques (dataset artifacts, label noise).
3. **Problem, objectives, scope** — blueprint §2, §4, §5. State clearly what is in/out of scope.
4. **Requirements & feasibility** — FR/NFR tables (blueprint §7–8); mark each Implemented / Partial / Not built using the README table.
5. **Architecture & design** — `docs/architecture.md`, sequence diagram (blueprint §10), data dictionary.
6. **Dataset & methodology** — which dataset/version, cleaning report (`manifest.json → clean_report`), split method, seeds, feature list (`flow-v1`), class balance handling (`class_weight`).
7. **Rule-based & ML detection** — rule table (ML analytics page), model choices, fusion policy, dedup.
8. **Implementation** — stack versions (`backend/requirements.txt`, `frontend/package.json`), key code excerpts (ingestion, rule window, fusion).
9. **Testing & results** — test plan table + pass output; ML results table from `ml/reports/<version>.md`; latency/throughput measurements with hardware; screenshots of each demo scenario.
10. **Security, privacy & ethics** — controls table in architecture.md; data minimisation; consent prompt in agent; retention.
11. **Limitations & future scope** — README "Honest limitations"; blueprint §26.
12. **Conclusion**
13. **References** — cite exact dataset version and library versions actually used.
14. **Appendices** — API examples (`docs/api-specification.md`), setup instructions (README).

> Report only measured numbers. Results from synthetic data must be labelled as such and must not be presented as detection performance.
