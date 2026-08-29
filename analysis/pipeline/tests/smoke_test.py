from pathlib import Path
import gzip, subprocess, tempfile, textwrap, csv, shutil

ROOT = Path(__file__).resolve().parents[1]


def gzwrite(path, text):
    with gzip.open(path, 'wt', encoding='utf-8') as f:
        f.write(text)


def make_plans(path, scores):
    persons=[]
    for pid,score in scores.items():
        persons.append(f'''<person id="{pid}"><attributes><attribute name="income" class="java.lang.Double">{1000 if pid=='p1' else 3000}</attribute><attribute name="age" class="java.lang.Integer">35</attribute><attribute name="sex" class="java.lang.String">m</attribute><attribute name="carAvail" class="java.lang.String">sometimes</attribute></attributes><plan selected="yes" score="{score}"><act type="home" x="1" y="2"/><leg mode="pt"/><act type="work" x="3" y="4"/></plan></person>''')
    gzwrite(path, '<population>'+''.join(persons)+'</population>')


def make_stats(path, name='avg', val=1):
    with open(path,'w') as f:
        f.write('iteration;'+name+'\n')
        for i in range(181,201): f.write(f'{i};{val+i*0.0001}\n')


def main():
    td = Path(tempfile.mkdtemp(prefix='matsim_analysis_smoke_'))
    try:
        b0=td/'B0'; a=td/'A8'; b0.mkdir(); a.mkdir()
        gzwrite(b0/'x.output_network.xml.gz','''<network><nodes><node id="1" x="0" y="0"/><node id="2" x="1000" y="0"/></nodes><links><link id="l1" from="1" to="2" length="1000" freespeed="10" capacity="1000" permlanes="1" modes="car"/></links></network>''')
        gzwrite(b0/'x.output_events.xml.gz','''<events>
<event time="100" type="TransitDriverStarts" vehicleId="bus1" transitLineId="890---22435" transitRouteId="r1"/>
<event time="110" type="PersonEntersVehicle" person="p1" vehicle="bus1"/>
<event time="120" type="entered link" vehicle="bus1" link="l1"/>
<event time="220" type="left link" vehicle="bus1" link="l1"/>
<event time="230" type="PersonLeavesVehicle" person="p1" vehicle="bus1"/>
<event time="240" type="vehicle leaves traffic" vehicle="bus1"/>
</events>''')
        with gzip.open(b0/'x.output_trips.csv.gz','wt') as f:
            f.write('person;trip_number;main_mode;dep_time;trav_time;wait_time;traveled_distance\n')
            f.write('p1;0;pt;00:01:40;00:08:20;00:00:10;1000\n')
            f.write('p2;0;car;00:02:00;00:05:00;00:00:00;2000\n')
        make_plans(b0/'x.output_experienced_plans.xml.gz', {'p1':10,'p2':5})
        make_stats(b0/'x.scorestats.csv'); make_stats(b0/'x.modestats.csv','car',.5)

        with gzip.open(a/'x.output_trips.csv.gz','wt') as f:
            f.write('person;trip_number;main_mode;dep_time;trav_time;wait_time;traveled_distance\n')
            f.write('p1;0;pt;00:01:40;00:06:40;00:00:20;900\n')
            f.write('p2;0;car;00:02:00;00:05:00;00:00:00;2000\n')
        with gzip.open(a/'x.output_legs.csv.gz','wt') as f:
            f.write('person;trip_number;mode\n'); f.write('p1;0;drt\n'); f.write('p2;0;car\n')
        make_plans(a/'x.output_experienced_plans.xml.gz', {'p1':11,'p2':5})
        make_stats(a/'x.scorestats.csv'); make_stats(a/'x.modestats.csv','car',.5)
        with open(a/'x.drt_customer_stats_drt.csv','w') as f:
            f.write('iteration;servedRequests;rejectedRequests;rejectionRate;waitTime;waitTimeP95;rideTime\n')
            for i in range(181,201): f.write(f'{i};1;0;0;20;30;300\n')
        with open(a/'x.drt_vehicle_stats_drt.csv','w') as f:
            f.write('iteration;totalDistance;emptyDistance;totalDriveTime;idleTime;minIdleVehicles\n')
            for i in range(181,201): f.write(f'{i};800;200;400;100;2\n')
        with open(a/'x.drt_sharing_metrics_drt.csv','w') as f:
            f.write('iteration;poolingRate;sharingFactor\n')
            for i in range(181,201): f.write(f'{i};0.5;1.5\n')
        gzwrite(a/'x.output_events.xml.gz','''<events>
<event time="100" type="entered link" vehicle="drt1" link="l1"/>
<event time="210" type="left link" vehicle="drt1" link="l1"/>
<event time="210" type="warmEmissionEvent" vehicleId="drt1" linkId="l1" CO2_TOTAL="12.5" NOx="0.2"/>
</events>''')

        manifest=td/'manifest.csv'
        manifest.write_text('''scenario,case,role,ready,output_dir,target_line_ids,fleet,capacity,service_hours,pricing_group,monetary_treatment,rq1_structural,rq2_design,rq3_distribution,network_events,notes\nB0,B0,baseline,1,{b0},,0,0,,BASELINE,baseline,0,0,0,1,test\nA8_FM,A,structural_control,1,{a},890---22435|890,8,4,16,FM,zero,1,1,1,1,test\n'''.format(b0=b0,a=a))
        cfg=ROOT/'analysis_config.json'
        work=td/'work'; work.mkdir()
        cmds=[
            ['python',str(ROOT/'00_preflight.py'),'--manifest',str(manifest),'--config',str(cfg),'--out',str(work/'00')],
            ['python',str(ROOT/'01_build_baseline_cohorts.py'),'--manifest',str(manifest),'--config',str(cfg),'--out',str(work/'01')],
            ['python',str(ROOT/'02_analyse_scenarios.py'),'--manifest',str(manifest),'--config',str(cfg),'--baseline-dir',str(work/'01'),'--out',str(work/'02')],
            ['python',str(ROOT/'03_analyse_network_events.py'),'--manifest',str(manifest),'--config',str(cfg),'--baseline-dir',str(work/'01'),'--out',str(work/'03')],
            ['python',str(ROOT/'04_build_rq_outputs.py'),'--manifest',str(manifest),'--baseline-dir',str(work/'01'),'--scenario-dir',str(work/'02'),'--network-dir',str(work/'03'),'--out',str(work/'04')],
            ['python',str(ROOT/'05_make_figures.py'),'--rq-dir',str(work/'04'),'--out',str(work/'05')],
        ]
        for cmd in cmds:
            subprocess.run(cmd, cwd=ROOT, check=True)
        rq1=work/'04'/'RQ1_context_suitability_A_B_C.csv'
        assert rq1.exists() and rq1.stat().st_size>20
        t=(work/'02'/'A8_FM'/'mode_transitions_original_target_bus_trips.csv').read_text()
        assert 'target_bus_to_DRT' in t
        print('SMOKE TEST PASSED:', td)
    finally:
        shutil.rmtree(td, ignore_errors=True)

if __name__=='__main__': main()
