# Read shared model settings and resolve data and output paths.
if (.Platform$OS.type=='windows') try(Sys.setlocale('LC_CTYPE','English_United States.utf8'),silent=TRUE)
if (!requireNamespace('jsonlite',quietly=TRUE)) stop('The jsonlite package must be available in the selected R library')
toolkit_root <- Sys.getenv('DRT_TOOLKIT_ROOT',unset='E:/On-demand Transport Service/Analysis/7_Toolkit')
toolkit_root <- normalizePath(toolkit_root,winslash='/',mustWork=TRUE)
settings <- jsonlite::fromJSON(file.path(toolkit_root,'desktop_scripts','desktop_settings.json'),simplifyVector=FALSE)
cfg <- jsonlite::fromJSON(file.path(toolkit_root,settings$config),simplifyVector=FALSE)
for (key in names(cfg$paths)) {
  value <- cfg$paths[[key]]
  if (!is.null(value) && nzchar(value)) cfg$paths[[key]] <- file.path(toolkit_root,value)
}
out <- file.path(toolkit_root,'outputs',settings$run_id)
dir.create(out,recursive=TRUE,showWarnings=FALSE)
message('Results: ',out)
