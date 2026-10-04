# Reference console, performance popover and window contour

Base: `a927c06`. Presentation changes only; no controller, authority,
gearbox, steering cadence or freshness limit changes.

## Implemented

- Console rows: `[INF]`, `[WRN]`, `[ERR]`, grey `HH:MM:SS`, light-grey
  message, real underlined `filename:line` aligned on the right. Colours:
  information `#00AF00`, warning `#D7AF00`, error `#FF0033`, numbers
  `#55DDEE`, startup RAM `#BAE6FD`. Plugin display names are yellow.
- Rich exception rendering: red frame, actual traceback, highlighted source,
  three context lines, at most twelve displayed frames, no local variables.
  The plain log retains the complete standard traceback. Known UI, HUD and
  worker exception paths now retain `exc_info` rather than flattening it.
- Plugin workers use the same console/file formatter as the main runtime.
  Plain records include source metadata before the message, without ANSI
  escapes. Diagnostic dictionary tails remain unchanged. The UI log supports
  both old records and new source metadata, escaping all messages. Dynamic
  Island strips source metadata before filtering and showing activity, so
  technical locations do not leak into its user-facing messages.
- Performance popover: dark `#202020` surface, thin pale border, small
  radius, Consolas 12 px, tree glyphs, memory before name, descending RSS,
  `Total` at the bottom. Existing PID-based measurements remain read-only.
  Large lists scroll; hidden popovers do not poll.
- Map initialization prints `Please wait for map to load the necessary data.`
  in yellow, also shown in the HUD while existing map progress is active.
  Loading receipts show cumulative elapsed centiseconds, actual loaded counts
  and signed RSS changes between boundaries. Cache receipts explicitly name
  the cached network. No additional asset parsing or invented ferry counts.
- HUD initialization reports actual element names and count. HUD advances
  from 1.0.1 to 1.0.2; unaffected plugin versions are unchanged.
- Outer window: one antialiased painted contour and an inset child clip.
  Removed the top-level binary mask and additional native rounding which
  could cut the already rounded border. The control notch remains available.

RSS includes Python and shared pages; it is not exclusive plugin allocation.
The accumulated map count and RAM deltas are current measurements, not copied
values from the screenshots. Map memory readings occur only at loader-thread
boundaries. Console window tabs, desktop background and DPI belong to the host
terminal, not the application renderer.

## Verification

Offline Qt previews inspected in light/dark mode. The contour regression checks
that each occupied corner scanline has continuous alpha coverage. Console
tests cover real source locations, warning colour and code-frame exceptions
without local values; memory tests cover exact PID scope and startup receipts.
Map receipt tests check actual elapsed time and positive/negative RSS deltas.
The scheduler regression mocks the new logging setup boundary and preserves
the original tick/overrun expectations. No application runtime or ETS2 launch.

Targeted result: 106 tests passed across the targeted checks, including the
real tiny-dataset loader/cache, six unchanged worker-period scenarios and
source-metadata compatibility. The additional Island regression failed before
its presentation fix and passed afterwards. Full pytest is left
to the user. `compileall` and `git diff --check` passed before handoff.
The final UI/log subset passed 43 checks. Its initial sandbox run hit Windows
`PermissionError` when pytest scanned its temporary directory; the same subset
passed outside that filesystem restriction, with no runtime/game launch.

No commit, deployment, installation or restart was performed.
