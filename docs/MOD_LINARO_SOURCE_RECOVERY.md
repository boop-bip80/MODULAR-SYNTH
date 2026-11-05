# MOD hardware build: Linaro GCC 7.5 source recovery

**Status (2026-11-05): blocked on independently authenticated source.** This is a recovery procedure, **not** a claim that an uncached MOD target builds successfully. Do not skip the toolchain integrity gate, replace GCC source with a prebuilt cross-compiler, or mark a missing archive as optional.

## What broke, and what source is required

The inherited `mod-plugin-builder` crosstool-NG configuration requests the **GCC source package** `gcc-linaro-7.5-2019.12.tar.xz`. The historical Linaro release URL now responds with a redirect/contact HTML page in place of a valid XZ archive. A successful HTTP response code does not imply a usable tarball.

The original publisher's [December 2019 release announcement](https://lists.linaro.org/archives/list/linaro-toolchain@lists.linaro.org/thread/PYDASQL6N3GUDPAE65SFQNXDRZCDAY4Z/) identifies the historical GCC source collection, while [Arm's legacy Linaro downloads notice](https://developer.arm.com/Downloads/-/Legacy%20Linaro%20GNU%20Toolchains) classifies this series as end-of-life. These are primary evidence of the package's provenance, **not** a present-day verified mirror or a published SHA-256 for the needed `.tar.xz`.

For clarity, files named `gcc-linaro-7.5.0-2019.12-x86_64_arm-linux-gnueabihf.tar.xz` or `gcc-linaro-7.5.0-2019.12-x86_64_aarch64-linux-gnu.tar.xz` are **binary cross-toolchains**, not the needed GCC **source** package. The package name, content tree and architecture are different; they cannot be swapped into the source download cache.

## Recovery procedure, without changing trust boundaries

1. Find the exact **source** archive from the publisher or a credible archival custodian. Record its permanent HTTPS URL, publication identity and source of authenticity (prefer an authenticated signed checksum manifest or publisher-provided SHA-256). A checksum calculated only from an untrusted mirror proves download consistency, **not** provenance.
2. Verify the original package's identity against that independent evidence. Check that it is an XZ tar archive with a `gcc-linaro-7.5-2019.12/` root and genuine GCC 7 source members, including `configure`, `gcc/config.gcc`, and `libgcc/config.host`.
3. In the `boop-bip80/MODULAR-SYNTH` repository's GitHub Actions variables, configure `MOD_LINARO_SOURCE_URL` with the authenticated HTTPS URL and `MOD_LINARO_SOURCE_SHA256` with the independently verified 64-hex digest. Do not put query-bearing signed URLs or credentials in source control.
4. Re-run the uncached `mod-plugin-builder` job. The preflight downloads into a temporary file, bounds the compressed and expanded tar input, checks SHA-256 and GCC source identity, and atomically places a valid archive at `~/mod-workdir/download/gcc-linaro-7.5-2019.12.tar.xz`. Bootstrap must still build the actual target toolchain; a green preflight alone does not pass the MOD hardware job.
5. Review the complete hosted MOD target results; do not infer target hardware compatibility, LV2 loading, real audio or a distributable release from a successful compiler bootstrap.

### Offline/manual source staging

If an independently authenticated archive is available on a runner but an authenticated HTTPS mirror is not, the same preflight can stage a **local** file without a network request:

```bash
python3 tools/ci/seed_mod_toolchain_source.py \
  --source-url '' \
  --source-file /path/to/gcc-linaro-7.5-2019.12.tar.xz \
  --sha256 '<independently-verified-64-hex-sha256>' \
  --cache-dir "$HOME/mod-workdir/download"
```

The placeholder is deliberately **not** a guessed digest. The local original is retained, a verified cached source is reused, and invalid candidates never overwrite the previous cache. This local mode is not currently wired to GitHub Actions because no authentic source artifact has been identified; manually staging an unverified file would not solve the supply-chain problem.

## Failure behavior and regression evidence

- Reject HTTP/FTP URLs, redirects to non-HTTPS, credential-bearing URLs, HTML redirects, digest mismatches and invalid XZ/tar data.
- Reject archives lacking canonical GCC source files, traversal/escaping links, special members, duplicate paths or unbounded declared payloads.
- Preserve existing cache content if a new candidate fails; do not mark an unavailable MOD toolchain as a passing build.
- Offline tests: `PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest tests.test_ci_mod_toolchain_diagnostics -v`.

**Remaining upstream dependency:** source archive authenticity, complete hosted bootstrap, target packaging and device audio smoke. Until independently verified evidence exists, the MOD hardware jobs are expected to fail closed.
