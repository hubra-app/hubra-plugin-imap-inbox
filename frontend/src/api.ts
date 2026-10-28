import { apiFetch, apiFetchRaw } from '@hubra/plugin-sdk'

export type Security = 'ssl' | 'starttls'

export interface Mailbox {
  id: number
  name: string
  groupId: number | null
  groupName: string | null
  active: boolean
  lastSyncAt: string | null
  lastError: string | null
  unread: number
  // Only for people who manage mailboxes:
  host?: string
  port?: number
  security?: Security
  username?: string
  hasPassword?: boolean
  folders?: string[]
  markSeen?: boolean
  retentionDays?: number
}

export interface MailboxInput {
  name: string
  host: string
  port: number
  security: Security
  username: string
  password?: string
  folders: string[]
  groupId: number | null
  markSeen: boolean
  active: boolean
  retentionDays: number
}

export interface MessageSummary {
  id: number
  mailboxId: number
  folder: string
  subject: string | null
  fromName: string | null
  fromAddress: string | null
  sentAt: string | null
  hasAttachments: boolean
  done: boolean
  preview: string
}

export interface Attachment {
  index: number
  filename: string
  contentType: string
  size: number
}

export interface Message extends MessageSummary {
  to: string | null
  cc: string | null
  text: string | null
  html: string | null
  attachments: Attachment[]
  truncated: boolean
  thread: Message[]
}

export interface GroupOption {
  id: number
  name: string
}

export const listMailboxes = () =>
  apiFetch<{ canManage: boolean; mailboxes: Mailbox[] }>('/inbox/mailboxes')

export const createMailbox = (input: MailboxInput) =>
  apiFetch<Mailbox>('/inbox/mailboxes', { method: 'POST', body: JSON.stringify(input) })

export const updateMailbox = (id: number, input: Partial<MailboxInput>) =>
  apiFetch<Mailbox>(`/inbox/mailboxes/${id}`, { method: 'PATCH', body: JSON.stringify(input) })

export const deleteMailbox = (id: number) =>
  apiFetch<void>(`/inbox/mailboxes/${id}`, { method: 'DELETE' })

export const testMailbox = (input: Partial<MailboxInput> & { mailboxId?: number }) =>
  apiFetch<{ ok: boolean; folders?: string[]; error?: string }>('/inbox/mailboxes/test', {
    method: 'POST',
    body: JSON.stringify(input),
  })

export const syncMailbox = (id: number) =>
  apiFetch<{ fetched?: number; error?: string | null; mailbox: Mailbox }>(
    `/inbox/mailboxes/${id}/sync`,
    { method: 'POST' },
  )

export function listMessages(params: { mailboxId?: number | null; q?: string; done?: boolean }) {
  const qs = new URLSearchParams()
  if (params.mailboxId) qs.set('mailbox_id', String(params.mailboxId))
  if (params.q) qs.set('q', params.q)
  if (params.done !== undefined) qs.set('done', params.done ? '1' : '0')
  qs.set('limit', '100')
  return apiFetch<MessageSummary[]>(`/inbox/messages?${qs}`)
}

export const getMessage = (id: number) => apiFetch<Message>(`/inbox/messages/${id}`)

export const setMessageDone = (id: number, done: boolean) =>
  apiFetch<MessageSummary>(`/inbox/messages/${id}`, {
    method: 'PATCH',
    body: JSON.stringify({ done }),
  })

export async function downloadAttachment(messageId: number, att: Attachment) {
  const res = await apiFetchRaw(`/inbox/messages/${messageId}/attachments/${att.index}`)
  const url = URL.createObjectURL(await res.blob())
  const a = document.createElement('a')
  a.href = url
  a.download = att.filename
  a.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export const listGroupOptions = () => apiFetch<GroupOption[]>('/groups')
