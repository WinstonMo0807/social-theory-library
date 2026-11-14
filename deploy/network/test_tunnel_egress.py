import importlib.util
from pathlib import Path
import unittest
path=Path(__file__).parent/'tunnel-egress.py'
spec=importlib.util.spec_from_file_location('egress',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class EgressDecision(unittest.TestCase):
 def test_boot_waits_for_gateway_without_latching_a_failure(self):
  self.assertEqual(module.decision({},False,0,0,100),('waiting','gateway-starting'))
 def test_gateway_loss_returns_direct_even_during_grace(self):
  self.assertEqual(module.decision({'applied_at':99},False,4,4,100),('direct','gateway-unavailable'))
 def test_initial_connection_has_bounded_grace(self):
  self.assertEqual(module.decision({'applied_at':50},True,0,0,100)[1],'connecting')
  self.assertEqual(module.decision({'applied_at':1},True,0,0,100)[1],'checking-connections')
 def test_direct_fallback_is_latched(self):
  self.assertEqual(module.decision({'mode':'direct','reason':'failure'},True,4,4,100),('direct','failure'))
 def test_health_needs_both_live_connections_and_hkg_locations(self):
  for connections,hkg in [(1,4),(4,1),(0,0)]:
   self.assertEqual(module.decision({'applied_at':1,'failures':2},True,connections,hkg,100)[0],'direct')
  self.assertEqual(module.decision({'applied_at':1,'failures':2},True,3,3,100),('hkg','healthy'))
 def test_transient_loss_gets_two_rechecks(self):
  for failures in [0,1]:self.assertEqual(module.decision({'applied_at':1,'failures':failures},True,0,0,100)[0],'hkg')

unittest.main()
