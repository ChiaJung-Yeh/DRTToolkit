# Reusable censored-normal models. Inputs are explicit, joined by RouteID only.
suppressPackageStartupMessages(library(jsonlite))
suppressPackageStartupMessages(library(AER))
if (.Platform$OS.type=='windows') try(Sys.setlocale('LC_CTYPE','English_United States.utf8'),silent=TRUE)
args <- commandArgs(trailingOnly=TRUE)
cfg <- fromJSON(args[1], simplifyVector=FALSE)
out <- args[2]
historical <- read.csv(cfg$paths$historical,check.names=FALSE,colClasses=c(RouteID='character'),fileEncoding='UTF-8-BOM')
d <- read.csv(cfg$paths$tobit_explanatory,check.names=FALSE,colClasses=c(RouteID='character'),fileEncoding='UTF-8-BOM')
if (anyDuplicated(d$RouteID)||anyNA(d$RouteID)||!setequal(d$RouteID,historical$RouteID)) stop('Tobit explanatory DMUs must match the filtered historical sample exactly')
if (!all(d$COUNTYNAME[match(historical$RouteID,d$RouteID)]==historical$COUNTYNAME)) stop('County mismatch between evaluation and explanatory tables')
# Stored national-frontier outcomes are not valid outcomes for the restricted sample.
d <- d[,setdiff(names(d),c('GroupEff','MetaEff','ClusterName','TGR'))]
scores <- read.csv(file.path(out, 'historical_scores.csv'), colClasses=c(DMU='character'),fileEncoding='UTF-8-BOM')
names(scores)[names(scores)=='DMU'] <- 'RouteID'
d <- merge(d, scores, by='RouteID', sort=FALSE)
write.csv(d,file.path(out,'tobit_model_data.csv'),row.names=FALSE,fileEncoding='UTF-8')
if (!is.null(cfg$paths$exogenous) && nzchar(cfg$paths$exogenous)) {
  exo <- read.csv(cfg$paths$exogenous, check.names=FALSE, colClasses=c(RouteID='character'))
  if (anyDuplicated(exo$RouteID) || anyNA(exo$RouteID)) stop('Duplicate or missing exogenous RouteID')
  if (!setequal(exo$RouteID, d$RouteID)) stop('Exogenous RouteIDs must match historical data')
  if (length(intersect(setdiff(names(exo),'RouteID'), names(d)))) stop('Exogenous columns overlap historical columns')
  d <- merge(d, exo, by='RouteID', sort=FALSE)
}
fits <- list()
coefs <- list()
specifications <- list()
for (spec in cfg$tobit$models) {
  z <- if (identical(spec$group,'ALL')) d else d[d$ClusterName==spec$group, ,drop=FALSE]
  f <- as.formula(spec$formula)
  needed <- all.vars(f)
  if (!all(needed %in% names(z))) stop(paste('Missing Tobit fields:', paste(setdiff(needed,names(z)),collapse=', ')))
  if (anyNA(z[,needed,drop=FALSE])) stop('Tobit contains missing data; no silent row deletion is allowed')
  if (!all(vapply(z[,needed,drop=FALSE], function(x) is.numeric(x) && all(is.finite(x)), logical(1)))) stop('Tobit fields must be finite numeric values')
  response <- z[[needed[1]]]
  if (any(response < 0 | response > 1)) stop('Tobit efficiency response must lie in [0,1]')
  original_formula <- spec$formula
  predictors <- attr(terms(f),'term.labels')
  constant <- predictors[vapply(predictors,function(v) length(unique(z[[v]]))<2,logical(1))]
  if (length(constant)) f <- reformulate(setdiff(predictors,constant),response=needed[1])
  design <- model.matrix(f,z)
  if (nrow(z)<=ncol(design)+2 || qr(design)$rank<ncol(design)) stop('Insufficient observations or rank-deficient Tobit design; revise model explicitly')
  fit <- AER::tobit(f, data=z, left=0, right=1)
  fits[[spec$name]] <- fit
  tab <- as.data.frame(unclass(coef(summary(fit))))
  tab$Term <- rownames(tab)
  tab$Model <- spec$name
  tab$N <- nrow(z)
  coefs[[spec$name]] <- tab
  specifications[[spec$name]] <- list(requested_formula=original_formula,estimated_formula=paste(deparse(f),collapse=' '),excluded_constant_predictors=constant,n=nrow(z),uncensored=sum(response>0 & response<1),note='Constants cannot be estimated within a restricted group; all nonconstant explanatory variables are retained.')
}
saveRDS(fits,file.path(out,'tobit_models.rds'))
write.csv(do.call(rbind,coefs),file.path(out,'tobit_coefficients.csv'),row.names=FALSE)
capture.output(lapply(fits,summary),file=file.path(out,'tobit_summary.txt'))
capture.output(sessionInfo(),file=file.path(out,'tobit_sessionInfo.txt'))
write_json(specifications,file.path(out,'tobit_specifications.json'),pretty=TRUE,auto_unbox=TRUE)
