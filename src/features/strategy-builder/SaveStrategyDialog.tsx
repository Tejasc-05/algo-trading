import * as Dialog from '@radix-ui/react-dialog'
import { useRef } from 'react'
import { X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'

interface Props {
  open: boolean
  name: string
  busy: boolean
  error: string | null
  updating: boolean
  onNameChange: (name: string) => void
  onOpenChange: (open: boolean) => void
  onSave: () => void
  onCloseFocus: () => void
}

export function SaveStrategyDialog({ open, name, busy, error, updating, onNameChange, onOpenChange, onSave, onCloseFocus }: Props) {
  const nameInput = useRef<HTMLInputElement>(null)
  return <Dialog.Root open={open} onOpenChange={next => { if (!busy) onOpenChange(next) }}>
    <Dialog.Portal>
      <Dialog.Overlay className="fixed inset-0 z-50 bg-black/60" />
      <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-[calc(100%_-_2rem)] max-w-md -translate-x-1/2 -translate-y-1/2 rounded-xl border border-border bg-background p-6 shadow-xl"
        onOpenAutoFocus={e => { e.preventDefault(); nameInput.current?.focus(); nameInput.current?.select() }}
        onCloseAutoFocus={e => { e.preventDefault(); onCloseFocus() }}
        onEscapeKeyDown={e => { if (busy) e.preventDefault() }}
        onPointerDownOutside={e => { if (busy) e.preventDefault() }}>
        <Dialog.Title className="text-lg font-semibold pr-8">Save strategy</Dialog.Title>
        <Dialog.Description className="mt-2 text-sm text-muted-foreground">
          {updating ? 'Save a new version of this strategy with the name below.' : 'Choose a name for your algorithm.'} It will appear in My Saved Strategies.
        </Dialog.Description>
        <Dialog.Close asChild><button type="button" aria-label="Close save dialog" disabled={busy} className="absolute right-3 top-3 flex min-h-11 min-w-11 items-center justify-center rounded-lg hover:bg-secondary focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"><X aria-hidden="true" className="h-4 w-4" /></button></Dialog.Close>
        <form className="mt-5 space-y-4" onSubmit={e => { e.preventDefault(); if (!busy) onSave() }}>
          <label className="block space-y-2 text-sm">Strategy name
            <Input ref={nameInput} value={name} onChange={e => onNameChange(e.target.value)} required maxLength={255} disabled={busy}
              aria-invalid={!!error} aria-describedby={error ? 'save-strategy-error' : undefined} className="min-h-11" />
          </label>
          {error && <p id="save-strategy-error" role="alert" className="text-sm text-destructive">{error}</p>}
          <div className="flex justify-end gap-3">
            <Dialog.Close asChild><Button type="button" variant="outline" disabled={busy} className="min-h-11">Cancel</Button></Dialog.Close>
            <Button type="submit" disabled={busy || !name.trim()} className="min-h-11">{busy ? 'Saving…' : 'Save strategy'}</Button>
          </div>
        </form>
      </Dialog.Content>
    </Dialog.Portal>
  </Dialog.Root>
}
