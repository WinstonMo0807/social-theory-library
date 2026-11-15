import json
from pathlib import Path
import tempfile
import unittest
from uuid import uuid4

from bridge import Bridge


class JournalChecks(unittest.TestCase):
    def test_plan_survives_restart_and_reuses_same_operation_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(json.dumps({"host": "unused", "identity_file": "unused", "container": "unused", "actor_id": 1, "token_version": 0, "allowed_work_ids": [], "required_sections": ["evidence"]}))
            bridge = Bridge(path)
            bridge.call = lambda *args: {"ok": True, "results": []}
            requirements = [{"section": "evidence", "state": "pending", "reason": "合成数据尚未核查"}]
            plan = bridge.prepare([{"key": "one", "kind": "editorial"}], requirements)
            restarted = Bridge(path)
            digest, stored = restarted.plan(plan["plan_id"])
            self.assertEqual(digest, plan["plan_digest"])
            request_id = stored["operations"][0]["request_id"]
            captured = []
            restarted.call = lambda action, args: captured.append(args) or {"ok": True}
            restarted.save(plan["plan_id"], digest)
            restarted.save(plan["plan_id"], digest)
            self.assertEqual([args["operations"][0]["request_id"] for args in captured], [request_id, request_id])
            with self.assertRaises(ValueError):
                restarted.save(plan["plan_id"], "changed")
            with self.assertRaises(ValueError):
                bridge.prepare([{"key": "one"}], [])

    def test_scope_mode_is_only_taken_from_validated_trusted_config(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            config = {"host": "unused", "identity_file": "unused", "container": "unused", "actor_id": 1,
                      "token_version": 0, "allowed_work_ids": [], "work_scope": "catalog"}
            path.write_text(json.dumps(config))
            self.assertEqual(Bridge(path).domain_config["work_scope"], "catalog")
            config["work_scope"] = "catlog"
            path.write_text(json.dumps(config))
            with self.assertRaises(ValueError):
                Bridge(path)


if __name__ == "__main__":
    unittest.main()
