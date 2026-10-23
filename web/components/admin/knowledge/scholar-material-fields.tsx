"use client";
import type { ScholarProfileSource } from "@/lib/api/scholars.types";
import { ManualMaterialField } from "../workflow/material-assistant";
type Values={birthYear:string;deathYear:string;description:string;biography:string;concerns:string;nationalities:string[];occupations:string[];profileSources:ScholarProfileSource[]};
export function ScholarMaterialFields({value,onChange}:{value:Values;onChange:(patch:Partial<Values>)=>void}){
  const groups=[
    {label:"生卒年",keys:["birthYear","deathYear"],labels:["出生年","逝世年"],sources:["birth_year","death_year"]},
    {label:"国籍与身份",keys:["nationalities","occupations"],labels:["国别（每行一项）","研究身份（每行一项）"],sources:["nationalities","occupations"]},
    {label:"主要领域",keys:["concerns"],labels:["关注领域（每行一项）"],sources:["key_concerns"]},
    {label:"学术简介",keys:["description","biography"],labels:["页面简介","完整传记"],sources:["short_description","biography"]},
  ];
  return <>{groups.map(group=><ManualMaterialField key={group.label} label={group.label} fields={group.keys.map((key,index)=>{const current=value[key as keyof Values];return {key,label:group.labels[index],value:Array.isArray(current)?current.join("\n"):String(current),type:group.label==="生卒年"?"number":"text",multiline:group.label!=="生卒年"};})} onChange={(key,text)=>onChange({[key]:key==="nationalities"||key==="occupations"?text.split("\n"):text})} sources={value.profileSources.filter(row=>row.fields.some(field=>group.sources.includes(field))).map(row=>({id:row.id,label:row.title,evidence:[{category:"当前草稿的来源记录",summary:row.note,url:row.url}]}))}/>)}</>;
}
