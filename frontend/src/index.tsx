import { registerPlugin } from '@hubra/plugin-sdk'
import { IconInbox } from '@tabler/icons-react'
import { InboxScreen } from './InboxScreen'
import translations from './translations.json'

registerPlugin({
  id: 'imap-inbox',
  routes: [
    {
      path: 'inbox',
      module: 'inbox',
      perm: 'inbox.messages.read',
      component: InboxScreen,
    },
    {
      // The mailbox set-up, the page's last tab "Einstellungen".
      path: 'inbox/settings',
      module: 'inbox',
      perm: 'inbox.mailboxes.manage',
      component: InboxScreen,
    },
  ],
  icons: { inbox: IconInbox },
  translations,
})
