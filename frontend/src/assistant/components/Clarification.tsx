import {useState} from 'react'
import {t} from '../../i18n'
import type {Missing} from '../types'

type Props={missing:Missing[];disabled:boolean;onSend:(text:string)=>Promise<void>}
export function Clarification({missing,disabled,onSend}:Props){
 const [opened,setOpened]=useState(false)
 const [values,setValues]=useState<Record<string,string>>({})
 async function submit(){const corrections=missing.flatMap(item=>item.fields.map(field=>t('assistant.correction_entry',{number:item.record,field,value:values[item.record+'-'+field]||''})));await onSend(t('assistant.correction_prompt',{entries:corrections.join('; ')}))}
 return <div className="clarification"><div className="missing-table"><table><thead><tr><th>{t('assistant.missing_title')}</th><th>{t('assistant.missing_fields')}</th></tr></thead><tbody>{missing.map(item=><tr key={item.record}><td>{item.label}<span className="caption">{t('assistant.record_number',{number:item.record})}</span></td><td>{item.fields.join(', ')}{item.reason&&<span className="caption">{item.reason}</span>}</td></tr>)}</tbody></table></div><div className="inline-actions"><button onClick={()=>setOpened(!opened)} disabled={disabled||!missing.some(item=>item.fields.length)}>{t('assistant.fill_missing')}</button><button onClick={()=>void onSend(t('assistant.skip_prompt'))} disabled={disabled}>{t('assistant.skip_missing')}</button></div>{opened&&<form className="correction-form" onSubmit={event=>{event.preventDefault();void submit()}}>{missing.flatMap(item=>item.fields.map(field=><label key={item.record+'-'+field}>{item.label} · {field}<input required value={values[item.record+'-'+field]||''} onChange={event=>setValues(previous=>({...previous,[item.record+'-'+field]:event.target.value}))}/></label>))}<button className="primary" disabled={disabled}>{t('assistant.continue')}</button></form>}</div>
}
