# Windows release payload integrity gate

The Windows tag workflow publishes separate `win32` and `win64` ZIP and
installer artifacts. The shell release gate delegates payload inspection to
`.github/workflows/scripts/verify-windows-payload.py`.

Before accepting a release, the gate checks the installer PE/COFF machine
against the selected target and inspects the ZIP's required native executables,
VST3 and CLAP plugins, LV2 manifests, and release metadata. The archive must
have readable, CRC-valid members; safe, unambiguous Windows extraction names;
no duplicate or conflicting paths, symlinks, or special files; and bounded
member and total uncompressed sizes.

**Every regular ZIP member whose case-insensitive name ends in `.exe`, `.dll`,
`.clap`, or `.vst3` is checked as a PE binary for the expected architecture.**
Executable `.exe` files must have application PE characteristics; the plugin
and DLL suffixes must have DLL PE characteristics. This includes additional
native helper binaries, so an incorrectly built helper cannot bypass the
gate by living outside the set of required release paths.

Run the offline release-gate fixture tests with:

```sh
python3 -B -m unittest discover -s tests -p 'test_ci_windows_release_assets.py' -v
```

These checks validate the packaged files and their headers. They do not prove
binary provenance, execute a Windows installer, or test plugin loading on an
installed Windows system.
