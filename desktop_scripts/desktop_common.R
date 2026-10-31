# Read shared model settings and resolve data and output paths.
if (.Platform$OS.type=='windows') try(Sys.setlocale('LC_CTYPE','English_United States.utf8'),silent=TRUE)
if (!requireNamespace('jsonlite',quietly=TRUE)) stop('The jsonlite package must be available in the selected R library')
# Resolve this toolkit after copying or moving the folder.
toolkit_root <- Sys.getenv('DRT_TOOLKIT_ROOT', unset='')
if (!nzchar(toolkit_root)) {
  source_files <- unlist(lapply(sys.frames(), function(frame) frame$ofile))
  script_args <- sub('^--file=', '', grep('^--file=', commandArgs(), value=TRUE))
  entry_files <- c(source_files, script_args)
  entry_files <- entry_files[file.exists(entry_files)]
  candidates <- c(vapply(entry_files, function(path) dirname(dirname(normalizePath(path, winslash='/'))), character(1)), getwd(), dirname(getwd()))
  valid <- vapply(candidates, function(path) file.exists(file.path(path,'desktop_scripts','desktop_helpers.py')) && dir.exists(file.path(path,'drt_toolkit')), logical(1))
  if (!any(valid)) stop('Set DRT_TOOLKIT_ROOT to the toolkit folder before sourcing this R script.')
  toolkit_root <- head(candidates[valid], 1)
}
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
