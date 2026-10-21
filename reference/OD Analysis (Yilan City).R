library(dplyr)
library(sf)
library(tmap)
library(data.table)
library(ggplot2)
library(TDX)
library(dodgr)
library(stringr)
library(mgcv)
library(maptiles)

# setwd("E:/On-demand Transport Service/Analysis/6_Agent-based Modelling/A_OD Analysis (TW Smartcard)/Yilan City")
# load("E:/On-demand Transport Service/Analysis/6_Agent-based Modelling/A_OD Analysis (TW Smartcard)/Yilan City/.RData")

windowsFonts(A=windowsFont("Tw Cen MT"))
windowsFonts(A=windowsFont("Times New Roman"))

tmap_mode("view")

client_id=Sys.getenv("TDX_CLIENT_ID")
client_secret=Sys.getenv("TDX_CLIENT_SECRET")
access_token=get_token(client_id, client_secret)

yilan_downtown=read_sf("E:/Yilan Bus/Analysis/Data/Sociodemographic/Downtown_Area.shp")

#### Data Collection ####
##### PT Data #####
bus_stop=Bus_StopOfRoute(access_token, "YilanCounty", dates="2024-12-31", dtype="sf")%>%
  st_transform(crs=3826)%>%
  mutate(StopNameZh_tw=ifelse(StopNameZh_tw=="大坡路(臨時站)", "大坡路", StopNameZh_tw))
names(bus_stop)=gsub("Zh_tw", "", names(bus_stop))
bus_stop=st_intersection(bus_stop, st_transform(filter(TWspdata::taiwan_town, COUNTYNAME=="宜蘭縣")[, c("TOWNNAME")], crs=3826))

bus_shape=Bus_Shape(access_token, "YilanCounty", dates="2024-06-30", dtype="sf")
names(bus_shape)=gsub("Zh_tw", "", names(bus_shape))
bus_shape=bus_shape[, c("RouteUID","RouteName","SubRouteUID","SubRouteName","Direction")]%>%
  st_transform(crs=3826)

sa_area=st_as_sfc(st_bbox(st_buffer(filter(bus_shape, RouteName=="黃1"), 1000)))
sa_grid=st_make_grid(st_bbox(sa_area), cellsize=300, square=F)
sa_grid=st_sf(data.frame(GridID=c(1:length(sa_grid)), geometry=sa_grid), crs=3826)
sa_grid_centre_buf=st_buffer(st_centroid(sa_grid), 500)

# tm_shape(sa_area)+
#   tm_polygons()+
#   tm_shape(filter(bus_shape, RouteName=="黃1"))+
#   tm_lines()

# 注意：大礁溪橋為唯一例外站名，同時包含員山鄉與礁溪鄉
bus_stop_loc=group_by(st_drop_geometry(bus_stop), TOWNNAME, StopName)%>%
  summarise(PositionLon=mean(PositionLon),
            PositionLat=mean(PositionLat))%>%
  st_as_sf(coords=c("PositionLon","PositionLat"), crs=4326)%>%
  st_transform(crs=3826)%>%
  st_intersection(sa_area)%>%
  st_intersection(sa_grid)

temp=filter(bus_stop, StopName %in% bus_stop_loc$StopName)$RouteName
bus_stop=filter(bus_stop, RouteName %in% temp, !grepl("學", RouteName))
bus_shape=filter(bus_shape, RouteName %in% temp, !grepl("學", RouteName))

# setdiff(bus_stop$RouteName, bus_shape$RouteName)
# setdiff(bus_shape$RouteName, bus_stop$RouteName)

# tm_shape(sa_grid)+
#   tm_polygons()+
#   tm_shape(bus_shape)+
#   tm_lines()+
#   tm_shape(filter(bus_shape, RouteName=="黃1"))+
#   tm_lines(col="red")



##### Smartcard Data #####
# 所有研究範圍內市區公車電子票證
bus_scd=fread("E:/On-demand Transport Service/Analysis/Data/TW PT/Smartcard/宜蘭縣公車電子票證資料(TO3).csv", skip=1)
bus_scd=bus_scd[BoardingStopName %in% bus_stop_loc$StopName & DeboardingStopName %in% bus_stop_loc$StopName & month(BoardingTime)==6]%>%
  mutate(Hour=hour(BoardingTime))


# 黃1電子票證
convert_time=function(x){
  ifelse(nchar(x)==5, paste0("0", substr(x, 1, 1), ":", substr(x, 2, 3), ":", substr(x, 4, 5)),
         paste0(substr(x, 1, 2), ":", substr(x, 3, 4), ":", substr(x, 5, 6)))
}
scd_all=readRDS("E:/On-demand Transport Service/Analysis/6_Agent-based Modelling/A_OD Analysis (TW)/scd_all.rds")%>%
  filter(!is.na(TripInfoID), !is.na(DeboardingTime))%>%
  mutate(BoardingDate=as.Date(BoardingDate, format="%Y%m%d"),
         BoardingTime=as.POSIXct(paste0(BoardingDate, " ", convert_time(BoardingTime)), tz="Asia/Taipei"),
         Hour=hour(BoardingTime),
         DeboardingTime=as.POSIXct(paste0(BoardingDate, " ", convert_time(DeboardingTime)), tz="Asia/Taipei"),
         TravelTime=as.numeric(difftime(DeboardingTime, BoardingTime, units="min")))%>%
  arrange(Month, TripInfoID, BoardingTime)%>%
  filter(month(BoardingTime)==6)

# table(scd_all$Hour)
# table(scd_all$CardType)/nrow(scd_all)


temp=filter(bus_stop_loc, !(StopName=="大礁溪橋" & TOWNNAME=="礁溪鄉"))%>%
  st_drop_geometry()%>%
  select(StopName, GridID)
bus_scd=left_join(bus_scd, rename_all(temp, function(x) paste0("Boarding", x)))%>%
  left_join(rename_all(temp, function(x) paste0("Deboarding", x)))%>%
  mutate(Weekday=as.numeric(lubridate::wday(BoardingTime, week_start=1)) %in% 1:5)

temp=filter(bus_stop_loc, !(StopName=="大礁溪橋" & TOWNNAME=="員山鄉"))%>%
  st_drop_geometry()%>%
  select(StopName, GridID)%>%
  rename(Name=StopName)
scd_all=left_join(scd_all, rename_all(temp, function(x) paste0("Boarding", x)))%>%
  left_join(rename_all(temp, function(x) paste0("Deboarding", x)))%>%
  mutate(Weekday=as.numeric(lubridate::wday(BoardingTime, week_start=1)) %in% 1:5)

filter(scd_all, Weekday==1)%>%
  group_by(BoardingDate)%>%
  summarise(Trips=n())


temp=data.frame(Date=as.Date(min(bus_scd$InfoDate):max(bus_scd$InfoDate)))%>%
  mutate(Weekday=lubridate::wday(Date, week_start=1) %in% 1:5)%>%
  group_by(Weekday)%>%
  summarise(days=n())
bus_scd_sum=rbind(group_by(bus_scd, Weekday, Hour, BoardingGridID, DeboardingGridID)%>%
                    summarise(Trips=n()),
                  group_by(scd_all, Weekday, Hour, BoardingGridID, DeboardingGridID)%>%
                    summarise(Trips=n()))%>%
  group_by(Weekday, Hour, BoardingGridID, DeboardingGridID)%>%
  summarise(Trips=sum(Trips))%>%
  left_join(temp, by="Weekday")%>%
  mutate(Trips=Trips/days)%>%
  select(-days)

# filter(bus_scd_sum, Weekday)%>%
#   group_by(BoardingGridID)%>%
#   summarise(Trips=sum(Trips))%>%
#   left_join(sa_grid, by=c("BoardingGridID"="GridID"))%>%
#   st_sf()%>%
#   tm_shape()+
#   tm_polygons(fill="Trips")



##### Characteristics of Grid #####

###### Population ######
grid100=read_sf("E:/On-demand Transport Service/Analysis/Data/TWData/Population/宜蘭縣/100m_grid_10002.shp")%>%
  st_transform(crs=3826)%>%
  rename(L6_ID=CGRID_ID)%>%
  select(L6_ID)%>%
  cbind(AREA=as.numeric(st_area(.)))
temp_id=lengths(st_intersects(grid100, sa_area))!=0
grid100=grid100[temp_id,]

pop=fread("E:/On-demand Transport Service/Analysis/Data/TWData/Population/宜蘭縣/113年12月宜蘭縣網格三段年齡組性別人口統計_六級網格.csv", skip=1)
names(pop)=names(fread("E:/On-demand Transport Service/Analysis/Data/TWData/Population/宜蘭縣/113年12月宜蘭縣網格三段年齡組性別人口統計_六級網格.csv", nrow=1))
pop=pop[, grepl("L6_ID", names(pop)) | (grepl("CNT", names(pop)) & !grepl("_M_|_F_", names(pop))), with=F]%>%
  mutate(TotalPop=A0A14_CNT+A15A64_CNT+A65UP_CNT)
temp=fread("E:/On-demand Transport Service/Analysis/Data/TWData/Population/宜蘭縣/113年12月宜蘭縣網格分齡兒童及少年性別人口統計_六級網格.csv", skip=1)
names(temp)=names(fread("E:/On-demand Transport Service/Analysis/Data/TWData/Population/宜蘭縣/113年12月宜蘭縣網格分齡兒童及少年性別人口統計_六級網格.csv", nrow=1))
temp=temp[, c("L6_ID","A12A17_CNT")]
pop=merge.data.table(pop, temp)%>%
  mutate(L6_ID=as.character(L6_ID))

grid100=left_join(grid100, pop)

temp=st_intersection(sa_grid_centre_buf, grid100)%>%
  mutate(AREA_per=as.numeric(st_area(.))/AREA)%>%
  st_drop_geometry()%>%
  group_by(GridID)%>%
  summarise(TotalPop=round(sum(TotalPop*AREA_per), 0),
            HighSchoolStudent=round(sum(A12A17_CNT*AREA_per), 0),
            Elderly=round(sum(A65UP_CNT*AREA_per), 0))
sa_grid=left_join(sa_grid, temp)


###### Transport ######
pt_hub=filter(bus_stop, grepl("宜蘭火車站\\(前站\\)|宜蘭轉運站", StopName))%>%
  mutate(StopName=gsub("2|\\(前站\\)", "", StopName))%>%
  st_drop_geometry()%>%
  group_by(StopName)%>%
  summarise(PositionLon=mean(PositionLon),
            PositionLat=mean(PositionLat))%>%
  st_as_sf(coords=c("PositionLon","PositionLat"), crs=4326)%>%
  st_transform(crs=3826)

temp=st_intersection(sa_grid_centre_buf, pt_hub)%>%
  st_drop_geometry()%>%
  group_by(GridID)%>%
  summarise(TransportHub=n())
sa_grid=left_join(sa_grid, temp)%>%
  mutate(TransportHub=ifelse(is.na(TransportHub), 0, TransportHub))



###### OSM POI ######
osm_poi=fread("E:/On-demand Transport Service/Analysis/Data/TWData/OSM Shop Amenity.csv")%>%
  st_as_sf(coords=c("X","Y"), crs=3826)

temp=st_intersection(sa_grid_centre_buf, osm_poi)%>%
  st_drop_geometry()%>%
  group_by(GridID, POIType)%>%
  summarise(count=n())%>%
  reshape2::dcast(GridID ~ POIType, value.var="count", fill=0)
sa_grid=left_join(sa_grid, temp)%>%
  mutate(Amenity=ifelse(is.na(Amenity), 0, Amenity),
         Shop=ifelse(is.na(Shop), 0, Shop))


###### Hospital ######
hospital=fread("E:/On-demand Transport Service/Analysis/Data/TWData/Hospital.csv")%>%
  filter(grepl("醫院", HospitalName), COUNTYNAME=="宜蘭縣")%>%
  st_as_sf(coords=c("X","Y"), crs=3826)
temp=st_intersection(sa_grid_centre_buf, hospital)%>%
  st_drop_geometry()%>%
  group_by(GridID)%>%
  summarise(Hospital=n())
sa_grid=left_join(sa_grid, temp)%>%
  mutate(Hospital=ifelse(is.na(Hospital), 0, Hospital))


###### School ######
school=rbind(cbind(Level="elementary", School(level="elementary", 2024, dtype="sf")[, c("NAME","STU_CNT")]),
             cbind(Level="junior", School(level="junior", 2024, dtype="sf")[, c("NAME","STU_CNT")]),
             cbind(Level="senior", School(level="senior", 2024, dtype="sf")[, c("NAME","STU_CNT")]))
temp=st_intersection(sa_grid_centre_buf, school)%>%
  st_drop_geometry()%>%
  group_by(GridID, Level)%>%
  summarise(count=n())%>%
  reshape2::dcast(GridID ~ Level, value.var="count", fill=0)
sa_grid=left_join(sa_grid, temp)%>%
  mutate(elementary=ifelse(is.na(elementary), 0, elementary),
         junior=ifelse(is.na(junior), 0, junior),
         senior=ifelse(is.na(senior), 0, senior),
         School=elementary+junior+senior)


###### Income ######
yilan_vil=st_transform(TWspdata::taiwan_village, crs=3826)%>%
  filter(COUNTYNAME=="宜蘭縣")%>%
  select(VILLCODE, TOWNNAME, VILLNAME)
temp=Income(2023)%>%
  filter(COUNTYNAME=="宜蘭縣")
yilan_vil=left_join(yilan_vil, temp[, c("TOWNNAME","VILLNAME","MEAN","MED")])%>%
  rename(Income_ave=MEAN, Income_med=MED)
temp=st_intersection(sa_grid_centre_buf, yilan_vil)%>%
  cbind(AREA=as.numeric(st_area(.)))%>%
  st_drop_geometry()%>%
  group_by(GridID)%>%
  slice(which.max(AREA))%>%
  select(GridID, Income_ave, Income_med)
sa_grid=left_join(sa_grid, temp)

# tm_shape(sa_grid)+
#   tm_polygons(fill="School")

# Downtown Area
sa_grid$Downtown=lengths(st_intersects(sa_grid, yilan_downtown))!=0


left_join(sa_grid, group_by(bus_scd_sum, BoardingGridID)%>%
            summarise(Trips=sum(Trips))%>%
            rename(GridID=BoardingGridID))%>%
  mutate(Trips=ifelse(is.na(Trips), 0, Trips))%>%
  tm_shape()+
  tm_polygons(fill="Trips", fill_alpha=0.3, fill.scale = tm_scale_intervals(
    style = "fisher",
    n = 5,
    values = "brewer.yl_or_rd"
  ))+
  tm_shape(bus_shape)+
  tm_lines()




###### OD Matrix ######
all_hour=6:22
od_mat=data.table(st_drop_geometry(bus_stop)[, c("SubRouteName","Direction","StopName","StopSequence")])
od_mat=merge.data.table(rename(od_mat, BoardingStopName=StopName, BoardingStopSequence=StopSequence),
                        rename(od_mat, DeboardingStopName=StopName, DeboardingStopSequence=StopSequence), by=c("SubRouteName","Direction"), allow.cartesian=T, sort=F)%>%
  filter(BoardingStopSequence<DeboardingStopSequence)%>%
  merge.data.table(rename_all(st_drop_geometry(bus_stop_loc)[, c("StopName","GridID")], function(x) paste0("Boarding", x)), by="BoardingStopName", sort=F)%>%
  merge.data.table(rename_all(st_drop_geometry(bus_stop_loc)[, c("StopName","GridID")], function(x) paste0("Deboarding", x)), by="DeboardingStopName", sort=F)%>%
  select(BoardingGridID, DeboardingGridID)%>%
  unique()
od_mat=cbind(Hour=rep(all_hour, times=nrow(od_mat)), od_mat[rep(c(1:nrow(od_mat)), each=length(all_hour)),])
od_mat=merge.data.table(od_mat, filter(bus_scd_sum, Weekday)[, c("Hour","BoardingGridID","DeboardingGridID","Trips")], all.x=T, sort=F)%>%
  mutate(Trips=ifelse(is.na(Trips), 0, Trips))%>%
  rename(GridID_O=BoardingGridID, GridID_D=DeboardingGridID)

mean(od_mat$Trips==0)
tm_shape(sa_grid)+
  tm_polygons()


temp=data.frame(GridID=sa_grid$GridID, st_coordinates(st_centroid(sa_grid)))
dt_model=merge.data.table(od_mat, rename_all(st_drop_geometry(sa_grid), function(x) paste0(x, "_O")), sort=F, all.x=T)%>%
  merge.data.table(rename_all(st_drop_geometry(sa_grid), function(x) paste0(x, "_D")), sort=F, all.x=T)%>%
  left_join(rename_all(temp, function(x) paste0(x, "_O")))%>%
  left_join(rename_all(temp, function(x) paste0(x, "_D")))%>%
  mutate(euclidist=((X_O-X_D)^2+(Y_O-Y_D)^2)^0.5/1000)%>%
  select(-X_O, -X_D, -Y_O, -Y_D)%>%
  mutate(TotalPop000_O=TotalPop_O/1000,
         TotalPop000_D=TotalPop_D/1000,
         Elderly000_O=Elderly_O/1000,
         Elderly000_D=Elderly_D/1000,
         HighSchoolStudent000_O=HighSchoolStudent_O/1000,
         HighSchoolStudent000_D=HighSchoolStudent_D/1000,
         Income_med_10k_O=Income_med_O/10,
         Income_med_10k_D=Income_med_D/10,
         zero_trip=as.numeric(Trips==0))


# dt_model%>%
#   mutate(Trips=Trips*20)%>%
#   write.csv("temp.csv")

res_model=gam(
  Trips ~
    School_O+School_D+Shop_O+Shop_D+Hospital_O+Hospital_D+
    TransportHub_O:Elderly000_D+
    TransportHub_D:Elderly000_O+
    Hospital_O:Elderly000_D+
    Hospital_D:Elderly000_O+
    School_O:HighSchoolStudent000_D+
    School_D:HighSchoolStudent000_O+
    Income_med_10k_O+TotalPop000_O+TotalPop000_D+
    s(euclidist)+
    s(Hour)+
    s(Hour, by=TransportHub_O)+
    s(Hour, by=TransportHub_D)+
    ti(Hour, Shop_O)+
    ti(Hour, Shop_D),
  family=tw(),
  data=filter(dt_model, Trips!=0),
  method = "REML"
)

summary(res_model)
gratia::draw(res_model)
# gam.check(res_model)


# Plot the partial effect manually
plot_list=list()
sm_var=unique(gsub("\\.\\d+$", "", names(res_model$coefficients)))
sm_var=sm_var[grepl("s\\(|ti\\(", sm_var)]
temp=strsplit(gsub("s\\(|ti\\(|\\)", "", sm_var), ":|\\,")
sm_var=cbind(sm_var=sm_var,
             as.data.frame(do.call(rbind, lapply(temp, function(x) {
               length(x)=max(lengths(temp))
               x
             })
             )))

temp=data.frame(var=c("euclidist","Hour","TransportHub_O","TransportHub_D","Shop_O","Shop_D","FromCBD","ToCBD"),
                varname=c("Desired distance between O/D (km)","Departure hour","# of transport hubs (O)","# of transport hubs (D)","# of shopping POIs (O)","# of shopping POIs (D)","Travel from downtown", "Travel to downtown"))
sm_var=left_join(sm_var, temp, by=c("V1"="var"))%>%
  rename(V1name=varname)%>%
  left_join(temp, by=c("V2"="var"))%>%
  rename(V2name=varname)%>%
  mutate(label_id=letters[1:n()])

sm=gratia::smooth_estimates(res_model)%>%
  gratia::add_confint(coverage=0.95)

temp=sm_var[grepl("s\\(", sm_var$sm_var),]
for(i in c(1:nrow(temp))){
  plot_list[[temp$sm_var[i]]]=ggplot(subset(sm, .smooth==temp$sm_var[i]), aes(x=!!sym(temp$V1[i]), y=.estimate))+
    geom_ribbon(aes(ymin=.lower_ci, ymax=.upper_ci), alpha=0.2)+
    geom_line(size=0.5)+
    scale_x_continuous(breaks=scales::pretty_breaks(n=20), expand=c(0.01,0,0.01,0))+
    scale_y_continuous(breaks=scales::pretty_breaks(n=10))+
    ggtitle(paste0("(", temp$label_id[i], ") ", gsub(" \\(km\\)", "", ifelse(is.na(temp$V2name[i]), temp$V1name[i], temp$V2name[i]))))+
    theme_bw()+
    labs(x=temp$V1name[i], y="Partial effect")+
    theme(axis.title=element_text(family="A", size=16),
          axis.text=element_text(family="A", size=12),
          plot.title=element_text(family="A", face="bold", size=18))
}

temp=sm_var[grepl("ti\\(", sm_var$sm_var),]
for(i in c(1:nrow(temp))){
  sm=gratia::smooth_estimates(res_model, select=temp$sm_var[i], n=100, dist=0.1)
  plot_list[[temp$sm_var[i]]]=ggplot(sm, aes(x=!!sym(temp$V1[i]), y=!!sym(temp$V2[i])))+
    geom_raster(aes(fill=.estimate))+
    geom_contour(aes(z=.estimate), colour="black", bins=15, linewidth=0.4, na.rm=T)+
    scale_fill_gradient2(low="#2166AC", mid="white", high="#B2182B", midpoint=0, name="Partial\neffect")+
    scale_x_continuous(breaks=scales::pretty_breaks(n=20), expand=c(0.01,0,0.01,0))+
    scale_y_continuous(breaks=scales::pretty_breaks(n=10))+
    labs(x=temp$V1name[i], y=temp$V2name[i])+
    ggtitle(paste0("(", temp$label_id[i], ") ", temp$V2name[i]))+
    coord_cartesian(expand=FALSE)+
    theme_bw()+
    theme(axis.title=element_text(family="A", size=16),
          axis.text=element_text(family="A", size=12),
          legend.title=element_text(family="A", size=14),
          legend.text=element_text(family="A", size=10),
          plot.title=element_text(family="A", face="bold", size=18))
}

png("E:/On-demand Transport Service/Paper/Plots/GAM smooth effect (Yilan).png", width=1450*2, height=800*2, res=200)
cowplot::plot_grid(cowplot::plot_grid(plotlist=plot_list[!grepl("ti", names(plot_list))], nrow=2, byrow=F),
                   cowplot::plot_grid(plotlist=plot_list[grepl("ti", names(plot_list))], nrow=1, byrow=F), ncol=1, rel_heights=c(2,1))
dev.off()



temp=summary(res_model)
data.frame(temp$p.coeff, temp$p.pv)%>%
  write.csv("temp.csv")
temp$dispersion

res_model$coefficients

res_model_zero=gam(
  zero_trip ~ Elderly000_O+Elderly000_D+TotalPop000_O+TotalPop000_D+Shop_O+Shop_D+TransportHub_O+TransportHub_D+euclidist+
    s(Hour),
  family=binomial(),
  data=dt_model
)
temp=summary(res_model_zero)
gratia::draw(res_model_zero)
data.frame(temp$p.coeff, temp$p.pv)%>%
  write.csv("temp.csv")

grid_pred=mutate(dt_model, Pred_HourTrips=NA, Pred_ZeroTrip=NA)
grid_pred$Pred_HourTrips=predict(res_model, grid_pred, type="response")
grid_pred$Pred_ZeroTrip=predict(res_model_zero, grid_pred, type="response")

min_temp=Inf
for(i in seq(0.84, 0.86, 0.001)){
  temp=abs(mean(grid_pred$zero_trip)-mean(grid_pred$Pred_ZeroTrip>i))
  if(temp<min_temp){
    min_temp=temp
    min_value=i
  }
}
print(min_value)

grid_pred$PredTrips=grid_pred$Pred_HourTrips*(1-as.numeric(grid_pred$Pred_ZeroTrip>min_value))



# ggplot()+
#   geom_point(data=filter(grid_pred, PredTrips!=0), aes(x=Trips, y=PredTrips))

sum(grid_pred$Trips)
sum(grid_pred$PredTrips)



# 
# # modal split (fixed-route & DRT)
# temp=rbind(group_by(bus_scd, Weekday, Hour, BoardingGridID, DeboardingGridID)%>%
#              summarise(Trips=n())%>%
#              mutate(FixedRoute=1),
#            group_by(scd_all, Weekday, Hour, BoardingGridID, DeboardingGridID)%>%
#              summarise(Trips=n())%>%
#              mutate(FixedRoute=0))%>%
#   filter(Weekday)%>%
#   group_by(FixedRoute, Hour)%>%
#   summarise(Trips=sum(Trips))%>%
#   ungroup()%>%
#   group_by(Hour)%>%
#   mutate(fixed_per=Trips/sum(Trips))%>%
#   filter(FixedRoute==1)%>%
#   select(Hour, fixed_per)
# 
# fixed_od=distinct(bus_scd, BoardingGridID, DeboardingGridID)%>%
#   rename(GridID_O=BoardingGridID, GridID_D=DeboardingGridID)%>%
#   mutate(FixedRoute=1)
# 
# grid_pred=left_join(grid_pred, fixed_od)%>%
#   mutate(FixedRoute=ifelse(is.na(FixedRoute), 0, FixedRoute))%>%
#   left_join(temp)%>%
#   mutate(PredTrips_DRT=ifelse(FixedRoute==1, PredTrips*(1-fixed_per), PredTrips))
# 
# 
# # group_by(grid_pred, Hour)%>%
# #   summarise(PredTrips=sum(PredTrips),
# #             Trips=sum(Trips),
# #             PredTrips_DRT=sum(PredTrips_DRT))%>%
# #   mutate(PredTrips_per=PredTrips/sum(PredTrips),
# #          Trips_per=Trips/sum(Trips),
# #          PredTrips_DRT=PredTrips_DRT/sum(PredTrips_DRT))
# 
# filter(grid_pred, GridID_O %in% drt_grid$GridID, GridID_D %in% drt_grid$GridID)%>%
#   group_by(Hour)%>%
#   summarise(PredTrips_DRT=sum(PredTrips_DRT),
#             PredTrips=sum(PredTrips),
#             Trips=sum(Trips))%>%
#   mutate(PredTrips_DRT_per=PredTrips_DRT/sum(PredTrips_DRT),
#          PredTrips_per=PredTrips/sum(PredTrips),
#          Trips_per=Trips/sum(Trips))





##### Model Prediction for simulation #####
bus_stop_y=filter(bus_stop, RouteName=="黃1", Direction==0)
bus_shape_y=filter(bus_shape, RouteName=="黃1", Direction==0)

temp=st_cast(st_line_sample(bus_shape_y$geometry, sample=as.numeric(seq(0, as.numeric(st_length(bus_shape_y$geometry)), 10)/st_length(bus_shape_y$geometry))), "POINT")
temp=lapply(c(1:(nrow(bus_stop_y)-1)), function(x){
  id1=st_nearest_feature(bus_stop_y[x,], temp)
  id2=st_nearest_feature(bus_stop_y[x+1,], temp)
  st_linestring(st_coordinates(temp[id1:id2]))
})%>%
  st_sfc()
bus_shape_y=data.frame(StopSequence_O=bus_stop_y$StopSequence[1:(nrow(bus_stop_y)-1)],
           StopSequence_D=bus_stop_y$StopSequence[2:nrow(bus_stop_y)],
           geometry=temp)%>%
  st_sf(crs=3826)

tm_shape(bus_shape_y)+
  tm_lines(col="StopSequence_O")+
  tm_shape(bus_stop_y)+
  tm_dots(col="StopSequence")

# saveRDS(list(bus_stop=bus_stop_y, bus_shape=bus_shape_y), "E:/On-demand Transport Service/Analysis/6_Agent-based Modelling/B_ABM (TW)/Data/黃1路線與站牌.rds")

drt_area=st_union(st_buffer(filter(bus_shape_y, StopSequence_O>=10), 200),
                  st_buffer(filter(bus_stop_y, StopSequence<10), 50))%>%
  st_union()
drt_grid=sa_grid[lengths(st_intersects(sa_grid, drt_area))!=0,]

tm_shape(drt_grid)+
  tm_polygons()+
  tm_shape(bus_shape_y)+
  tm_lines(col="red")

# drt_grid[, c("GridID")]%>%
#   mutate(GridID=paste0("ILA_", stringr::str_pad(GridID, 4, "left", 0)))%>%
#   st_transform(crs=4326)%>%
#   write_sf("E:/On-demand Transport Service/Analysis/6_Agent-based Modelling/B_ABM (TW)/Data/DRT Grid (Buffer).gpkg")

temp=data.frame(GridID=sa_grid$GridID, st_coordinates(st_centroid(sa_grid)))
odmat_pred=data.table(GridID_O=rep(drt_grid$GridID, each=nrow(drt_grid)),
                      GridID_D=rep(drt_grid$GridID, times=nrow(drt_grid)))%>%
  filter(GridID_O!=GridID_D)%>%
  merge.data.table(rename_all(st_drop_geometry(drt_grid), function(x) paste0(x, "_O")), by="GridID_O")%>%
  merge.data.table(rename_all(st_drop_geometry(drt_grid), function(x) paste0(x, "_D")), by="GridID_D")%>%
  left_join(rename_all(temp, function(x) paste0(x, "_O")))%>%
  left_join(rename_all(temp, function(x) paste0(x, "_D")))%>%
  mutate(euclidist=((X_O-X_D)^2+(Y_O-Y_D)^2)^0.5/1000)%>%
  select(-X_O, -X_D, -Y_O, -Y_D)%>%
  mutate(TotalPop000_O=TotalPop_O/1000,
         TotalPop000_D=TotalPop_D/1000,
         Elderly000_O=Elderly_O/1000,
         Elderly000_D=Elderly_D/1000,
         HighSchoolStudent000_O=HighSchoolStudent_O/1000,
         HighSchoolStudent000_D=HighSchoolStudent_D/1000,
         Income_med_10k_O=Income_med_O/10,
         Income_med_10k_D=Income_med_D/10)
odmat_pred=cbind(Hour=rep(all_hour, times=nrow(odmat_pred)), odmat_pred[rep(c(1:nrow(odmat_pred)), each=length(all_hour)),])

odmat_pred$Pred_HourTrips=predict(res_model, odmat_pred, type="response")
odmat_pred$Pred_ZeroTrip=predict(res_model_zero, odmat_pred, type="response")

odmat_pred$PredTrips=odmat_pred$Pred_HourTrips*(1-as.numeric(odmat_pred$Pred_ZeroTrip>min_value))


# 
# # modal split (fixed-route & DRT)
# temp=rbind(group_by(bus_scd, Weekday, Hour, BoardingGridID, DeboardingGridID)%>%
#              summarise(Trips=n())%>%
#              mutate(FixedRoute=1),
#            group_by(scd_all, Weekday, Hour, BoardingGridID, DeboardingGridID)%>%
#              summarise(Trips=n())%>%
#              mutate(FixedRoute=0))%>%
#   filter(Weekday)%>%
#   group_by(FixedRoute, Hour)%>%
#   summarise(Trips=sum(Trips))%>%
#   ungroup()%>%
#   group_by(Hour)%>%
#   mutate(fixed_per=Trips/sum(Trips))%>%
#   filter(FixedRoute==1)%>%
#   select(Hour, fixed_per)
# 
# fixed_od=distinct(bus_scd, BoardingGridID, DeboardingGridID)%>%
#   rename(GridID_O=BoardingGridID, GridID_D=DeboardingGridID)%>%
#   mutate(FixedRoute=1)
# 
# odmat_pred=left_join(odmat_pred, fixed_od)%>%
#   mutate(FixedRoute=ifelse(is.na(FixedRoute), 0, FixedRoute))%>%
#   left_join(temp)%>%
#   mutate(PredTrips_DRT=ifelse(FixedRoute==1, PredTrips*(1-fixed_per), PredTrips))
# sum(odmat_pred$PredTrips_DRT)

odmat_pred[, c("Hour","GridID_O","GridID_D","PredTrips_DRT")]%>%
  rename(PredTrips=PredTrips_DRT)%>%
  mutate(GridID_O=paste0("ILA_", stringr::str_pad(GridID_O, 4, "left", 0)),
         GridID_D=paste0("ILA_", stringr::str_pad(GridID_D, 4, "left", 0)))%>%
  fwrite("ODdata/ILA BUFFER DRT OD.csv", row.names=F)


# group_by(odmat_pred, Hour)%>%
#   summarise(PredTrips_DRT=sum(PredTrips_DRT),
#             PredTrips=sum(PredTrips))%>%
#   mutate(PredTrips_DRT_per=PredTrips_DRT/sum(PredTrips_DRT),
#          PredTrips_per=PredTrips/sum(PredTrips))

# table(scd_all$Hour)/nrow(scd_all)*100
# filter(bus_scd_sum, Weekday)%>%
#   group_by(Hour)%>%
#   summarise(Trips=sum(Trips))


temp=group_by(odmat_pred, GridID_O)%>%
  summarise(PredTrips=sum(PredTrips))%>%
  rename(GridID=GridID_O)%>%
  left_join(sa_grid)%>%
  st_sf()

tm_shape(filter(temp, PredTrips!=0))+
  tm_polygons(fill="PredTrips")+
  tm_shape(filter(temp, PredTrips==0))+
  tm_polygons()

group_by(odmat_pred, GridID_O, GridID_D)%>%
  summarise(PredTrips=sum(PredTrips))%>%
  arrange(-PredTrips)


temp=filter(bus_stop, RouteName=="黃1")
temp=unique(drt_grid$GridID[unlist(st_intersects(temp, drt_grid))])
sum(filter(odmat_pred, GridID_O %in% temp, GridID_D %in% temp)$PredTrips_DRT)

filter(scd_all, Weekday==T)%>%
  group_by(BoardingDate)%>%
  summarise(Trips=n())%>%  
  summarise(mean(Trips))



i=7
filter(odmat_pred, Hour==i, PredTrips!=0)%>%
  group_by(GridID_O, GridID_D)%>%
  summarise(PredTrips=sum(PredTrips))%>%
  left_join(st_drop_geometry(st_centroid(sa_grid)[, c("GridID")] %>% cbind(st_coordinates(.))), by=c("GridID_O"="GridID"))%>%
  rename(X_O=X, Y_O=Y)%>%
  left_join(st_drop_geometry(st_centroid(sa_grid)[, c("GridID")] %>% cbind(st_coordinates(.))), by=c("GridID_D"="GridID"))%>%
  rename(X_D=X, Y_D=Y)%>%
  mutate(geometry=st_as_sfc(paste0("LINESTRING(", X_O, " ", Y_O, ",", X_D, " ", Y_D, ")")))%>%
  st_sf(crs=3826)%>%
  arrange(PredTrips)%>%
  tm_shape()+
  tm_lines(col="PredTrips")+
  tm_shape(st_sf(left_join(filter(odmat_pred, Hour==i, PredTrips!=0), sa_grid, by=c("GridID_O"="GridID")), crs=3826))+
  tm_dots()


group_by(odmat_pred, Hour)%>%
  summarise(PredTrips=sum(PredTrips))%>%
  mutate(PredTrips_per=PredTrips/sum(PredTrips))



##### Fixed-route Simulation #####
# bus_trip=Bus_ScheduleEst(access_token, "YilanCounty", unique(bus_stop$RouteName))
# bus_trip$StopName=bus_trip$StopName$Zh_tw
# bus_trip$ServiceDay=bus_trip$ServiceDay$ServiceTag
# fwrite(bus_trip, "E:/On-demand Transport Service/Analysis/Data/TW PT/Transport/Bus/Timetable/Bus Timetable.csv", row.names=F)

# st_drop_geometry(bus_stop)[, c("RouteUID","SubRouteUID","Direction","StopUID","StopSequence","PositionLat","PositionLon")]%>%
#   fwrite("E:/On-demand Transport Service/Analysis/Data/TW PT/Transport/Bus/Timetable/Bus Route Stop.csv", row.names=F)





##### Road Network for Simulation #####
# road_node=fread("E:/On-demand Transport Service/Analysis/Data/Road Network/TW/node.csv")
# road_node=st_as_sf(road_node, coords=c("lon","lat"), crs=4326)%>%
#   st_transform(crs=3826)
# # temp_id=st_intersects(road_node, st_as_sfc(st_transform(st_bbox(all_loc), crs=3826)+c(-3000,-3000,3000,3000))) # 梨山
# temp_id=st_intersects(road_node, st_as_sfc(st_bbox(filter(bus_shape, RouteName=="黃1"))+c(-5000,-5000,5000,5000))) # 宜蘭黃1
# road_node=road_node[lengths(temp_id)!=0,]
# 
# road_link=fread("E:/On-demand Transport Service/Analysis/Data/Road Network/TW/link.csv")
# road_link=road_link[fromnode %in% road_node$nodeid | tonode %in% road_node$nodeid]
# 
# temp=data.table(st_drop_geometry(st_read("G:/OSM Grid/Feature/OSM/Taiwan/Taiwan.gpkg", layer="lines"))[, c("osm_id","highway")])%>%
#   mutate(osm_id=as.numeric(osm_id))%>%
#   rename(way=highway)
# road_link=merge.data.table(road_link, temp, by.x="externalid", by.y="osm_id")
# rm(temp)
# 
# road_link$geometry=lapply(strsplit(road_link$geometry, " "), function(x) matrix(as.numeric(unlist(strsplit(x, ","))), ncol=2, byrow=T)[,2:1])%>%
#   lapply(function(x) st_linestring(x))
# road_link=st_sf(road_link, crs=4326)
# 
# tm_shape(road_link)+
#   tm_lines()
# 
# 
# wts=distinct(st_drop_geometry(road_link), way)%>%
#   left_join(filter(dodgr::weighting_profiles[[1]], name=="motorcar"), by=c("way"))%>%
#   select(name, way, value)%>%
#   filter(!is.na(name))
# road_net=weight_streetnet(road_link, wt_profile=wts, type_col="way", id_col="linkid")
# road_net_sf=data.frame(road_net)%>%
#   mutate(geometry=st_as_sfc(paste0("LINESTRING(", from_lon, " ", from_lat, ",", to_lon, " ", to_lat, ")")))%>%
#   st_sf(crs=4326)
# verts=dodgr_vertices(road_net)
# 
# filter(dodgr::weighting_profiles[[1]], name=="motorcar")[, c("way","max_speed")]%>%
#   filter(!is.na(max_speed))%>%
#   write.csv("osm_weight.csv", row.names=F)
# 
# network_data=list(road_node=road_node, road_link=road_link, road_net=road_net)
# saveRDS(network_data, "E:/On-demand Transport Service/Analysis/Data/Road Network/Network_Yilan.rds")

temp=group_by(scd_all, BoardingGridID, DeboardingGridID)%>%
  summarise(Count=n())%>%
  left_join(st_drop_geometry(st_centroid(sa_grid)[, c("GridID")] %>% cbind(st_coordinates(.))), by=c("BoardingGridID"="GridID"))%>%
  rename(X_O=X, Y_O=Y)%>%
  left_join(st_drop_geometry(st_centroid(sa_grid)[, c("GridID")] %>% cbind(st_coordinates(.))), by=c("DeboardingGridID"="GridID"))%>%
  rename(X_D=X, Y_D=Y)%>%
  mutate(geometry=st_as_sfc(paste0("LINESTRING(", X_O, " ", Y_O, ",", X_D, " ", Y_D, ")")))%>%
  st_sf(crs=3826)

temp=group_by(st_drop_geometry(odmat_pred), GridID_O, GridID_D)%>%
  summarise(Count=sum(PredTrips))%>%
  left_join(st_drop_geometry(st_centroid(sa_grid)[, c("GridID")] %>% cbind(st_coordinates(.))), by=c("GridID_O"="GridID"))%>%
  rename(X_O=X, Y_O=Y)%>%
  left_join(st_drop_geometry(st_centroid(sa_grid)[, c("GridID")] %>% cbind(st_coordinates(.))), by=c("GridID_D"="GridID"))%>%
  rename(X_D=X, Y_D=Y)%>%
  mutate(geometry=st_as_sfc(paste0("LINESTRING(", X_O, " ", Y_O, ",", X_D, " ", Y_D, ")")))%>%
  st_sf(crs=3826)%>%
  arrange(Count)%>%
  filter(Count!=0)
tm_shape(temp)+
  tm_lines(col="Count")

st_transform(st_centroid(sa_grid), crs=4326)%>%
  cbind(st_coordinates(.))%>%
  select(GridID, X, Y)%>%
  st_drop_geometry()%>%
  write.csv("ML model/SA Grid.csv", row.names=F)


# tm_shape(sa_grid)+
#   tm_polygons()+
#   tm_shape(bus_shape)+
#   tm_lines()



sa_box=st_bbox(st_transform(sa_grid, crs=3857))
carto_light <- maptiles::create_provider(
  name = "CARTO_LIGHT",
  url = "https://basemaps.cartocdn.com/rastertiles/light_nolabels/{z}/{x}/{y}.png?key=REMOVED_CONFIGURE_YOUR_OWN_KEY",
  citation = "© OpenStreetMap contributors © CARTO"
)
tiles=maptiles::get_tiles(
  x = sa_box,
  provider = carto_light,
  zoom = 14,
  crop = TRUE,
  project = FALSE,
  forceDownload = TRUE
)

HR=17
temp=filter(bus_scd_sum, Weekday==T, Hour==HR, BoardingGridID!=DeboardingGridID)%>%
  left_join(st_drop_geometry(st_centroid(st_transform(sa_grid, crs=3857)) %>% cbind(st_coordinates(.)))[, c("GridID","X","Y")], by=c("BoardingGridID"="GridID"))%>%
  rename(X_O=X, Y_O=Y)%>%
  left_join(st_drop_geometry(st_centroid(st_transform(sa_grid, crs=3857)) %>% cbind(st_coordinates(.)))[, c("GridID","X","Y")], by=c("DeboardingGridID"="GridID"))%>%
  rename(X_D=X, Y_D=Y)%>%
  arrange(Trips)

png(paste0("E:/On-demand Transport Service/Paper/Plots/Yilan Hourly Trips (", HR, ").png"), width=795*2, height=644*2, res=200)
ggplot()+
  tidyterra::geom_spatraster_rgb(data=tiles)+
  geom_sf(data=yilan_downtown, fill="#009100", color=NA, alpha=0.2)+
  geom_sf(data=st_transform(bus_shape, crs=3857), color="#8E8E8E")+
  geom_sf(data=filter(bus_shape, RouteName=="黃1"), color="#004B97", linewidth=0.8)+
  geom_curve(data=temp, aes(x=X_O, y=Y_O, xend=X_D, yend=Y_D, color=Trips, linewidth=Trips), arrow=arrow(length=unit(0.2, "cm"), type="closed"), curvature=0.3, alpha=0.6)+
  scale_color_distiller(palette="YlOrRd", direction=1, guide="legend", name="Hourly Passengers", limits=c(0,2))+
  scale_linewidth_continuous(range=c(0,2), breaks=seq(0,2,0.5), guide="legend", name="Hourly Passengers", limits=c(0,2))+
  coord_sf(xlim=c(sa_box[c(1,3)]+c(500,-500)), ylim=c(sa_box[c(2,4)])+c(500,-500), crs=3857)+
  theme_void()+
  theme(legend.title=element_text(family="A", size=16, face="bold"),
        legend.text=element_text(family="A", size=14),
        legend.justification=c("left","top"),
        legend.background=element_blank(),
        legend.position=c(0.05,0.95))
dev.off()





