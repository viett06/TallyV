import {useCallback,useEffect,useRef,useState} from 'react'
import {ArrowUp,ChevronDown,FileText,Folder,MessageSquare,Plus,Sparkles,X,Mail,LoaderCircle,PanelLeft} from 'lucide-react'
import {t} from '../i18n'
import {api,ApiError,json} from './api'
import './assistant.css'
import {ArtifactPanel} from './components/ArtifactPanel'
import {BusinessMemory} from './components/BusinessMemory'
import {Clarification} from './components/Clarification'
import {ResultCard} from './components/ResultCard'
import {TaskPanel,TaskPlan,TaskProgress} from './components/TaskPanel'
import type {Attachment,Capabilities,Conversation,Detail,Message,Run,Upload} from './types'

type Mode='auto'|'documents'|'data'

export function AssistantWorkspace({onSessionExpired}:{onSessionExpired:()=>void}){
 const [cap,setCap]=useState<Capabilities|null>(null)
 const [conversations,setConversations]=useState<Conversation[]>([])
 const [selected,setSelected]=useState<string|null>(()=>new URLSearchParams(location.search).get('chat'))
 const [detail,setDetail]=useState<Detail|null>(null)
 const [uploads,setUploads]=useState<Upload[]>([]),[draft,setDraft]=useState(''),[mode,setMode]=useState<Mode>('auto')
 const [sending,setSending]=useState(false),[error,setError]=useState(''),[artifactId,setArtifactId]=useState<string|null>(null)
 const [attachMenu,setAttachMenu]=useState(false),[sidebarOpen,setSidebarOpen]=useState(false),[dragover,setDragover]=useState(false)
 const selectedRef=useRef<string|null>(selected),fileInput=useRef<HTMLInputElement>(null),bottom=useRef<HTMLDivElement>(null)
 const busy=sending||!!detail?.runs.some(run=>['QUEUED','RUNNING'].includes(run.status))
 const activeArtifact=detail?.runs.flatMap(run=>run.artifacts).find(artifact=>artifact.id===artifactId)
 const latestRun=detail?.runs.at(-1)

 function handleError(value:unknown){
  if(value instanceof ApiError&&value.status===401){onSessionExpired();selectedRef.current=null;setSelected(null);setDetail(null)}
  setError(value instanceof Error?value.message:String(value))
 }
 useEffect(()=>{void api<Capabilities>('/capabilities').then(setCap).catch(handleError);void api<Conversation[]>('/conversations').then(setConversations).catch(handleError)},[])
 const refresh=useCallback(async()=>{const id=selectedRef.current;if(!id)return;const result=await api<Detail>('/conversations/'+id);if(id===selectedRef.current)setDetail(result)},[])
 useEffect(()=>{if(selected)void refresh().catch(handleError)},[selected,refresh])
 useEffect(()=>{if(!selected||!detail?.runs.some(run=>['QUEUED','RUNNING'].includes(run.status)))return;const timer=setInterval(()=>{void refresh().catch(handleError)},1400);return()=>clearInterval(timer)},[selected,detail?.runs,refresh])
 useEffect(()=>{bottom.current?.scrollIntoView({block:'end',behavior:'smooth'})},[detail?.messages.length,latestRun?.status,sending])
 function setChatAddress(id:string|null){const url=new URL(location.href);if(id)url.searchParams.set('chat',id);else url.searchParams.delete('chat');history.replaceState(null,'',url)}
 async function ensureConversation(){if(selectedRef.current)return selectedRef.current;const conversation=await api<Conversation>('/conversations',{method:'POST'});selectedRef.current=conversation.id;setChatAddress(conversation.id);setSelected(conversation.id);setConversations(list=>[conversation,...list]);return conversation.id}
 function chooseChat(id:string|null){setChatAddress(id);selectedRef.current=id;setSelected(id);setDetail(null);setUploads([]);setDraft('');setMode('auto');setArtifactId(null);setError('');setSidebarOpen(false)}
 async function send(textOverride?:string){
  const text=(textOverride??draft).trim();if(!text||busy)return;setSending(true);setError('')
  try{
   const id=await ensureConversation(),attachmentIds:string[]=[]
   if(!textOverride){for(const upload of uploads){if(upload.uploaded){attachmentIds.push(upload.uploaded.id);continue}const data=new FormData();data.set('role',upload.role);data.set('file',upload.file!);const attachment=await api<Attachment>('/conversations/'+id+'/attachments',{method:'POST',body:data});attachmentIds.push(attachment.id);setUploads(list=>list.map(item=>item.key===upload.key?{...item,uploaded:attachment}:item))}}
   await api('/conversations/'+id+'/messages',{method:'POST',body:json({text,attachment_ids:attachmentIds,request_key:crypto.randomUUID(),task_mode:mode})})
   if(id===selectedRef.current){setDraft('');setUploads([]);await refresh();setConversations(await api<Conversation[]>('/conversations'))}
  }catch(value){handleError(value)}finally{setSending(false)}
 }
 async function demo(kind:'data'|'documents'='data',missing=false,plain=false){
  if(busy)return;setSending(true);setError('')
  try{const id=await ensureConversation();const path=kind==='data'?'/demo-data':`/demo?missing=${missing}&plain_template=${plain}`;const result=await api<{attachments:Attachment[];prompt:string}>(`/conversations/${id}${path}`,{method:'POST'});if(id===selectedRef.current){setUploads(result.attachments.map(item=>({key:item.id,name:item.name,role:item.role,uploaded:item})));setDraft(result.prompt);setMode(kind);setAttachMenu(false);await refresh()}}
  catch(value){handleError(value)}finally{setSending(false)}
 }
 function addFiles(files:File[]){
  if(busy)return;setError('');const next=[...uploads]
  for(const file of files){if(next.length>=6){setError(t('assistant.file_limit'));break}if(file.size>15*1024*1024){setError(t('assistant.file_size'));continue}if(!/\.(xlsx|csv|txt|docx|pdf)$/i.test(file.name)){setError(t('assistant.file_formats'));continue}const role:Upload['role']=/mau|mẫu|template/i.test(file.name)?'template':/\.(xlsx|csv|pdf)$/i.test(file.name)?'data':!next.some(item=>item.role==='template')?'template':'data';next.push({key:crypto.randomUUID(),file,name:file.name,role})}
  setUploads(next);setAttachMenu(false)
 }
 async function retry(run:Run){if(!selected||busy)return;setError('');try{await api(`/conversations/${selected}/runs/${run.id}/retry`,{method:'POST'});await refresh()}catch(value){handleError(value)}}
 async function cancel(run:Run){if(!selected)return;try{await api(`/conversations/${selected}/runs/${run.id}/cancel`,{method:'POST'});await refresh()}catch(value){handleError(value)}}
 function results(run:Run){return <><ResultCard run={run} onOpen={artifact=>setArtifactId(artifact.id)}/>{run.kind==='DATA_TASK'?<TaskPanel run={run} conversationId={selected!} disabled={busy} onUpdated={refresh} onError={handleError}/>:<div className="inline-actions"><button onClick={()=>void send(t('assistant.email_prompt'))} disabled={busy}><Mail/>{t('assistant.email_create')}</button><a href={'/api/assistant/runs/'+run.id+'/download?kind=csv'} className="text-link">{t('assistant.process_report')}</a></div>}<p className="caption result-note">{t('assistant.result_note')}</p></>}
 function renderMessage(item:Message){
  const run=detail?.runs.find(candidate=>candidate.id===item.details.run_id),older=run&&run.id!==latestRun?.id
  return <article className={item.role==='user'?'message user-message':'message assistant-message'} key={item.id}>
   {item.role==='assistant'&&<span className="assistant-mark"><Sparkles/></span>}
   <div className="message-body">
    {!!item.details.attachment_ids?.length&&<div className="user-files">{item.details.attachment_ids.map(id=>{const attachment=detail?.attachments.find(file=>file.id===id);return attachment&&<div className="mini-file" key={id}><FileText/><span>{attachment.name}<small>{t(attachment.role==='template'?'assistant.file_template':'assistant.file_data')}</small></span></div>})}</div>}
    <div className={item.role==='user'?'user-bubble':'assistant-text'}>{item.content}</div>
    {run&&<details className="processing-detail"><summary>{t('assistant.details')}<ChevronDown/></summary>{run.kind==='DATA_TASK'?<TaskPlan run={run}/>:<pre>{JSON.stringify(run.plan,null,2)}</pre>}</details>}
    {run?.status==='COMPLETED'&&item.details.kind==='results'&&(older?<details className="older-results"><summary>{t('assistant.previous_results',{count:run.artifacts.length})}</summary>{results(run)}</details>:results(run))}
    {run?.kind==='DATA_TASK'&&item.details.kind==='task_input'&&<TaskPanel run={run} conversationId={selected!} disabled={busy} onUpdated={refresh} onError={handleError}/>}
    {!!item.details.missing?.length&&run?.status==='NEEDS_INPUT'&&!older&&<Clarification missing={item.details.missing} disabled={busy} onSend={send}/>}
    {run?.status==='FAILED'&&item.details.kind==='error'&&<button className="retry" onClick={()=>void retry(run)} disabled={busy}>{t('assistant.retry')}</button>}
   </div>
  </article>
 }
 return <div className={'assistant-workspace assistant-layout '+(activeArtifact?'with-artifact ':'')+(sidebarOpen?'history-open':'')}>
  <aside className="assistant-history"><div className="history-title"><FileText/>{t('assistant.workspace')}</div><button className="new-chat" onClick={()=>chooseChat(null)}><Plus/>{t('assistant.new_chat')}</button><div className="sidebar-heading">{t('assistant.history')}</div><nav aria-label={t('assistant.history')}>{conversations.length?conversations.map(conversation=><button key={conversation.id} className={'conversation-link '+(selected===conversation.id?'selected':'')} onClick={()=>chooseChat(conversation.id)}><MessageSquare/><span>{conversation.title}</span></button>):<p className="caption empty-history">{t('assistant.empty_history')}</p>}</nav><BusinessMemory onError={handleError}/><div className="history-footer"><p>{t('assistant.history_note')}</p></div></aside>
  {sidebarOpen&&<button className="sidebar-backdrop" aria-label={t('assistant.history_close')} onClick={()=>setSidebarOpen(false)}/>}
  <section className="chat-stage"><header className="chat-header"><div className="header-title"><button className="history-toggle icon-button" aria-label={t('assistant.history_open')} onClick={()=>setSidebarOpen(!sidebarOpen)}><PanelLeft/></button><span>{t('assistant.workspace')}</span><span className="badge">MVP</span></div><div className="header-meta"><span className="local-dot"/>{!cap?t('assistant.loading'):t(cap.processing_mode==='LOCAL_LLM'?'assistant.local_ai':'assistant.rules_mode')}<details><summary><span className="badge subtle">{t('assistant.info')}</span></summary><div className="capabilities-popup"><strong>{cap?.orchestrator||t('assistant.loading')}</strong><p>{t('assistant.formats')}</p><p>{t('assistant.limits',{rows:cap?.data_limits?.rows||10000})}</p><p>{t('assistant.draft_note')}</p></div></details></div></header>
  {error&&<div className="error-banner" role="alert"><span>{error}</span><button className="icon-button" aria-label={t('assistant.error_close')} onClick={()=>setError('')}><X/></button></div>}
  <div className={'messages-scroll '+(!detail?.messages.length?'empty-chat':'')}><div className="messages-inner">
   {!detail?.messages.length?<div className="empty-hero"><span className="hero-mark"><Sparkles/></span><h1>{t('assistant.hero_title')}</h1><p>{t('assistant.hero_description')}</p><div className="suggestions"><button onClick={()=>{setMode('data');setDraft(t('assistant.prompt_statistics'))}}><Folder/>{t('assistant.suggest_statistics')}</button><button onClick={()=>{setMode('documents');setDraft(t('assistant.prompt_document'))}}><FileText/>{t('assistant.suggest_document')}</button></div></div>:detail.messages.map(renderMessage)}
   {busy&&<article className="message assistant-message processing" aria-live="polite"><span className="assistant-mark"><Sparkles/></span><div className="message-body">{latestRun?.kind==='DATA_TASK'&&!sending?<TaskProgress run={latestRun} disabled={sending} onCancel={()=>void cancel(latestRun)}/>:<p><LoaderCircle className="spin"/>{t(sending?'assistant.sending':'assistant.processing')}</p>}<span className="caption">{t('assistant.waiting_model')}{latestRun?.job?.attempts&&latestRun.job.attempts>1?' '+t('assistant.retrying'):''}</span></div></article>}
   <div ref={bottom}/>
  </div></div>
  <div className={'composer-zone '+(!detail?.messages.length?'initial-composer':'')}><form className={'composer '+(dragover?'dragover':'')} onSubmit={event=>{event.preventDefault();void send()}} onDragOver={event=>{event.preventDefault();setDragover(true)}} onDragLeave={()=>setDragover(false)} onDrop={event=>{event.preventDefault();setDragover(false);addFiles(Array.from(event.dataTransfer.files))}}>
   {!!uploads.length&&<div className="attachment-list">{uploads.map(item=><div className="attachment-chip" key={item.key}><span className={'file-label '+item.role}>{item.name.split('.').at(-1)?.toUpperCase()}</span><div><strong>{item.name}</strong>{item.uploaded?<span className="caption">{t(item.role==='template'?'assistant.file_template':'assistant.file_data')}</span>:<label><span className="sr-only">{t('assistant.file_role',{name:item.name})}</span><select value={item.role} onChange={event=>setUploads(list=>list.map(file=>file.key===item.key?{...file,role:event.target.value as Upload['role']}:file))}><option value="template">{t('assistant.file_template')}</option><option value="data">{t('assistant.file_data')}</option></select></label>}</div><button type="button" className="remove-file" aria-label={t('assistant.file_remove',{name:item.name})} disabled={busy} onClick={()=>setUploads(list=>list.filter(file=>file.key!==item.key))}><X/></button></div>)}</div>}
   <label className="sr-only" htmlFor="prompt">{t('assistant.prompt_label')}</label><textarea id="prompt" placeholder={t(detail?.messages.length?'assistant.prompt_followup':'assistant.prompt_placeholder')} value={draft} onChange={event=>setDraft(event.target.value)} disabled={busy} rows={2} onKeyDown={event=>{if(event.key==='Enter'&&!event.shiftKey&&!event.nativeEvent.isComposing){event.preventDefault();void send()}}}/>
   <div className="composer-tools"><div><button className="attach-button icon-button" type="button" aria-label={t('assistant.attach')} aria-expanded={attachMenu} disabled={busy} onClick={()=>setAttachMenu(!attachMenu)}><Plus/></button><select className="task-mode" aria-label={t('assistant.mode')} value={mode} disabled={busy} onChange={event=>setMode(event.target.value as Mode)}><option value="auto">{t('assistant.mode_auto')}</option><option value="data">{t('assistant.mode_data')}</option><option value="documents">{t('assistant.mode_documents')}</option></select></div><button className="send-button" type="submit" aria-label={t('assistant.send')} disabled={busy||!draft.trim()}><ArrowUp/></button></div>
   {attachMenu&&<div className="attachment-menu"><button type="button" onClick={()=>fileInput.current?.click()}>{t('assistant.choose_files')}</button><button type="button" onClick={()=>void demo('data')}>{t('assistant.demo_data')}</button><button type="button" onClick={()=>void demo('documents')}>{t('assistant.demo_documents')}</button></div>}
   <input type="file" ref={fileInput} multiple accept=".xlsx,.csv,.txt,.docx,.pdf" hidden onChange={event=>{addFiles(Array.from(event.target.files||[]));event.target.value=''}}/>
  </form><p className="composer-foot">{t('assistant.draft_note')}</p>{!detail?.messages.length&&<div className="demo-links"><span>{t('assistant.demo_label')}</span><button disabled={busy} onClick={()=>void demo('data')}>{t('assistant.demo_data')}</button><button disabled={busy} onClick={()=>void demo('documents')}>{t('assistant.demo_documents')}</button><button disabled={busy} onClick={()=>void demo('documents',true)}>{t('assistant.demo_missing')}</button></div>}</div>
  </section>
  {activeArtifact&&<ArtifactPanel artifact={activeArtifact} conversationId={selected!} onClose={()=>setArtifactId(null)} onUpdated={refresh} onError={setError}/>}
 </div>
}
