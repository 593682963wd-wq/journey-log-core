import unittest,tempfile,json
from pathlib import Path
from core import run

class Tests(unittest.TestCase):
 def test_record(self):self.assertEqual(run(json.loads(Path('example.json').read_text()))['summary']['total_flights'],1)
 def test_empty(self):self.assertEqual(run({})['records'],[])
 def test_bad(self):
  with self.assertRaises(ValueError):run({'journeys':[{'id':'a','date':'bad','origin':'a','destination':'b'}]})
 def test_delete(self):
  p=json.loads(Path('example.json').read_text());p['delete_ids']=['synthetic-a'];self.assertEqual(run(p)['records'],[])

if __name__=="__main__":unittest.main()
