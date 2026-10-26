"""Node-based event simulation with feasible pickup/dropoff insertion.

The next stop of an in-transit vehicle is locked. This avoids teleporting
vehicles when the queue changes. Distances follow the fastest directed path.
"""
from dataclasses import dataclass, field
import heapq
import math
import numpy as np
import pandas as pd
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import dijkstra
from .common import read_csv, numeric, unique


class Network:
    def __init__(self, edges):
        unique(edges, ['from_node', 'to_node'])
        numeric(edges, ['travel_time_s', 'distance_km'])
        if (edges.travel_time_s <= 0).any():
            raise ValueError('Network travel times must be positive')
        self.adj, self.cache = {}, {}
        self.nodes = set(edges.from_node) | set(edges.to_node)
        self.labels = sorted(self.nodes)
        self.index = {v:i for i,v in enumerate(self.labels)}
        self.edge_km = {}
        for r in edges.itertuples():
            self.adj.setdefault(r.from_node, []).append((r.to_node, r.travel_time_s, r.distance_km))
            self.edge_km[self.index[r.from_node],self.index[r.to_node]] = r.distance_km
        self.graph = coo_matrix((edges.travel_time_s.to_numpy(),
            ([self.index[v] for v in edges.from_node],[self.index[v] for v in edges.to_node])),
            shape=(len(self.labels),len(self.labels))).tocsr()
        self._source_cache = {}

    def _source(self, origin):
        if origin not in self.index:
            raise ValueError(f'Unknown network node {origin}')
        if origin not in self._source_cache:
            self._source_cache[origin] = dijkstra(self.graph,directed=True,
                indices=self.index[origin],return_predecessors=True)
        return self._source_cache[origin]

    def precompute(self, nodes):
        """One shortest-path search per access node, not per OD pair."""
        nodes = sorted(set(nodes))
        for origin in nodes:
            self._source(origin)
            for dest in nodes:
                self.route(origin,dest)
            self._source_cache.clear()

    def route(self, origin, dest):
        if (origin, dest) in self.cache:
            return self.cache[origin, dest]
        if dest not in self.index:
            raise ValueError(f'Unknown network node {dest}')
        times, predecessor = self._source(origin)
        t = float(times[self.index[dest]])
        if not math.isfinite(t):
            raise ValueError(f'No directed path from {origin} to {dest}; repair network connectivity')
        node, end, km = self.index[dest], self.index[origin], 0.
        while node != end:
            parent = int(predecessor[node])
            if parent < 0:
                raise ValueError('Missing shortest-path predecessor')
            km += self.edge_km[parent,node]
            node = parent
        self.cache[origin,dest] = (t,float(km))
        return self.cache[origin,dest]


@dataclass
class Vehicle:
    id: int
    node: str
    depart: float = 0
    stops: list = field(default_factory=list)
    load: int = 0
    arrival: float = math.inf
    km: float = 0
    empty_km: float = 0
    tours: int = 0
    max_load: int = 0
    drive_s: float = 0
    loaded_drive_s: float = 0
    busy_s: float = 0


def generate_requests(od, grid, seed, scale=1):
    unique(od, ['Hour', 'GridID_O', 'GridID_D'])
    unique(grid, ['GridID'])
    numeric(od, ['PredTrips'])
    numeric(od, ['Hour'], upper=23)
    if not (od.Hour % 1 == 0).all():
        raise ValueError('Hour must be an integer from 0 to 23')
    lookup = dict(zip(grid.GridID.astype(str), grid.node_id.astype(str)))
    used = set(od.GridID_O.astype(str)) | set(od.GridID_D.astype(str))
    if not used <= lookup.keys():
        raise ValueError(f'Unmapped grids: {sorted(used - lookup.keys())[:10]}')
    rng = np.random.default_rng(seed)
    rows = []
    ordered = od.sort_values(['Hour','GridID_O','GridID_D']).reset_index(drop=True)
    counts = rng.poisson(ordered.PredTrips.to_numpy(float)*scale)
    for idx in np.flatnonzero(counts):
        r = ordered.iloc[idx]
        count = counts[idx]
        rows.extend(dict(request_time_s=float(r.Hour*3600 + t), origin=lookup[str(r.GridID_O)],
                         destination=lookup[str(r.GridID_D)]) for t in rng.uniform(0, 3600, count))
    result = pd.DataFrame(rows, columns=['request_time_s', 'origin', 'destination'])
    result = result.sort_values('request_time_s').reset_index(drop=True)
    result['request_id'] = np.arange(len(result))
    return result


def simulate(requests, net, spec):
    fleet, capacity = int(spec['fleet_size']), int(spec['capacity'])
    if fleet != spec['fleet_size'] or capacity != spec['capacity']:
        raise ValueError('fleet_size and capacity must be integers')
    if fleet < 1 or capacity < 1 or spec['dwell_s'] < 0 or spec['max_wait_s'] < 0 or spec['max_ride_factor'] < 1 or spec['max_ride_extra_s'] < 0 or spec['alpha'] < 0 or spec['beta'] < 0:
        raise ValueError('Invalid fleet, capacity, dwell, waiting or ride parameters')
    depots = [str(n) for n in spec.get('depot_nodes',[spec.get('depot_node')])]
    if not set(depots) <= net.nodes:
        raise ValueError('Depot node is absent from network')
    rng = np.random.default_rng(spec.get('deployment_seed',0))
    # The first N vehicle assignments are shared by fleet alternatives within a replication.
    initial = rng.choice(depots,size=fleet)
    vehicles = [Vehicle(i,str(initial[i])) for i in range(fleet)]
    pax = {}
    dwell = spec['dwell_s']

    def start(v, now):
        if v.stops:
            dt, _ = net.route(v.node, v.stops[0][2])
            v.depart = now
            v.arrival = now + dt
        else:
            v.depart, v.arrival = now, math.inf

    def advance(now):
        for v in vehicles:
            while v.stops and v.arrival <= now:
                pid, kind, node = v.stops.pop(0)
                dt, km = net.route(v.node, node)
                v.km += km
                v.empty_km += km if v.load == 0 else 0
                v.drive_s += dt
                v.loaded_drive_s += dt if v.load > 0 else 0
                v.busy_s += dt + dwell
                v.node = node
                if kind == 'O':
                    v.load += 1
                    v.max_load = max(v.max_load, v.load)
                    pax[pid]['pickup_s'] = v.arrival
                else:
                    v.load -= 1
                    pax[pid]['dropoff_s'] = v.arrival
                    pax[pid]['status'] = 'served'
                next_depart = v.arrival + dwell
                start(v, next_depart)

    def schedule(v, stops, now):
        t = v.depart if v.stops else max(v.depart, now)
        node, load, times = v.node, v.load, {}
        picked = {pid: p['pickup_s'] for pid, p in pax.items() if 'pickup_s' in p}
        for pid, kind, nxt in stops:
            dt, _ = net.route(node, nxt)
            t += dt
            times[pid, kind] = t
            p = pax[pid]
            if kind == 'O':
                load += 1
                picked[pid] = t
                if t - p['request_time_s'] > spec['max_wait_s'] + 1e-8:
                    return None
            else:
                load -= 1
                direct = net.route(p['origin'], p['destination'])[0]
                if t - picked[pid] > direct * spec['max_ride_factor'] + spec['max_ride_extra_s'] + 1e-8:
                    return None
            if not 0 <= load <= capacity:
                return None
            t += dwell
            node = nxt
        return times, t

    for r in requests.to_dict('records'):
        now, pid = float(r['request_time_s']), int(r['request_id'])
        advance(now)
        pax[pid] = dict(r, status='rejected', vehicle_id=-1)
        best = None
        for v in vehicles:
            old = schedule(v, v.stops, now)
            if old is None:
                raise RuntimeError('Existing route became infeasible')
            lock = 1 if v.stops else 0
            for i in range(lock, len(v.stops) + 1):
                for j in range(i+1, len(v.stops)+2):
                    candidate = v.stops.copy()
                    candidate.insert(i, (pid, 'O', str(r['origin'])))
                    candidate.insert(j, (pid, 'D', str(r['destination'])))
                    info = schedule(v, candidate, now)
                    if info is None:
                        continue
                    times, end = info
                    delay = sum(max(0, times[k] - t) for k, t in old[0].items() if k[1] == 'D')
                    baseline_end = old[1] if v.stops else max(v.depart, now)
                    added = end - baseline_end - 2*dwell
                    cost = added + spec['alpha']*delay + spec['beta']*(times[pid, 'O']-now)
                    if best is None or cost < best[0]:
                        best = cost, v, candidate
        if best:
            _, v, plan = best
            idle = not v.stops
            v.stops = plan
            pax[pid].update(status='accepted', vehicle_id=v.id)
            if idle:
                v.tours += 1
                start(v, max(now, v.depart))
    advance(math.inf)  # drain accepted trips; explicitly include overtime
    passengers = pd.DataFrame(list(pax.values()), columns=['request_id','request_time_s','origin','destination','status','vehicle_id','pickup_s','dropoff_s'])
    vehicle_df = pd.DataFrame([dict(vehicle_id=v.id,initial_depot_node=str(initial[v.id]),vkt_km=v.km, empty_vkt_km=v.empty_km,
                                   dispatch_tours=v.tours, max_onboard=v.max_load,drive_time_s=v.drive_s,
                                   loaded_drive_time_s=v.loaded_drive_s,busy_time_s=v.busy_s) for v in vehicles])
    served = passengers[passengers.status == 'served'].copy()
    waits = served.pickup_s - served.request_time_s
    rides = served.dropoff_s - served.pickup_s
    return passengers, vehicle_df, dict(requests=len(passengers), served=len(served), rejected=len(passengers)-len(served),
        vkt_km=float(vehicle_df.vkt_km.sum()), empty_vkt_km=float(vehicle_df.empty_vkt_km.sum()),
        dispatch_tours=int(vehicle_df.dispatch_tours.sum()),
        trips_with_passengers=int(vehicle_df.dispatch_tours.sum()),
        vehicle_drive_time_s=float(vehicle_df.drive_time_s.sum()),
        vehicle_busy_time_s=float(vehicle_df.busy_time_s.sum()),
        mean_wait_s=float(waits.mean()) if len(served) else 0.,
        p95_wait_s=float(waits.quantile(.95)) if len(served) else 0.,
        mean_ride_s=float(rides.mean()) if len(served) else 0.,
        last_dropoff_s=float(served.dropoff_s.max()) if len(served) else 0.)


def run_simulations(cfg, od_path, out):
    od = None
    grid = read_csv(cfg['paths']['grid_nodes'], ['GridID','node_id'])
    edges = read_csv(cfg['paths']['network'], ['from_node','to_node','travel_time_s','distance_km'])
    for c in ['from_node','to_node']:
        edges[c] = edges[c].astype(str)
    grid.node_id = grid.node_id.astype(str)
    net = Network(edges)
    if not set(grid.node_id) <= net.nodes:
        raise ValueError('Grid node IDs must exist in network')
    depots = [str(x) for x in cfg['simulation'].get('depot_nodes',[cfg['simulation'].get('depot_node')])]
    scenarios = cfg['simulation']['scenarios']
    names = [s['RouteID'] for s in scenarios]
    if len(set(names)) != len(names):
        raise ValueError('Scenario RouteIDs must be unique')
    rows = []
    groups = {}
    for n,scenario in enumerate(scenarios):
        groups.setdefault(str(scenario.get('demand_case','default')),[]).append((n,scenario))
    for case,members in groups.items():
        forecast = out/f'ml_demand_{case}.csv.gz' if cfg['demand']['source']=='ml' else od_path
        od = read_csv(forecast,['Hour','GridID_O','GridID_D','PredTrips'])
        # Identifiers in source ML inputs are numeric; spatial tables use ILA_0001 style.
        for col in ['GridID_O','GridID_D']:
            if cfg['demand']['source']=='ml' and not od[col].astype(str).str.startswith('ILA_').all():
                od[col] = od[col].map(lambda x:f'ILA_{int(x):04d}')
        used = set(od.GridID_O)|set(od.GridID_D)
        active_grid = grid[grid.GridID.isin(used)].copy()
        if set(active_grid.GridID)!=used:
            raise ValueError('A forecast grid is absent from the configured spatial mapping')
        net.precompute(set(active_grid.node_id)|set(depots))
        for rep in range(cfg['simulation']['replications']):
            seed = cfg['seed'] + rep
            requests = generate_requests(od,active_grid,seed,cfg['simulation']['demand_scale'])
            requests.to_csv(out/f'requests_{case}_rep{rep:03d}.csv',index=False)
            for n,scenario in members:
                settings = {**cfg['simulation'],**scenario,'deployment_seed':seed}
                passengers,vehicles,stats = simulate(requests,net,settings)
                passengers.to_csv(out/f'passengers_s{n:02d}_rep{rep:03d}.csv',index=False)
                vehicles.to_csv(out/f'vehicles_s{n:02d}_rep{rep:03d}.csv',index=False)
                window = (cfg['simulation']['end_hour_exclusive']-cfg['simulation']['start_hour'])*3600
                rows.append(dict(RouteID=scenario['RouteID'],demand_case=case,replication=rep,seed=seed,
                    busy_time_utilization=stats['vehicle_busy_time_s']/(settings['fleet_size']*window),**stats))
    daily = pd.DataFrame(rows)
    daily.to_csv(out/'simulation_daily.csv', index=False)
    columns = ['served','rejected','vkt_km','dispatch_tours','mean_wait_s','p95_wait_s']
    summary = daily.groupby('RouteID')[columns].agg(['mean','std','min','max'])
    summary.columns = ['_'.join(c) for c in summary.columns]
    summary.to_csv(out/'simulation_summary.csv')
    return daily
