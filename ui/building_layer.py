"""Read-only, display-only spatial layer. Never contributes route candidates."""
import json
import math
import re
import sqlite3
from contextlib import closing
from pathlib import Path


def query_buildings(root, dataset_key, fingerprint, centre, radius=2000, limit=700):
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}(?:\.[0-9]{1,3})?",str(dataset_key or "")):
        return []
    if not re.fullmatch(r"[a-f0-9]{24}",str(fingerprint or "")):
        return []
    try:
        x,z=map(float,centre)
        radius=min(5000,max(50,float(radius)))
        if not all(math.isfinite(v) for v in (x,z,radius)):
            return []
        path=Path(root)/dataset_key/'buildings.sqlite'
        if not path.is_file():
            return []
        with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True,timeout=.5)) as connection:
            connection.execute('PRAGMA query_only=ON')
            metadata=dict(connection.execute('SELECT key,value FROM metadata'))
            if (metadata.get('schema_version')!='1' or metadata.get('dataset_key')!=dataset_key
                    or metadata.get('dataset_fingerprint')!=fingerprint):
                return []
            rows=connection.execute('''SELECT b.uid,b.points,b.height
                FROM bounds r JOIN building b ON b.id=r.id
                WHERE r.maxx>=? AND r.minx<=? AND r.maxz>=? AND r.minz<=?
                ORDER BY ((r.minx+r.maxx)*.5-?)*((r.minx+r.maxx)*.5-?)
                       + ((r.minz+r.maxz)*.5-?)*((r.minz+r.maxz)*.5-?) LIMIT ?''',
                (x-radius,x+radius,z-radius,z+radius,x,x,z,z,min(1000,max(1,int(limit))))).fetchall()
        result=[]
        for uid,encoded,height in rows:
            points=json.loads(encoded)
            if not 3<=len(points)<=32 or not math.isfinite(height) or not 2<=height<=350:
                continue
            if not all(isinstance(p,list) and len(p)==2 and all(math.isfinite(float(v)) for v in p) for p in points):
                continue
            xs,zs=[p[0] for p in points],[p[1] for p in points]
            result.append(dict(uid=uid,points=tuple(tuple(p) for p in points),height=float(height),
                               bounds=(min(xs),max(xs),min(zs),max(zs)),kind='building'))
        return result
    except (OSError,sqlite3.Error,ValueError,TypeError,OverflowError):
        return []
