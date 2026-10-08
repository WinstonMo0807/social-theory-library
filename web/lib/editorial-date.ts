const editorialClock = new Intl.DateTimeFormat("en-CA", { timeZone:"Asia/Hong_Kong", year:"numeric", month:"2-digit", day:"2-digit", hour:"2-digit", minute:"2-digit", hourCycle:"h23" });

export function editorialLocalDateTime(value:string) {
  const parts=editorialClock.formatToParts(new Date(value));
  const part=(type:string)=>parts.find(row=>row.type===type)?.value || "";
  return `${part("year")}-${part("month")}-${part("day")}T${part("hour")}:${part("minute")}`;
}

export function editorialInstant(day:string,time="08:00") { return new Date(`${day}T${time}:00+08:00`).toISOString(); }

export function editorialShiftDay(day:string,offset:number) {
  const date=new Date(`${day}T12:00:00+08:00`);
  date.setUTCDate(date.getUTCDate()+offset);
  return editorialLocalDateTime(date.toISOString()).slice(0,10);
}

export function editorialShiftMonth(month:string,offset:number) {
  const date=new Date(`${month}-15T00:00:00Z`);
  date.setUTCMonth(date.getUTCMonth()+offset);
  return date.toISOString().slice(0,7);
}

export function editorialDayInRange(value:string|null,from:string,days:number) {
  if(!value)return false;
  const day=editorialLocalDateTime(value).slice(0,10);
  return day>=from && day<editorialShiftDay(from,days);
}
