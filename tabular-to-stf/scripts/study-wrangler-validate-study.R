# Loads a whole STF directory with study.wrangler and validates it the way the
# EDA does: geo variables inferred, then the baseline and eda profiles.
# Prints one marker line: STF_LOAD_ERROR (the study did not load), STF_VALIDATION_ERROR
# (it loaded, but geo inference or validate() raised an R error) or STF_VALIDATION: PASS|FAIL.
# Exit 0 pass, 1 fail, 2 load or validation error.
# Usage: Rscript study-wrangler-validate-study.R <stfDir>
suppressPackageStartupMessages(library(study.wrangler))
sink(stdout(), type = "message") # one stream, so the caller sees everything in order
dir <- commandArgs(trailingOnly = TRUE)[1]
profiles <- c("baseline", "eda")

study <- tryCatch(
  study_from_stf(dir, validate = FALSE),
  error = function(e) {
    cat("STF_LOAD_ERROR:", conditionMessage(e), "\n")
    quit(status = 2)
  }
)
validation_error <- function(e) {
  cat("STF_VALIDATION_ERROR:", conditionMessage(e), "\n")
  quit(status = 2)
}
study <- tryCatch(map_entities(study, infer_geo_variables_for_eda), error = validation_error)
ok <- tryCatch(isTRUE(validate(study, profiles = profiles)), error = validation_error)
if (!ok) {
  # study-level validation hides the details of each entity's failures
  for (entity in get_entities(study)) {
    cat("== entity:", get_entity_name(entity), "==\n")
    tryCatch(
      validate(verbose(entity), profiles = profiles),
      error = function(e) cat("(verbose validation raised an error:", conditionMessage(e), ")\n")
    )
  }
}
cat(if (ok) "STF_VALIDATION: PASS\n" else "STF_VALIDATION: FAIL\n")
quit(status = if (ok) 0 else 1)
