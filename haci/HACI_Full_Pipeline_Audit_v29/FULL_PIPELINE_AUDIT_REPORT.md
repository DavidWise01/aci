# HACI Full Pipeline Audit through v2.9
## Verdict
v2.9 keeps the earlier fixes. I did not find a regression in the previously patched layers.

## Current open failure
- Same-file chronology: v2.9 accepts a return before the ask later in the same file.
- This appears to be a latent pipeline gap exposed by hardening, not a regression introduced by v2.9.

## Fixed-layer checks on v2.9
- `commit_gating_pending_decl_no_symbol_mutation`: PASS
- `accepted_return_unique_closes`: PASS
- `pending_parent_blocks_child_commit_even_loose`: PASS
- `return_question_payload_specific_pairs`: PASS
- `pending_declaration_does_not_create_graph_edge`: PASS
- `cross_file_return_before_ask_allowed`: PASS
- `committed_declaration_still_creates_edge`: PASS

## Version history signal
Each probe shows whether that version satisfies the current expected behavior.

### commit_gating_pending_decl_no_symbol_mutation
- v2.4: FAIL
- v2.5: PASS
- v2.6: PASS
- v2.7: PASS
- v2.8: PASS
- v2.9: PASS

### accepted_return_unique_closes
- v2.4: FAIL
- v2.5: FAIL
- v2.6: PASS
- v2.7: PASS
- v2.8: PASS
- v2.9: PASS

### pending_parent_blocks_child_commit_even_loose
- v2.4: FAIL
- v2.5: FAIL
- v2.6: FAIL
- v2.7: PASS
- v2.8: PASS
- v2.9: PASS

### return_question_payload_specific_pairs
- v2.4: FAIL
- v2.5: FAIL
- v2.6: FAIL
- v2.7: FAIL
- v2.8: PASS
- v2.9: PASS

### pending_declaration_does_not_create_graph_edge
- v2.4: FAIL
- v2.5: FAIL
- v2.6: FAIL
- v2.7: FAIL
- v2.8: FAIL
- v2.9: PASS

### same_file_return_before_ask_rejected
- v2.4: FAIL
- v2.5: FAIL
- v2.6: FAIL
- v2.7: FAIL
- v2.8: FAIL
- v2.9: FAIL

### cross_file_return_before_ask_allowed
- v2.4: PASS
- v2.5: PASS
- v2.6: PASS
- v2.7: PASS
- v2.8: PASS
- v2.9: PASS

### committed_declaration_still_creates_edge
- v2.4: PASS
- v2.5: PASS
- v2.6: PASS
- v2.7: PASS
- v2.8: PASS
- v2.9: PASS

## Interpretation
The pattern is progress: each patch sealed one layer, then the audit revealed the next unsealed layer. That is expected in this style of invariant hardening. The same-file chronology bug existed because return pairing was deliberately order-independent for cross-file merge support; the missing rule is to keep cross-file order independence while enforcing same-file line chronology.
