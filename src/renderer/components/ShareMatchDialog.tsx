import {t, useLocale, displayText} from '../i18n'
import {usePlayerPrivacy} from './PlayerPrivacy'
import {useEffect, useMemo, useState} from 'react'
import {AspectRatio} from '@astryxdesign/core/AspectRatio'
import {Button} from '@astryxdesign/core/Button'
import {Dialog, DialogHeader} from '@astryxdesign/core/Dialog'
import {HStack} from '@astryxdesign/core/HStack'
import {Icon} from '@astryxdesign/core/Icon'
import {Layout, LayoutContent, LayoutFooter} from '@astryxdesign/core/Layout'
import {Spinner} from '@astryxdesign/core/Spinner'
import {Text} from '@astryxdesign/core/Text'
import {VStack} from '@astryxdesign/core/VStack'
import {ArrowUpRight, Check, Clipboard, Download, ImagePlus, Share2, ShieldCheck} from 'lucide-react'
import {valorantMapName} from '../assets'
import {renderMatchPoster} from '../matchPoster'
import {matchShareCaption, matchShareFilename, matchShareSummary} from '../matchShare'
import type {Account, Match} from '../types'

export interface ShareMatchDialogProps {
  isOpen: boolean
  onOpenChange: (isOpen: boolean) => void
  match: Match
  account?: Account
}

function blobDataUrl(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => typeof reader.result === 'string'
      ? resolve(reader.result)
      : reject(new Error('The match image could not be read.'))
    reader.onerror = () => reject(new Error('The match image could not be read.'))
    reader.readAsDataURL(blob)
  })
}

export function ShareMatchDialog({isOpen, onOpenChange, match, account}: ShareMatchDialogProps) {
  const language = useLocale()
  const {displayName, enabled} = usePlayerPrivacy()
  const summary = useMemo(() => ({...matchShareSummary(match, account, displayName), language}), [match, account, displayName, language])
  const [generatedPoster, setPoster] = useState<{blob: Blob; url: string; summary: typeof summary; language: string} | null>(null)
  // Never flash or export a poster generated before a privacy setting changed.
  const poster = generatedPoster?.summary === summary && generatedPoster.language === language ? generatedPoster : null
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [attempt, setAttempt] = useState(0)
  const map = summary.game === 'VALORANT' ? valorantMapName(summary.map) : summary.map ?? summary.game
  const caption = matchShareCaption(summary, map)
  const filename = matchShareFilename(summary)

  useEffect(() => {
    if (!isOpen) return
    let cancelled = false
    let previewUrl: string | undefined
    setPoster(null)
    setError('')
    setNotice('')
    void renderMatchPoster(summary).then(blob => {
      if (cancelled) return
      previewUrl = URL.createObjectURL(blob)
      setPoster({blob, url: previewUrl, summary, language})
    }).catch(() => {
      if (!cancelled) setError('The match image could not be created. Try again.')
    })
    return () => {
      cancelled = true
      if (previewUrl) URL.revokeObjectURL(previewUrl)
    }
  }, [isOpen, summary, attempt, language])

  const copyImage = async () => {
    if (!poster) return
    setError('')
    setNotice('')
    try {
      if (window.peaks) {
        await window.peaks.invoke('copy_match_image', {dataUrl: await blobDataUrl(poster.blob)})
      } else {
        if (!navigator.clipboard?.write || typeof ClipboardItem === 'undefined') throw new Error('unsupported')
        await navigator.clipboard.write([new ClipboardItem({'image/png': poster.blob})])
      }
      setNotice('Image copied. Paste it into your post or message.')
    } catch {
      setError('Image copy is unavailable here. Save the PNG and attach it to your post.')
    }
  }

  const saveImage = () => {
    if (!poster) return
    const link = document.createElement('a')
    link.href = poster.url
    link.download = filename
    link.click()
    setError('')
    setNotice('PNG download started. Attach the saved image to your post.')
  }

  const shareFile = async () => {
    if (!poster || !navigator.share) return
    try {
      await navigator.share({
        files: [new File([poster.blob], filename, {type: 'image/png'})],
        title: t('{{game}} match recap', {game: summary.game}),
        text: caption,
      })
      setNotice('Image handed to your chosen sharing app.')
      setError('')
    } catch (shareError) {
      if (!(shareError instanceof DOMException && shareError.name === 'AbortError')) {
        setError('Sharing is unavailable here. Copy the image or save the PNG instead.')
      }
    }
  }

  let canShareFile = false
  try {
    canShareFile = Boolean(poster && navigator.canShare?.({
      files: [new File([poster.blob], filename, {type: 'image/png'})],
    }))
  } catch { /* File sharing is optional in the desktop runtime. */ }

  return (
    <Dialog
      className="pd-dialog pd-share"
      isOpen={isOpen}
      maxHeight="calc(100dvh - var(--spacing-8))"
      onOpenChange={onOpenChange}
      padding={0}
      purpose="info"
      style={{height: 'min(calc(var(--spacing-12) * 15), calc(100dvh - var(--spacing-8)))'}}
      width="calc(var(--spacing-12) * 20)">
      <Layout
        defaultHasDividers
        height="fill"
        padding={6}
        header={<DialogHeader
          onOpenChange={onOpenChange}
          startContent={<HStack className="pd-dialog__header-icon" align="center" justify="center"><Icon icon={Share2} /></HStack>}
          subtitle={`${map} · ${displayText(summary.result)}`}
          title={t("Share your match")}
        />}
        content={
          <LayoutContent isScrollable padding={6}>
            <VStack gap={3}>
              {enabled ? <HStack align="center" gap={2}>
                  <Icon icon={ShieldCheck} size="sm" color="secondary" />
                  <Text type="supporting">{t("Streamer Mode applied")}</Text>
                </HStack> : null}
              <VStack className="pd-share__preview" gap={0} width="100%">
                <AspectRatio ratio={16 / 9}>
                  {poster ? (
                    <img className="pd-share__image" alt={t("{{result}} on {{map}}, {{score}}. Peaks match image preview.", {result: displayText(summary.result), map: map, score: summary.score})} src={poster.url} />
                  ) : (
                    <VStack align="center" height="100%" justify="center" gap={3}>
                      {error ? <Icon color="secondary" icon={ImagePlus} /> : <Spinner label={t("Creating your match image…")} />}
                      {error ? <Button label={t("Try again")} onClick={() => setAttempt(value => value + 1)} size="sm" /> : null}
                    </VStack>
                  )}
                </AspectRatio>
              </VStack>
            </VStack>
          </LayoutContent>
        }
        footer={
          <LayoutFooter hasDivider padding={6}>
            <VStack gap={4} width="100%">
              <HStack align="center" gap={3} justify="between" wrap="wrap">
                <HStack align="center" gap={2}>
                  <Button endContent={<Icon icon={ArrowUpRight} />} href={`https://x.com/intent/post?text=${encodeURIComponent(caption)}`} isDisabled={!poster} label={t("X")} rel="noopener noreferrer" target="_blank" variant="ghost" />
                  <Button endContent={<Icon icon={ArrowUpRight} />} href={`https://www.reddit.com/submit?title=${encodeURIComponent(caption.replace(/\n/g, ' '))}`} isDisabled={!poster} label={t("Reddit")} rel="noopener noreferrer" target="_blank" variant="ghost" />
                </HStack>
                <HStack align="center" gap={2} wrap="wrap">
                  <Button icon={<Icon icon={Download} />} isDisabled={!poster} label={t("Save PNG")} onClick={saveImage} />
                  {canShareFile ? <Button clickAction={shareFile} icon={<Icon icon={Share2} />} label={t("Share…")} /> : null}
                  <Button clickAction={copyImage} icon={<Icon icon={Clipboard} />} isDisabled={!poster} label={t("Copy image")} variant="primary" />
                </HStack>
              </HStack>
              {notice ? <HStack className="pd-share__notice" align="center" gap={2} padding={3}><Icon color="secondary" icon={Check} /><Text role="status">{displayText(notice)}</Text></HStack> : null}
              {error ? <Text className="pd-share__error" role="alert">{displayText(error)}</Text> : null}
            </VStack>
          </LayoutFooter>
        }
      />
    </Dialog>
  )
}
