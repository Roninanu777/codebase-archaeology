# Eval report - evals/cases-v1.jsonl

## attribution (A)

**9/9** passed - avg 56ms - p95 81ms

| case | ok | detail | latency ms |
|---|---|---|---|
| attr-createRoot | yes | introduced b8f825877 | 57 |
| attr-reconcileChildFibers | yes | introduced d4f58c3b8 | 54 |
| attr-renderWithHooks | yes | introduced 7bee9fbdd | 195 |
| attr-scheduleUpdateOnFiber | yes | introduced 9055e31e5 | 81 |
| attr-flushSyncFromReconciler | yes | introduced 9055e31e5 | 81 |
| attr-createContext | yes | introduced 87ae211cc | 8 |
| attr-throwException | yes | introduced 8af1f8792 | 19 |
| attr-memo | yes | introduced a0733fe13 | 6 |
| attr-forwardRef | yes | introduced bc70441c8 | 7 |

## abstention (A)

**1/1** passed - avg 744ms - p95 744ms

| case | ok | detail | latency ms |
|---|---|---|---|
| abstain-bogus-symbol | yes | status=abstained reason=symbol_not_found | 744 |

## retrieval (B)

**7/7** passed - avg 8675ms - p95 7459ms

| case | ok | detail | latency ms |
|---|---|---|---|
| recall-ums-removal | yes | matched 80d9a4011 at rank 5 | 23953 |
| recall-act-use | yes | matched c63580787 at rank 5 | 5442 |
| recall-context-api | yes | matched pr:11818 at rank 2 | 6217 |
| recall-rfc-createroot | yes | matched text/0212 at rank 2 | 6795 |
| recall-rfc-memo | yes | matched text/0063 at rank 1 | 7459 |
| recall-rfc-uses | yes | matched text/0214 at rank 1 | 5241 |
| recall-rfc-forwardref | yes | matched pr:30 at rank 2 | 5617 |

## known_gap (B)

**2/2** passed - avg 7054ms - p95 6934ms

| case | ok | detail | latency ms |
|---|---|---|---|
| gap-lanes-rationale | yes | gap confirmed (truth absent from corpus); VERIFIED ABSENT twice: zero 'lane' mentions in facebook/react #19108 discussion AND in reactjs/rfcs texts+discussions; rationale is blog/talks-only | 6934 |
| gap-create-root-vs-render | yes | gap confirmed (truth absent from corpus); VERIFIED ABSENT: #17331 discussion has zero createRoot/render mentions; migration rationale lives in blogs/talks outside the repo | 7174 |

## synthesis (S)

**1/1** passed - avg 813ms - p95 813ms

| case | ok | detail | latency ms |
|---|---|---|---|
| syn-createRoot | skip | llm_unavailable: OPENROUTER_API_KEY is not set; get one at https://openrouter.ai/keys | 150 |
| syn-memo-pure-origin | skip | llm_unavailable: OPENROUTER_API_KEY is not set; get one at https://openrouter.ai/keys | 101 |
| syn-forwardRef-rfc30 | skip | llm_unavailable: OPENROUTER_API_KEY is not set; get one at https://openrouter.ai/keys | 109 |
| syn-context-api | skip | llm_unavailable: OPENROUTER_API_KEY is not set; get one at https://openrouter.ai/keys | 111 |
| syn-bogus-abstains-free | yes | status=abstained reason=symbol_not_found | 813 |

