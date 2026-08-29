from pathlib import Path
import argparse, gzip, xml.etree.ElementTree as ET
import pandas as pd

def strip(tag): return tag.split('}')[-1].lower()
def opener(p): return gzip.open(p,'rb') if str(p).endswith('.gz') else open(p,'rb')

def find_plans(idir):
    for pat in ['*plans*.xml.gz','*plans*.xml']:
        hits=sorted(idir.glob(pat))
        if hits: return hits[0]
    return None

def parse_selected(path, keep):
    found={}
    with opener(path) as fh:
        for _,elem in ET.iterparse(fh,events=('end',)):
            if strip(elem.tag)!='person': continue
            pid=str(elem.attrib.get('id',''))
            if pid not in keep: elem.clear(); continue
            selected=None
            for child in list(elem):
                if strip(child.tag)=='plan' and str(child.attrib.get('selected','')).lower() in {'yes','true','1'}:
                    selected=child; break
            if selected is None:
                plans=[c for c in list(elem) if strip(c.tag)=='plan']; selected=plans[0] if plans else None
            if selected is not None:
                modes=[]; acts=[]
                for x in list(selected):
                    if strip(x.tag)=='leg': modes.append(str(x.attrib.get('mode','')))
                    elif strip(x.tag)=='act': acts.append(str(x.attrib.get('type','')))
                found[pid]={'selected_plan_score':pd.to_numeric(selected.attrib.get('score'),errors='coerce'),
                            'leg_mode_sequence':' > '.join(modes),'activity_sequence':' > '.join(acts),'n_legs':len(modes)}
            elem.clear()
    return found

def main():
    ap=argparse.ArgumentParser(description='Extract selected-plan score and mode sequence for a small set of agents across MATSim iterations. This is a replanning trajectory, not an experienced-time decomposition.')
    ap.add_argument('scenario_dir')
    ap.add_argument('--agents-csv',required=True)
    ap.add_argument('--person-col',default='person_id')
    ap.add_argument('--start',type=int,default=179); ap.add_argument('--end',type=int,default=200)
    ap.add_argument('--out',default='analysis_results/selected_agent_plan_trajectories.csv')
    args=ap.parse_args(); keep=set(pd.read_csv(args.agents_csv)[args.person_col].astype(str)); root=Path(args.scenario_dir); rows=[]
    for it in range(args.start,args.end+1):
        p=find_plans(root/'ITERS'/f'it.{it}')
        if not p: continue
        data=parse_selected(p,keep)
        for pid,d in data.items(): rows.append({'iteration':it,'person_id':pid,'plans_file':str(p),**d})
    out=Path(args.out); out.parent.mkdir(parents=True,exist_ok=True); pd.DataFrame(rows).to_csv(out,index=False)
    print('Wrote',out)

if __name__=='__main__': main()
