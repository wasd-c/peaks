import {accountRegionLabel} from '../accountRegions'
import {t, useLocale, displayText} from '../i18n'
import {usePlayerPrivacy} from './PlayerPrivacy'
import {useCallback, useEffect, useRef, useState} from 'react'
import {Avatar} from '@astryxdesign/core/Avatar'
import {Button} from '@astryxdesign/core/Button'
import {Dialog, DialogHeader} from '@astryxdesign/core/Dialog'
import {Heading} from '@astryxdesign/core/Heading'
import {HStack} from '@astryxdesign/core/HStack'
import {Icon} from '@astryxdesign/core/Icon'
import {Layout, LayoutContent, LayoutFooter} from '@astryxdesign/core/Layout'
import {List, ListItem} from '@astryxdesign/core/List'
import {Section} from '@astryxdesign/core/Section'
import {Spinner} from '@astryxdesign/core/Spinner'
import {StatusDot} from '@astryxdesign/core/StatusDot'
import {Text} from '@astryxdesign/core/Text'
import {VStack} from '@astryxdesign/core/VStack'
import {ArrowUpRight, ChevronRight, ExternalLink, Fingerprint, Gamepad2, KeyRound, LockKeyhole, QrCode, ShieldCheck, TriangleAlert} from 'lucide-react'
import type {Account, TotpSetupResult} from '../types'
import {MFA_VERIFICATION_WARNING} from '../mfa'

interface AddAccountDialogProps {
  isOpen: boolean
  onOpenChange: (isOpen: boolean) => void
  onConnect: () => Promise<void>
}

type AccountConnectionState = 'connecting' | 'error'

const userFacingError = (error: unknown, fallback: string) => (
  error instanceof Error
    ? error.message.replace(/^Error invoking remote method '[^']+': Error:\s*/, '')
    : fallback
)

export function AddAccountDialog({isOpen, onOpenChange, onConnect}: AddAccountDialogProps) {
  useLocale()
  const {redact} = usePlayerPrivacy()
  const [connectionState, setConnectionState] = useState<AccountConnectionState>('connecting')
  const [errorMessage, setErrorMessage] = useState('')
  const attemptId = useRef(0)
  const startedForOpen = useRef(false)

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
              <Section className="pd-dialog__stage" padding={6} variant="transparent">
                <VStack gap={4} align="center">
                  <HStack className="pd-dialog__orbit" align="center" justify="center">
                    {connectionState === 'connecting' ? (
                      <Spinner size="lg" aria-label={t("Connecting Riot account")} />
                    ) : (
                      <Icon icon="error" color="error" size="lg" />
                    )}
                  </HStack>
                  <VStack gap={2} align="center">
                  <Text className="pd-dialog__eyebrow" type="supporting">{connectionState === 'connecting' ? t("RIOT SIGN-IN") : t("CONNECTION PAUSED")}</Text>
                  <Heading level={2} type="display-3" justify="center" role={connectionState === 'error' ? 'alert' : 'status'}>
                    {connectionState === 'connecting'
                      ? t("Connecting your account…")
                      : t("Could not add the account")}
                  </Heading>
                  <Text color="secondary" justify="center">
                    {connectionState === 'connecting'
                      ? t("Keep Peaks open. Complete sign-in in the Riot window if one appears.")
                      : redact(displayText(errorMessage))}
                  </Text>
                  </VStack>
                </VStack>
              </Section>

              <List className="pd-dialog__steps" density="spacious" hasDividers>
                <ListItem label={t("Already in VALORANT?")} description={t("We’ll find the account signed in on this PC.")}
                  startContent={<Icon icon={Gamepad2} color="secondary" />} />
                <ListItem label={t("Or sign in with Riot")} description={t("Use the Riot window. Your account appears here automatically.")}
                  startContent={<Icon icon={ExternalLink} color="secondary" />} />
              </List>
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
        ) : undefined}
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
  onEnableMfa: (account: Account) => Promise<TotpSetupResult>
}

export function ConnectDialog({
  account,
  isOpen,
  onOpenChange,
  onConnectQr,
  onCopyTotp,
  onAction,
  onEnableMfa,
}: ConnectDialogProps) {
  useLocale()
  const {displayName, redact} = usePlayerPrivacy()
  const [totpState, setTotpState] = useState<'choices' | 'connecting' | 'enabling' | 'partial'>('choices')
  const busyRef = useRef(false)
  const [totpError, setTotpError] = useState('')
  const [totpWarning, setTotpWarning] = useState('')
  const [connectionKind, setConnectionKind] = useState<'qr' | 'session' | null>(null)
  const canConnectQr = account?.canConnectQr ?? account?.connected ?? false
  const canSaveRiotSession = account?.canSaveRiotSession ?? Boolean(account?.owned)
  const canSetupMfa = account?.canSetupMfa ?? (Boolean(account?.connected) && !account?.hasTotp)

  const connectQr = useCallback(async () => {
    if (!account || busyRef.current) return
    busyRef.current = true
    setTotpError('')
    setTotpState('connecting')
    setConnectionKind('qr')
    try {
      await onConnectQr(account)
      onOpenChange(false)
    } catch (error) {
      setTotpError(userFacingError(error, 'Riot Client QR connection failed'))
      setTotpState('choices')
      setConnectionKind(null)
    } finally {
      busyRef.current = false
    }
  }, [account, onConnectQr, onOpenChange])

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
    try {
      await onAction('import_session', account)
      onOpenChange(false)
    } catch (error) {
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
                    <VStack gap={0.5}>
                      <Text className="pd-dialog__eyebrow" type="supporting">{t("SELECTED ACCOUNT ·")} {accountRegionLabel(account)}</Text>
                      <Text type="large" weight="semibold">{displayName(account.riotId)}</Text>
                    </VStack>
                  </HStack>
                  <Icon icon={LockKeyhole} color="secondary" />
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
                            : t("Scanning the Riot Client sign-in QR…")}
                      </Text>
                      <Text color="secondary" role="status">
                        {totpState === 'enabling'
                          ? t('Keep Peaks open while Riot activates your authenticator.')
                          : connectionKind === 'session'
                            ? t("Finish signing in through the Riot window opened by Peaks. Use the selected account shown above.")
                            : t("Keep Riot Client open on its QR sign-in screen. Peaks will connect the account shown above.")}
                      </Text>
                    </VStack>
                  </HStack>
                  <HStack className="pd-dialog__progress-track" gap={2} align="center">
                    <StatusDot label={t("Connection in progress")} variant="neutral" isPulsing />
                    <Text type="supporting">{totpState === 'enabling' ? t('Activating authenticator') : t("Keep the Riot window open")}</Text>
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
                <HStack className="pd-dialog__notice" gap={3} align="start" padding={4}>
                  <Icon icon={TriangleAlert} color="warning" />
                  <VStack gap={1}>
                    <Text weight="semibold">{t("Saved, but Riot verification needs attention")}</Text>
                    <Text color="secondary" role="alert">{redact(displayText(totpWarning))}</Text>
                  </VStack>
                </HStack>
              ) : (
                <>
                  {totpError && (
                    <HStack className="pd-dialog__notice" gap={3} align="start" padding={4}>
                      <Icon icon="error" color="error" />
                      <Text color="secondary" role="alert">{redact(displayText(totpError))}</Text>
                    </HStack>
                  )}

                  <List
                    className="pd-dialog__actions"
                    density="spacious"
                    hasDividers
                    header={<Text className="pd-dialog__eyebrow" type="supporting">{t("CONNECTION OPTIONS")}</Text>}>
                    {canConnectQr ? (
                      <ListItem
                        label={t("Scan Riot Client QR")}
                        description={<Text color="secondary">{t("Connect using the QR shown in Riot Client.")}</Text>}
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
        footer={totpState === 'partial' ? (
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
