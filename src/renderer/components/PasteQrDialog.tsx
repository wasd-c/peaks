import {t, useLocale, displayText} from '../i18n'
import {usePlayerPrivacy} from './PlayerPrivacy'
import {useCallback, useEffect, useRef, useState} from 'react'
import {Dialog, DialogHeader} from '@astryxdesign/core/Dialog'
import {FileInput} from '@astryxdesign/core/FileInput'
import {Heading} from '@astryxdesign/core/Heading'
import {HStack} from '@astryxdesign/core/HStack'
import {Icon} from '@astryxdesign/core/Icon'
import {Layout, LayoutContent} from '@astryxdesign/core/Layout'
import {Section} from '@astryxdesign/core/Section'
import {Spinner} from '@astryxdesign/core/Spinner'
import {Text} from '@astryxdesign/core/Text'
import {VStack} from '@astryxdesign/core/VStack'
import {ClipboardPaste, Fingerprint, QrCode} from 'lucide-react'
import {
  encodeQrImage,
  QR_IMAGE_ACCEPT,
  QR_IMAGE_MAX_BYTES,
  qrImageValidationError,
  type QrImageRequest,
} from '../qrImage'

interface PasteQrDialogProps {
  accountRiotId: string
  isOpen: boolean
  onConnect: (payload: QrImageRequest) => Promise<void>
  onOpenChange: (isOpen: boolean) => void
}

const userFacingError = (error: unknown) => (
  error instanceof Error
    ? error.message.replace(/^Error invoking remote method '[^']+': Error:\s*/, '')
    : 'The QR image could not be connected'
)

export function PasteQrDialog({
  accountRiotId,
  isOpen,
  onConnect,
  onOpenChange,
}: PasteQrDialogProps) {
  useLocale()
  const {displayName, redact} = usePlayerPrivacy()
  const [file, setFile] = useState<File | null>(null)
  const [errorMessage, setErrorMessage] = useState('')
  const [isConnecting, setConnecting] = useState(false)
  const connectingRef = useRef(false)

  const selectFile = useCallback((next: File | File[] | null) => {
    const selected = next instanceof File ? next : null
    setFile(selected)
    setErrorMessage('')
  }, [])

  const connectFile = useCallback(async (next: File | File[] | null) => {
    if (connectingRef.current) return
    const selected = next instanceof File ? next : null
    const error = qrImageValidationError(selected)
    setFile(error ? null : selected)
    setErrorMessage(error)
    if (!selected || error) return

    connectingRef.current = true
    setConnecting(true)
    try {
      await onConnect(await encodeQrImage(selected))
      onOpenChange(false)
    } catch (connectError) {
      setErrorMessage(userFacingError(connectError))
    } finally {
      connectingRef.current = false
      setConnecting(false)
    }
  }, [onConnect, onOpenChange])

  useEffect(() => {
    if (!isOpen) {
      setFile(null)
      setErrorMessage('')
      setConnecting(false)
      connectingRef.current = false
      return
    }

    const pasteImage = (event: ClipboardEvent) => {
      const clipboardItems = Array.from(event.clipboardData?.items ?? [])
      const image = clipboardItems
        .find(item => item.kind === 'file' && item.type.startsWith('image/'))
        ?.getAsFile()
      if (!image) {
        setErrorMessage('The clipboard does not contain an image')
        return
      }
      event.preventDefault()
      void connectFile(image)
    }

    window.addEventListener('paste', pasteImage)
    return () => window.removeEventListener('paste', pasteImage)
  }, [connectFile, isOpen])

  const closeDialog = (nextOpen: boolean) => {
    if (nextOpen || isConnecting) return
    onOpenChange(false)
  }

  return (
    <Dialog
      className="pd-dialog pd-qr"
      isOpen={isOpen}
      onOpenChange={closeDialog}
      padding={0}
      purpose="form"
      maxHeight="calc(100dvh - var(--spacing-8))"
      width="calc(var(--spacing-12) * 12)">
      <Layout
        defaultHasDividers
        height="auto"
        padding={6}
        header={
          <DialogHeader
            title={t("Connect with a QR image")}
            startContent={<HStack className="pd-dialog__header-icon" align="center" justify="center"><Icon icon={QrCode} /></HStack>}
            onOpenChange={isConnecting ? undefined : closeDialog}
          />
        }
        content={
          <LayoutContent isScrollable padding={6}>
            <VStack gap={5}>
              <HStack className="pd-dialog__identity" align="center" gap={3} padding={4}>
                <Icon icon={Fingerprint} color="secondary" />
                <VStack gap={0.5}>
                  <Text className="pd-dialog__eyebrow" type="supporting">{t("CONNECTING AS")}</Text>
                  <Text weight="semibold">{displayName(accountRiotId)}</Text>
                </VStack>
              </HStack>
              <Section className="pd-qr__scan-surface" padding={5} variant="transparent">
                <VStack gap={4} align="center">
                  <HStack className="pd-qr__scan-mark" align="center" justify="center"><Icon icon={QrCode} size="lg" /></HStack>
                  <VStack gap={1} align="center">
                    <Heading level={2}>{t("Add a QR screenshot")}</Heading>
                    <Text color="secondary" justify="center">{t("Screenshot the sign-in code in Riot Client.")}</Text>
                  </VStack>
              <FileInput
                accept={QR_IMAGE_ACCEPT}
                changeAction={connectFile}
                className="pd-qr__dropzone"
                description={t("PNG, JPEG, WebP or BMP · Up to 8 MB")}
                isDisabled={isConnecting}
                isLabelHidden
                isLoading={isConnecting}
                label={t("Riot Client QR image")}
                maxSize={QR_IMAGE_MAX_BYTES}
                mode="dropzone"
                onChange={selectFile}
                placeholder={t("Drop a QR screenshot or choose an image")}
                status={errorMessage
                  ? {type: 'error', message: redact(displayText(errorMessage))}
                  : file && !isConnecting
                    ? {type: 'success', message: t('QR image received')}
                    : undefined}
                statusVariant="detached"
                value={file}
                width="100%"
              />
                </VStack>
              </Section>

              {isConnecting ? (
                <HStack className="pd-dialog__progress-track" align="start" gap={3} padding={4}>
                  <Spinner aria-label={t("Connecting pasted Riot QR")} size="md" />
                  <VStack gap={1}>
                    <Text weight="semibold">{t("Connecting your account…")}</Text>
                    <Text color="secondary" role="status">{t('Verifying this QR for {{name}}.', {name: displayName(accountRiotId)})}
                    </Text>
                  </VStack>
                </HStack>
              ) : null}

              <HStack align="center" gap={3} justify="between">
                <HStack align="center" gap={3}>
                <Icon color="secondary" icon={ClipboardPaste} />
                <VStack gap={1}>
                  <Text weight="semibold">{t("Paste from clipboard")}</Text>
                  <Text color="secondary">{t("Paste, drop or choose to connect immediately.")}</Text>
                </VStack>
                </HStack>
                <Text className="pd-qr__shortcut" type="supporting">{t("Ctrl + V")}</Text>
              </HStack>

            </VStack>
          </LayoutContent>
        }
      />
    </Dialog>
  )
}
