# Source-bundle integrity and reproducibility audit

Instrument Builder's `audit` command checks an existing `.msinstrument` ZIP
without extracting it, modifying it, or changing the v1/v2 format. It first
performs the complete `read_bundle` validation: the ZIP has the two expected
regular, stored members, the saved `.vcv` source matches its derived manifest,
and the preserved v2 control-mapping contract (if present) is consistent.

```sh
python3 tools/instrument-builder/instrument_builder.py audit synth.msinstrument
python3 tools/instrument-builder/instrument_builder.py audit synth.msinstrument \
  --require-reproducible --expect-sha256 <64-character-SHA-256-hex>
```

The command prints stable JSON with the whole ZIP's `bundleSha256`, the raw
`.vcv` source's `patchSha256`, `formatVersion`, `reproducible`,
`expectedSha256Matches` (null unless a pin was provided), `routingStatus`
(`not-checked`), and overall `status` (`PASS` or `FAIL`). The bundle SHA can
be recorded with a source release and compared later. Both a mismatched pin
and a failed `--require-reproducible` check produce exit code **1** and a
`FAIL` report. Invalid ZIPs, patch/manifest mismatches, unsafe inputs and
malformed pins produce exit code **2** with a diagnostic on stderr.

`reproducible` means the original archive bytes equal the builder's fixed
uncompressed, two-member ZIP envelope with canonical manifest JSON and
unchanged `.vcv` bytes. It can be false for an otherwise fully valid bundle
(for example, reversed ZIP entry order). By default, that distinction is
reported but does not fail the audit; opt into the stricter requirement.
Historical v2 mapping contracts are audited as saved, never silently upgraded
to current port contracts. Neither `PASS` nor `reproducible: true` verifies
third-party routing, stereo sound, compiled DSP, or a DAW/plugin export.

For an automated source-release gate, record a digest from an independently
approved bundle, then rerun `audit --expect-sha256 ... --require-reproducible`
on the candidate artifact. A freshly calculated digest of that same candidate
alone does not provide an independent provenance assertion.
