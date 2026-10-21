library(dplyr)
library(sf)
library(tmap)
library(data.table)
library(stringr)
library(ggplot2)
library(cowplot)
library(TDX)
library(rDEA)
library(AER)
library(ggh4x)

windowsFonts(A=windowsFont("Tw Cen MT"))
windowsFonts(A=windowsFont("Times New Roman"))
windowsFonts(B=windowsFont("Times New Roman"))
windowsFonts(C=windowsFont("Consolas"))

tmap_mode("view")

client_id=Sys.getenv("TDX_CLIENT_ID")
client_secret=Sys.getenv("TDX_CLIENT_SECRET")
access_token=get_token(client_id, client_secret)


# ################################## #
#### Read TW DRTS data ####
# ################################## #
##### Read Stop Data #####
drt_stop=readxl::read_excel("E:/On-demand Transport Service/Analysis/Data/DRTS/Stop and Region/DRTS Route Stop.xlsx", sheet="DRTS Route Stop")%>%
  mutate(geometry=ifelse(is.na(PositionGeo), paste0("POINT(", PositionLon, " ", PositionLat, ")"),
                         paste0("POINT(", substr(PositionGeo, regexpr(",", PositionGeo)+1, 100), " ", substr(PositionGeo, 1, regexpr(",", PositionGeo)-1), ")")),
         geometry=st_as_sfc(geometry))%>%
  st_sf(crs=4326)


##### Read Route Data #####
# give the ShapeID for each SubRoute and identify the operational type
drt_route=readxl::read_excel("E:/On-demand Transport Service/Analysis/Data/DRTS/Stop and Region/DRTS Route.xlsx")

temp=rbind(cbind(readxl::read_excel("E:/On-demand Transport Service/Analysis/Data/DRTS/Stop and Region/DRTS Route Stop.xlsx", sheet="DRTS Route Stop")[, c("COUNTYNAME","RouteName","SubRouteName")], OpeType="Route"),
           cbind(readxl::read_excel("E:/On-demand Transport Service/Analysis/Data/DRTS/Stop and Region/DRTS Route Stop.xlsx", sheet="DRTS Route Region")[, c("COUNTYNAME","RouteName","SubRouteName")], OpeType="Zone"))%>%
  distinct()

drt_route=left_join(drt_route, temp)%>%
  mutate(ShapeID=c(1:nrow(.)))
  

##### Read Shape Data #####
dir_files=dir("E:/On-demand Transport Service/Analysis/Data/DRTS/Stop and Region/Route Shape", full.names=T)
drt_shape=rbindlist(lapply(dir_files, function(x){
  temp=fread(x)
  route_info=data.frame(t(unlist(strsplit(gsub(".csv", "", tail(unlist(strsplit(x, "/")), 1)), "_"))))
  names(route_info)=c("COUNTYNAME","RouteName","SubRouteName","Direction")
  temp=cbind(route_info, temp)
  return(temp)
}))
drt_shape=st_as_sf(drt_shape, wkt="geometry", crs=4326)%>%
  st_transform(crs=3826)
drt_shape=left_join(drt_shape, filter(drt_route, OpeType=="Route")[, c("ShapeID","COUNTYNAME","RouteName","SubRouteName")])


drt_shape_route=group_by(drt_shape, ShapeID, COUNTYNAME, RouteName, SubRouteName, Direction)%>%
  summarise()%>%
  mutate(Length=as.numeric(st_length(geometry)))%>%
  group_by(ShapeID, COUNTYNAME, RouteName, SubRouteName)%>%
  slice(which.max(Length))%>%
  select(-Direction)%>%
  cbind(OpeType="Route")

drt_shape_area=read_sf("E:/On-demand Transport Service/Analysis/Data/DRTS/Stop and Region/Route Area.gpkg")%>%
  st_transform(crs=3826)%>%
  st_make_valid()%>%
  rename(geometry=geom)%>%
  mutate(geometry=ifelse(grepl("LINE|POINT", st_geometry_type(geometry)), st_buffer(geometry, 500), geometry))%>%
  group_by(COUNTYNAME, RouteName, SubRouteName)%>%
  reframe(geometry=st_union(geometry))%>%
  cbind(OpeType="Zone")%>%
  st_sf(crs=3826)%>%
  left_join(filter(drt_route, OpeType=="Zone")[, c("COUNTYNAME","RouteName","SubRouteName","ShapeID")])


# 少數營運範圍同時提供route-based & zone-based (如南投1路(埔里-中正村-法治村))，故需再次union
drt_shape_all=rbind(select(drt_shape_route, -Length), drt_shape_area)%>%
  group_by(COUNTYNAME, RouteName, SubRouteName)%>%
  reframe(ShapeID=list(sort(unique(ShapeID))),
          OpeType=list(sort(unique(OpeType))),
          geometry=st_union(geometry))%>%
  st_sf()
table(unlist(lapply(drt_shape_all$OpeType, function(x) paste(x, collapse="|"))))

# ggplot()+
#   geom_sf(data=drt_shape_route)+
#   geom_sf(data=drt_shape_area)+
#   geom_sf(data=drt_stop)
# ggplot(drt_shape_all)+
#   geom_sf()

# tm_shape(drt_shape_area)+
#   tm_dots()


##### Read Operational Data #####
ope_data=readxl::read_excel("E:/On-demand Transport Service/Analysis/Data/DRTS/Operational Data/Operational Data Summary.xlsx")%>%
  mutate(Year=as.numeric(gsub("年", "", Year))+1911,
         Month=as.numeric(gsub("月", "", Month)))%>%
  filter(Year>=2022)

# 名稱重複修正
ope_data=mutate(ope_data, OpeName=case_when(
  TOWNNAME=="望安鄉" & OpeName=="船班路線" ~ "船班路線(望安)",
  TOWNNAME=="七美鄉" & OpeName=="船班路線" ~ "船班路線(七美)",
  TRUE ~ OpeName
))


ope_data=ope_data[apply(ope_data[, grepl("Fixed|Booking", names(ope_data))], 1, sum, na.rm=T)!=0,]
ope_data=group_by(ope_data, Year, Month, COUNTYNAME, TOWNNAME, OpeName)%>%
  summarise_all(sum, na.rm=T)

ope_data_sum=select(ungroup(ope_data), -Year, -Month, -TOWNNAME)%>%
  group_by(COUNTYNAME, OpeName)%>%
  summarise_all(sum)
temp=select(ungroup(ope_data), -TOWNNAME)%>%
  mutate(MON=paste0(Year, "-", str_pad(Month, 2, "left", 0)))%>%
  group_by(COUNTYNAME, OpeName)%>%
  summarise(Period_min=min(MON), Period_max=max(MON), AllPeriod=list(unique(sort(MON))), TotalMonth=length(unique(MON)))
ope_data_sum=left_join(ope_data_sum, temp)

ope_data_route=distinct(ungroup(ope_data), COUNTYNAME, OpeName)


drt_route_ope=reshape2::melt(select(drt_route, -ShapeID, -OpeType), id.vars=c("COUNTYNAME","RouteName","SubRouteName"), value.name="OpeName")%>%
  select(-variable)%>%
  distinct()
drt_route_ope=rbind(drt_route_ope, select(drt_route_ope, -OpeName)%>%
             mutate(OpeName=SubRouteName))%>%
  distinct()%>%
  filter(!is.na(OpeName))%>%
  left_join(st_drop_geometry(drt_shape_all))



# 配對營運資料路線名稱與路線圖資名稱
ope_data_route=left_join(ope_data_route, drt_route_ope)
# temp=ope_data_route[duplicated(ope_data_route[, c("COUNTYNAME","OpeName")]), c("COUNTYNAME","OpeName")]%>%
#   distinct()%>%
#   left_join(ope_data_route)


# 有7.9%無法正確匹配（資料過時，找不到），直接刪除！
mean(lengths(ope_data_route$ShapeID)==0)
ope_data_route=filter(ope_data_route, !is.na(ShapeID))

# tm_shape(st_sf(filter(drt_shape_all, ShapeID==238)))+
#   tm_lines(col="blue")+
#   tm_shape(st_sf(filter(drt_shape_all, ShapeID==237)))+
#   tm_lines(col="red")

ope_data_sum_route=left_join(ope_data_sum, ope_data_route)%>%
  filter(lengths(ShapeID)!=0)%>%
  left_join(drt_shape_all)%>%
  st_sf()

temp=distinct(select(ungroup(st_drop_geometry(ope_data_sum_route)), -ShapeID, -RouteName, -SubRouteName, -OpeType))%>%
  left_join(group_by(ungroup(st_drop_geometry(ope_data_sum_route)), COUNTYNAME, OpeName)%>%
              summarise(OpeType=list(sort(unique(unlist(OpeType))))))

# 若同一營運名稱對應多個OpeName，表示該路線有多條子路線，或有合併路線之情形，需將geometry合併
ope_data_sum_route=group_by(ope_data_sum_route, COUNTYNAME, OpeName)%>%
  summarise(ShapeID=list(sort(unique(unlist(ShapeID)))),
            RouteName=paste(RouteName, collapse="|"),
            SubRouteName=paste(SubRouteName, collapse="|"),
            OpeType=list(sort(unique(unlist(OpeType)))))%>%
  left_join(temp)


# 若同一條路線(ShapeID)指向多個營運路線名稱，表示該路線名稱歷年來的紀錄不一致或有更名，須將其營運資料全數合併
ope_data_sum_route=group_by(ope_data_sum_route, ShapeID, COUNTYNAME, RouteName, SubRouteName, OpeType)%>%
  summarise(OpeName=paste(OpeName, collapse="|"),
            across(TotalTrips_Fixed:Revenue_Booking, ~ sum(.x)),
            AllPeriod=list(unique(unlist(AllPeriod))),
            Period_min=min(unlist(AllPeriod)),
            Period_max=max(unlist(AllPeriod)),
            TotalMonth=length(unlist(AllPeriod)))

# saveRDS(ope_data_sum_route, "Data/Operational Data (Route Shape.rds)")

sum(duplicated(st_drop_geometry(ope_data_sum_route)[, c("COUNTYNAME","OpeName")]))

table(unlist(lapply(ope_data_sum_route$OpeType, function(x) paste(unlist(x), collapse="|"))))



##### Read Service Data (Service Type) #####
ope_name=strsplit(ope_data_sum_route$RouteName, "\\|")
ope_name=data.frame(COUNTYNAME=rep(ope_data_sum_route$COUNTYNAME, times=lengths(ope_name)),
                    OpeName=rep(ope_data_sum_route$OpeName, times=lengths(ope_name)),
                    RouteName=unlist(ope_name),
                    SubRouteName=unlist(strsplit(ope_data_sum_route$SubRouteName, "\\|")))

drt_route_type=st_drop_geometry(drt_stop)[, c("COUNTYNAME","RouteName","SubRouteName","Reservation","Hail")]%>%
  distinct()%>%
  group_by(COUNTYNAME, RouteName, SubRouteName)%>%
  summarise(Deviation_Reservation=max(Reservation),
            Hail=max(Hail))%>%
  left_join(ope_name)
temp=readxl::read_excel("E:/On-demand Transport Service/Analysis/Data/DRTS/Stop and Region/DRTS Route Stop.xlsx", sheet="DRTS Route Region")[, c("COUNTYNAME","RouteName","SubRouteName")]%>%
  distinct()%>%
  cbind(P2P=1)%>%
  left_join(ope_name)
drt_route_type=rbind(drt_route_type, temp)%>%
  filter(!is.na(OpeName))
drt_route_type[is.na(drt_route_type)]=0
drt_route_type=distinct(select(ungroup(drt_route_type), -RouteName, -SubRouteName))%>%
  group_by(COUNTYNAME, OpeName)%>%
  summarise(Deviation_Reservation=max(Deviation_Reservation),
            Hail=max(Hail),
            P2P=max(P2P))

# 直接用營運資料判斷該路線是否可預約
temp=group_by(st_drop_geometry(ope_data_sum_route), COUNTYNAME, OpeName)%>%
  summarise(Patronage_Booking=sum(Patronage_Booking))%>%
  mutate(Booking=ifelse(Patronage_Booking!=0, 1, 0))%>%
  select(COUNTYNAME, OpeName, Booking)
drt_route_type=left_join(drt_route_type, temp)

drt_route_type=mutate(drt_route_type, ServiceType=case_when(
  Deviation_Reservation==1 | Hail==1 | (Booking==1 & P2P!=1) ~ "Flexible Fixed-Route",
  P2P==1 ~ "Point-to-Point",
  TRUE ~ "Fixed-Route"
))
table(drt_route_type$ServiceType)

ope_data_sum_route=left_join(ope_data_sum_route, drt_route_type)
# saveRDS(ope_data_sum_route, "Data/Operational Data (Route Shape.rds)")



##### Read Service Data (Fleet) #####
drt_fleet=readxl::read_excel("E:/On-demand Transport Service/Analysis/Data/DRTS/Operational Data/Fleet.xlsx", sheet="Fleet")%>%
  mutate(小型車=小型車+小型車無障礙)
unique(ope_data_sum_route$OpeName)[!unique(ope_data_sum_route$OpeName) %in% drt_fleet$OpeName]

names(drt_fleet)[names(drt_fleet) %in% c("營運主體","車輛總數","共用","甲類","乙類","小型車")]=c("Operator","FleetNum","Shared","Bus","Minibus","Car")
drt_fleet=drt_fleet[, grepl("[A-Za-z]", names(drt_fleet))]

unique(drt_fleet$Operator)
drt_fleet=mutate(drt_fleet, OperatorType=case_when(
  grepl("客運|捷乘|昱境通運|大南汽車", Operator) ~ "Bus Operator",
  grepl("公所|公共汽車管理處|竹塘鄉|公車處", Operator) ~ "City Council",
  grepl("大車隊|計程車|皇冠交通|怡美交通", Operator) ~ "Taxi Operator",
  grepl("台灣真好", Operator) ~ "Charter Operator",
  grepl("發展協會|關懷協會|基金會|合作社|服務協會", Operator) ~ "NGO"
))

drt_fleet=group_by(drt_fleet, COUNTYNAME, OpeName)%>%
  summarise(FleetNum=sum(FleetNum),
            Shared=ifelse(sum(Shared=="有")!=0, 1, 0),
            Bus=sum(Bus), Minibus=sum(Minibus), Car=sum(Car),
            OperatorType=paste(sort(unique(OperatorType)), collapse="|"))


ope_data_sum_route=left_join(ope_data_sum_route, drt_fleet)
# saveRDS(ope_data_sum_route, "Data/Operational Data (Route Shape.rds)")



# ################################## #
#### Service Intention ####
# ################################## #
drt_intention_infer=left_join(drt_stop, select(filter(drt_route, OpeType=="Route"), COUNTYNAME, RouteName, SubRouteName, ShapeID))%>%
  st_drop_geometry()
temp=data.frame(OpeName=rep(ope_data_sum_route$OpeName, times=lengths(ope_data_sum_route$ShapeID)),
                ShapeID=unlist(ope_data_sum_route$ShapeID))
drt_intention_infer=left_join(drt_intention_infer, temp)%>%
  mutate(Medicare=ifelse(grepl("醫院|診所|衛生所|衛生室|皮膚科|牙科|骨科", StopRegion), 1, 0),
         Education=ifelse(grepl("國小|國中|高中|中學|分校", StopRegion) & !grepl("高中里|高中二里", StopRegion), 1, 0),
         TransportHub=ifelse(grepl("車站|轉運站|捷運|臺鐵|高鐵|碼頭", StopRegion) & !grepl("勝興車站", StopRegion), 1, 0),
         Indigenous=ifelse(grepl("文健站|部落|原住民|集會所|聚會所", StopRegion), 1, 0),
         Downtown=ifelse(grepl("公所|銀行|郵局|農會", StopRegion), 1, 0))%>%
  group_by(COUNTYNAME, OpeName)%>%
  summarise(Medicare=as.numeric(sum(Medicare)!=0),
            Education=as.numeric(sum(Education)!=0),
            TransportHub=as.numeric(sum(TransportHub)!=0),
            Indigenous=as.numeric(sum(Indigenous)!=0),
            Downtown=as.numeric(sum(Downtown)!=0))

# drt_intention_infer=reshape2::melt(drt_intention_infer, id.vars=c("COUNTYNAME","OpeName"))%>%
#   filter(value==1)%>%
#   group_by(COUNTYNAME, OpeName)%>%
#   summarise(variable=paste(variable, collapse="|"))%>%
#   tidyr::separate(col="variable", into=LETTERS[1:5])
# writexl::write_xlsx(temp, "drt_intention_infer.xlsx")



# ################################## #
#### Plot Service Data ####
# ################################## #
ope_data_sum_route=readRDS("Data/Operational Data (Route Shape.rds)")
drt_intention=readxl::read_excel("E:/On-demand Transport Service/Analysis/Data/DRTS/Operational Data/Service Intention.xlsx")%>%
  select(-Reference1, -Reference2)%>%
  reshape2::melt(id.vars=c("COUNTYNAME","OpeName"), value.name="ServiceIntention")%>%
  filter(!is.na(ServiceIntention))%>%
  select(-variable)
unique(drt_intention$ServiceIntention)



temp=mutate(st_drop_geometry(ope_data_sum_route), ServiceTypeLAB=case_when(
  ServiceType=="Fixed-Route" ~ "Flexible fleet fixed-route (FFFR)",
  ServiceType=="Flexible Fixed-Route" ~ "Flexible fixed-route (FFR)",
  ServiceType=="Point-to-Point" ~ "Point-to-point (P2P)"
))%>%
  group_by(ServiceTypeLAB)%>%
  summarise(Count=n())%>%
  mutate(Count_per=Count/sum(Count)*100,
         ServiceTypeLAB=factor(ServiceTypeLAB, levels=c("Flexible fleet fixed-route (FFFR)","Flexible fixed-route (FFR)","Point-to-point (P2P)")))%>%
  arrange(desc(ServiceTypeLAB))%>%
  mutate(Count_per_cum=cumsum(Count_per),   # 計算累積比例
         lab_y=Count_per_cum-Count_per/2,
         lab=paste0("<b><SPAN STYLE='font-size:17pt'>", Count, "</SPAN></b>", "<br>[", format(round(Count_per, 1), nsmall=1), "%]"))   

# png("figure/DRT Service Type.png", width=850*2, height=576*2, res=200)
png("E:/On-demand Transport Service/Paper/Plots/DRT Operational Model (TW).png", width=850*2, height=576*2, res=200)
ggplot()+
  geom_col(data=temp, aes(x="", y=Count_per, fill=ServiceTypeLAB), alpha=0.8)+
  ggtext::geom_richtext(data=temp, aes(x="", y=lab_y, label=lab), family="A", size=5, fill=NA, label.color=NA)+
  scale_fill_manual(values=c("#E41A1CFF","#4D9221","#377EB8FF"), name="Service Type")+
  coord_polar("y")+
  theme_void()+
  theme(legend.title=element_text(family="A", size=18, face="bold", hjust=0.5),
        legend.text=element_text(family="A", size=16),
        legend.justification=c(0.5,0.5,0,0),
        legend.position="bottom",
        legend.key.spacing.x=unit(0.5, "cm"),
        legend.box.margin=margin(t=-30),
        legend.direction="horizontal",
        legend.title.position="top")
dev.off()




temp=group_by(st_drop_geometry(ope_data_sum_route), OperatorType)%>%
  summarise(Count=n())%>%
  arrange(Count)%>%
  mutate(Count_per=Count/sum(Count)*100,
         OperatorType=factor(OperatorType, levels=OperatorType))%>%
  arrange(desc(OperatorType))%>%
  mutate(Count_per_cum=cumsum(Count_per),   # 計算累積比例
         lab_y=Count_per_cum-Count_per/2,
         lab=paste0("<b><SPAN STYLE='font-size:17pt'>", Count, "</SPAN></b>", "<br>[", format(round(Count_per, 1), nsmall=1), "%]"))   

png("figure/DRT Operator Type.png", width=700*2, height=649*2, res=200)
# png("E:/On-demand Transport Service/Paper/Plots/DRT Operator Type (TW).png", width=776*2, height=576*2, res=200)
ggplot()+
  geom_col(data=temp, aes(x="", y=Count_per, fill=OperatorType))+
  ggtext::geom_richtext(data=temp, aes(x="", y=lab_y, label=lab), family="A", size=5, fill=NA, label.color=NA, vjust=c(0.5,0.5,0.5,0.5,-0.5))+
  scale_fill_manual(values=paletteer::paletteer_d("ggsci::springfield_simpsons"), name="Operator Type")+
  coord_polar("y")+
  theme_void()+
  theme(legend.title=element_text(family="A", size=18, face="bold", hjust=0.5),
        legend.text=element_text(family="A", size=16),
        legend.justification=c(0.5,0.5,0,0),
        legend.position="bottom",
        legend.box.margin=margin(t=-30),
        legend.direction="horizontal",
        legend.title.position="top")+
  guides(fill=guide_legend(nrow=2))
dev.off()


temp=mutate(ope_data_sum_route, ServiceTypeLAB=case_when(
  ServiceType=="Fixed-Route" ~ "Flexible fleet fixed-route (FFFR)",
  ServiceType=="Flexible Fixed-Route" ~ "Flexible fixed-route (FFR)",
  ServiceType=="Point-to-Point" ~ "Point-to-point (P2P)"
))%>%
  mutate(ServiceTypeLAB=factor(ServiceTypeLAB, levels=c("Flexible fleet fixed-route (FFFR)","Flexible fixed-route (FFR)","Point-to-point (P2P)")))
area_box=st_bbox(ope_data_sum_route)

png("figure/DRT Service Map.png", width=642*2, height=578*2, res=200)
# png("E:/On-demand Transport Service/Paper/Plots/DRT Service Map (TW).png", width=642*2, height=578*2, res=200)
ggplot()+
  geom_sf(data=st_transform(TWspdata::taiwan_county, crs=3826), color="#F0F0F0", fill="#9D9D9D")+
  geom_sf(data=filter(temp, ServiceType=="Point-to-Point"), aes(fill=ServiceTypeLAB), color="#7B7B7B")+
  geom_sf(data=filter(temp, ServiceType!="Point-to-Point"), aes(color=ServiceTypeLAB), show.legend="line")+
  # scale_color_brewer(palette="Set2")+
  scale_color_manual(values=c("#E41A1CFF","#4D9221"), name="Operational Model")+
  scale_fill_manual(values="#377EB8FF", name=NULL)+
  coord_sf(xlim=c(area_box[1], area_box[3]),
           ylim=c(area_box[2], area_box[4]))+
  theme_void()+
  theme(legend.title=element_text(family="A", size=14, face="bold"),
        legend.text=element_text(family="A", size=12),
        legend.position=c(0.15,0.25),
        legend.justification="top")+
  guides(fill=guide_legend(override.aes=list(color=NA), order=2),
         color=guide_legend(override.aes=list(linewidth=1), order=1))
dev.off()


temp=mutate(drt_intention, ServiceIntention=case_when(
  ServiceIntention %in% c("ConnectDowntown","Mobility","TransportHub") ~ "Access to Local Centres",
  ServiceIntention=="Education" ~ "Access to Education",
  ServiceIntention=="Elderly" ~ "Support for Older Adults",
  ServiceIntention=="Indigenous" ~ "Support for Indigenous Communities",
  ServiceIntention=="Medicare" ~ "Access to Medical Services",
  # ServiceIntention=="Mobility" ~ "Mobility Enhancement",
  ServiceIntention=="Substitution" ~ "	Conventional bus route replacement",
  ServiceIntention=="Tourism" ~ "Tourism Access"
  # ServiceIntention=="TransportHub" ~ "Access to Transport Hubs"
))%>%
  group_by(ServiceIntention)%>%
  summarise(Count=n())%>%
  mutate(Count_per=Count/nrow(distinct(drt_intention[, c("COUNTYNAME","OpeName")]))*100)%>%
  arrange(Count_per)%>%
  mutate(ServiceIntention=factor(ServiceIntention, levels=ServiceIntention))

# png("figure/DRT Service Intention.png", width=700*2, height=530*2, res=200)
png("E:/On-demand Transport Service/Paper/Plots/DRT Service Intention (TW).png", width=700*2, height=530*2, res=200)
ggplot()+
  geom_segment(data=temp, aes(x=0, xend=Count, y=ServiceIntention, yend=ServiceIntention))+
  geom_point(data=temp, aes(x=Count, y=ServiceIntention))+
  geom_text(data=temp, aes(x=Count+5, y=ServiceIntention, label=paste0(Count, "\n[", format(round(Count_per, 1), 1), "%]")), hjust=0, family="A", fontface="bold")+
  scale_x_continuous(breaks=seq(0,450,50), expand=c(0,0,0.2,0.2))+
  xlab("Number of Service Schemes") + ylab("Service Intention")+
  theme_bw()+
  theme(axis.title=element_text(family="A", size=16, face="bold", hjust=0.5),
        axis.text.x=element_text(family="A", size=14),
        axis.text.y=element_text(family="A", size=12))
dev.off()




# ################################## #
#### Modelling Data ####
# ################################## #
ope_data_sum_route=readRDS("Data/Operational Data (Route Shape.rds)")

drt_shape_buf_feature=readRDS("Data/Route Shape Feature.rds")%>%
  mutate(MedicalService=Clinic+HealthCentre+Hospital)%>%
  select(COUNTYNAME, RouteName, SubRouteName, Population, DayworkPop, KidsTeen, Elderly, Indigenous, School, MedicalService, TransportHub, Amenity, Shop, TourismComment)

drt_shape_intention=readxl::read_excel("E:/On-demand Transport Service/Analysis/Data/DRTS/Operational Data/Service Intention.xlsx")%>%
  select(-Reference1, -Reference2)%>%
  reshape2::melt(id.vars=c("COUNTYNAME","OpeName"), value.name="ServiceIntention")%>%
  mutate(ServiceIntention=case_when(
    ServiceIntention %in% c("ConnectDowntown","Mobility","TransportHub") ~ "LocalCentre",
    TRUE ~ ServiceIntention
  ))%>%
  distinct()%>%
  filter(!is.na(ServiceIntention))%>%
  select(-variable)%>%
  distinct()%>%
  group_by(COUNTYNAME, OpeName)%>%
  mutate(ServiceIntention=paste0("SI_", ServiceIntention))%>%
  reshape2::dcast(COUNTYNAME+OpeName ~ ServiceIntention, fun.aggregate=length)

model_data=st_drop_geometry(ope_data_sum_route)%>%
  mutate(TotalTrips_Fixed=TotalTrips_Fixed/TotalMonth,
         TripsNoPax_Fixed=TripsNoPax_Fixed/TotalMonth,
         VKT_Fixed=VKT_Fixed/TotalMonth,
         Patronage_Fixed=Patronage_Fixed/TotalMonth,
         Revenue_Fixed=Revenue_Fixed/TotalMonth,
         TotalTrips_Booking=TotalTrips_Booking/TotalMonth,
         TripsNoPax_Booking=TripsNoPax_Booking/TotalMonth,
         VKT_Booking=VKT_Booking/TotalMonth,
         Patronage_Booking=Patronage_Booking/TotalMonth,
         Revenue_Booking=Revenue_Booking/TotalMonth,
         MonthlyTrips=TotalTrips_Fixed+TotalTrips_Booking,
         MonthlyPatronage=Patronage_Fixed+Patronage_Booking,
         MonthlyVKT=VKT_Fixed+VKT_Booking,
         Util_Rate=1-(TripsNoPax_Fixed+TripsNoPax_Booking)/(TotalTrips_Fixed+TotalTrips_Booking))%>%
  left_join(TDX_County[, c("CityCode","Operator")], by=c("COUNTYNAME"="Operator"))%>%
  mutate(OpeType=paste(unlist(OpeType), collapse="|"))%>%
  group_by(COUNTYNAME)%>%
  mutate(RouteID=paste0(CityCode, "_", str_pad(c(1:n()), 2, "left", 0)))%>%
  left_join(st_drop_geometry(drt_shape_buf_feature))%>%
  left_join(drt_shape_intention)%>%
  select(-ShapeID, -CityCode, -AllPeriod)


# Attach the operational cost (cost per kilometre)
drt_cost=read.csv("E:/On-demand Transport Service/Analysis/Data/DRTS/Operational Data/Operational Cost.csv")
drt_cost_bus=filter(drt_cost, Service=="Bus") %>% select(-Service)
drt_cost_taxi=filter(drt_cost, Service=="Taxi") %>% select(-Service, -TOWNNAME)

temp_bus=filter(model_data, OperatorType!="Taxi Operator")%>%
  left_join(select(drt_shape_buf_feature, COUNTYNAME, RouteName, SubRouteName))%>%
  st_sf()%>%
  st_intersection(st_transform(TWspdata::taiwan_town, crs=3826)[, c("COUNTYNAME","TOWNNAME")] %>% rename(COUNTYNAME_temp=COUNTYNAME))%>%
  mutate(AREA=as.numeric(st_area(.)))%>%
  st_drop_geometry()%>%
  group_by(RouteID)%>%
  slice(which.max(AREA))%>%
  select(RouteID, COUNTYNAME_temp, TOWNNAME)%>%
  rename(COUNTYNAME=COUNTYNAME_temp)%>%
  left_join(drt_cost_bus)
temp=filter(temp_bus, is.na(KMCost))%>%
  select(-KMCost)%>%
  left_join(st_transform(TWspdata::taiwan_town, crs=3826)[, c("COUNTYNAME","TOWNNAME")])%>%
  st_sf()%>%
  st_centroid()
temp_id=st_nearest_feature(temp, left_join(drt_cost_bus, st_transform(TWspdata::taiwan_town, crs=3826)[, c("COUNTYNAME","TOWNNAME")])%>%
                     st_sf()%>%
                     st_centroid())
temp_bus$KMCost[is.na(temp_bus$KMCost)]=drt_cost_bus$KMCost[temp_id]


temp_taxi=filter(model_data, OperatorType=="Taxi Operator")%>%
  left_join(select(drt_shape_buf_feature, COUNTYNAME, RouteName, SubRouteName))%>%
  st_sf()%>%
  st_intersection(TWspdata::tw_county_main[, c("COUNTYNAME")] %>% rename(COUNTYNAME_temp=COUNTYNAME))%>%
  mutate(AREA=as.numeric(st_area(.)))%>%
  st_drop_geometry()%>%
  group_by(RouteID)%>%
  slice(which.max(AREA))%>%
  select(RouteID, COUNTYNAME_temp)%>%
  rename(COUNTYNAME=COUNTYNAME_temp)%>%
  left_join(drt_cost_taxi)
temp=filter(temp_taxi, is.na(KMCost))%>%
  select(-KMCost)%>%
  left_join(TWspdata::tw_county_main[, c("COUNTYNAME")])%>%
  st_sf()%>%
  st_centroid()
temp_id=st_nearest_feature(temp, left_join(drt_cost_taxi, TWspdata::tw_county_main[, c("COUNTYNAME")])%>%
                             st_sf()%>%
                             st_centroid())
temp_taxi$KMCost[is.na(temp_taxi$KMCost)]=drt_cost_taxi$KMCost[temp_id]

temp=rbind(temp_bus, temp_taxi)%>%
  select(RouteID, KMCost)
model_data=left_join(model_data, temp)
# model_data$RouteID[is.na(model_data$KMCost)]

model_data=select(model_data, c("RouteID", names(model_data)[names(model_data)!="RouteID"]))


min_max_norm=function(x){
  (x-min(x))/(max(x)-min(x))
}

for(i in names(model_data)[which(names(model_data)=="Population"):which(names(model_data)=="TourismComment")]){
  model_data[[paste0(i, "_NM")]]=min_max_norm(model_data[[i]])
}

# write.csv(model_data, "Data/Model Data.csv", row.names=F)

names(model_data)[grepl("SI", names(model_data))]
names(model_data)[which(names(model_data)=="Population"):which(names(model_data)=="TourismComment")]

cor(model_data[, grepl("SI", names(model_data))])


temp=left_join(model_data, ope_data_sum_route[, c("COUNTYNAME","RouteName","SubRouteName")])%>%
  st_sf()
names(temp)
var_name=paste0("TourismComment")
png(paste0("figure/Feature/DRT Operational Map (", var_name, ").png"), width=642*2, height=578*2, res=200)
ggplot()+
  geom_sf(data=st_transform(TWspdata::taiwan_county, crs=3826), color="#F0F0F0", fill="#9D9D9D")+
  geom_sf(data=temp, aes(fill=!!sym(var_name), color=!!sym(var_name)))+
  scale_color_distiller(palette="YlOrRd", direction=1)+
  scale_fill_distiller(palette="YlOrRd", direction=1)+
  coord_sf(xlim=c(area_box[1], area_box[3]),
           ylim=c(area_box[2], area_box[4]))+
  theme_void()+
  theme(legend.title=element_blank(),
        legend.text=element_text(family="A", size=12),
        legend.position=c(0.1,0.5),
        legend.justification="top")
dev.off()






# ################################## #
#### Efficiency Result ####
# ################################## #

meta_ddf=read.csv("MetaDDF.csv")%>%
  mutate(ClusterName=ifelse(ClusterName=="FR", "FFFR", ClusterName))%>%
  rename(RouteID=DMU)
meta_ddf=left_join(model_data, ope_data_sum_route[, c("COUNTYNAME","RouteName","SubRouteName")])%>%
  st_sf()%>%
  left_join(meta_ddf)%>%
  mutate(ClusterName=factor(ClusterName, levels=c("FFFR","FFR","P2P")))
temp=group_by(st_drop_geometry(meta_ddf), ClusterName)%>%
  summarise(Count=n())%>%
  arrange(ClusterName)%>%
  mutate(ClusterNameLab=paste0(ClusterName, " (#:", Count, ")"),
         ClusterNameLab=factor(ClusterNameLab, levels=ClusterNameLab))%>%
  select(-Count)
meta_ddf=left_join(meta_ddf, temp)


range(meta_ddf$GroupEff)
area_box=st_bbox(meta_ddf)
png(paste0("figure/DRT Efficiency (Group).png"), width=642*2, height=578*2, res=200)
# png(paste0("E:/On-demand Transport Service/Paper/Plots/DRT Efficiency (Group).png"), width=642*2, height=578*2, res=200)
ggplot()+
  geom_sf(data=st_transform(TWspdata::taiwan_county, crs=3826), color="#F0F0F0", fill="#9D9D9D")+
  geom_sf(data=filter(meta_ddf, ServiceType=="Point-to-Point"), aes(fill=GroupEff), color=NA)+
  scale_fill_distiller(palette="Blues", direction=1, limits=c(0.6,1), breaks=seq(0.6,1,0.1), name="P2P", guide=guide_colorbar(order=3))+
  geom_sf(data=filter(meta_ddf, ServiceType=="Fixed-Route"), aes(color=GroupEff))+
  scale_color_distiller(palette="Reds", direction=1, limits=c(0.6,1), breaks=seq(0.6,1,0.1), name="FFFR", guide=guide_colorbar(order=1))+
  ggnewscale::new_scale_color()+
  geom_sf(data=filter(meta_ddf, ServiceType=="Flexible Fixed-Route"), aes(color=GroupEff))+
  scale_color_distiller(palette="Greens", direction=1, limits=c(0.6,1), breaks=seq(0.6,1,0.1), name="FFR", guide=guide_colorbar(order=2))+
  coord_sf(xlim=c(area_box[1], area_box[3]),
           ylim=c(area_box[2], area_box[4]))+
  theme_void()+
  theme(legend.title=element_text(family="A", size=15, face="bold"),
        legend.text=element_text(family="A", size=12),
        legend.position=c(0.08,0.08),
        legend.justification="bottom",
        legend.box="horizontal")
dev.off()


png(paste0("figure/DRT Efficiency (Meta).png"), width=642*2, height=578*2, res=200)
# png(paste0("E:/On-demand Transport Service/Paper/Plots/DRT Efficiency (Meta).png"), width=642*2, height=578*2, res=200)
ggplot()+
  geom_sf(data=st_transform(TWspdata::taiwan_county, crs=3826), color="#F0F0F0", fill="#9D9D9D")+
  geom_sf(data=meta_ddf, aes(color=MetaEff, fill=MetaEff))+
  scale_color_distiller(palette="YlOrRd", direction=1, name="Efficiency")+
  scale_fill_distiller(palette="YlOrRd", direction=1, name="Efficiency")+
  coord_sf(xlim=c(area_box[1], area_box[3]),
           ylim=c(area_box[2], area_box[4]))+
  theme_void()+
  theme(legend.title=element_text(family="A", size=15, face="bold"),
        legend.text=element_text(family="A", size=12),
        legend.position=c(0.08,0.08),
        legend.justification="bottom",
        legend.box="horizontal")
dev.off()



png("figure/Meta Analysis DDF.png", width=956*2, height=620*2, res=200)
# png("E:/On-demand Transport Service/Paper/Plots/Meta Analysis DDF (Taiwan).png", width=956*2, height=620*2, res=200)
ggplot()+
  geom_abline(slope=1, linetype="dashed", color="#6C6C6C", linewidth=0.5)+
  geom_abline(slope=0.9, linetype="dashed", color="#6C6C6C", linewidth=0.5)+
  geom_abline(slope=0.8, linetype="dashed", color="#6C6C6C", linewidth=0.5)+
  geom_point(data=arrange(meta_ddf, ClusterNameLab), aes(x=GroupEff, y=MetaEff, color=ClusterNameLab, shape=ClusterNameLab), size=2)+
  # geom_jitter(data=arrange(meta_ddf, ClusterNameLab), aes(x=GroupEff, y=MetaEff, color=ClusterNameLab, shape=ClusterNameLab), size=2, width=0.005, height=0.005)+
  geom_text(aes(x=0.75, y=0.75*1, label="TGR=1.0"), color="#4F4F4F", size=4.5, family="C", angle=28, fontface="bold")+
  geom_text(aes(x=0.75, y=0.75*0.9, label="TGR=0.9"), color="#4F4F4F", size=4.5, family="C", angle=26, fontface="bold")+
  geom_text(aes(x=0.75, y=0.75*0.8, label="TGR=0.8"), color="#4F4F4F", size=4.5, family="C", angle=24, fontface="bold")+
  scale_color_manual(values=paletteer::paletteer_d("RColorBrewer::Set1")[c(1,3,2)], name="Operational Model")+
  scale_shape_discrete(name="Operational Model")+
  scale_x_continuous(breaks=seq(0,1,0.05), limits=c(0.54,1), expand=c(0.02,0,0.02,0))+
  scale_y_continuous(breaks=seq(0,1,0.05), limits=c(0.54,1), expand=c(0.02,0,0.02,0))+
  theme_bw()+
  xlab("Group Efficiency") + ylab("Meta Efficiency") +
  theme(axis.title=element_text(family="A", size=16),
        axis.text=element_text(family="A", size=13),
        legend.box=c("horizontal"),
        legend.title=element_text(family="A", size=16, face="bold"),
        legend.text=element_text(family="A", size=14),
        legend.key=element_blank(),
        legend.position=c(0.02,0.88),
        legend.justification="left",
        legend.background=element_rect(fill=NA))
dev.off()




# ################################## #
#### Tobit Model ####
# ################################## #

meta_ddf_socio=st_drop_geometry(meta_ddf)%>%
  left_join(cbind(st_drop_geometry(drt_shape_buf_feature)[, c("COUNTYNAME","SubRouteName")], AREA=as.numeric(st_area(drt_shape_buf_feature))/1000000))%>%
  mutate(KidsTeen_per=KidsTeen/Population,
         Elderly_per=Elderly/Population,
         PopDensity=Population/AREA,
         DayworkPopDensity=DayworkPop/AREA/1000)

meta_ddf_socio=left_join(meta_ddf_socio, mutate(meta_ddf_socio, OperatorType=paste0("Operator_", gsub("Operator| ", "", OperatorType)))%>%
                           reshape2::dcast(COUNTYNAME+OpeName~OperatorType, function(x) as.numeric(length(x)!=0)))



##### Exogenous Features ######

###### Bus Trips ######
temp=fread("F:/TPASS/Analysis/Data/Bus/TDX/2023/Bus Route.csv")%>%
  filter(BusRouteType==13)
bus_stop=readRDS("E:/On-demand Transport Service/Analysis/Data/TWData/PT Info.rds")$BusStop%>%
  st_as_sf(coords=c("X","Y"), crs=3826)%>%
  mutate(CityCode=substr(RouteUID, 1, 3))%>%
  left_join(TDX_County[, c("Operator","CityCode")])%>%
  rename(COUNTYNAME=Operator)%>%
  filter(!RouteUID %in% temp$RouteUID,
         !(RouteName %in% c(106,107,108,"竹62","竹60","竹120") & CityCode=="HSQ"))

drt_route_name=reshape2::melt(drt_route, id.vars=c("COUNTYNAME"), value.name="RouteName")%>%
  filter(grepl("RouteName", variable))%>%
  select(-variable)%>%
  distinct()
temp=intersect(st_drop_geometry(bus_stop)[, c("COUNTYNAME","RouteName")], drt_route_name)%>%
  mutate(TEMPID=paste0(COUNTYNAME, "_", RouteName))
bus_stop=bus_stop[!paste0(bus_stop$COUNTYNAME, "_", bus_stop$RouteName) %in% temp$TEMPID,]

for(i in c("NewTaipei","Tainan")){
  url=paste0("https://tdx.transportdata.tw/api/basic/v3/Bus/DRTS/Route/City/", i, "?%24format=JSON")
  x=GET(url, add_headers(Accept="application/+json", Authorization=paste("Bearer", access_token)))
  temp=fromJSON(content(x, as="text"))
  
  bus_stop=bus_stop[!bus_stop$RouteUID %in% paste0(TDX_County$CityCode[i==TDX_County$Code], temp$Routes$RouteID),]
}

bus_schedule=fread("E:/On-demand Transport Service/Analysis/Data/TWData/TransportSchedule/Bus Schedule.csv")
temp1=filter(bus_schedule, !is.na(ArrivalTime), Wednesday==1)%>%
  group_by(RouteUID, SubRouteUID, Direction)%>%
  summarise(Trips=n())
temp2=filter(bus_schedule, is.na(ArrivalTime), Wednesday==1)%>%
  mutate(Duration=as.numeric(substr(EndTime, 1, 2))*60+as.numeric(substr(EndTime, 4, 5))-(as.numeric(substr(StartTime, 1, 2))*60+as.numeric(substr(StartTime, 4, 5))),
         Duration=ifelse(Duration<0, Duration+1440, Duration),
         Trips=round(Duration/((MinHeadwayMins+MaxHeadwayMins)/2), 0))%>%
  group_by(RouteUID, SubRouteUID, Direction)%>%
  summarise(Trips=sum(Trips))
bus_schedule_trips=rbind(temp1, temp2)%>%
  group_by(RouteUID, SubRouteUID, Direction)%>%
  summarise(Trips=sum(Trips))
rm(temp1, temp2)

temp_id=st_intersects(drt_shape_buf_feature, bus_stop)
temp=cbind(st_drop_geometry(drt_shape_buf_feature)[rep(1:nrow(drt_shape_buf_feature), lengths(temp_id)), c("COUNTYNAME","RouteName","SubRouteName")],
           SubRouteUID=bus_stop$SubRouteUID[unlist(temp_id)],
           RouteUID=bus_stop$RouteUID[unlist(temp_id)],
           Direction=bus_stop$Direction[unlist(temp_id)])%>%
  distinct()%>%
  left_join(bus_schedule_trips)%>%
  mutate(Trips=ifelse(is.na(Trips), 0, Trips))%>%
  group_by(COUNTYNAME, RouteName, SubRouteName)%>%
  summarise(BusTrips=sum(Trips),
            NumBusRoute=length(unique(RouteUID)))

meta_ddf_socio=left_join(meta_ddf_socio, temp)%>%
  mutate(BusTrips=ifelse(is.na(BusTrips), 0, BusTrips),
         NumBusRoute=ifelse(is.na(NumBusRoute), 0, NumBusRoute))


# 與其他公共運輸涵蓋之比例
fr_buf=cbind(st_drop_geometry(drt_shape_buf_feature)[rep(1:nrow(drt_shape_buf_feature), lengths(temp_id)), c("COUNTYNAME","RouteName","SubRouteName")],
      bus_stop[unlist(temp_id), c("RouteUID","SubRouteUID","Direction","StopUID")])%>%
  st_sf()%>%
  st_buffer(500)%>%
  group_by(COUNTYNAME, RouteName, SubRouteName)%>%
  summarise()
temp=inner_join(data.frame(fr_buf), data.frame(cbind(drt_shape_buf_feature, AREA=as.numeric(st_area(drt_shape_buf_feature))/1000000)),
                by=c("COUNTYNAME","RouteName","SubRouteName"))%>%
  group_by(COUNTYNAME, RouteName, SubRouteName, AREA)%>%
  mutate(geometry=st_union(st_intersection(geometry.x, geometry.y)),
         AREA_inter=as.numeric(st_area(geometry))/1000000,
         PTOverlap_per=AREA_inter/AREA)%>%
  ungroup()%>%
  select(COUNTYNAME, RouteName, SubRouteName, PTOverlap_per)

meta_ddf_socio=left_join(meta_ddf_socio, temp)%>%
  mutate(PTOverlap_per=ifelse(is.na(PTOverlap_per), 0, PTOverlap_per))



unique(meta_ddf_socio$ClusterName)
names(meta_ddf_socio)

tobit_mod_FR=tobit(GroupEff ~ SI_Education+SI_Elderly+SI_Indigenous+SI_Medicare+SI_Tourism+PTOverlap_per+Elderly_per+DayworkPopDensity+Operator_Bus+Operator_Taxi+Operator_NGO, data=filter(meta_ddf_socio, ClusterName=="FR"), left=0, right=1)

fralog_mod_FR=glm(GroupEff ~ Indigenous+SI_Education+SI_Elderly+SI_Indigenous+SI_Medicare+SI_Tourism+SI_LocalCentre+PTOverlap_per+Elderly_per+DayworkPopDensity+Operator_Bus+Operator_Taxi+Operator_NGO+Operator_CityCouncil,
                  family=quasibinomial(link = "logit"), data=filter(meta_ddf_socio, ClusterName=="FR"))
summary(fralog_mod_FR)

tobit_mod_FFR=tobit(GroupEff ~ SI_Education+SI_Elderly+SI_Indigenous+SI_Medicare+SI_Tourism+PTOverlap_per+Elderly_per+DayworkPopDensity+Operator_Bus+Operator_Taxi+Operator_NGO+Deviation_Reservation+Hail, data=filter(meta_ddf_socio, ClusterName=="FFR"), left=0, right=1)
summary(tobit_mod_FFR)

fralog_mod_FR=glm(GroupEff ~ Indigenous+SI_Education+SI_Elderly+SI_Indigenous+SI_Medicare+SI_Tourism+SI_LocalCentre+PTOverlap_per+Elderly_per+DayworkPopDensity+Operator_Bus+Operator_Taxi+Operator_NGO+Operator_CityCouncil+Deviation_Reservation+Hail,
                  family=quasibinomial(link = "logit"), data=filter(meta_ddf_socio, ClusterName=="FFR"))
summary(fralog_mod_FR)


# tobit_mod_P2P=tobit(GroupEff ~ SI_Medicare+PTOverlap_per+Elderly_per+DayworkPopDensity, data=filter(meta_ddf_socio, ClusterName=="P2P"), left=0, right=1)
tobit_mod_meta=tobit(MetaEff ~ SI_Education+SI_Elderly+SI_Indigenous+SI_Medicare+SI_Tourism+PTOverlap_per+Elderly_per+DayworkPopDensity+Operator_Bus+Operator_Taxi+Operator_NGO+P2P+Deviation_Reservation+Hail, data=meta_ddf_socio, left=0, right=1)


fralog_mod_meta=glm(MetaEff ~ Indigenous+SI_Education+SI_Elderly+SI_Indigenous+SI_Medicare+SI_Tourism+SI_LocalCentre+PTOverlap_per+Elderly_per+DayworkPopDensity+Operator_Bus+Operator_Taxi+Operator_NGO+Operator_CityCouncil+P2P+Deviation_Reservation+Hail,
                  family=quasibinomial(link = "logit"), data=meta_ddf_socio)
summary(fralog_mod_meta)

model_conv=function(x){
  temp=summary(x)
  data.frame(Var=names(temp$coefficients[,1]),
             Coefficient=temp$coefficients[,1],
             SE=temp$coefficients[,2],
             Zvalue=temp$coefficients[,3],
             Pvalue=temp$coefficients[,4])
}


tobit_mod=full_join(rename_all(model_conv(tobit_mod_FR), function(x) ifelse(x=="Var", "Var", paste0("FR_", x))),
          rename_all(model_conv(tobit_mod_FFR), function(x) ifelse(x=="Var", "Var", paste0("FFR_", x))))%>%
  # full_join(rename_all(model_conv(tobit_mod_P2P), function(x) ifelse(x=="Var", "Var", paste0("P2P_", x))))%>%
  full_join(rename_all(model_conv(tobit_mod_meta), function(x) ifelse(x=="Var", "Var", paste0("Meta_", x))))

tobit_mod=cbind(Var=tobit_mod$Var, format(round(tobit_mod[, !grepl("Var", names(tobit_mod))], 3), nsmall=3))
write.csv(tobit_mod, "temp.csv", row.names=F)


length(tobit_mod_meta$y)
tobit_mod_meta$loglik
logLik(tobit_mod_meta)
AIC(tobit_mod_meta)

tobit_mod_meta$scale



# ################################## #
#### Descriptive Analysis ####
# ################################## #
county_name=st_drop_geometry(TWspdata::taiwan_county)%>%
  select(COUNTYNAME, COUNTYENG)%>%
  mutate(District=case_when(
    COUNTYNAME %in% c("臺北市","新北市","基隆市","桃園市","新竹縣","新竹市","宜蘭縣") ~ "Northern",
    COUNTYNAME %in% c("苗栗縣","臺中市","彰化縣","南投縣","雲林縣") ~ "Central",
    COUNTYNAME %in% c("嘉義縣","嘉義市","臺南市","高雄市","屏東縣") ~ "Southern",
    COUNTYNAME %in% c("花蓮縣","臺東縣") ~ "Eastern",
    COUNTYNAME %in% c("連江縣","澎湖縣","金門縣") ~ "Offshore Island"
  ),
  District=factor(District, levels=c("Northern","Central","Southern","Eastern","Offshore Island")))

# meta_county=left_join(meta_ddf_socio, temp)%>%
#   mutate(Type=ifelse(MetaEff==1, "Efficient", "Inefficient"),
#          COUNTYNAME=factor(COUNTYNAME, levels=TDX::TDX_County$Operator[1:22]))%>%
#   group_by(District, Type)%>%
#   summarise(Count=n())%>%
#   mutate(Count_per=Count/sum(Count))%>%
#   reshape2::dcast(District~Type,  value.var="Count_per", fill=0)%>%
#   reshape2::melt(id.vars=c("District"))

meta_county=left_join(meta_ddf_socio, county_name)%>%
  mutate(PerfType=ifelse(MetaEff!=1, "Low-performing", "High-performing"),
         PerfType=factor(PerfType, levels=c("High-performing","Low-performing")),
         COUNTYNAME=factor(COUNTYNAME, levels=TDX::TDX_County$Operator[1:22]))%>%
  arrange(COUNTYNAME)%>%
  mutate(COUNTYENG=factor(COUNTYENG, levels=unique(COUNTYENG)))%>%
  group_by(COUNTYENG, District, PerfType)%>%
  summarise(Count=n())%>%
  reshape2::dcast(COUNTYENG+District~PerfType,  value.var="Count", fill=0)%>%
  mutate(High_per=`High-performing`/(`High-performing`+`Low-performing`)*100,
         SampleNum=(`High-performing`+`Low-performing`))

meta_ddf_sta=left_join(meta_ddf_socio, county_name)%>%
  group_by(District)%>%
  summarise(MetaEff_mean=mean(MetaEff), MetaEff_sd=sd(MetaEff), samples=n())

meta_county=left_join(meta_county, meta_ddf_sta[, c("District","samples")])%>%
  mutate(District_samples=paste0(District, "  (n=", samples, ")"))
# mutate(District_samples=paste0(District, "  <SPAN STYLE='font-size:10.0pt'>(n=", samples, ")</SPAN>"))
meta_county_long=reshape2::melt(meta_county, id.vars=c("COUNTYENG","District"), measure.vars=c("High-performing","Low-performing"))

plot_list=list()
for(i in c(levels(meta_county$District))){
  temp=left_join(meta_ddf_socio, county_name)%>%
    mutate(COUNTYNAME=factor(COUNTYNAME, levels=TDX::TDX_County$Operator[1:22]))%>%
    arrange(COUNTYNAME)%>%
    mutate(COUNTYENG=factor(COUNTYENG, levels=unique(COUNTYENG)))%>%
    filter(District==i)%>%
    left_join(distinct(meta_county[, c("District","District_samples")]))
  
  temp_plot=ggplot()+
    geom_boxplot(data=temp, aes(x=MetaEff))+
    geom_text(data=data.frame(District=temp$District_samples[1], MetaEff_mean=mean(temp$MetaEff), MetaEff_sd=sd(temp$MetaEff)),
              aes(x=0.45, y=0.3, label=paste0("Ave: ", format(round(MetaEff_mean, 3), 3), "\nSD:  ", format(round(MetaEff_sd, 3), 3))), hjust=0, vjust=0.8, family="A", size=3, fontface="bold", color="#4F4F4F")+
    scale_x_continuous(breaks=seq(0.4,1,0.1), limits=c(0.45,1))+
    facet_wrap(~District_samples, ncol=1)+
    theme_bw()
  
  if(i=="Offshore Island"){
    plot_list[[i]]=temp_plot+xlab("Meta Efficiency Score")+
      theme(axis.title.x=element_text(family="A", size=15, face="bold"),
            axis.title.y=element_blank(),
            axis.text.x=element_text(family="A", size=12),
            axis.text.y=element_blank(),
            axis.ticks=element_blank(),
            strip.text=ggtext::element_markdown(family="A", size=12, face="bold"))
  }else{
    plot_list[[i]]=temp_plot+theme(axis.title=element_blank(),
                              axis.text=element_blank(),
                              axis.ticks=element_blank(),
                              strip.text=element_text(family="A", size=12, face="bold"))
  }
}


png("figure/Meta Analysis Performance Level Statistics by County.png", width=740*2, height=650*2, res=200)
# png("E:/On-demand Transport Service/Paper/Plots/Meta Analysis Performance Level Statistics by County.png", width=1040*2, height=650*2, res=200)
p1=ggplot()+
  geom_col(data=meta_county_long, aes(x=value, y=interaction(COUNTYENG, District), fill=variable))+
  scale_fill_manual(values=c("#D73027","#4575B4"), name="Performance Level")+
  geom_text(data=meta_county, aes(x=SampleNum+0.3, y=interaction(COUNTYENG, District), label=paste0(format(round(High_per, 1), nsmall=1), "%")), color="#D73027", size=3, family="A", hjust=0, fontface="bold")+
  scale_x_continuous(breaks=seq(0,100,10), expand=c(0,0,0,11))+
  scale_y_discrete(guide=guide_axis_nested(), limits=rev, expand=c(0,0,0,0))+
  xlab("# of DRT Services") + ylab("District/County")+
  theme_bw()+
  theme(axis.title=element_text(family="A", size=15, face="bold"),
        axis.text=ggtext::element_markdown(family="A", size=12),
        legend.title=element_text(family="A", size=15, face="bold", hjust=0.5),
        legend.text=element_text(family="A", size=12),
        legend.position="top",
        legend.direction="horizontal",
        legend.title.position="top",
        legend.box.margin=margin(b=-10),
        plot.margin = margin(5, 55, 5, 5))+
  guides(fill=guide_legend(reverse=T))
cowplot::plot_grid(p1,
                   cowplot::plot_grid(ggplot()+theme_void(), cowplot::plot_grid(plotlist=plot_list, ncol=1), ncol=1, rel_heights=c(0.095,0.905)),
                   ncol=2, rel_widths=c(0.7,0.3))
dev.off()




group_by(meta_ddf_socio, ServiceType)%>%
  summarise(Count=n(),
            across(c(MetaEff, GroupEff, TGR), list(mean=mean, sd=sd), .names = "{.fn}.{.col}"),
            MetaEff_per=mean(MetaEff==1),
            GroupEff_per=mean(GroupEff==1))%>%
  mutate(Count_per=Count/sum(Count))%>%
  write.csv("temp.csv", row.names=F)



write.csv(psych::describe(meta_ddf_socio), "temp.csv")
mean(filter(meta_ddf_socio, ClusterName=="P2P")$GroupEff!=1)

table(filter(meta_ddf_socio, ServiceType=="Flexible Fixed-Route")$OperatorType)
filter(meta_ddf_socio, ServiceType=="Flexible Fixed-Route")%>%
  reshape2::melt(id.vars="RouteID", measure.vars=c("Deviation_Reservation","Booking","Hail"), variable.name="Type")%>%
  filter(value==1)%>%
  group_by(Type)%>%
  summarise(Count=n())%>%
  mutate(Count_per=Count/nrow(filter(meta_ddf_socio, ServiceType=="Flexible Fixed-Route")))




temp=filter(ungroup(ope_data), COUNTYNAME=="宜蘭縣", OpeName=="黃1")%>%
  mutate(Total_Patro=Patronage_Fixed+Patronage_Booking,
         Type="Yilan case patronage")%>%
  select(Year, Month, Type, Total_Patro)%>%
  rbind(filter(ope_data, Year>=2022, !(Year==2024 & Month>5))%>%
          mutate(Total_Patro=Patronage_Fixed+Patronage_Booking)%>%
          group_by(Year, Month)%>%
          summarise(Total_Patro=mean(Total_Patro))%>%
          mutate(Type="Average patronage nationwide")%>%
          select(Year, Month, Type, Total_Patro))%>%
  mutate(Type=factor(Type, levels=c("Yilan case patronage","Average patronage nationwide")))

png("figure/Monthly Patronage (Yilan case study).png", width=1000*2, height=510*2, res=200)
ggplot()+
  geom_point(data=temp, aes(x=interaction(Month, Year), y=Total_Patro, color=Type))+
  geom_line(data=temp, aes(x=interaction(Month, Year), y=Total_Patro, group=Type, color=Type))+
  guides(x=guide_axis_nested(delim="."))+
  scale_color_brewer(palette="Set1")+
  scale_y_continuous(breaks=seq(0,1000,100))+
  ylab("Monthly Patronage")+
  theme_bw()+
  theme(axis.title.x=element_blank(),
        axis.title.y=element_text(family="A", face="bold", size=15),
        axis.text=element_text(family="A", size=13),
        legend.title=element_blank(),
        legend.text=element_text(family="A", size=13),
        legend.background=element_blank(),
        legend.justification="left",
        legend.position=c(0.02,0.91))
dev.off()

mean(filter(temp, grepl("Yilan", Type))$Total_Patro)
mean(filter(temp, !grepl("Yilan", Type))$Total_Patro)


st_drop_geometry(meta_ddf)%>%
  as.data.frame()%>%
  xlsx::write.xlsx("Result.xlsx", row.names=F)

temp=xlsx::read.xlsx("Result.xlsx", sheetIndex=1)%>%
  arrange(MetaEff)%>%
  mutate(RouteID=factor(RouteID, levels=RouteID))
tt=filter(temp, grepl("黃1", RouteName), COUNTYNAME=="宜蘭縣")

png("figure/Performance score distribution (Yilan case study).png", width=800*2, height=800*2, res=200)
ggplot()+
  geom_col(data=temp, aes(x=MetaEff, y=RouteID), fill="#BEBEBE")+
  geom_col(data=filter(temp, MetaEff==1), aes(x=MetaEff, y=RouteID), fill="#8E8E8E")+
  geom_text(data=filter(temp, MetaEff==1) %>% slice(n()/2), aes(x=MetaEff/2, y=RouteID, label="Efficient DRT Cases"), color="#003D79", family="A", fontface="bold", size=10)+
  geom_col(data=tt, aes(x=MetaEff, y=RouteID), fill="red", width=2)+
  geom_text(data=tt, aes(x=MetaEff+0.06, y=RouteID, label=paste0(RouteID, "\n(", round(MetaEff, 2), ")")), color="#930000", size=4, family="A", fontface="bold")+
  scale_x_continuous(breaks=seq(0,1,0.1), expand=c(0,0,0.02,0.02))+
  xlab("Meta Efficiency") + ylab("Route (Total #: 442)")+
  theme_bw()+
  theme(axis.text.y=element_blank(),
        axis.ticks.y=element_blank(),
        axis.title=element_text(family="A", face="bold", size=15),
        axis.text=element_text(family="A", size=13),
        panel.grid=element_blank())
dev.off()


  
  
  
  
  