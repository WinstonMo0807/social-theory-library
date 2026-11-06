import assert from 'node:assert/strict';
import test from 'node:test';
import { R2MultipartUploadManager } from '../lib/r2-multipart-upload.ts';
import { r2TransferProgress } from '../lib/ingestion-staging-status.ts';

test('reopened batches use confirmed part bytes until R2 completion', () => {
  const session={staging_status:'uploading',file_size:100,completed_parts:[{size:35}]};
  assert.equal(r2TransferProgress(session),35);
  assert.equal(r2TransferProgress({...session,completed_parts:[{size:100}]}),99);
  assert.equal(r2TransferProgress({...session,staging_status:'import_failed'}),100);
  assert.equal(r2TransferProgress({...session,completed_parts:[]}),0);
});

test('busy control requests retry the same body and recheck the owner', async t => {
  const originalFetch = globalThis.fetch;
  const originalTimeout = globalThis.setTimeout;
  const calls = [];
  let requests = 0;
  globalThis.setTimeout = (callback, delay, ...args) => originalTimeout(callback, delay === 2000 ? 0 : delay, ...args);
  globalThis.fetch = async (url, options) => {
    calls.push({url:String(url), body:options?.body});
    if (String(url).includes('/auth/me/')) return new Response(JSON.stringify({id:1}), {status:200});
    requests += 1;
    return new Response(JSON.stringify(requests === 1 ? {detail:'capacity full'} : {upload_session_id:'same-session'}), {status: requests === 1 ? 429 : 200});
  };
  t.after(() => {globalThis.fetch=originalFetch;globalThis.setTimeout=originalTimeout;});
  const manager = new R2MultipartUploadManager();
  manager.bindOwner('1');
  const task = manager.newTask(new File(['%PDF'], 'test.pdf'), 'batch', 'token', '');
  const result = await manager.request(task, '/ingestion/uploads/r2/init/', {method:'POST',body:'{"client_token":"same"}'});
  assert.equal(result.upload_session_id, 'same-session');
  const uploads = calls.filter(call=>call.url.includes('/r2/init/'));
  assert.equal(uploads.length, 2);
  assert.equal(uploads[0].body, uploads[1].body);
  assert.equal(calls.filter(call=>call.url.includes('/auth/me/')).length, 3);
});

test('a resumable server session does not disguise a failed browser transfer as running', () => {
  const manager = new R2MultipartUploadManager();
  manager.bindOwner('1');
  const task = manager.newTask(new File(['%PDF'], 'test.pdf'), 'batch', 'token', 'session');
  task.status='failed';task.error='request failed';task.message='upload failed';
  manager.tasks.set(task.taskId,task);
  manager.hydrateSessions([{upload_session_id:'session',staging_status:'uploading',error_message:''}]);
  assert.equal(manager.snapshots()[0].status,'failed');
  assert.equal(manager.snapshots()[0].error,'request failed');
});
