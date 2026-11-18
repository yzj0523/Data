import { Icon } from './Icon'

export function PendingNotice({ children }: { children: string }) {
  return <div className="pending-notice" role="note"><Icon name="info" /><p>{children}</p></div>
}
