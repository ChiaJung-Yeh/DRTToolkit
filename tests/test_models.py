import unittest
import tempfile
from pathlib import Path
import numpy as np
import pandas as pd
from drt_toolkit.evaluation import evaluate, solve_ddf
from drt_toolkit.simulation import Network, generate_requests, simulate
from drt_toolkit.pipeline import bridge, run_stage


class ModelTests(unittest.TestCase):
    def test_known_vrs_solution(self):
        # A=(x=2,y=1), B=(x=1,y=2). At A, beta<=0.5 from input.
        X=np.array([[2.],[1.]])
        Y=np.array([[1.],[2.]])
        b, w, residual=solve_ddf(X,Y,np.ones_like(Y),0,np.array([0,1]))
        self.assertAlmostEqual(b,.5)
        self.assertAlmostEqual(sum(w),1)
        self.assertLess(residual,1e-7)
        self.assertAlmostEqual(solve_ddf(X,Y,np.ones_like(Y),1,np.array([0,1]))[0],0)

    def test_group_and_meta(self):
        d=pd.DataFrame(dict(ServiceID=['A','B'],ServiceType=['Fixed-Route','Point-to-Point'],
            FleetNum=[2,1],MonthlyTrips=[2,1],MonthlyVKT=[2,1],KMCost=[2,1],
            MonthlyPatronage=[1,2],Util_Rate=[.5,1],SI_Elderly=[1,1],Elderly=[1,2]))
        m=pd.DataFrame(dict(ServiceIntention=['SI_Elderly'],Elderly=[1]))
        spec=dict(inputs=['FleetNum','MonthlyTrips','MonthlyVKT','KMCost'],outputs=['MonthlyPatronage','Util_Rate'])
        scores,_=evaluate(d,m,spec)
        self.assertAlmostEqual(scores.iloc[0].MetaEff,.5)
        self.assertTrue((scores.MetaEff<=scores.GroupEff+1e-7).all())
        self.assertTrue((scores.GroupEff==1).all())
        d.loc[0,'SI_Elderly']=0
        with self.assertRaises(ValueError):evaluate(d,m,spec)

    def fixture(self):
        edges=pd.DataFrame([dict(from_node=str(i),to_node=str(j),travel_time_s=100*abs(i-j),distance_km=abs(i-j)) for i in range(3) for j in range(3) if i!=j])
        settings=dict(fleet_size=1,capacity=1,depot_node='0',dwell_s=0,max_wait_s=500,
            max_ride_factor=1,max_ride_extra_s=0,alpha=1.5,beta=3)
        return Network(edges),settings

    def test_conservation_capacity_and_in_transit_lock(self):
        net,spec=self.fixture()
        r=pd.DataFrame([dict(request_id=0,request_time_s=0,origin='1',destination='2'),
                        dict(request_id=1,request_time_s=50,origin='0',destination='2')])
        p,v,stats=simulate(r,net,spec)
        self.assertEqual(stats['requests'],stats['served']+stats['rejected'])
        self.assertEqual(stats['served'],2)
        self.assertEqual(p.iloc[0].pickup_s,100) # cannot reroute first locked leg
        self.assertEqual(p.iloc[0].dropoff_s,200)
        self.assertEqual(p.iloc[1].pickup_s,400)
        self.assertEqual(p.iloc[1].dropoff_s,600)
        self.assertEqual(v.iloc[0].max_onboard,1)
        self.assertEqual(stats['vkt_km'],6)
        self.assertEqual(stats['empty_vkt_km'],3)

    def test_wait_rejection_and_zero_requests(self):
        net,spec=self.fixture();spec['max_wait_s']=1
        r=pd.DataFrame([dict(request_id=0,request_time_s=0,origin='1',destination='2')])
        p,v,stats=simulate(r,net,spec)
        self.assertEqual(stats['rejected'],1)
        self.assertEqual(stats['vkt_km'],0)
        p,v,stats=simulate(r.iloc[0:0],net,spec)
        self.assertEqual(stats['requests'],0)

    def test_seeded_request_generation(self):
        od=pd.DataFrame([dict(Hour=7,GridID_O='A',GridID_D='B',PredTrips=20)])
        grid=pd.DataFrame(dict(GridID=['A','B'],node_id=['0','1']))
        a=generate_requests(od,grid,14);b=generate_requests(od,grid,14)
        pd.testing.assert_frame_equal(a,b)
        self.assertTrue(a.request_time_s.between(7*3600,8*3600).all())

    def test_directed_disconnected_network(self):
        edges=pd.DataFrame([dict(from_node='a',to_node='b',travel_time_s=1,distance_km=1)])
        net=Network(edges)
        with self.assertRaises(ValueError):net.route('b','a')

    def test_bridge_requires_comparability_review(self):
        with self.assertRaises(ValueError):
            bridge({'bridge':{'comparable_trip_definition_confirmed':False}},pd.DataFrame())

    def test_fastest_path_distance_is_not_independent_shortest_distance(self):
        edges=pd.DataFrame([dict(from_node='a',to_node='b',travel_time_s=1,distance_km=10),
                            dict(from_node='a',to_node='c',travel_time_s=2,distance_km=1),
                            dict(from_node='c',to_node='b',travel_time_s=2,distance_km=1)])
        net=Network(edges)
        self.assertEqual(net.route('a','b'),(1.,10.))

    def test_packaged_case_scope_and_explanatory_match(self):
        root=Path(__file__).resolve().parents[1]
        historical=pd.read_csv(root/'data/evaluation/Model Data.csv')
        socio=pd.read_csv(root/'data/tobit/tobit_socio.csv')
        allowed={'Tainan City','Kaohsiung City','Yilan County','Hualien County','Taitung County','New Taipei City'}
        self.assertEqual(len(historical),200)
        self.assertEqual(set(historical.Jurisdiction),allowed)
        self.assertEqual(set(historical.ServiceID),set(socio.ServiceID))
        self.assertFalse(socio.ServiceID.duplicated().any())
        self.assertTrue({'PTOverlap_per','DayworkPopDensity','Elderly_per'}<=set(socio))

    def test_all_eight_packaged_scenarios(self):
        root=Path(__file__).resolve().parents[1]
        catalog=pd.read_csv(root/'data/scenarios/scenario_catalog.csv')
        self.assertEqual(set(zip(catalog.Buffer,catalog.FleetNum)),
                         {(radius,fleet) for radius in [200,500] for fleet in [2,3,4,5]})
        self.assertEqual(len(catalog),8)

    def test_inactive_intention_metric_universe(self):
        d=pd.DataFrame(dict(ServiceID=['A','B'],ServiceType=['Fixed-Route']*2,
            FleetNum=[2,1],MonthlyTrips=[2,1],MonthlyVKT=[2,1],KMCost=[2,1],
            MonthlyPatronage=[1,2],Util_Rate=[.5,1],SI_A=[1,1],SI_B=[0,0],MetricA=[1,2],MetricB=[100,0]))
        m=pd.DataFrame(dict(ServiceIntention=['SI_A','SI_B'],MetricA=[1,0],MetricB=[0,1]))
        spec=dict(inputs=['FleetNum','MonthlyTrips','MonthlyVKT','KMCost'],outputs=['MonthlyPatronage','Util_Rate'])
        a,_=evaluate(d,m,spec)
        self.assertAlmostEqual(a.iloc[0].MetaEff,.5)
        b,_=evaluate(d,m,{**spec,'output_universe':['MetricB']})
        self.assertAlmostEqual(b.iloc[0].MetaEff,1)

    def test_external_monthly_scenarios(self):
        with tempfile.TemporaryDirectory() as folder:
            out=Path(folder)
            d=pd.DataFrame(dict(ServiceID=['A','B'],ServiceType=['Point-to-Point']*2,
                FleetNum=[2,1],MonthlyTrips=[2,1],MonthlyVKT=[2,1],KMCost=[2,1],
                MonthlyPatronage=[1,2],Util_Rate=[.5,1],SI_Elderly=[1,1],Elderly=[1,2]))
            s=d.iloc[:1].copy();s.ServiceID='C'
            m=pd.DataFrame(dict(ServiceIntention=['SI_Elderly'],Elderly=[1]))
            for frame,name in [(d,'h.csv'),(s,'s.csv'),(m,'m.csv')]:frame.to_csv(out/name,index=False)
            cfg=dict(paths=dict(historical=str(out/'h.csv'),si_mapping=str(out/'m.csv'),external_scenarios=str(out/'s.csv')),
                bridge=dict(comparable_trip_definition_confirmed=True,comparability_note='Test fixture with identical accounting'),
                evaluation=dict(inputs=['FleetNum','MonthlyTrips','MonthlyVKT','KMCost'],outputs=['MonthlyPatronage','Util_Rate']))
            run_stage(cfg,'compare',out)
            self.assertEqual(len(pd.read_csv(out/'pooled_comparison.csv')),3)
            self.assertTrue((out/'replication_score_status.json').exists())


if __name__=='__main__':unittest.main()
