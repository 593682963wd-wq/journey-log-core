"""作者：Wangyuan；日期：2026-10-29；职责：显式旅程记录的持久化、重复检查和统计。"""
import tempfile,hashlib,json,math
from dataclasses import replace
from pathlib import Path
from datetime import date
from personal_flight_archive.domain.models import PersonalFlight
from personal_flight_archive.infrastructure.repository import PersonalArchiveRepository
from statistics import StatisticsService

def run(payload):
    if not isinstance(payload,dict):raise TypeError('输入须对象')
    journeys=payload.get('journeys',[])
    if not isinstance(journeys,list):raise TypeError('journeys须数组')
    # Validate the complete request before opening a persistent database.
    prepared=[]
    for row in journeys:
        if not isinstance(row,dict):raise TypeError('journey须对象')
        day=date.fromisoformat(row['date']).isoformat();start=str(row['origin']).strip();end=str(row['destination']).strip()
        if not start or not end or start==end:raise ValueError('起终点须明确且不同')
        values={}
        for field in ('duration_minutes','distance_nm'):
            if field not in row:continue
            value=row[field]
            if value is not None:
                if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or value<0:
                    raise ValueError(f'{field}须有限非负数或null')
            values[field]=value
        ident=str(row['id'])
        key=hashlib.sha256(json.dumps([day,start,end],ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
        prepared.append((ident,day,start,end,key,values))
    with tempfile.TemporaryDirectory() as d:
        repo=PersonalArchiveRepository(payload.get('database') or Path(d)/'journeys.sqlite3')
        for ident,day,start,end,key,values in prepared:
            existing=repo.get_flight(ident)
            if existing:
                record=replace(existing,flight_date=day,origin_icao=start,destination_icao=end,dedupe_key=key,**values)
                repo.update_flight(record)
            else:
                record=PersonalFlight(flight_id=ident,flight_date=day,flight_number=None,origin_icao=start,destination_icao=end,dedupe_key=key,source='manual',**values)
                repo.add_flight(record)
        for ident in payload.get('delete_ids',[]):repo.soft_delete_flight(str(ident),confirm=True)
        stats=StatisticsService(repo,None)
        return {'records':[r.to_dict() for r in repo.list_flights()],'summary':stats.summary(),'calendar':stats.calendar()}
