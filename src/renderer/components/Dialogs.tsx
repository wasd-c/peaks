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
import type {Account, TotpSetupProposal, TotpSetupResult} from '../types'
import {
  cancelPendingTotp,
  canConfirmTotp,
  type TotpDialogState,
} from './totpDialog'

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
            title="Add a Riot account"
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
                      <Spinner size="lg" aria-label="Connecting Riot account" />
                    ) : (
                      <Icon icon="error" color="error" size="lg" />
                    )}
                  </HStack>
                  <VStack gap={2} align="center">
                  <Text className="pd-dialog__eyebrow" type="supporting">{connectionState === 'connecting' ? 'RIOT SIGN-IN' : 'CONNECTION PAUSED'}</Text>
                  <Heading level={2} type="display-3" justify="center" role={connectionState === 'error' ? 'alert' : 'status'}>
                    {connectionState === 'connecting'
                      ? 'Connecting your account…'
                      : 'Could not add the account'}
                  </Heading>
                  <Text color="secondary" justify="center">
                    {connectionState === 'connecting'
                      ? 'Keep Peaks open. Complete sign-in in the Riot window if one appears.'
                      : redact(errorMessage)}
                  </Text>
                  </VStack>
                </VStack>
              </Section>

              <List className="pd-dialog__steps" density="spacious" hasDividers>
                <ListItem label="Already in VALORANT?" description="We’ll find the account signed in on this PC."
                  startContent={<Icon icon={Gamepad2} color="secondary" />} />
                <ListItem label="Or sign in with Riot" description="Use the Riot window. Your account appears here automatically."
                  startContent={<Icon icon={ExternalLink} color="secondary" />} />
              </List>
            </VStack>
          </LayoutContent>
        }
        footer={connectionState === 'error' ? (
          <LayoutFooter hasDivider padding={6}>
            <HStack gap={2} justify="end">
              <Button label="Cancel" variant="ghost" onClick={() => onOpenChange(false)} />
              <Button label="Try again" variant="primary" endContent={<Icon icon={ArrowUpRight} />} clickAction={connect} />
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
  onCancelTotp: (confirmationId: string) => Promise<void>
  onConfirmTotp: (proposal: TotpSetupProposal) => Promise<TotpSetupResult>
  onPrepareTotp: (account: Account) => Promise<TotpSetupProposal>
}

export function ConnectDialog({
  account,
  isOpen,
  onOpenChange,
  onConnectQr,
  onCopyTotp,
  onAction,
  onCancelTotp,
  onConfirmTotp,
  onPrepareTotp,
}: ConnectDialogProps) {
  const {displayName, redact} = usePlayerPrivacy()
  const [totpState, setTotpState] = useState<TotpDialogState>('choices')
  const [proposal, setProposal] = useState<TotpSetupProposal | null>(null)
  const [totpError, setTotpError] = useState('')
  const [totpWarning, setTotpWarning] = useState('')
  const [connectionKind, setConnectionKind] = useState<'qr' | 'session' | null>(null)
  const canConnectQr = account?.canConnectQr ?? account?.connected ?? false
  const canSaveRiotSession = account?.canSaveRiotSession ?? Boolean(account?.owned)
  const canSetupMfa = account?.canSetupMfa ?? (Boolean(account?.connected) && !account?.hasTotp)

  const connectQr = useCallback(async () => {
    if (!account) return
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
    }
  }, [account, onConnectQr, onOpenChange])

  useEffect(() => {
    if (isOpen) return
    setTotpState('choices')
    setProposal(null)
    setTotpError('')
    setTotpWarning('')
    setConnectionKind(null)
  }, [isOpen])

  const choose = async () => {
    if (!account) return
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
    }
  }

  const prepareTotp = async () => {
    if (!account) return
    setTotpError('')
    setTotpState('preparing')
    try {
      const next = await onPrepareTotp(account)
      setProposal(next)
      setTotpState('confirming')
    } catch (error) {
      setTotpError(userFacingError(error, 'Authenticator setup could not start'))
      setTotpState('choices')
    }
  }

  const cancelTotp = async () => {
    const current = proposal
    setProposal(null)
    setTotpState('choices')
    setTotpError('')
    await cancelPendingTotp(current, onCancelTotp)
  }

  const confirmTotp = async () => {
    if (!canConfirmTotp(totpState, proposal)) return
    setTotpError('')
    setTotpState('saving')
    try {
      const result = await onConfirmTotp(proposal)
      if (result.warning) {
        setTotpWarning(result.warning)
        setProposal(null)
        setTotpState('partial')
        return
      }
      setProposal(null)
      setTotpState('choices')
      onOpenChange(false)
    } catch (error) {
      setProposal(null)
      setTotpError(userFacingError(error, 'Authenticator setup failed'))
      setTotpState('choices')
    }
  }

  const confirming = totpState === 'confirming' || totpState === 'saving'
  const busy = totpState === 'connecting' || totpState === 'preparing' || totpState === 'saving'

  const closeDialog = (nextOpen: boolean) => {
    if (nextOpen) return
    if (busy) return
    void cancelPendingTotp(proposal, onCancelTotp)
    onOpenChange(false)
  }

  return (
    <Dialog
      className="pd-dialog pd-dialog--connection"
      isOpen={isOpen && Boolean(account)}
      onOpenChange={closeDialog}
      purpose={busy || confirming ? 'required' : 'form'}
      maxHeight="calc(100dvh - var(--spacing-8))"
      width="calc(var(--spacing-12) * 12)"
      padding={0}>
      <Layout
        height="auto"
        defaultHasDividers
        padding={6}
        header={
          <DialogHeader
            startContent={<HStack className="pd-dialog__header-icon" align="center" justify="center"><Icon icon={confirming ? ShieldCheck : Fingerprint} /></HStack>}
            title={totpState === 'connecting' || totpState === 'preparing'
              ? totpState === 'preparing'
                ? 'Preparing Riot authenticator…'
                : 'Connecting Riot account…'
              : confirming
                ? 'Enable Riot Mobile authenticator?'
                : canConnectQr
                  ? 'Connect your account'
                  : 'Reconnect your account'}
            subtitle={confirming
              ? 'Review the account and security change before continuing.'
              : canConnectQr
                ? 'Choose how to connect this account to Riot Client.'
                : 'Sign in to Riot to enable QR connection for this account.'}
            onOpenChange={busy || confirming ? undefined : closeDialog}
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
                      <Text className="pd-dialog__eyebrow" type="supporting">SELECTED ACCOUNT · {account.region.toUpperCase()}</Text>
                      <Text type="large" weight="semibold">{displayName(account.riotId)}</Text>
                    </VStack>
                  </HStack>
                  <Icon icon={LockKeyhole} color="secondary" />
                </HStack>
              )}

              {totpState === 'connecting' || totpState === 'preparing' ? (
                <VStack className="pd-dialog__progress" gap={5} width="100%" paddingBlock={4}>
                  <HStack gap={4} align="start">
                    <HStack className="pd-dialog__progress-icon" align="center" justify="center">
                    <Spinner
                      size="md"
                      aria-label={totpState === 'preparing'
                        ? 'Preparing Riot authenticator setup'
                        : 'Connecting Riot account'}
                    />
                    </HStack>
                    <VStack gap={1}>
                      <Text type="large" weight="semibold">
                        {totpState === 'preparing'
                          ? 'Checking Riot authenticator settings…'
                          : connectionKind === 'session'
                            ? 'Waiting for Riot sign-in…'
                            : 'Scanning the Riot Client sign-in QR…'}
                      </Text>
                      <Text color="secondary" role="status">
                        {totpState === 'preparing'
                          ? 'Complete Riot sign-in if prompted. Review and confirm the security change here before it is applied.'
                          : connectionKind === 'session'
                            ? 'Finish signing in through the Riot window opened by Peaks. Use the selected account shown above.'
                            : 'Keep Riot Client open on its QR sign-in screen. Peaks will connect the account shown above.'}
                      </Text>
                    </VStack>
                  </HStack>
                  <HStack className="pd-dialog__progress-track" gap={2} align="center">
                    <StatusDot label="Connection in progress" variant="neutral" isPulsing />
                    <Text type="supporting">Keep the Riot window open</Text>
                  </HStack>
                  {totpState === 'connecting' && connectionKind === 'session' && account?.hasTotp ? (
                    <VStack gap={1}>
                      <Button
                        label="Copy authenticator code"
                        variant="secondary"
                        icon={<Icon icon={KeyRound} />}
                        isInterruptible
                        clickAction={() => onCopyTotp(account)}
                      />
                      <Text type="supporting" color="secondary">
                        Paste it in the Riot sign-in window. The clipboard clears automatically.
                      </Text>
                    </VStack>
                  ) : null}
                </VStack>
              ) : confirming ? (
                <VStack className="pd-dialog__confirmation" gap={4} padding={5}>
                  <HStack gap={3} align="start">
                    <Icon icon={TriangleAlert} color="warning" />
                    <VStack gap={1}>
                      <Text className="pd-dialog__eyebrow" type="supporting">REVIEW SECURITY CHANGE</Text>
                      <Heading level={2}>Enable your authenticator.</Heading>
                      <Text weight="semibold">This changes your Riot account security</Text>
                      <Text color="secondary">
                        Peaks will enable Riot Mobile authentication for {displayName(proposal?.riotId ?? account?.riotId ?? 'Selected player')}, save the issued secret in your encrypted vault, then verify it with Riot.
                      </Text>
                    </VStack>
                  </HStack>
                  <Text type="supporting" color="secondary">
                    Email MFA must already be enabled. Peaks refuses to replace an existing Riot Mobile factor. If verification fails after Riot issues a secret, Peaks keeps that secret so you are not locked out.
                  </Text>
                </VStack>
              ) : totpState === 'partial' ? (
                <HStack className="pd-dialog__notice" gap={3} align="start" padding={4}>
                  <Icon icon={TriangleAlert} color="warning" />
                  <VStack gap={1}>
                    <Text weight="semibold">Saved, but Riot verification needs attention</Text>
                    <Text color="secondary" role="alert">{redact(totpWarning)}</Text>
                  </VStack>
                </HStack>
              ) : (
                <>
                  {totpError && (
                    <HStack className="pd-dialog__notice" gap={3} align="start" padding={4}>
                      <Icon icon="error" color="error" />
                      <Text color="secondary" role="alert">{redact(totpError)}</Text>
                    </HStack>
                  )}

                  <List
                    className="pd-dialog__actions"
                    density="spacious"
                    hasDividers
                    header={<Text className="pd-dialog__eyebrow" type="supporting">CONNECTION OPTIONS</Text>}>
                    {canConnectQr ? (
                      <ListItem
                        label="Scan Riot Client QR"
                        description={<Text color="secondary">Connect using the QR shown in Riot Client.</Text>}
                        startContent={<Icon icon={QrCode} color="primary" />}
                        endContent={<Icon icon={ChevronRight} size="sm" color="secondary" />}
                        onClick={() => void connectQr()}
                      />
                    ) : null}
                    {canSaveRiotSession ? (
                      <ListItem
                        label={canConnectQr ? 'Refresh Riot sign-in' : 'Sign in to Riot again'}
                        description={<Text color="secondary">Save a fresh connection for this account.</Text>}
                        startContent={<Icon icon={ShieldCheck} color="primary" />}
                        endContent={<Icon icon={ChevronRight} size="sm" color="secondary" />}
                        onClick={() => void choose()}
                      />
                    ) : null}
                    {canSetupMfa ? (
                      <ListItem
                        label="Add Riot MFA"
                        description={<Text color="secondary">Set up authentication codes. You’ll review the change first.</Text>}
                        startContent={<Icon icon={KeyRound} color="primary" />}
                        endContent={<Icon icon={ChevronRight} size="sm" color="secondary" />}
                        onClick={() => void prepareTotp()}
                      />
                    ) : null}
                  </List>

                  {!canSetupMfa && account?.hasTotp ? (
                    <HStack gap={2} align="center">
                      <Icon icon={ShieldCheck} color="secondary" />
                      <Text type="supporting" color="secondary">
                        Authenticator ready. Copy a code from the account actions menu.
                      </Text>
                    </HStack>
                  ) : !canSetupMfa ? (
                    <HStack gap={2} align="center">
                      <Icon icon={KeyRound} color="secondary" />
                      <Text type="supporting" color="secondary">
                        Sign in to Riot before setting up an authenticator.
                      </Text>
                    </HStack>
                  ) : null}

                </>
              )}
            </VStack>
          </LayoutContent>
        }
        footer={confirming ? (
          <LayoutFooter hasDivider padding={6}>
            <HStack gap={2} justify="end">
              <Button label="Cancel" variant="ghost" isDisabled={busy} clickAction={cancelTotp} />
              <Button label="Enable and save" icon={<Icon icon={ShieldCheck} />} variant="primary" isLoading={totpState === 'saving'} clickAction={confirmTotp} />
            </HStack>
          </LayoutFooter>
        ) : totpState === 'partial' ? (
          <LayoutFooter hasDivider padding={6}>
            <HStack justify="end">
              <Button label="Done" variant="primary" onClick={() => onOpenChange(false)} />
            </HStack>
          </LayoutFooter>
        ) : undefined}
      />
    </Dialog>
  )
}
