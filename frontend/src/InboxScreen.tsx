import { useState } from 'react'
import {
  ActionIcon,
  Alert,
  Badge,
  Button,
  Group,
  Loader,
  Paper,
  SegmentedControl,
  Select,
  Stack,
  Text,
  TextInput,
  Tooltip,
  UnstyledButton,
} from '@mantine/core'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  IconCheck,
  IconPaperclip,
  IconRefresh,
  IconSearch,
  IconSettings,
} from '@tabler/icons-react'
import { PageHead, formatDateTime, useT, useToast } from '@hubra/plugin-sdk'
import {
  downloadAttachment,
  getMessage,
  listMailboxes,
  listMessages,
  setMessageDone,
  syncMailbox,
  type Message,
} from './api'
import { MailboxSettings } from './MailboxSettings'

type Filter = 'open' | 'done' | 'all'

export function InboxScreen() {
  const { t } = useT()
  const { notify } = useToast()
  const queryClient = useQueryClient()
  const [mailboxId, setMailboxId] = useState<number | null>(null)
  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState<Filter>('open')
  const [selected, setSelected] = useState<number | null>(null)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [syncing, setSyncing] = useState(false)

  const { data: boxes } = useQuery({ queryKey: ['inbox-mailboxes'], queryFn: listMailboxes })
  const mailboxes = boxes?.mailboxes ?? []
  const done = filter === 'all' ? undefined : filter === 'done'
  const { data: messages = [], isLoading } = useQuery({
    queryKey: ['inbox-messages', mailboxId, search, filter],
    queryFn: () => listMessages({ mailboxId, q: search.trim() || undefined, done }),
  })
  const { data: message } = useQuery({
    queryKey: ['inbox-message', selected],
    queryFn: () => getMessage(selected as number),
    enabled: selected !== null,
  })

  const fail = (err: unknown) =>
    notify('error', t('common.error'), err instanceof Error ? err.message : String(err))

  const refresh = async () => {
    await queryClient.invalidateQueries({ queryKey: ['inbox-mailboxes'] })
    await queryClient.invalidateQueries({ queryKey: ['inbox-messages'] })
  }

  const syncNow = async () => {
    const targets = mailboxId ? mailboxes.filter((m) => m.id === mailboxId) : mailboxes
    setSyncing(true)
    try {
      let fetched = 0
      for (const m of targets) {
        const r = await syncMailbox(m.id)
        if (r.error) notify('error', m.name, r.error)
        fetched += r.fetched ?? 0
      }
      await refresh()
      notify('success', t('inbox.synced', '{{count}} new messages', { count: fetched }))
    } catch (err) {
      fail(err)
    } finally {
      setSyncing(false)
    }
  }

  const toggleDone = async (m: Message) => {
    try {
      await setMessageDone(m.id, !m.done)
      await queryClient.invalidateQueries({ queryKey: ['inbox-message', m.id] })
      await refresh()
    } catch (err) {
      fail(err)
    }
  }

  const errors = mailboxes.filter((m) => m.lastError)

  return (
    <Stack gap="md">
      <PageHead
        title={t('inbox.title', 'Shared inbox')}
        desc={t(
          'inbox.desc',
          'Mail of the club mailboxes, read-only. Replies are sent from your usual mail program.',
        )}
        actions={
          <Group gap="xs">
            <Button
              variant="default"
              leftSection={<IconRefresh size={16} />}
              loading={syncing}
              disabled={mailboxes.length === 0}
              onClick={syncNow}
            >
              {t('inbox.syncNow', 'Sync now')}
            </Button>
            {boxes?.canManage && (
              <Button
                variant="default"
                leftSection={<IconSettings size={16} />}
                onClick={() => setSettingsOpen(true)}
              >
                {t('inbox.mailboxes', 'Mailboxes')}
              </Button>
            )}
          </Group>
        }
      />

      {errors.map((m) => (
        <Alert key={m.id} color="red" variant="light" title={m.name}>
          {m.lastError}
        </Alert>
      ))}

      {boxes && mailboxes.length === 0 ? (
        <Paper withBorder radius="lg" p="xl">
          <Text fw={600}>{t('inbox.emptyTitle', 'No mailbox yet')}</Text>
          <Text fz="sm" c="dimmed">
            {boxes.canManage
              ? t(
                  'inbox.emptyManage',
                  'Add the club mailbox (for example info@) under Mailboxes. Hubra reads it without changing anything on the server.',
                )
              : t('inbox.emptyMember', 'No mailbox is shared with your groups yet.')}
          </Text>
        </Paper>
      ) : (
        <Group align="flex-start" gap="md" wrap="nowrap" style={{ minHeight: 480 }}>
          <Paper withBorder radius="lg" p="sm" style={{ width: 380, flexShrink: 0 }}>
            <Stack gap="xs">
              <Select
                size="xs"
                data={[
                  { value: '', label: t('inbox.allMailboxes', 'All mailboxes') },
                  ...mailboxes.map((m) => ({
                    value: String(m.id),
                    label: m.unread ? `${m.name} (${m.unread})` : m.name,
                  })),
                ]}
                value={mailboxId ? String(mailboxId) : ''}
                onChange={(v) => {
                  setMailboxId(v ? Number(v) : null)
                  setSelected(null)
                }}
                allowDeselect={false}
              />
              <TextInput
                size="xs"
                leftSection={<IconSearch size={14} />}
                placeholder={t('inbox.search', 'Search subject, sender, text')}
                value={search}
                onChange={(e) => setSearch(e.currentTarget.value)}
              />
              <SegmentedControl
                size="xs"
                value={filter}
                onChange={(v) => setFilter(v as Filter)}
                data={[
                  { value: 'open', label: t('inbox.open', 'Open') },
                  { value: 'done', label: t('inbox.done', 'Done') },
                  { value: 'all', label: t('inbox.all', 'All') },
                ]}
              />
              {isLoading && <Loader size="sm" />}
              {!isLoading && messages.length === 0 && (
                <Text fz="sm" c="dimmed" ta="center" py="md">
                  {t('inbox.noMessages', 'No messages')}
                </Text>
              )}
              <Stack gap={2} style={{ maxHeight: 640, overflowY: 'auto' }}>
                {messages.map((m) => (
                  <UnstyledButton
                    key={m.id}
                    onClick={() => setSelected(m.id)}
                    p="xs"
                    style={{
                      borderRadius: 8,
                      background:
                        selected === m.id ? 'var(--mantine-color-default-hover)' : undefined,
                    }}
                  >
                    <Group justify="space-between" gap={4} wrap="nowrap">
                      <Text fz="sm" fw={m.done ? 400 : 600} truncate>
                        {m.fromName || m.fromAddress || '—'}
                      </Text>
                      <Text fz="xs" c="dimmed" style={{ flexShrink: 0 }}>
                        {m.sentAt ? formatDateTime(m.sentAt) : ''}
                      </Text>
                    </Group>
                    <Group gap={4} wrap="nowrap">
                      {m.hasAttachments && <IconPaperclip size={12} />}
                      <Text fz="sm" truncate>
                        {m.subject || t('inbox.noSubject', '(no subject)')}
                      </Text>
                    </Group>
                    <Text fz="xs" c="dimmed" truncate>
                      {m.preview}
                    </Text>
                  </UnstyledButton>
                ))}
              </Stack>
            </Stack>
          </Paper>

          <Paper withBorder radius="lg" p="lg" style={{ flex: 1, minWidth: 0 }}>
            {message ? (
              <MessageView
                message={message}
                onToggleDone={() => toggleDone(message)}
                onError={fail}
              />
            ) : (
              <Text c="dimmed" ta="center" py="xl">
                {t('inbox.pick', 'Pick a message')}
              </Text>
            )}
          </Paper>
        </Group>
      )}

      {boxes?.canManage && (
        <MailboxSettings
          open={settingsOpen}
          onClose={() => setSettingsOpen(false)}
          mailboxes={mailboxes}
          onChanged={refresh}
        />
      )}
    </Stack>
  )
}

function MessageView({
  message,
  onToggleDone,
  onError,
}: {
  message: Message
  onToggleDone: () => void
  onError: (err: unknown) => void
}) {
  const { t } = useT()
  const thread = message.thread.length > 1 ? message.thread : [message]
  return (
    <Stack gap="md">
      <Group justify="space-between" align="flex-start" wrap="nowrap">
        <Text fw={700} fz="lg">
          {message.subject || t('inbox.noSubject', '(no subject)')}
        </Text>
        <Tooltip
          label={message.done ? t('inbox.reopen', 'Mark open') : t('inbox.markDone', 'Mark done')}
        >
          <ActionIcon
            variant={message.done ? 'filled' : 'default'}
            color="green"
            onClick={onToggleDone}
            aria-label={t('inbox.markDone', 'Mark done')}
          >
            <IconCheck size={16} />
          </ActionIcon>
        </Tooltip>
      </Group>
      {thread.map((m) => (
        <Stack
          key={m.id}
          gap={6}
          style={{ borderTop: '1px solid var(--mantine-color-default-border)', paddingTop: 10 }}
        >
          <Group justify="space-between" gap="xs">
            <Text fz="sm" fw={600}>
              {m.fromName ? `${m.fromName} <${m.fromAddress}>` : m.fromAddress}
            </Text>
            <Text fz="xs" c="dimmed">
              {m.sentAt ? formatDateTime(m.sentAt) : ''}
            </Text>
          </Group>
          {m.to && (
            <Text fz="xs" c="dimmed">
              {t('inbox.to', 'To')}: {m.to}
              {m.cc ? ` · Cc: ${m.cc}` : ''}
            </Text>
          )}
          {m.truncated && (
            <Badge color="orange" variant="light">
              {t('inbox.truncated', 'Too large to show here; open it in your mail program')}
            </Badge>
          )}
          <MessageBody message={m} />
          {m.attachments.length > 0 && (
            <Group gap="xs">
              {m.attachments.map((a) => (
                <Button
                  key={a.index}
                  size="xs"
                  variant="default"
                  leftSection={<IconPaperclip size={12} />}
                  onClick={() => downloadAttachment(m.id, a).catch(onError)}
                >
                  {a.filename} · {Math.max(1, Math.round(a.size / 1024))} KB
                </Button>
              ))}
            </Group>
          )}
        </Stack>
      ))}
    </Stack>
  )
}

// The sandbox (no allow-scripts) and the CSP keep scripts from running and
// block remote content; same-origin only lets the app read the height.
// Links open in a new tab.
const FRAME_HEAD =
  '<meta charset="utf-8"><meta http-equiv="Content-Security-Policy" ' +
  "content=\"default-src 'none'; img-src data:; style-src 'unsafe-inline'\">" +
  '<base target="_blank"><style>body{font:14px/1.5 system-ui,sans-serif;margin:0;' +
  'word-wrap:break-word}img{max-width:100%;height:auto}</style>'

function MessageBody({ message }: { message: Message }) {
  const [height, setHeight] = useState(240)
  if (message.html) {
    return (
      <iframe
        title={message.subject ?? 'mail'}
        sandbox="allow-popups allow-popups-to-escape-sandbox allow-same-origin"
        srcDoc={FRAME_HEAD + message.html}
        style={{ width: '100%', height, border: 0 }}
        onLoad={(e) => {
          const doc = e.currentTarget.contentDocument
          if (doc) setHeight(Math.min(2000, doc.documentElement.scrollHeight + 16))
        }}
      />
    )
  }
  return (
    <Text fz="sm" style={{ whiteSpace: 'pre-wrap' }}>
      {message.text}
    </Text>
  )
}
