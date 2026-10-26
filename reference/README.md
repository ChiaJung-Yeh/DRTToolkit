# Regression specification reference

`hurdle_tweedie_specification.R` records the two model calls extracted from `add FR.R`. It is a specification reference, not a standalone workflow entry point.

Run the `demand` stage to load the included `dt_model.csv`, estimate both models and save their diagnostics. The executable R implementation is `drt_toolkit/r/demand.R`.

The source's catchment, spatial feature-construction and raw smartcard blocks are not included. Existing prepared inputs supply those attributes directly.
