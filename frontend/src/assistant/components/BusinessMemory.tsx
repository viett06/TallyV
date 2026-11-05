import {useState} from 'react'
import {t} from '../../i18n'
import {api,json} from '../api'
import type {BusinessRule} from '../types'

export function BusinessMemory({onError}:{onError:(error:unknown)=>void}){
 const [rules,setRules]=useState<BusinessRule[]>([]),[busy,setBusy]=useState(false)
 async function load(){try{setRules(await api<BusinessRule[]>('/rules'))}catch(error){onError(error)}}
 async function retire(rule:BusinessRule){setBusy(true);try{await api('/rules/'+rule.id+'/retire',{method:'POST',body:json({version:rule.version})});await load()}catch(error){onError(error)}finally{setBusy(false)}}
 return <details className="business-memory" onToggle={event=>{if(event.currentTarget.open)void load()}}><summary>{t('assistant.memory')}</summary><p className="caption">{t('assistant.memory_scope')}</p>{rules.length?rules.map(rule=><div className="memory-rule" key={rule.id}><strong>{rule.source_value}</strong><span>{rule.source_column} → {rule.category}</span><button disabled={busy} onClick={()=>void retire(rule)}>{t('assistant.retire_rule')}</button></div>):<p className="caption">{t('assistant.memory_empty')}</p>}</details>
}
