// Deferred acceptance definitions. Do not run during the implementation phase.
import assert from "node:assert/strict";
import test from "node:test";
import { parseRecoveryBatch, recoveryBatchKey } from "../components/admin/recovery-batch-state.ts";

const first={kind:"work",object_id:"00000000-0000-4000-8000-000000000001",request_id:"00000000-0000-4000-8000-000000000002",expected_version:"a".repeat(64),confirmed:true};
const second={...first,object_id:"00000000-0000-4000-8000-000000000003",request_id:"00000000-0000-4000-8000-000000000004"};
test("a recovered batch retains original requests and unresolved outcome without replay",()=>{
  const value={version:1,items:[{command:first,state:"applied"},{command:second,state:"pending"}]};
  assert.deepEqual(parseRecoveryBatch(JSON.stringify(value)),value);
  assert.notEqual(recoveryBatchKey("1"),recoveryBatchKey("2"));
});
test("reject ambiguity and expanded authority in persisted restore commands",()=>{
  for(const items of [
    [{command:first,state:"ready"},{command:first,state:"ready"}],
    [{command:first,state:"pending"},{command:second,state:"pending"}],
    [{command:{...first,keep_separate:true},state:"ready"}],
    [{command:{...first,confirmed:false},state:"ready"}],
    [{command:{...first,expected_version:"old"},state:"ready"}],
    [{command:{...first,object_id:"/other"},state:"ready"}],
    [{command:first,state:"success"}],
    Array.from({length:21},()=>({command:first,state:"ready"})),
  ])assert.throws(()=>parseRecoveryBatch(JSON.stringify({version:1,items})));
  assert.throws(()=>parseRecoveryBatch('{"version":1,"items":[]}'));
  assert.throws(()=>parseRecoveryBatch(JSON.stringify({version:2,items:[{command:first,state:"ready"}]})));
});
