import { useEffect, useId, useRef, type KeyboardEvent, type PointerEvent, type ReactNode } from 'react'

import { Icon } from './Icon'

type ModalProps = {
  open: boolean
  title: string
  onClose: () => void
  children: ReactNode
}

export function Modal({ open, title, onClose, children }: ModalProps) {
  const ref = useRef<HTMLDialogElement>(null)
  const backdropPress = useRef(false)
  const titleId = useId()

  useEffect(() => {
    backdropPress.current = false
    const dialog = ref.current
    if (!dialog) return
    if (open && !dialog.open) dialog.showModal()
    if (!open && dialog.open) dialog.close()
  }, [open])

  function isBackdrop(event: PointerEvent<HTMLDialogElement>) {
    const bounds = event.currentTarget.getBoundingClientRect()
    return event.target === event.currentTarget && (
      event.clientX < bounds.left || event.clientX > bounds.right
      || event.clientY < bounds.top || event.clientY > bounds.bottom
    )
  }

  function keepFocusInDialog(event: KeyboardEvent<HTMLDialogElement>) {
    if (event.key !== 'Tab') return
    const controls = Array.from(event.currentTarget.querySelectorAll<HTMLElement>(
      'button:not(:disabled), a[href], input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex]:not([tabindex="-1"])',
    )).filter((element) => element.getClientRects().length > 0)
    const first = controls[0]
    const last = controls[controls.length - 1]
    if (!first || !last) return
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault()
      last.focus()
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault()
      first.focus()
    }
  }

  return (
    <dialog ref={ref} aria-labelledby={titleId} className="modal" onClose={onClose}
      onKeyDown={keepFocusInDialog}
      onCancel={(event) => { event.preventDefault(); onClose() }}
      onPointerDown={(event) => { backdropPress.current = isBackdrop(event) }}
      onPointerUp={(event) => { backdropPress.current = backdropPress.current && isBackdrop(event) }}
      onPointerCancel={() => { backdropPress.current = false }}
      onClick={(event) => {
        const closeFromBackdrop = backdropPress.current && event.target === event.currentTarget
        backdropPress.current = false
        if (closeFromBackdrop) onClose()
      }}>
      <div className="modal-inner">
        <header className="modal-header">
          <h2 id={titleId}>{title}</h2>
          <button type="button" className="icon-button" aria-label={`关闭${title}`} onClick={onClose}>
            <Icon name="close" />
          </button>
        </header>
        <div className="modal-body">{children}</div>
        <footer className="modal-footer">
          <button type="button" className="button primary" onClick={onClose}>我知道了</button>
        </footer>
      </div>
    </dialog>
  )
}
