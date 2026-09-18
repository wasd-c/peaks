import {useCallback, useEffect, useState} from 'react'
import {Button} from '@astryxdesign/core/Button'
import {Dialog, DialogHeader} from '@astryxdesign/core/Dialog'
import {Heading} from '@astryxdesign/core/Heading'
import {HStack} from '@astryxdesign/core/HStack'
import {Icon} from '@astryxdesign/core/Icon'
import {Layout, LayoutContent, LayoutFooter} from '@astryxdesign/core/Layout'
import {List, ListItem} from '@astryxdesign/core/List'
import {Section} from '@astryxdesign/core/Section'
import {Text} from '@astryxdesign/core/Text'
import {VStack} from '@astryxdesign/core/VStack'
import {ArrowUpRight, Check, Minus, Plus, Wrench} from 'lucide-react'
import type {ReleaseHistoryState} from '../../../electron/releaseHistoryTypes'
import {version} from '../../../package.json'
import {t, useLocale} from '../i18n'
import {releaseNotes, releaseNoteSections} from '../releaseNotes'

const icons = {added: Plus, fixed: Wrench, changed: ArrowUpRight, removed: Minus}

export function ReleaseNotesDialog({isOpen, onClose, currentVersion = version, busy = false, error = ''}: {
  isOpen: boolean; onClose: () => void; currentVersion?: string; busy?: boolean; error?: string
}) {
  useLocale()
  return <Dialog className="pd-dialog" isOpen={isOpen} onOpenChange={open => { if (!open && !busy) onClose() }}
    padding={0} width="calc(var(--spacing-12) * 14)" maxHeight="calc(100dvh - var(--spacing-8))"
    style={{height: 'min(calc(var(--spacing-12) * 17), calc(100dvh - var(--spacing-8)))'}}>
    <Layout height="fill" padding={6} defaultHasDividers
      header={<DialogHeader title={t('What’s new in Peaks')} subtitle={t('Version {{version}}', {version: currentVersion})}
        onOpenChange={open => { if (!open && !busy) onClose() }} />}
      content={<LayoutContent padding={6} isScrollable><VStack gap={6}>
        <Section padding={5} variant="muted"><VStack gap={2}>
          <Text type="supporting" weight="semibold">{t('Summary')}</Text>
          <Text type="large">{t(releaseNotes.summary)}</Text>
        </VStack></Section>
        {releaseNoteSections.filter(section => releaseNotes[section.key].length).map(section => (
          <List key={section.key} density="balanced" hasDividers
            header={<HStack gap={2} align="center"><Icon icon={icons[section.key]} /><Heading level={2}>{t(section.label)}</Heading></HStack>}>
            {releaseNotes[section.key].map(item => <ListItem key={item} label={t(item)} />)}
          </List>
        ))}
        {error ? <Text role="alert">{t(error)}</Text> : null}
      </VStack></LayoutContent>}
      footer={<LayoutFooter padding={6} hasDivider><HStack width="100%" justify="end">
        <Button label={t('Got it')} icon={<Icon icon={Check} />} variant="primary" isLoading={busy} onClick={onClose} />
      </HStack></LayoutFooter>} />
  </Dialog>
}

/** Defer the automatic dialog until the vault is unlocked; never dismiss on a poll. */
export function useReleaseNotes() {
  const [state, setState] = useState<ReleaseHistoryState | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => {
    let cancelled = false
    if (window.peaks) {
      void window.peaks.invoke<ReleaseHistoryState>('release_history').then(next => { if (!cancelled) setState(next) }).catch(() => undefined)
    } else if (import.meta.env.DEV && new URLSearchParams(window.location.search).get('changelogPreview') === '1') {
      setState({currentVersion: version, pending: true})
    }
    return () => { cancelled = true }
  }, [])
  const dismiss = useCallback(async () => {
    if (busy) return
    setBusy(true)
    setError('')
    try {
      const next = window.peaks ? await window.peaks.invoke<ReleaseHistoryState>('release_history_ack') : {...state!, pending: false}
      setState(next)
    } catch { setError('Could not save the changelog preference. Try again.') }
    finally { setBusy(false) }
  }, [busy, state])
  return {pending: state?.pending === true, currentVersion: state?.currentVersion ?? version, busy, error, dismiss}
}
