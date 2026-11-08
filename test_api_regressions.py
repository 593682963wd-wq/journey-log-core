import tempfile
import unittest
from pathlib import Path
from core import run
from personal_flight_archive.domain.models import PersonalFlight
from personal_flight_archive.domain.validation import DuplicateFlightError
from personal_flight_archive.infrastructure.repository import PersonalArchiveRepository

class ApiRegressions(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.db=Path(self.temp.name)/'journeys.sqlite3'
    def row(self,**changes):
        return {'id':'a','date':'2026-01-01','origin':'A','destination':'B',**changes}
    def test_update_preserves_existing_metadata(self):
        repo=PersonalArchiveRepository(self.db)
        repo.add_flight(PersonalFlight('a','2026-01-01','SYN1','A','B',notes='keep',purpose_tags=['synthetic'],airline='Synthetic',duration_minutes=42,dedupe_key='seed'))
        result=run({'database':str(self.db),'journeys':[self.row(date='2026-01-02')]})['records'][0]
        self.assertEqual(result['notes'],'keep');self.assertEqual(result['purpose_tags'],['synthetic'])
        self.assertEqual(result['airline'],'Synthetic');self.assertEqual(result['duration_minutes'],42)
        self.assertEqual(result['flight_date'],'2026-01-02')
    def test_bad_numeric_request_does_not_persist_any_rows(self):
        PersonalArchiveRepository(self.db)
        for field in ('duration_minutes','distance_nm'):
            for value in ('bad',float('nan'),float('inf'),-1,True):
                with self.subTest(field=field,value=value):
                    with self.assertRaises(ValueError):
                        run({'database':str(self.db),'journeys':[self.row(),self.row(id='b',date='2026-01-02',**{field:value})]})
                    self.assertEqual(PersonalArchiveRepository(self.db).list_flights(),[])
    def test_business_duplicate_different_id(self):
        run({'database':str(self.db),'journeys':[self.row()]})
        with self.assertRaises(DuplicateFlightError):
            run({'database':str(self.db),'journeys':[self.row(id='b')]})
        self.assertEqual(len(PersonalArchiveRepository(self.db).list_flights()),1)
    def test_route_keys_do_not_collide(self):
        summary=run({'journeys':[self.row(origin='A-B',destination='C'),self.row(id='b',origin='A',destination='B-C')]})['summary']
        self.assertEqual(len(summary['by_route']),2)
        self.assertEqual(sorted(summary['by_route'].values()),[1,1])
