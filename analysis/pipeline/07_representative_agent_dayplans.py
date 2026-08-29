from pathlib import Path
import argparse
import numpy as np
import pandas as pd

LABELS={
    'target_bus_to_DRT':'DRT retention',
    'target_bus_to_other_PT':'Other PT',
    'target_bus_to_car':'Car',
    'target_bus_to_other':'Ride/other',
}

def main():
    ap=argparse.ArgumentParser(description='Select non-cherry-picked representative affected riders and export final B0-to-scenario daily trip timelines.')
    ap.add_argument('--scenario',default='A8_FM')
    ap.add_argument('--scenario-dir',default='analysis_results/02_scenarios')
    ap.add_argument('--out',default='analysis_results/06_agent_dayplans')
    args=ap.parse_args()
    sd=Path(args.scenario_dir)/args.scenario
    p=pd.read_csv(sd/'person_level_impacts.csv.gz',low_memory=False)
    t=pd.read_csv(sd/'trip_level_impacts.csv.gz',low_memory=False)
    affected=p[p['baseline_target_line_rider']==True].copy()
    target=t[t['baseline_target_line_trip']==True].copy()

    agg=[]
    for pid,g in target.groupby('person_id'):
        vc=g['transition_class'].value_counts()
        agg.append({'person_id':pid,'dominant_transition':vc.index[0],
                    'mean_target_delta_journey_min':g['delta_journey_sec'].mean()/60,
                    'mean_target_delta_wait_min':g['delta_wait_sec'].mean()/60,
                    'n_target_trips':len(g),'target_drt_share':g['scenario_drt_trip'].mean()})
    a=affected.merge(pd.DataFrame(agg),on='person_id',how='inner')

    reps=[]
    for transition,label in LABELS.items():
        g=a[a['dominant_transition']==transition].copy()
        if g.empty: continue
        med_u=g['delta_score'].median(); med_j=g['mean_target_delta_journey_min'].median()
        su=max(g['delta_score'].std(ddof=0),1e-6); sj=max(g['mean_target_delta_journey_min'].std(ddof=0),1e-6)
        g['_distance']=((g['delta_score']-med_u)/su)**2+((g['mean_target_delta_journey_min']-med_j)/sj)**2
        r=g.sort_values(['_distance','person_id']).iloc[0].copy()
        r['adaptation_label']=label; r['group_n']=len(g); r['group_mean_delta_score']=g['delta_score'].mean(); r['group_median_delta_score']=med_u
        reps.append(r)
    reps=pd.DataFrame(reps)
    out=Path(args.out); out.mkdir(parents=True,exist_ok=True)
    keep=[c for c in ['adaptation_label','person_id','group_n','delta_score','group_mean_delta_score','group_median_delta_score',
                      'mean_target_delta_journey_min','mean_target_delta_wait_min','n_target_trips','income_group','age_group','gender_group','car_availability_group'] if c in reps.columns]
    reps[keep].to_csv(out/f'{args.scenario}_representative_agents.csv',index=False)

    timeline=[]
    for _,rr in reps.iterrows():
        g=t[t['person_id']==rr['person_id']].sort_values('trip_key')
        for _,tr in g.iterrows():
            for state,prefix in [('B0','b0_'),(args.scenario,'scenario_')]:
                dep=pd.to_numeric(tr.get(prefix+'dep_sec'),errors='coerce'); dur=pd.to_numeric(tr.get(prefix+'trav_sec'),errors='coerce')
                timeline.append({'adaptation_label':rr['adaptation_label'],'person_id':rr['person_id'],'state':state,'trip_key':tr['trip_key'],
                                 'start_activity':tr.get(prefix+'start_activity'),'end_activity':tr.get(prefix+'end_activity'),'mode':tr.get(prefix+'mode'),
                                 'dep_sec':dep,'arr_sec':dep+dur if pd.notna(dep) and pd.notna(dur) else np.nan,'trav_sec':dur,
                                 'wait_sec':pd.to_numeric(tr.get(prefix+'wait_sec'),errors='coerce'),'baseline_target_line_trip':tr.get('baseline_target_line_trip'),
                                 'transition_class':tr.get('transition_class'),'delta_score':rr['delta_score'],
                                 'mean_target_delta_journey_min':rr['mean_target_delta_journey_min']})
    pd.DataFrame(timeline).to_csv(out/f'{args.scenario}_representative_dayplan_timeline.csv',index=False)
    print('Representative agents and final B0-to-scenario timelines written to',out)
    print('Selection rule: closest to the group medians of delta utility and target-trip journey-time change after within-group standardisation.')

if __name__=='__main__': main()
