# Local Linux report verification

Observed on 2026-10-15 with CPython 3.12.3 on Ubuntu 24.04 in WSL2. This
increment starts from public commit
`aae22c091550a30175483a85f7b98fc28f9de84f`. The existing simulator and fixed
demo were reused; the report renderer was moved into the installed package.

## Observed results

- A new Linux virtual environment installed the project. Its runtime has no
  third-party dependencies; pip used isolated package builds. `pip check` passed.
- All 27 unittest tests passed, including the existing 21 tests and six new
  report tests. Ruff 0.16.10 lint and format checks passed.
- The installed command ran outside the source checkout. Default, shared-cap-50
  and short-deadline JSON outputs are byte-identical to the existing three
  checked-in examples. The fixed source demo and installed short-deadline report
  produce identical HTML and JSON.
- The final wheel and installed modules contain the exact executable bytes that
  were tested. The original MIT license is included in the wheel.
- Reusing an existing report directory returns 2 without changing either file.
  Tests also cover pre-existing files and Linux dangling symlinks, mutually
  exclusive output modes, invalid settings and a simulated HTML write failure
  after a JSON file has been saved.
- Four actual report variants, including zero successful requests, were checked
  at 1440- and 390-pixel widths. Displayed aggregates and setting/seed rows agree
  with their JSON. Details and horizontal tables work with a keyboard. The
  reports work with JavaScript disabled and make no external requests. Print
  and reduced-motion rendering were checked.

The simulation classes, event engine, aggregation and percentile functions have
unchanged ASTs. Existing numerical JSON, tests of the simulation, methodology,
research references and license are unchanged. The [local receipt](verification/linux-reports.json)
records the tested module and wheel hashes without private machine paths.

## Limits and unperformed checks

This is a synthetic retry model, not a network or production benchmark. Passing
software checks does not calibrate its assumptions, prove a superior retry
policy or establish an operational SLO. The research references provide context;
they do not validate these numerical results.

The report writes a new directory, then JSON, then HTML. This is not an atomic
two-file transaction: an I/O failure can leave partial output. Existing paths
are refused rather than replaced. The JSON-only `--output` mode retains its
existing replacement behavior. A valid simulation returns 0 even if requests
miss; invalid input and report I/O errors return 2.

The [GitHub CI run](https://github.com/skyon0522-ai/retry-budget-lab/actions/runs/38686785815)
completed successfully on 2026-10-15 for
[commit `3a766d4`](https://github.com/skyon0522-ai/retry-budget-lab/commit/3a766d46eec0912582cd5290fe397abc8d3da4dd).
Python 3.10, 3.12 and 3.14 passed the test and installed-command report steps;
Ruff ran on Python 3.12. These results were checked on 2026-10-18.

This local record does not include new Windows verification or an independent
review of the 2026-10-15 increment. Local artifact and source checks alone do
not establish publication or Human approval.
