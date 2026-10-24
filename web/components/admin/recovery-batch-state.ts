import type { components } from "@/lib/api/generated/schema";
type Command=components["schemas"]["RecoveryConfirmInputRequest"];
export type RecoveryBatchItem={command:Command;state:"ready"|"pending"|"applied"|"cancelled"};
export type RecoveryBatchState={version:1;items:RecoveryBatchItem[]};
export const recoveryBatchKey=(owner:string)=>`stl-recovery-batch:${owner}`;
export function parseRecoveryBatch(raw:string):RecoveryBatchState{
  const value=JSON.parse(raw) as RecoveryBatchState;
  const uuid=/^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i;
  if(!value||value.version!==1||Object.keys(value).sort().join()!=="items,version"||!Array.isArray(value.items)||!value.items.length||value.items.length>20)throw Error("批量恢复记录不完整，请保留记录并核对原对象历史。");
  const objects=new Set<string>(),requests=new Set<string>();
  for(const item of value.items){
    const command=item?.command;
    if(!item||Object.keys(item).sort().join()!=="command,state"||!["ready","pending","applied","cancelled"].includes(item.state)||!command||Object.keys(command).sort().join()!=="confirmed,expected_version,kind,object_id,request_id"||!uuid.test(command.request_id)||!uuid.test(command.object_id)||!/^[a-f0-9]{64}$/.test(command.expected_version)||!/^[a-z-]{1,40}$/.test(command.kind)||command.confirmed!==true)throw Error("批量恢复的原请求字段不完整，请保留记录。");
    const key=`${command.kind}:${command.object_id}`;
    if(objects.has(key)||requests.has(command.request_id))throw Error("批量恢复记录包含重复身份，请保留记录核对。");
    objects.add(key);requests.add(command.request_id);
  }
  if(value.items.filter(item=>item.state==="pending").length>1)throw Error("批量恢复存在多个待核对请求，请保留记录核对。");
  return value;
}
