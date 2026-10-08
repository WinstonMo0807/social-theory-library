import assert from 'node:assert/strict';
import test from 'node:test';
import { editorialDayInRange, editorialInstant, editorialLocalDateTime, editorialShiftDay, editorialShiftMonth } from '../lib/editorial-date.ts';

test('editorial dates keep Hong Kong midnight and the selected publishing time across browser time zones',()=>{
  for(const zone of ['UTC','America/Los_Angeles','Pacific/Kiritimati']){
    const previous=process.env.TZ;
    try {
      process.env.TZ=zone;
      assert.equal(editorialLocalDateTime('2026-10-08T16:00:00Z'),'2026-10-09T00:00');
      assert.equal(editorialInstant('2026-10-09','00:15'),'2026-10-08T16:15:00.000Z');
      assert.equal(editorialLocalDateTime(editorialInstant('2028-02-29','23:59')),'2028-02-29T23:59');
      assert.equal(editorialShiftDay('2028-03-01',-1),'2028-02-29');
      assert.equal(editorialShiftMonth('2026-12',1),'2027-01');
      assert.equal(editorialShiftMonth('2026-01',-1),'2025-12');
      assert.equal(editorialDayInRange('2026-10-10T15:59:00Z','2026-10-08',3),true);
      assert.equal(editorialDayInRange('2026-10-10T16:00:00Z','2026-10-08',3),false);
      assert.equal(editorialDayInRange('2026-10-07T15:59:00Z','2026-10-08',3),false);
    } finally { if(previous===undefined)delete process.env.TZ;else process.env.TZ=previous; }
  }
});
