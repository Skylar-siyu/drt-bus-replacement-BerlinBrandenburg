from pathlib import Path
import argparse, re
import pandas as pd

PATTERNS={
    'plans':['*plans*.xml.gz','*plans*.xml'],
    'events':['*events*.xml.gz','*events*.xml'],
    'trips':['*trips*.csv.gz','*trips*.csv'],
    'legs':['*legs*.csv.gz','*legs*.csv'],
    'experienced_plan_scores':['*experienced*plans*scores*.txt.gz','*experienced*plans*scores*.txt','*experienced*scores*.txt.gz'],
}

def main():
    ap=argparse.ArgumentParser(description='Inventory MATSim ITERS assets before deciding whether per-agent iteration trajectories are worth extracting.')
    ap.add_argument('scenario_dirs',nargs='+')
    ap.add_argument('--start',type=int,default=179)
    ap.add_argument('--end',type=int,default=200)
    ap.add_argument('--out',default='analysis_results/iteration_asset_inventory.csv')
    args=ap.parse_args(); rows=[]
    for s in args.scenario_dirs:
        root=Path(s); iters=root/'ITERS'
        for it in range(args.start,args.end+1):
            idir=iters/f'it.{it}'
            row={'scenario_dir':str(root),'iteration':it,'iteration_dir_exists':idir.exists()}
            for key,pats in PATTERNS.items():
                hits=[]
                if idir.exists():
                    for pat in pats: hits.extend(idir.glob(pat))
                row[key+'_count']=len(set(hits)); row[key+'_example']=str(sorted(set(hits))[0]) if hits else ''
            rows.append(row)
        # final output score-component check
        final=[]
        for pat in PATTERNS['experienced_plan_scores']: final.extend(root.glob(pat))
        rows.append({'scenario_dir':str(root),'iteration':'FINAL','iteration_dir_exists':True,
                     'experienced_plan_scores_count':len(set(final)),
                     'experienced_plan_scores_example':str(sorted(set(final))[0]) if final else ''})
    out=Path(args.out); out.parent.mkdir(parents=True,exist_ok=True); pd.DataFrame(rows).to_csv(out,index=False)
    print('Inventory written to',out)
    print('For the main dissertation result, final B0-to-scenario day-plan comparison does not require iterations 1-178.')

if __name__=='__main__': main()
