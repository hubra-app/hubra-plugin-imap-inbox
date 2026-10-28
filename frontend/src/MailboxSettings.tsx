import { useState } from 'react'
import {
  Alert,
  Button,
  Group,
  MultiSelect,
  NumberInput,
  PasswordInput,
  Select,
  Stack,
  Switch,
  Table,
  Text,
  TextInput,
} from '@mantine/core'
import { useQuery } from '@tanstack/react-query'
import { IconPlus } from '@tabler/icons-react'
import { ConfirmModal, Field, Modal, useT, useToast } from '@hubra/plugin-sdk'
import {
  createMailbox,
  deleteMailbox,
  listGroupOptions,
  testMailbox,
  updateMailbox,
  type Mailbox,
  type MailboxInput,
} from './api'

const EMPTY: MailboxInput = {
  name: '',
  host: '',
  port: 993,
  security: 'ssl',
  username: '',
  password: '',
  folders: ['INBOX'],
  groupId: null,
  markSeen: false,
  active: true,
  retentionDays: 180,
}

function toInput(m: Mailbox): MailboxInput {
  return {
    name: m.name,
    host: m.host ?? '',
    port: m.port ?? 993,
    security: m.security ?? 'ssl',
    username: m.username ?? '',
    password: '',
    folders: m.folders ?? ['INBOX'],
    groupId: m.groupId,
    markSeen: m.markSeen ?? false,
    active: m.active,
    retentionDays: m.retentionDays ?? 180,
  }
}

export function MailboxSettings({
  open,
  onClose,
  mailboxes,
  onChanged,
}: {
  open: boolean
  onClose: () => void
  mailboxes: Mailbox[]
  onChanged: () => Promise<void>
}) {
  const { t } = useT()
  const { notify } = useToast()
  const [editing, setEditing] = useState<Mailbox | 'new' | null>(null)
  const [form, setForm] = useState<MailboxInput>(EMPTY)
  const [folders, setFolders] = useState<string[]>([])
  const [testResult, setTestResult] = useState<{ ok: boolean; text: string } | null>(null)
  const [busy, setBusy] = useState(false)
  const [deleting, setDeleting] = useState<Mailbox | null>(null)
  const { data: groups = [] } = useQuery({
    queryKey: ['inbox-groups'],
    queryFn: listGroupOptions,
    enabled: open,
  })

  const edit = (m: Mailbox | 'new') => {
    setEditing(m)
    setForm(m === 'new' ? EMPTY : toInput(m))
    setFolders(m === 'new' ? [] : (m.folders ?? []))
    setTestResult(null)
  }

  const fail = (err: unknown) =>
    notify('error', t('common.error'), err instanceof Error ? err.message : String(err))

  const savedId = editing && editing !== 'new' ? editing.id : undefined
  const serverChanged =
    editing !== null &&
    editing !== 'new' &&
    (form.host !== editing.host ||
      form.port !== editing.port ||
      form.security !== editing.security ||
      form.username !== editing.username)
  const needsPassword = editing === 'new' || serverChanged

  const runTest = async () => {
    setBusy(true)
    try {
      const r = await testMailbox(
        form.password ? { ...form, mailboxId: savedId } : { mailboxId: savedId },
      )
      if (r.ok) {
        setFolders(r.folders ?? [])
        setTestResult({
          ok: true,
          text: t('inbox.testOk', 'Connected. {{count}} folders found.', {
            count: r.folders?.length ?? 0,
          }),
        })
      } else {
        setTestResult({ ok: false, text: r.error ?? '' })
      }
    } catch (err) {
      fail(err)
    } finally {
      setBusy(false)
    }
  }

  const save = async () => {
    setBusy(true)
    try {
      const body: Partial<MailboxInput> = { ...form }
      if (!body.password) delete body.password
      if (editing === 'new') await createMailbox(body as MailboxInput)
      else if (editing) await updateMailbox(editing.id, body)
      await onChanged()
      setEditing(null)
    } catch (err) {
      fail(err)
    } finally {
      setBusy(false)
    }
  }

  const folderOptions = Array.from(new Set([...folders, ...form.folders]))
  const canSave =
    form.name.trim() &&
    form.host.trim() &&
    form.username.trim() &&
    (!needsPassword || Boolean(form.password))

  return (
    <>
      <Modal
        open={open && editing === null}
        onClose={onClose}
        title={t('inbox.mailboxes', 'Mailboxes')}
        wide
        footer={
          <Button leftSection={<IconPlus size={16} />} onClick={() => edit('new')}>
            {t('inbox.addMailbox', 'Add mailbox')}
          </Button>
        }
      >
        {mailboxes.length === 0 ? (
          <Text c="dimmed" fz="sm">
            {t('inbox.noMailboxes', 'No mailbox set up yet.')}
          </Text>
        ) : (
          <Table fz="sm" verticalSpacing={6}>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>{t('inbox.name', 'Name')}</Table.Th>
                <Table.Th>{t('inbox.account', 'Account')}</Table.Th>
                <Table.Th>{t('inbox.visibleTo', 'Visible to')}</Table.Th>
                <Table.Th>{t('inbox.lastSync', 'Last sync')}</Table.Th>
                <Table.Th />
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {mailboxes.map((m) => (
                <Table.Tr key={m.id}>
                  <Table.Td>{m.name}</Table.Td>
                  <Table.Td>
                    {m.username} @ {m.host}
                  </Table.Td>
                  <Table.Td>
                    {m.groupName ?? t('inbox.managersOnly', 'Inbox managers only')}
                  </Table.Td>
                  <Table.Td c={m.lastError ? 'red' : undefined}>
                    {m.lastError
                      ? t('inbox.failed', 'Failed')
                      : m.lastSyncAt
                        ? new Date(m.lastSyncAt).toLocaleString()
                        : '—'}
                  </Table.Td>
                  <Table.Td>
                    <Group gap={4} justify="flex-end" wrap="nowrap">
                      <Button size="xs" variant="default" onClick={() => edit(m)}>
                        {t('common.edit', 'Edit')}
                      </Button>
                      <Button size="xs" variant="subtle" color="red" onClick={() => setDeleting(m)}>
                        {t('common.delete', 'Delete')}
                      </Button>
                    </Group>
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        )}
      </Modal>

      <Modal
        open={open && editing !== null}
        onClose={() => setEditing(null)}
        title={
          editing === 'new'
            ? t('inbox.addMailbox', 'Add mailbox')
            : t('inbox.editMailbox', 'Edit mailbox')
        }
        footer={
          <>
            <Button variant="subtle" onClick={() => setEditing(null)}>
              {t('common.cancel', 'Cancel')}
            </Button>
            <Button
              variant="default"
              loading={busy}
              onClick={runTest}
              disabled={needsPassword && !form.password}
            >
              {t('inbox.test', 'Test connection')}
            </Button>
            <Button loading={busy} disabled={!canSave} onClick={save}>
              {t('common.save', 'Save')}
            </Button>
          </>
        }
      >
        <Stack gap="sm">
          <Field label={t('inbox.name', 'Name')}>
            <TextInput
              value={form.name}
              placeholder="info@"
              onChange={(e) => setForm({ ...form, name: e.currentTarget.value })}
            />
          </Field>
          <Group grow align="flex-start">
            <Field label={t('inbox.host', 'IMAP server')}>
              <TextInput
                value={form.host}
                placeholder="mail.infomaniak.com"
                onChange={(e) => setForm({ ...form, host: e.currentTarget.value.trim() })}
              />
            </Field>
            <Field label={t('inbox.security', 'Security')}>
              <Select
                value={form.security}
                allowDeselect={false}
                data={[
                  { value: 'ssl', label: 'SSL/TLS (993)' },
                  { value: 'starttls', label: 'STARTTLS (143)' },
                ]}
                onChange={(v) => {
                  const security = (v ?? 'ssl') as MailboxInput['security']
                  setForm({ ...form, security, port: security === 'ssl' ? 993 : 143 })
                }}
              />
            </Field>
            <Field label={t('inbox.port', 'Port')}>
              <NumberInput
                value={form.port}
                min={1}
                max={65535}
                onChange={(v) => setForm({ ...form, port: Number(v) || 993 })}
              />
            </Field>
          </Group>
          <Group grow align="flex-start">
            <Field label={t('inbox.username', 'User name')}>
              <TextInput
                value={form.username}
                placeholder="info@club.ch"
                autoComplete="off"
                onChange={(e) => setForm({ ...form, username: e.currentTarget.value.trim() })}
              />
            </Field>
            <Field label={t('inbox.password', 'Password or app password')}>
              <PasswordInput
                value={form.password ?? ''}
                autoComplete="new-password"
                placeholder={
                  needsPassword ? '' : t('inbox.passwordKept', 'Saved; leave empty to keep it')
                }
                onChange={(e) => setForm({ ...form, password: e.currentTarget.value })}
              />
            </Field>
          </Group>
          {serverChanged && !form.password && (
            <Text fz="xs" c="orange">
              {t(
                'inbox.passwordAgain',
                'Enter the password again: a saved password is only ever used with the server it was saved for.',
              )}
            </Text>
          )}
          {testResult && (
            <Alert color={testResult.ok ? 'green' : 'red'} variant="light">
              {testResult.text}
            </Alert>
          )}
          <Field label={t('inbox.folders', 'Folders to read')}>
            <MultiSelect
              data={folderOptions}
              value={form.folders}
              searchable
              onChange={(v) => setForm({ ...form, folders: v.length ? v : ['INBOX'] })}
            />
          </Field>
          <Field label={t('inbox.visibleTo', 'Visible to')}>
            <Select
              clearable
              searchable
              placeholder={t('inbox.managersOnly', 'Inbox managers only')}
              data={groups.map((g) => ({ value: String(g.id), label: g.name }))}
              value={form.groupId ? String(form.groupId) : null}
              onChange={(v) => setForm({ ...form, groupId: v ? Number(v) : null })}
            />
          </Field>
          <Group grow align="flex-start">
            <Field label={t('inbox.retention', 'Keep in Hubra (days)')}>
              <NumberInput
                value={form.retentionDays}
                min={1}
                max={3650}
                onChange={(v) => setForm({ ...form, retentionDays: Number(v) || 180 })}
              />
            </Field>
            <Stack gap={6} pt={24}>
              <Switch
                label={t('inbox.active', 'Sync every 5 minutes')}
                checked={form.active}
                onChange={(e) => setForm({ ...form, active: e.currentTarget.checked })}
              />
              <Switch
                label={t('inbox.markSeen', 'Mark mail as read on the server')}
                checked={form.markSeen}
                onChange={(e) => setForm({ ...form, markSeen: e.currentTarget.checked })}
              />
            </Stack>
          </Group>
          <Text fz="xs" c="dimmed">
            {t(
              'inbox.readOnlyHint',
              'Hubra only reads: it never deletes or moves mail. Older mail is removed from Hubra after the days above, not from the server.',
            )}
          </Text>
        </Stack>
      </Modal>

      <ConfirmModal
        open={!!deleting}
        onClose={() => setDeleting(null)}
        title={t('inbox.deleteTitle', 'Remove mailbox?')}
        body={t(
          'inbox.deleteMessage',
          'Hubra forgets the login and the copies of the messages. The mailbox on the server stays as it is.',
        )}
        onConfirm={async () => {
          if (!deleting) return
          try {
            await deleteMailbox(deleting.id)
            await onChanged()
          } catch (err) {
            fail(err)
          }
          setDeleting(null)
        }}
      />
    </>
  )
}
