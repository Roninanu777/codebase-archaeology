# Eval report - evals/cases-v1.jsonl

## attribution (A)

**9/9** passed - avg 57ms - p95 85ms

| case | ok | detail | latency ms |
|---|---|---|---|
| attr-createRoot | yes | introduced b8f825877 | 49 |
| attr-reconcileChildFibers | yes | introduced d4f58c3b8 | 54 |
| attr-renderWithHooks | yes | introduced 7bee9fbdd | 194 |
| attr-scheduleUpdateOnFiber | yes | introduced 9055e31e5 | 85 |
| attr-flushSyncFromReconciler | yes | introduced 9055e31e5 | 82 |
| attr-createContext | yes | introduced 87ae211cc | 12 |
| attr-throwException | yes | introduced 8af1f8792 | 22 |
| attr-memo | yes | introduced a0733fe13 | 10 |
| attr-forwardRef | yes | introduced bc70441c8 | 9 |

## abstention (A)

**1/1** passed - avg 802ms - p95 802ms

| case | ok | detail | latency ms |
|---|---|---|---|
| abstain-bogus-symbol | yes | status=abstained reason=symbol_not_found | 802 |

## retrieval (B)

**3/3** passed - avg 12484ms - p95 6255ms

| case | ok | detail | latency ms |
|---|---|---|---|
| recall-ums-removal | yes | matched 80d9a4011 at rank 5 | 25175 |
| recall-act-use | yes | matched c63580787 at rank 5 | 6255 |
| recall-context-api | yes | matched 87ae211ccd at rank 15 | 6023 |

## known_gap (B)

**2/2** passed - avg 7810ms - p95 7515ms

| case | ok | detail | latency ms |
|---|---|---|---|
| gap-lanes-rationale | yes | gap confirmed (truth absent from corpus); VERIFIED ABSENT: #19108 discussion is a devtools-debugging thread, zero 'lane' mentions; rationale lives in rfcs/blogs outside GitHub PRs | 7515 |
| gap-create-root-vs-render | yes | gap confirmed (truth absent from corpus); VERIFIED ABSENT: #17331 discussion has zero createRoot/render mentions; migration rationale lives in blogs/talks outside the repo | 8104 |

## synthesis (S)

**5/5** passed - avg 11873ms - p95 13869ms

| case | ok | detail | latency ms |
|---|---|---|---|
| syn-createRoot | yes | cited b8f825877,3f85d53ca,ccab49473,823dc581f,142d4f1c0,9fba65efa,356c17108,848bb2426,993ca533b, | 19714 |
| syn-memo-pure-origin | yes | cited a0733fe13,40a521aa7,15b11d23f,769b1f270,9ac42dd07,b15bf3675,0cf22a56a,c5d2fc712,416942019, | 11979 |
| syn-forwardRef-rfc30 | yes | cited bc70441c8,920f30ef7,095dd5049,f89f25f47,f9358c51c,ecbf7af40,c898020e0,9ac42dd07,b15bf3675, | 12954 |
| syn-context-api | yes | cited 87ae211cc,28aa084ad,ad9544f48,ba245f6f9,b0726e994,f9358c51c,2b509e2c8,2a2ef7e0f,1bc975d07, | 13869 |
| syn-bogus-abstains-free | yes | status=abstained reason=symbol_not_found | 850 |

