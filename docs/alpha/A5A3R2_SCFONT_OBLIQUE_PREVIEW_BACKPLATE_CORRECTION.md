    # A5a3r2 SCFONT, Oblique Preview, and Backplate Correction

    **Record type:** Reconstructed public compatibility record  
    **Phase:** `A5a3r2`  
    **Purpose:** Restore the source-level contract preserved by the shipped tests, manifests, implementation reports, and public release documentation after machine-local development content was intentionally excluded.

    This record is privacy-safe. It contains no username, hostname, serial number, absolute home path, machine profile, benchmark result, or conversation transcript. It is not represented as a byte-for-byte copy of the former local phase document.

    ## Preserved phase contract

    - **Terminal_00.scfont**
- **oblique**
- **prefix**
- **backplate**
- **legacy fallback**
- **engine/scfont/scfont.cpp**
- **signalcloud_scfont_tests**
- **run_selftests.sh**
- **setup_dev_environment.sh**
- **changed_font_count**



    ## Recovery boundary

    The executable source remains authoritative. This record documents the intended feature boundary so regression tests, public contributors, and the portable core builder can agree on the same phase lineage. Generated machine state remains under user-owned runtime locations and is not committed as public source.

    ## Validation expectation

    Run `./scripts/build_core.sh --force`, then `./scripts/run_selftests.sh`. Native GUI and renderer behavior must still be confirmed on the target Linux machine after the source and headless gates pass.
