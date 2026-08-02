    # A9a3 Workload, Memory, and Thermal Closure

    **Record type:** Reconstructed public compatibility record  
    **Phase:** `A9a3`  
    **Purpose:** Restore the source-level contract preserved by the shipped tests, manifests, implementation reports, and public release documentation after machine-local development content was intentionally excluded.

    This record is privacy-safe. It contains no username, hostname, serial number, absolute home path, machine profile, benchmark result, or conversation transcript. It is not represented as a byte-for-byte copy of the former local phase document.

    ## Preserved phase contract

    - **workload**
- **memory_guard_refusal**
- **thermal_data_unavailable**
- **thermal_guard**
- **Official + Promote**
- **A10**



    ## Recovery boundary

    The executable source remains authoritative. This record documents the intended feature boundary so regression tests, public contributors, and the portable core builder can agree on the same phase lineage. Generated machine state remains under user-owned runtime locations and is not committed as public source.

    ## Validation expectation

    Run `./scripts/build_core.sh --force`, then `./scripts/run_selftests.sh`. Native GUI and renderer behavior must still be confirmed on the target Linux machine after the source and headless gates pass.
