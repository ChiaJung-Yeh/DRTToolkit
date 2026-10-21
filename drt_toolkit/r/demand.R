# Same positive-flow Tweedie GAM + zero-occurrence GAM structure as source OD.R.
suppressPackageStartupMessages(library(jsonlite))
suppressPackageStartupMessages(library(mgcv))
args <- commandArgs(trailingOnly=TRUE)
cfg <- fromJSON(args[1], simplifyVector=FALSE)
out <- args[2]
d <- read.csv(cfg$paths$demand_training,check.names=FALSE,colClasses=c(GridID_O='character',GridID_D='character'))
pred <- read.csv(cfg$paths$demand_prediction_features,check.names=FALSE,colClasses=c(GridID_O='character',GridID_D='character'))
positive_formula <- as.formula(cfg$demand$positive_formula)
zero_formula <- as.formula(cfg$demand$zero_formula)
needed <- union(all.vars(positive_formula),all.vars(zero_formula))
d$zero_trip <- as.numeric(d$Trips==0)
features <- setdiff(needed,c('Trips','zero_trip'))
if (!all(needed %in% names(d)) || !all(c('Hour','GridID_O','GridID_D',features) %in% names(pred))) stop('Demand tables lack formula fields or OD identifiers')
for (tab in list(d[,needed,drop=FALSE],pred[,features,drop=FALSE])) {
  if (!all(vapply(tab,function(x) is.numeric(x) && all(is.finite(x)),logical(1)))) stop('Demand formula fields must be finite numeric values')
}
if (any(d$Trips<0) || length(unique(d$zero_trip))!=2) stop('Training requires nonnegative trips including both zeros and positive flows')
if (any(pred$Hour<0 | pred$Hour>23 | pred$Hour%%1!=0)) stop('Prediction hours must be integers 0..23')
if (anyDuplicated(pred[,c('Hour','GridID_O','GridID_D')])) stop('Duplicate prediction OD-hour keys')
holdout <- NULL
if ('Split' %in% names(d)) {
  if (!all(d$Split %in% c('train','test'))) stop('Split must be train or test')
  holdout <- d[d$Split=='test',,drop=FALSE]
  d <- d[d$Split=='train',,drop=FALSE]
  if (!nrow(holdout)) stop('Split provided without test observations')
}
if (length(unique(d$zero_trip))!=2) stop('Training split needs both zero and positive trips')
res_model <- gam(positive_formula,family=tw(),data=d[d$Trips>0,,drop=FALSE],method='REML')
res_model_zero <- gam(zero_formula,family=binomial(),data=d,method='REML')
pzero_train <- predict(res_model_zero,d,type='response')
threshold <- cfg$demand$zero_threshold
if (is.null(threshold)) {
  candidates <- unlist(cfg$demand$threshold_candidates)
  # Matches source criterion: zero-share error on training only. No test-set tuning.
  errors <- sapply(candidates,function(x) abs(mean(d$zero_trip)-mean(pzero_train>x)))
  threshold <- candidates[which.min(errors)]
}
if (!is.finite(threshold) || threshold<0 || threshold>1) stop('zero_threshold must be in [0,1]')
predict_od <- function(z) {
  amount <- as.numeric(predict(res_model,z,type='response'))
  pzero <- as.numeric(predict(res_model_zero,z,type='response'))
  # threshold method is the supplied script; expected_value is an explicit alternative.
  value <- if (cfg$demand$zero_method=='threshold') amount*as.numeric(pzero<=threshold) else if (cfg$demand$zero_method=='expected_value') amount*(1-pzero) else stop('Unknown zero_method')
  list(amount=amount,pzero=pzero,value=value)
}
r <- predict_od(pred)
if (any(!is.finite(r$value)) || any(r$value<0)) stop('Invalid demand predictions')
result <- pred[,c('Hour','GridID_O','GridID_D')]
result$PositiveFlow <- r$amount
result$ZeroProbability <- r$pzero
result$PredTrips <- r$value
write.csv(result,file.path(out,'demand_predictions.csv'),row.names=FALSE)
saveRDS(list(positive=res_model,zero=res_model_zero,threshold=threshold,method=cfg$demand$zero_method),file.path(out,'demand_models.rds'))
diagnostics <- list(zero_threshold=threshold,zero_method=cfg$demand$zero_method,training_rows=nrow(d),positive_rows=sum(d$Trips>0),holdout_available=!is.null(holdout))
if (!is.null(holdout)) {
  h <- predict_od(holdout)
  diagnostics$holdout_rows <- nrow(holdout)
  diagnostics$holdout_MAE <- mean(abs(h$value-holdout$Trips))
  diagnostics$holdout_RMSE <- sqrt(mean((h$value-holdout$Trips)^2))
  diagnostics$holdout_observed_total <- sum(holdout$Trips)
  diagnostics$holdout_predicted_total <- sum(h$value)
  diagnostics$holdout_zero_Brier <- mean((h$pzero-holdout$zero_trip)^2)
  holdout$Prediction <- h$value
  write.csv(holdout,file.path(out,'demand_holdout.csv'),row.names=FALSE)
}
write_json(diagnostics,file.path(out,'demand_diagnostics.json'),pretty=TRUE,auto_unbox=TRUE)
capture.output(summary(res_model),summary(res_model_zero),file=file.path(out,'demand_summary.txt'))
capture.output(sessionInfo(),file=file.path(out,'demand_sessionInfo.txt'))
pdf(file.path(out,'demand_model_diagnostics.pdf'))
gam.check(res_model)
gam.check(res_model_zero)
dev.off()
