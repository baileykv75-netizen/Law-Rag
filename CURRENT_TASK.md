# CURRENT_TASK.md

# Law-Rag — Current Delivery State

## Status

```text
Stage 11A–11E   COMPLETE / benchmark + quality + release foundations
Stage 12A–12F   COMPLETE / RC2 VALIDATED
Stage 13A–13G   COMPLETE / ISSUE_V1 production migration validated
Stage 14.1–14.7 COMPLETE / OCR distribution + DOCX + packaged Windows validation
Stage 15.1–15.5 COMPLETE / official three-domain corpus + domain-aware RAG + Windows baseline validated

Stage 16.1      COMPLETE / versioned evaluation-suite architecture + evidence-class isolation
Stage 16.2      COMPLETE / public deterministic three-domain regression corpus + gates
Stage 16.3      ENGINEERING COMPLETE / private expert protocol + scoped evaluator validated; real expert evidence pending final acceptance
Stage 16.4      ENGINEERING COMPLETE / ISSUE_V1 UAT capture + suite mechanics validated; paid/network UAT deferred to final acceptance
Stage 16.5      ENGINEERING COMPLETE / release-quality evidence matrix + provider-free final regression validated

Stage 16 external acceptance
                PENDING / PRIVATE_EXPERT + REAL_PROVIDER_UAT evidence intentionally deferred until final acceptance

Stage 17        NEXT / tray + graceful quit + history + storage management
Stage 18        PENDING / runtime encryption + DOCX/PDF report export + cost/resource controls + advanced provider settings
Stage 19        PENDING / installer + code signing + safe updates + final documentation
Final acceptance PENDING / private expert evidence + explicit real-provider UAT + complete-evidence gate
```

The user explicitly requested that real DeepSeek/Kimi UAT be performed only at the final acceptance boundary. Missing external evidence must therefore remain visible as `PENDING`; it must not block Stage 17–19 engineering and must never be relabeled as completed evidence.

## Authoritative production architecture

```text
PDF / JPG / JPEG / PNG / DOCX
 -> Source Evidence
 -> Canonical Contract
 -> deterministic rules
 -> Audit Planner + explicit canonical-object coverage
 -> deterministic Issue domain route
 -> READY Corpus Pack eligibility
 -> applicable Authority Version for as_of
 -> Exact Citation + FTS5/BM25 + optional local BGE
 -> deterministic retrieval fusion
 -> one bounded DeepSeek primary request per AuditPlan Issue
 -> one bounded Kimi finding + coverage review per Issue
 -> deterministic Issue comparison
 -> append-only human review
 -> architecture-aware Results / Workspace / Developer
```

Canonical legal identity remains:

```text
Authority -> Version -> Article / Legal Evidence
```

Do not introduce a third-model vote, unrestricted browsing, arbitrary agent shell/filesystem access, cloud OCR as the default path, or a second contract-analysis pipeline.

## Frozen Stage 15 baseline

```text
Corpus Release  three-domain-core@1.0.0
READY Packs     3
Authorities     14
Versions        15
Unique Articles 1274
```

Stage 15 closeout baseline:

```text
2ea5b936723133ddf5eb8829534c0e1530c60f85
Law-Rag Stage 15 CI #123              32456205510 SUCCESS
Stage 15.5 Windows Baseline CI #9     32456205586 SUCCESS
```

## Stage 16 evidence model

Stage 16 keeps three evidence classes separate:

```text
PUBLIC_REGRESSION
PRIVATE_EXPERT
REAL_PROVIDER_UAT
```

They must never be collapsed into one invented `overall_accuracy`, `legal_accuracy`, or global professional score.

### Stage 16.1 — COMPLETE

Versioned evaluation-suite architecture with public/private/UAT path isolation, source fingerprints, sanitized reports and deterministic CLI.

```text
head 706ce85bc5b472896d33dcf4d926501755656247
Stage 16 CI #15  32458037391 SUCCESS
```

### Stage 16.2 — COMPLETE

Versioned public three-domain deterministic regression using the frozen Stage 15 corpus/routing truth.

```text
head 67407e54b27e595e82119b055774241ce708b971
Stage 16 CI #50  32459347103 SUCCESS
backend           434 passed, 5 skipped
public regression 10 / 10 gates PASS
Stage16b suite     3 / 3 entries PASS
```

The named regression has scoped/broad lexical Recall@5 and MRR of 1.00 on its nine-case fixture, but those values are only deterministic regression evidence for that named dataset, not professional legal correctness.

### Stage 16.3 — ENGINEERING COMPLETE

Private expert protocol/evaluator infrastructure is validated:

```text
ExpertBenchmarkProtocol
 + private BenchmarkDataset
 + private BenchmarkObservationSet
 + ExpertLabelAuditArtifact
 -> ExpertBenchmarkRunReport
```

Expert label states remain explicit:

```text
AGREED
ADJUDICATED
AMBIGUOUS
```

Only scoped binary-classification and exhaustive-set precision/recall/F1 are supported. No real professionally labeled dataset has yet been supplied, so real professional evidence remains pending final acceptance.

```text
head 3393caa150e2baee459ca0969e8f17ee451d6156
Stage 16 CI #62  32460155009 SUCCESS
backend           443 passed, 5 skipped
```

### Stage 16.4 — ENGINEERING COMPLETE / REAL UAT DEFERRED

Provider-free ISSUE_V1 UAT capture infrastructure is validated.

```text
existing production ISSUE_V1 artifacts
 -> provenance/fingerprint/Issue/stage-state validation
 -> private IssueV1UATObservation
 -> sanitized IssueV1UATSanitizedReport
 -> REAL_PROVIDER_UAT / UAT_CAPTURE evaluation-suite entry
```

Key boundaries:

- capture never calls DeepSeek/Kimi/OCR itself;
- private observation stays external or under ignored `benchmark_private/`;
- explicit `TEST_DOUBLE` vs `REAL_PROVIDER` modes;
- Planner/Primary -> DeepSeek and Secondary -> Kimi identity enforcement;
- AuditPlan/Legal Context/Primary/Secondary/comparison fingerprints and Issue coverage must reconcile;
- COMPLETE, PRIMARY_INTERRUPTED and SECONDARY_INTERRUPTED checkpoint states are preserved;
- pipeline/artifact contradictions, stale fingerprints and fake provider identities fail closed;
- sanitized reports omit job IDs, Issue IDs, request IDs, raw-response hashes, private contract text and credentials;
- UAT completion means provider-chain completion/provenance only, not legal correctness.

```text
provider-free frozen head 72b254ea29f9fb2343d0396aae8a45edf5b20c58
Stage 16 CI #110           32463724778 SUCCESS
```

Actual paid/network DeepSeek/Kimi UAT is intentionally deferred to final acceptance.

### Stage 16.5 — ENGINEERING COMPLETE

Branch:

```text
stage16-5-release-quality-matrix
```

Draft PR #19 is the stacked validation carrier and must remain unmerged without separate authorization.

Stage 16.5 adds the deterministic release-quality evidence matrix:

```text
PUBLIC_REGRESSION -> PASS / FAIL
PRIVATE_EXPERT    -> PRESENT / PENDING / FAIL
REAL_PROVIDER_UAT -> PASS / PENDING / FAIL
```

Two flags remain intentionally separate:

```text
engineering_ready
stage16_evidence_complete
```

`engineering_ready=true` requires the pinned Stage16b public suite to pass.

`stage16_evidence_complete=true` additionally requires real private expert evidence and a complete real-provider UAT capture. The latter two are external acceptance evidence and remain pending by design.

Provider-free validation:

```text
Stage 16 CI #124  32464408663 SUCCESS
backend            475 passed, 5 skipped, 1 third-party warning
historical 11B     PASS
Stage 16.2 direct  PASS
Stage16b suite      PASS
release matrix      PASS
frontend build      PASS
```

CI matrix state:

```text
engineering_ready         true
stage16_evidence_complete false
PUBLIC_REGRESSION         PASS
PRIVATE_EXPERT            PENDING
REAL_PROVIDER_UAT         PENDING
```

Final acceptance will use:

```text
python -m app.release_evidence_cli \
  --repo-root .. \
  --expert-report <external-or-benchmark_private/expert-report.json> \
  --uat-suite <external-or-benchmark_private/uat-suite.json> \
  --require-complete-evidence
```

Detailed docs:

```text
docs/STAGE16_EVALUATION.md
docs/STAGE16_EXPERT_BENCHMARK.md
docs/REAL_PROVIDER_UAT.md
docs/STAGE16_RELEASE_EVIDENCE.md
```

## Next engineering scope — Stage 17

Stage 17 is now authorized by the user's sequencing instruction and must be implemented before final external UAT.

Required focus:

```text
17.1 desktop lifecycle / tray / graceful quit
17.2 persistent job history UX over existing ISSUE_V1/legacy-compatible artifacts
17.3 storage visibility + safe job cleanup without touching immutable packaged legal baseline
17.4 Windows/provider-free regression and documentation closeout
```

Stage 17 must preserve:

- loopback-only local server binding;
- explicit provider approval/cancellation boundary;
- safe pipeline recovery/checkpoint semantics;
- immutable packaged legal baseline and writable runtime legal corpus separation;
- append-only human review semantics;
- no deletion of active/running jobs;
- no deletion of shared legal corpus while cleaning job history;
- no implicit cloud/provider call from history/storage/tray surfaces.

Do not begin Stage 18 until Stage 17 has its own provider-free validation baseline.

## Later scope

### Stage 18

```text
runtime encryption
DOCX/PDF report export
cost/resource controls
advanced provider settings
```

### Stage 19

```text
installer
code signing
safe updates
final user/developer documentation
```

### Final acceptance after Stage 19 engineering

At the end, perform only with explicit authorization/data availability:

```text
real private expert benchmark evidence
explicit paid/network DeepSeek + Kimi ISSUE_V1 UAT
Stage16 --require-complete-evidence gate
final packaged Windows acceptance smoke
```

## PR / merge boundary

Draft PRs #13–#19 are stacked validation carriers. Do not merge them, retarget them to `main`, or mark them as production releases without separate explicit authorization.
