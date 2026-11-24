import {Alert, Spin, Tag} from 'antd'
import {t, useLocale, displayText} from '../i18n'
import {usePlayerPrivacy} from './PlayerPrivacy'
import {useCallback, useEffect, useRef, useState} from 'react'
import {Button, Dialog, DialogHeader, FileInput, HStack, Icon, Layout, LayoutContent, LayoutFooter, VStack} from '../ui'
import {Fingerprint, QrCode} from 'lucide-react'
import {invoke} from '../bridge'
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
  const attemptId = useRef(0)
  const [cancelling, setCancelling] = useState(false)

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
    const attempt = ++attemptId.current
    setConnecting(true)
    try {
      const payload = await encodeQrImage(selected)
      if (attempt !== attemptId.current) return
      await onConnect(payload)
      if (attempt === attemptId.current) onOpenChange(false)
    } catch (connectError) {
      if (attempt === attemptId.current) setErrorMessage(userFacingError(connectError))
    } finally {
      if (attempt === attemptId.current) {
        connectingRef.current = false
        setConnecting(false)
      }
    }
  }, [onConnect, onOpenChange])

  const cancelConnection = async () => {
    attemptId.current += 1
    setCancelling(true)
    try {
      await invoke('cancel_connection')
      connectingRef.current = false
      setConnecting(false)
      onOpenChange(false)
    } catch {
      setErrorMessage(t('Could not cancel the connection. Try again.'))
    } finally {
      setCancelling(false)
    }
  }

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
              <Tag icon={<Fingerprint size={12} aria-hidden />} className="pd-qr__identity">{displayName(accountRiotId)}</Tag>
              <FileInput
                accept={QR_IMAGE_ACCEPT}
                changeAction={connectFile}
                className="pd-qr__dropzone"
                description={`${t("PNG, JPEG, WebP or BMP · Up to 8 MB")} · ${t("Ctrl + V")}`}
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
              {isConnecting ? <Alert type="info" showIcon icon={<Spin size="small" aria-label={t("Connecting pasted Riot QR")} />} role="status"
                title={t('Verifying this QR for {{name}}.', {name: displayName(accountRiotId)})} /> : null}
            </VStack>
          </LayoutContent>
        }
        footer={isConnecting ? <LayoutFooter hasDivider padding={6}>
          <HStack justify="end"><Button label={t('Cancel')} variant="ghost" isLoading={cancelling} onClick={() => { void cancelConnection() }} /></HStack>
        </LayoutFooter> : undefined}
      />
    </Dialog>
  )
}
