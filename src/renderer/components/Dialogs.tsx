import {Alert, Result, Spin, Steps, Tag} from 'antd'
import {accountRegionLabel} from '../accountRegions'
import {accountConnectionError} from '../accountConnection'
import {t, useLocale, displayText} from '../i18n'
import {usePlayerPrivacy} from './PlayerPrivacy'
import {useCallback, useEffect, useRef, useState} from 'react'
import {Avatar, Button, Dialog, DialogHeader, HStack, Icon, Layout, LayoutContent, LayoutFooter, List, ListItem, Spinner, Text, VStack} from '../ui'
import {ArrowUpRight, ChevronRight, ExternalLink, Fingerprint, Gamepad2, KeyRound, QrCode, ShieldCheck} from 'lucide-react'
import type {Account, TotpSetupResult} from '../types'
import {MFA_VERIFICATION_WARNING} from '../mfa'

interface AddAccountDialogProps {
  isOpen: boolean
  onOpenChange: (isOpen: boolean) => void
  onConnect: () => Promise<void>
  onCancel: () => Promise<void>
}

type AccountConnectionState = 'connecting' | 'error'

const userFacingError = (error: unknown, fallback: string) => (
  error instanceof Error
    ? error.message.replace(/^Error invoking remote method '[^']+': Error:\s*/, '')
    : fallback
)

export function AddAccountDialog({isOpen, onOpenChange, onConnect, onCancel}: AddAccountDialogProps) {
  useLocale()
  const {redact} = usePlayerPrivacy()
  const [connectionState, setConnectionState] = useState<AccountConnectionState>('connecting')
  const [errorMessage, setErrorMessage] = useState('')
  const attemptId = useRef(0)
  const startedForOpen = useRef(false)
  const [cancelling, setCancelling] = useState(false)

  const cancel = async () => {
    attemptId.current += 1
    setCancelling(true)
    try {
      await onCancel()
      onOpenChange(false)
    } catch {
      setErrorMessage(t('Could not cancel the connection. Try again.'))
      setConnectionState('error')
    } finally {
      setCancelling(false)
    }
  }

  const connect = useCallback(async () => {
    const currentAttempt = ++attemptId.current
    setConnectionState('connecting')
    setErrorMessage('')

    try {
      await onConnect()
      if (currentAttempt === attemptId.current) onOpenChange(false)
    } catch (error) {
      if (currentAttempt !== attemptId.current) return
      setErrorMessage(userFacingError(error, 'Riot sign-in could not be completed'))
      setConnectionState('error')
    }
  }, [onConnect, onOpenChange])

  useEffect(() => {
    if (!isOpen) {
      startedForOpen.current = false
      attemptId.current += 1
      setConnectionState('connecting')
      setErrorMessage('')
      return
    }

    if (startedForOpen.current) return
    startedForOpen.current = true
    void connect()
  }, [connect, isOpen])

  return (
    <Dialog
      className="pd-dialog pd-dialog--connection"
      isOpen={isOpen}
      onOpenChange={onOpenChange}
      purpose={connectionState === 'error' ? 'info' : 'required'}
      maxHeight="calc(100dvh - var(--spacing-8))"
      width="calc(var(--spacing-12) * 12)"
      padding={0}>
      <Layout
        height="auto"
        defaultHasDividers
        padding={6}
        header={
          <DialogHeader
            title={t("Add a Riot account")}
            startContent={<HStack className="pd-dialog__header-icon" align="center" justify="center"><Icon icon={Fingerprint} /></HStack>}
            onOpenChange={connectionState === 'error' ? onOpenChange : undefined}
          />
        }
        content={
          <LayoutContent padding={6} isScrollable>
            <VStack gap={6}>
              <Result className="pd-dialog__result" status={connectionState === 'error' ? 'error' : undefined}
                icon={connectionState === 'connecting' ? <Spin size="large" aria-label={t("Connecting Riot account")} /> : undefined}
                title={<span role={connectionState === 'error' ? 'alert' : 'status'}>{connectionState === 'connecting' ? t("Connecting your account…") : t("Could not add the account")}</span>}
                subTitle={connectionState === 'connecting' ? t("Keep Peaks open. Complete sign-in in the Riot window if one appears.") : redact(displayText(errorMessage))} />
              <Steps orientation="vertical" size="small" current={-1} items={[
                {icon: <Gamepad2 size={18} aria-hidden />, title: t("Already in VALORANT?"), content: t("We’ll find the account signed in on this PC.")},
                {icon: <ExternalLink size={18} aria-hidden />, title: t("Or sign in with Riot"), content: t("Use the Riot window. Your account appears here automatically.")},
              ]} />
            </VStack>
          </LayoutContent>
        }
        footer={connectionState === 'error' ? (
          <LayoutFooter hasDivider padding={6}>
            <HStack gap={2} justify="end">
              <Button label={t("Cancel")} variant="ghost" onClick={() => onOpenChange(false)} />
              <Button label={t("Try again")} variant="primary" endContent={<Icon icon={ArrowUpRight} />} clickAction={connect} />
            </HStack>
          </LayoutFooter>
        ) : (
          <LayoutFooter hasDivider padding={6}>
            <HStack justify="end"><Button label={t('Cancel')} variant="ghost" isLoading={cancelling} onClick={() => { void cancel() }} /></HStack>
          </LayoutFooter>
        )}
      />
    </Dialog>
  )
}

interface ConnectDialogProps {
  account: Account | null
  isOpen: boolean
  onOpenChange: (isOpen: boolean) => void
  onConnectQr: (account: Account) => Promise<void>
  onCopyTotp: (account: Account) => Promise<void>
  onAction: (command: 'import_session', account: Account) => Promise<void>
  onCancel: () => Promise<void>
  onEnableMfa: (account: Account) => Promise<TotpSetupResult>
}

export function ConnectDialog({
  account,
  isOpen,
  onOpenChange,
  onConnectQr,
  onCopyTotp,
  onAction,
  onCancel,
  onEnableMfa,
}: ConnectDialogProps) {
  useLocale()
  const {displayName, redact} = usePlayerPrivacy()
  const [totpState, setTotpState] = useState<'choices' | 'connecting' | 'enabling' | 'partial'>('choices')
  const busyRef = useRef(false)
  const [totpError, setTotpError] = useState('')
  const [totpWarning, setTotpWarning] = useState('')
  const [connectionKind, setConnectionKind] = useState<'qr' | 'session' | null>(null)
  const connectionAttempt = useRef(0)
  const [cancelling, setCancelling] = useState(false)
  const canConnectQr = account?.canConnectQr ?? account?.connected ?? false
  const canSaveRiotSession = account?.canSaveRiotSession ?? Boolean(account?.owned)
  const canSetupMfa = account?.canSetupMfa ?? (Boolean(account?.connected) && !account?.hasTotp)

  const connectQr = useCallback(async () => {
    if (!account || busyRef.current) return
    busyRef.current = true
    setTotpError('')
    setTotpState('connecting')
    setConnectionKind('qr')
    const attempt = ++connectionAttempt.current
    try {
      await onConnectQr(account)
      if (attempt === connectionAttempt.current) onOpenChange(false)
    } catch (error) {
      if (attempt !== connectionAttempt.current) return
      setTotpError(accountConnectionError(error))
      setTotpState('choices')
      setConnectionKind(null)
    } finally {
      busyRef.current = false
    }
  }, [account, onConnectQr, onOpenChange])

  const cancelConnection = async () => {
    connectionAttempt.current += 1
    setCancelling(true)
    try {
      await onCancel()
      onOpenChange(false)
    } catch {
      setTotpError(t('Could not cancel the connection. Try again.'))
      setTotpState('choices')
    } finally {
      busyRef.current = false
      setCancelling(false)
    }
  }

  useEffect(() => {
    if (isOpen) return
    setTotpState('choices')
    setTotpError('')
    setTotpWarning('')
    setConnectionKind(null)
  }, [isOpen])

  const choose = async () => {
    if (!account || busyRef.current) return
    busyRef.current = true
    setTotpError('')
    setTotpState('connecting')
    setConnectionKind('session')
    const attempt = ++connectionAttempt.current
    try {
      await onAction('import_session', account)
      if (attempt === connectionAttempt.current) onOpenChange(false)
    } catch (error) {
      if (attempt !== connectionAttempt.current) return
      setTotpError(userFacingError(error, 'Riot connection could not be completed'))
      setTotpState('choices')
      setConnectionKind(null)
    } finally {
      busyRef.current = false
    }
  }

  const enableMfa = async () => {
    if (!account || busyRef.current) return
    busyRef.current = true
    setTotpError('')
    setTotpState('enabling')
    try {
      const result = await onEnableMfa(account)
      if (result.warning || !result.verified) {
        setTotpWarning(MFA_VERIFICATION_WARNING)
        setTotpState('partial')
        return
      }
      setTotpState('choices')
      onOpenChange(false)
    } catch (error) {
      setTotpError(userFacingError(error, t('MFA could not be enabled. Please try again.')))
      setTotpState('choices')
    } finally {
      busyRef.current = false
    }
  }

  const busy = totpState === 'connecting' || totpState === 'enabling'

  const closeDialog = (nextOpen: boolean) => {
    if (nextOpen) return
    if (busy) return
    onOpenChange(false)
  }

  return (
    <Dialog
      className="pd-dialog pd-dialog--connection"
      isOpen={isOpen && Boolean(account)}
      onOpenChange={closeDialog}
      purpose={busy ? 'required' : 'form'}
      maxHeight="calc(100dvh - var(--spacing-8))"
      width="calc(var(--spacing-12) * 12)"
      padding={0}>
      <Layout
        height="auto"
        defaultHasDividers
        padding={6}
        header={
          <DialogHeader
            startContent={<HStack className="pd-dialog__header-icon" align="center" justify="center"><Icon icon={totpState === 'enabling' ? ShieldCheck : Fingerprint} /></HStack>}
            title={busy
              ? totpState === 'enabling'
                ? t('Enabling MFA…')
                : t("Connecting Riot account…")
              : canConnectQr
                  ? t("Connect your account")
                  : t("Reconnect your account")}
            subtitle={totpState === 'enabling'
              ? undefined
              : canConnectQr
                ? t("Choose how to connect this account to Riot Client.")
                : t("Sign in to Riot to enable QR connection for this account.")}
            onOpenChange={busy ? undefined : closeDialog}
          />
        }
        content={
          <LayoutContent padding={6} isScrollable>
            <VStack gap={5}>
              {account && (
                <HStack className="pd-dialog__identity" gap={4} align="center" justify="between" padding={4}>
                  <HStack gap={3} align="center">
                    <Avatar name={displayName(account.riotId)} src={account.avatar} size="lg" tooltip={false} />
                    <Text type="large" weight="semibold">{displayName(account.riotId)}</Text>
                  </HStack>
                  <Tag>{accountRegionLabel(account)}</Tag>
                </HStack>
              )}

              {busy ? (
                <VStack className="pd-dialog__progress" gap={5} width="100%" paddingBlock={4}>
                  <HStack gap={4} align="start">
                    <HStack className="pd-dialog__progress-icon" align="center" justify="center">
                    <Spinner
                      size="md"
                      aria-label={totpState === 'enabling'
                        ? t('Enabling MFA…')
                        : t("Connecting Riot account")}
                    />
                    </HStack>
                    <VStack gap={1}>
                      <Text type="large" weight="semibold">
                        {totpState === 'enabling'
                          ? t('Enabling MFA…')
                          : connectionKind === 'session'
                            ? t("Waiting for Riot sign-in…")
                            : t("Opening Riot Client and connecting…")}
                      </Text>
                      <Text color="secondary" role="status">
                        {totpState === 'enabling'
                          ? t('Keep Peaks open while Riot activates your authenticator.')
                          : connectionKind === 'session'
                            ? t("Finish signing in through the Riot window opened by Peaks. Use the selected account shown above.")
                            : t("Peaks opens Riot Client and connects the account shown above automatically.")}
                      </Text>
                    </VStack>
                  </HStack>
                  {totpState === 'connecting' && connectionKind === 'session' && account?.hasTotp ? (
                    <VStack gap={1}>
                      <Button
                        label={t("Copy authenticator code")}
                        variant="secondary"
                        icon={<Icon icon={KeyRound} />}
                        isInterruptible
                        clickAction={() => onCopyTotp(account)}
                      />
                      <Text type="supporting" color="secondary">{t("Paste it in the Riot sign-in window. The clipboard clears automatically.")}</Text>
                    </VStack>
                  ) : null}
                </VStack>
              ) : totpState === 'partial' ? (
                <Alert type="warning" showIcon role="alert" title={t("Saved, but Riot verification needs attention")} description={redact(displayText(totpWarning))} />
              ) : (
                <>
                  {totpError && (
                    <Alert type="error" showIcon role="alert" title={redact(displayText(totpError))} />
                  )}

                  <List
                    className="pd-dialog__actions"
                    density="spacious"
                    hasDividers>
                    {canConnectQr ? (
                      <ListItem
                        label={t("Connect to Riot Client")}
                        description={<Text color="secondary">{t("Open Riot Client and connect this account automatically.")}</Text>}
                        startContent={<Icon icon={QrCode} color="primary" />}
                        endContent={<Icon icon={ChevronRight} size="sm" color="secondary" />}
                        onClick={() => void connectQr()}
                      />
                    ) : null}
                    {canSaveRiotSession ? (
                      <ListItem
                        label={canConnectQr ? t("Refresh Riot sign-in") : t("Sign in to Riot again")}
                        description={<Text color="secondary">{t("Save a fresh connection for this account.")}</Text>}
                        startContent={<Icon icon={ShieldCheck} color="primary" />}
                        endContent={<Icon icon={ChevronRight} size="sm" color="secondary" />}
                        onClick={() => void choose()}
                      />
                    ) : null}
                    {canSetupMfa ? (
                      <ListItem
                        label={t('Enable MFA')}
                        description={<Text color="secondary">{t('Activate your authenticator directly in Peaks.')}</Text>}
                        startContent={<Icon icon={KeyRound} color="primary" />}
                        endContent={<Icon icon={ChevronRight} size="sm" color="secondary" />}
                        onClick={() => void enableMfa()}
                      />
                    ) : null}
                  </List>

                  {!canSetupMfa && account?.hasTotp ? (
                    <HStack gap={2} align="center">
                      <Icon icon={ShieldCheck} color="secondary" />
                      <Text type="supporting" color="secondary">{t("Authenticator ready. Copy a code from the account actions menu.")}</Text>
                    </HStack>
                  ) : !canSetupMfa ? (
                    <HStack gap={2} align="center">
                      <Icon icon={KeyRound} color="secondary" />
                      <Text type="supporting" color="secondary">{t("Sign in to Riot before setting up an authenticator.")}</Text>
                    </HStack>
                  ) : null}

                </>
              )}
            </VStack>
          </LayoutContent>
        }
        footer={totpState === 'connecting' ? (
          <LayoutFooter hasDivider padding={6}>
            <HStack justify="end"><Button label={t('Cancel')} variant="ghost" isLoading={cancelling} onClick={() => { void cancelConnection() }} /></HStack>
          </LayoutFooter>
        ) : totpState === 'partial' ? (
          <LayoutFooter hasDivider padding={6}>
            <HStack justify="end">
              <Button label={t("Done")} variant="primary" onClick={() => onOpenChange(false)} />
            </HStack>
          </LayoutFooter>
        ) : undefined}
      />
    </Dialog>
  )
}
