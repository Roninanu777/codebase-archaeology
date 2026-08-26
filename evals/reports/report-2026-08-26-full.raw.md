# Eval report - evals/cases-v1.jsonl

## attribution (A)

**11/11** passed - avg 51ms - p95 89ms

| case | ok | detail | latency ms |
|---|---|---|---|
| attr-createRoot | yes | introduced b8f825877 | 59 |
| attr-reconcileChildFibers | yes | introduced d4f58c3b8 | 54 |
| attr-renderWithHooks | yes | introduced 7bee9fbdd | 196 |
| attr-scheduleUpdateOnFiber | yes | introduced 9055e31e5 | 89 |
| attr-flushSyncFromReconciler | yes | introduced 9055e31e5 | 81 |
| attr-createContext | yes | introduced 87ae211cc | 9 |
| attr-throwException | yes | introduced 8af1f8792 | 21 |
| attr-memo | yes | introduced a0733fe13 | 7 |
| attr-forwardRef | yes | introduced bc70441c8 | 7 |
| attr-readContext | yes | introduced 47b003a82 | 25 |
| attr-uses-native-wiring | yes | introduced 77912d9a0 | 15 |

## abstention (A)

**2/2** passed - avg 387ms - p95 5ms

| case | ok | detail | latency ms |
|---|---|---|---|
| abstain-bogus-symbol | yes | status=abstained reason=symbol_not_found | 769 |
| abstain-rfcs-no-code | yes | status=abstained reason=symbol_not_found | 5 |

## retrieval (B)

**17/17** passed - avg 7206ms - p95 8216ms

| case | ok | detail | latency ms |
|---|---|---|---|
| recall-ums-removal | yes | matched 80d9a4011 at rank 5 | 24666 |
| recall-act-use | yes | matched c63580787 at rank 5 | 5320 |
| recall-context-api | yes | matched pr:11818 at rank 2 | 5562 |
| recall-rfc-createroot | yes | matched text/0212 at rank 2 | 5452 |
| recall-rfc-memo | yes | matched text/0063 at rank 1 | 6246 |
| recall-rfc-uses | yes | matched text/0214 at rank 1 | 6601 |
| recall-rfc-forwardref | yes | matched pr:30 at rank 2 | 6694 |
| recall-rfc-hooks | yes | matched text/0068 at rank 1 | 7452 |
| recall-rfc-server-components | yes | matched text/0188 at rank 1 | 7724 |
| recall-rfc-suspense-18 | yes | matched text/0213 at rank 1 | 8216 |
| recall-rfc-profiler | yes | matched text/0051 at rank 1 | 5689 |
| recall-rfc-lazy | yes | matched text/0064 at rank 1 | 5498 |
| recall-rfc-static-lifecycle | yes | matched text/0006 at rank 1 | 5466 |
| recall-rfc-snapshot | yes | matched text/0033 at rank 1 | 4247 |
| recall-rfc-contexttype | yes | matched text/0065 at rank 1 | 5663 |
| recall-uses-native-wiring | yes | matched 77912d9a0 at rank 1 | 5578 |
| recall-mutable-source-predecessor | yes | matched text/0147 at rank 2 | 6428 |

## known_gap (B)

**2/2** passed - avg 6226ms - p95 6097ms

| case | ok | detail | latency ms |
|---|---|---|---|
| gap-lanes-rationale | yes | gap confirmed (truth absent from corpus); VERIFIED ABSENT twice: zero 'lane' mentions in facebook/react #19108 discussion AND in reactjs/rfcs texts+discussions; rationale is blog/talks-only | 6097 |
| gap-create-root-vs-render | yes | gap confirmed (truth absent from corpus); VERIFIED ABSENT: #17331 discussion has zero createRoot/render mentions; migration rationale lives in blogs/talks outside the repo | 6354 |

## synthesis (S)

**1/1** passed - avg 808ms - p95 808ms

| case | ok | detail | latency ms |
|---|---|---|---|
| syn-createRoot | skip | llm_unavailable: OPENROUTER_API_KEY is not set; get one at https://openrouter.ai/keys | 138 |
| syn-memo-pure-origin | skip | llm_unavailable: OPENROUTER_API_KEY is not set; get one at https://openrouter.ai/keys | 100 |
| syn-forwardRef-rfc30 | skip | llm_unavailable: OPENROUTER_API_KEY is not set; get one at https://openrouter.ai/keys | 107 |
| syn-context-api | skip | llm_unavailable: OPENROUTER_API_KEY is not set; get one at https://openrouter.ai/keys | 110 |
| syn-bogus-abstains-free | yes | status=abstained reason=symbol_not_found | 808 |
| syn-readcontext | skip | llm_unavailable: OPENROUTER_API_KEY is not set; get one at https://openrouter.ai/keys | 171 |
| syn-uses-native-wiring | skip | llm_unavailable: OPENROUTER_API_KEY is not set; get one at https://openrouter.ai/keys | 78 |

