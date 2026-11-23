# October 29 full-suite failure corrections

Scope: test infrastructure and stale test contracts only. No control/runtime
or installed files changed by this correction. Existing unrelated changes
remain untouched.

## Reported five failures

- The nested-sharing test required a rejected optimization of the legacy
  shared-envelope format. The earlier simple-record proposal explicitly
  recorded that this reproduction remained red and did not qualify its new
  independent-record design. The replacement exercises that approved design:
  both rows and exact nested values must survive, source mutation cannot alter
  retained evidence, and charged storage stays within its configured limit.
  It does not assert that the legacy nested-sharing optimization was fixed.
- Both daemon process tests passed independently before correction. The user's
  full-run stderr instead showed failure to import their test target modules
  while Windows spawn was unpickling, before export execution. Their fixture
  now prepends this checkout's absolute root to the inherited child search
  path, avoiding dependence on pytest's already loaded parent test modules or
  another `tests` package. No export timeouts or expected integrity checks were
  relaxed. Full-suite verification is necessary to establish the fix in context.
- Existing display work deliberately introduced theme/perspective controls
  (five controls rather than three) and changed both initial/reset radius from
  1050 to 650. UI tests now check the five actual tooltip functions and reset
  behavior, rather than reverting that unrelated display work.

## Verification

Before correction: focused diagnostic reproduction 1 failed, 2 passed.
After correction: 58 affected diagnostic/UI tests passed in 6.37 seconds.
Full-suite result: **3290 passed, 14 skipped, 1725 subtests passed** in
796.11 seconds (13:16), with zero failures. The same 14 skips existed in the
user's original run; no new skip or xfail was introduced. Log is
`docs/steering-audit/oct29-transition/full-suite-five-fixes.log`.

No deployment, repackaging, game startup or vehicle input was performed.
