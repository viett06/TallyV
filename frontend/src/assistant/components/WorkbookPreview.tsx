import {useEffect,useState} from 'react'
import {t} from '../../i18n'
import {api} from '../api'

type Preview={kind:string;sheets:string[];sheet:string;rows:string[][];total:number;offset:number}
export function WorkbookPreview({artifactId,onError}:{artifactId:string;onError:(text:string)=>void}){
 const [sheet,setSheet]=useState(''),[offset,setOffset]=useState(0),[data,setData]=useState<Preview|null>(null)
 useEffect(()=>{let active=true;void api<Preview>('/artifacts/'+artifactId+'/preview?'+new URLSearchParams({sheet:sheet||'',offset:String(offset)})).then(result=>{if(active)setData(result)}).catch(error=>onError((error as Error).message));return()=>{active=false}},[artifactId,sheet,offset])
 if(!data)return <p>{t('assistant.loading')}</p>
 return <div className="workbook-preview"><label>{t('assistant.preview_sheet')}<select value={sheet||data.sheet} onChange={e=>{setSheet(e.target.value);setOffset(0)}}>{data.sheets.map(name=><option key={name}>{name}</option>)}</select></label><div className="task-table-scroll"><table><tbody>{data.rows.map((row,index)=><tr key={offset+index}><th>{offset+index+1}</th>{row.map((value,column)=><td key={column}>{value}</td>)}</tr>)}</tbody></table></div><div className="task-pagination"><span>{t('assistant.rows_range',{start:offset+1,end:Math.min(offset+50,data.total),total:data.total})}</span><button disabled={offset===0} onClick={()=>setOffset(Math.max(0,offset-50))}>{t('assistant.previous')}</button><button disabled={offset+50>=data.total} onClick={()=>setOffset(offset+50)}>{t('assistant.next')}</button></div></div>
}
