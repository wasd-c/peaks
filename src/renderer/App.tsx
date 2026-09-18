import {accountRegionForGame} from './accountRegions'
import {t, useLocale, displayText} from './i18n'
import {useCallback, useEffect, useMemo, useRef, useState} from 'react'
import {AppShell} from '@astryxdesign/core/AppShell'
import {Button} from '@astryxdesign/core/Button'
import {Center} from '@astryxdesign/core/Center'
import {Heading} from '@astryxdesign/core/Heading'
import {Spinner} from '@astryxdesign/core/Spinner'
import {Text} from '@astryxdesign/core/Text'
import {useToast} from '@astryxdesign/core/Toast'
import {VStack} from '@astryxdesign/core/VStack'
import {AppNavigation, type Page} from './components/AppNavigation'
import {WorkspaceBar} from './components/WorkspaceBar'
import {AddAccountDialog, ConnectDialog} from './components/Dialogs'
import {LockScreen} from './components/LockScreen'
import {OnboardingScreen} from './components/OnboardingScreen'
import {PostMatchReviewDialog} from './components/PostMatchReviewDialog'
import {ShareMatchDialog} from './components/ShareMatchDialog'
import {ReleaseNotesDialog, useReleaseNotes} from './components/ReleaseNotesDialog'
import {PlayerPrivacyProvider, usePlayerPrivacy} from './components/PlayerPrivacy'
import {AutoLockCoordinator, type AutoLockReason, pausesAutoLock} from './autoLock'
import {RESET_APPLICATION_CONFIRMATION, invoke} from './bridge'
import {
  AccountDetailScreen,
  CurrentMatchScreen,
  MatchDetailScreen,
  OverviewScreen,
  PlayerProfileScreen,
  SearchScreen,
  SettingsScreen,
  WatchlistScreen,
  type AuthenticatedView,
} from './screens'
import {
  clearOnboardingCompletion,
  getOnboardingStorage,
  isFirstRunPreview,
  persistOnboardingCompletion,
  readOnboardingCompletion,
  shouldShowOnboarding,
} from './onboarding'
import {mergeRiotProfile, playerIsWatched} from './playerProfiles'
import {
  clearMatchReportLoading,
  matchReportNeedsRefresh,
  resolveMatchReport,
  startMatchReportRefresh,
  type MatchSelection,
} from './matchReportRefresh'
import {
  advancePostMatchTracker,
  clearReviewedMatches,
  createPostMatchTracker,
  getReviewStorage,
  persistReviewedMatch,
  readReviewedMatches,
  type PostMatchReview,
  type PostMatchTracker,
} from './postMatch'
import type {Account, AppState, Player, TotpSetupResult} from './types'
import {EditAccountDialog} from './components/EditAccountDialog'
import {accountConnectionError} from './accountConnection'
import {useAccountConnection} from './useAccountConnection'
import {MFA_VERIFICATION_WARNING, riotMfaError} from './mfa'

export function App() {
  useLocale()
  const [state, setState] = useState<AppState | null>(null)
  const [loadError, setLoadError] = useState('')
  const previewFirstRun = typeof window !== 'undefined' && isFirstRunPreview(window.location.search)
  const [onboardingComplete, setOnboardingComplete] = useState(
    () => !previewFirstRun && readOnboardingCompletion(getOnboardingStorage()),
  )

  const load = useCallback(async () => {
    setLoadError('')
    try {
      setState(await invoke<AppState>('state'))
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : 'Peaks could not start')
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const submitPin = useCallback(async (pin: string) => {
    const next = await invoke<AppState>('pin', {pin})
    setState(next)
  }, [])

  const finishOnboarding = useCallback(() => {
    persistOnboardingCompletion(getOnboardingStorage())
    setOnboardingComplete(true)
  }, [])

  const resetApplication = useCallback(async () => {
    const next = await invoke<AppState>('reset_application', {
      confirmation: RESET_APPLICATION_CONFIRMATION,
    })
    clearOnboardingCompletion(getOnboardingStorage())
    clearReviewedMatches(getReviewStorage())
    setOnboardingComplete(false)
    setState(next)
  }, [])

  if (!state) {
    return (
      <Center className="boot-screen" minHeight="100dvh" padding={6}>
        {loadError ? (
          <VStack gap={3} align="center">
            <Heading level={1}>{t("Peaks could not start")}</Heading>
            <Text color="secondary">{displayText(loadError)}</Text>
            <Button label={t("Try again")} onClick={() => void load()} variant="primary" />
          </VStack>
        ) : (
          <VStack gap={3} align="center">
            <Spinner size="md" label={t('Opening Peaks…')} />
            <Text color="secondary">{t("Opening Peaks…")}</Text>
          </VStack>
        )}
      </Center>
    )
  }

  if (shouldShowOnboarding(state.hasPasscode, onboardingComplete)) {
    return (
      <OnboardingScreen
        onGetStarted={finishOnboarding}
        reduceMotion={state.settings.reduceMotion}
      />
    )
  }

  if (state.locked || !state.hasPasscode) {
    return (
      <LockScreen
        mode={state.pinMode}
        onReset={resetApplication}
        onSubmit={submitPin}
        reduceMotion={state.settings.reduceMotion}
      />
    )
  }

  return (
    <PlayerPrivacyProvider state={state}>
      <AuthenticatedApp state={state} setState={setState} />
    </PlayerPrivacyProvider>
  )
}

interface AuthenticatedAppProps {
  state: AppState
  setState: (state: AppState) => void
}

function AuthenticatedApp({state, setState}: AuthenticatedAppProps) {
  const release = useReleaseNotes()
  useLocale()
  const [page, setPage] = useState<Page>('overview')
  const [view, setView] = useState<AuthenticatedView>('grid')
  const [selectedAccountId, setSelectedAccountId] = useState<string | null>(null)
  const [selectedMatch, setSelectedMatch] = useState<MatchSelection | null>(null)
  const [selectedPlayer, setSelectedPlayer] = useState<Player | null>(null)
  const [isAddOpen, setAddOpen] = useState(false)
  const [connectAccountId, setConnectAccountId] = useState<string | null>(null)
  const [postMatchReviews, setPostMatchReviews] = useState<PostMatchReview[]>([])
  const [sharedReviewKey, setSharedReviewKey] = useState<string | null>(null)
  const postMatchTracker = useRef<PostMatchTracker | null>(null)
  const activityPending = useRef(false)
  const autoLockCoordinator = useRef<AutoLockCoordinator | null>(null)
  const settingsRef = useRef(state.settings)

  const getAutoLockCoordinator = useCallback(() => {
    if (!autoLockCoordinator.current) {
      autoLockCoordinator.current = new AutoLockCoordinator(Date.now())
    }
    return autoLockCoordinator.current
  }, [])

  const requestLock = useCallback(async (reason: AutoLockReason) => {
    const coordinator = getAutoLockCoordinator()
    if (!coordinator.tryBeginLock(reason, settingsRef.current, Date.now())) return

    try {
      setState(await invoke<AppState>('lock'))
    } catch (error) {
      coordinator.releaseFailedLock(Date.now())
      throw error
    }
  }, [getAutoLockCoordinator, setState])

  const runWithAutoLockPaused = useCallback(async <Result,>(
    operation: () => Promise<Result>,
  ): Promise<Result> => {
    const resume = getAutoLockCoordinator().pause()
    try {
      return await operation()
    } finally {
      resume(Date.now())
    }
  }, [getAutoLockCoordinator])

  useEffect(() => {
    settingsRef.current = state.settings
  }, [state.settings])

  useEffect(() => {
    const tracker = postMatchTracker.current
      ?? createPostMatchTracker(readReviewedMatches(getReviewStorage()))
    const next = advancePostMatchTracker(tracker, state, Date.now())
    postMatchTracker.current = next.tracker
    setPostMatchReviews(previous => {
      const retained = previous.filter(review => state.accounts.some(account => (
        account.id === review.account.id && account.owned !== false
      )))
      return retained.length === previous.length && !next.reviews.length
        ? previous : [...retained, ...next.reviews]
    })
  }, [state])

  useEffect(() => {
    let cancelled = false
    const refreshActivity = async () => {
      const coordinator = getAutoLockCoordinator()
      if (activityPending.current || coordinator.isPaused || coordinator.hasLockPending) return
      activityPending.current = true
      try {
        const next = await invoke<AppState>('activity')
        if (!cancelled && !coordinator.isPaused && !coordinator.hasLockPending) setState(next)
      } catch {
        // Backend diagnostics record the safe stage. Keep the last usable UI
        // snapshot and try again on the next bounded interval.
      } finally {
        activityPending.current = false
      }
    }
    void refreshActivity()
    const interval = window.setInterval(() => void refreshActivity(), 15_000)
    return () => {
      cancelled = true
      window.clearInterval(interval)
    }
  }, [getAutoLockCoordinator, setState])

  useEffect(() => {
    const coordinator = getAutoLockCoordinator()
    const recordActivity = () => coordinator.recordActivity(Date.now())
    const activityEvents = ['keydown', 'pointerdown', 'pointermove', 'touchstart', 'wheel'] as const

    for (const eventName of activityEvents) {
      window.addEventListener(eventName, recordActivity, {passive: true})
    }

    const interval = window.setInterval(() => {
      void requestLock('inactivity').catch(() => undefined)
    }, 1_000)

    return () => {
      for (const eventName of activityEvents) {
        window.removeEventListener(eventName, recordActivity)
      }
      window.clearInterval(interval)
    }
  }, [getAutoLockCoordinator, requestLock])

  const selectedAccount = useMemo(
    () => state.accounts.find(account => account.id === selectedAccountId) ?? null,
    [selectedAccountId, state.accounts],
  )
  const connectAccount = useMemo(
    () => state.accounts.find(account => account.id === connectAccountId) ?? null,
    [connectAccountId, state.accounts],
  )
  const postMatchReview = postMatchReviews.find(review => state.accounts.some(account => (
    account.id === review.account.id && account.owned !== false
  )))
  const isShareMatchOpen = Boolean(postMatchReview && sharedReviewKey === postMatchReview.key)
  const canShowPostMatch = !isAddOpen && !connectAccount && !release.pending

  const dismissPostMatch = () => {
    if (postMatchReview) persistReviewedMatch(getReviewStorage(), postMatchReview.key)
    setSharedReviewKey(null)
    setPostMatchReviews(previous => previous.filter(review => review.key !== postMatchReview?.key))
  }

  const changePage = (next: Page) => {
    setSelectedAccountId(null)
    setSelectedMatch(null)
    setSelectedPlayer(null)
    setPage(next)
  }

  return (
    <AppShell
      className={state.settings.reduceMotion ? 'peaks-app reduce-motion' : 'peaks-app'}
      contentPadding={0}
      height="fill"
      variant="surface"
      mobileNav={{breakpoint: 'none', hasToggle: false}}
      topNav={<WorkspaceBar state={state} onPage={changePage} onAdd={() => setAddOpen(true)} onLock={() => void requestLock('manual').catch(() => undefined)} onSelect={account => {
        setPage('overview')
        setSelectedPlayer(null)
        setSelectedMatch(null)
        setSelectedAccountId(account.id)
      }} />}
      sideNav={
        <AppNavigation
          page={page}
          state={state}
          onLock={() => void requestLock('manual').catch(() => undefined)}
          onPage={changePage}
        />
      }>
      <Workspace
        connectAccount={connectAccount}
        isAddOpen={isAddOpen}
        onAddOpen={setAddOpen}
        onClearAccount={() => {
          setSelectedPlayer(null)
          setSelectedMatch(null)
          setSelectedAccountId(null)
        }}
        onConnectAccount={setConnectAccountId}
        onRequestLock={() => requestLock('manual')}
        onSelectAccount={account => {
          setSelectedPlayer(null)
          setSelectedMatch(null)
          setSelectedAccountId(account.id)
        }}
        onSelectMatch={setSelectedMatch}
        onSelectPlayer={setSelectedPlayer}
        page={page}
        selectedAccount={selectedAccount}
        selectedMatch={selectedMatch}
        selectedPlayer={selectedPlayer}
        setState={setState}
        state={state}
        runWithAutoLockPaused={runWithAutoLockPaused}
        view={view}
        onView={setView}
      />
      <ReleaseNotesDialog isOpen={release.pending && !isAddOpen && !connectAccount} onClose={() => { void release.dismiss() }}
        currentVersion={release.currentVersion} busy={release.busy} error={release.error} />
      {postMatchReview ? (
        <>
          <PostMatchReviewDialog
            isOpen={canShowPostMatch && !isShareMatchOpen}
            onDismiss={dismissPostMatch}
            onOpenReport={() => {
              setSelectedPlayer(null)
              setSelectedAccountId(null)
              setSelectedMatch({match: postMatchReview.match, region: accountRegionForGame(postMatchReview.account, postMatchReview.match.game), accountId: postMatchReview.account.id})
              dismissPostMatch()
            }}
            onShare={() => setSharedReviewKey(postMatchReview.key)}
            review={postMatchReview}
          />
          <ShareMatchDialog
            account={postMatchReview.account}
            isOpen={canShowPostMatch && isShareMatchOpen}
            match={postMatchReview.match}
            onOpenChange={open => setSharedReviewKey(open ? postMatchReview.key : null)}
          />
        </>
      ) : null}
    </AppShell>
  )
}

interface WorkspaceProps {
  connectAccount: Account | null
  isAddOpen: boolean
  onAddOpen: (isOpen: boolean) => void
  onClearAccount: () => void
  onConnectAccount: (accountId: string | null) => void
  onRequestLock: () => Promise<void>
  onSelectAccount: (account: Account) => void
  onSelectMatch: (selection: MatchSelection | null) => void
  onSelectPlayer: (player: Player | null) => void
  page: Page
  selectedAccount: Account | null
  selectedMatch: MatchSelection | null
  selectedPlayer: Player | null
  setState: (state: AppState) => void
  state: AppState
  runWithAutoLockPaused: <Result>(operation: () => Promise<Result>) => Promise<Result>
  view: AuthenticatedView
  onView: (view: AuthenticatedView) => void
}

function Workspace({
  connectAccount,
  isAddOpen,
  onAddOpen,
  onClearAccount,
  onConnectAccount,
  onRequestLock,
  onSelectAccount,
  onSelectMatch,
  onSelectPlayer,
  page,
  selectedAccount,
  selectedMatch,
  selectedPlayer,
  setState,
  state,
  runWithAutoLockPaused,
  view,
  onView,
}: WorkspaceProps) {
  useLocale()
  const showToast = useToast()
  const {redact} = usePlayerPrivacy()
  const [editingAccountId, setEditingAccountId] = useState<string | null>(null)
  const editingAccount = state.accounts.find(account => account.id === editingAccountId)
  const pendingMfa = useRef(new Map<string, Promise<TotpSetupResult>>())
  const [enablingMfaAccounts, setEnablingMfaAccounts] = useState<ReadonlySet<string>>(new Set())
  const [stoppedReport, setStoppedReport] = useState<string | null>(null)
  const [profileLookup, setProfileLookup] = useState<{riotId: string; players: Player[]; loading: boolean} | null>(null)
  const profileRiotId = selectedPlayer?.riotId
  useEffect(() => {
    if (!profileRiotId) return
    let cancelled = false
    setProfileLookup({riotId: profileRiotId, players: [], loading: true})
    // The existing keyless lookup uses connected Riot clients when available.
    // Bind the response to this identity so a late response cannot replace
    // another player's profile, or return after the workspace locks.
    void invoke<Player[]>('search', {query: profileRiotId}).then(players => {
      if (!cancelled) setProfileLookup({riotId: profileRiotId, players, loading: false})
    }).catch(() => {
      if (!cancelled) setProfileLookup({riotId: profileRiotId, players: [], loading: false})
    })
    return () => { cancelled = true }
  }, [profileRiotId])
  const lookup = profileLookup?.riotId === profileRiotId ? profileLookup : null
  const riotProfile = selectedPlayer ? mergeRiotProfile(selectedPlayer, state.accounts, state.followed, lookup?.players) : null

  const action = useCallback(async (
    command: string,
    payload: unknown = {},
    propagateError = false,
    quiet = false,
  ) => {
    const execute = async () => {
      try {
        if (command === 'lock') {
          await onRequestLock()
          return
        }

        const next = await invoke<AppState>(command, payload)
        setState(next)
        const successMessages: Record<string, string> = {
          add_account: 'Account added',
          api_key: 'API key saved',
          change_pin: 'Security code changed. Your accounts are preserved.',
          copy_totp: 'Code copied · clipboard clears automatically',
          import_session: 'Riot account connected',
          remove_account: 'Account and its local data deleted',
          refresh: 'Local intelligence refreshed',
        }
        const successMessage = next.operationNotice ?? successMessages[command]
        if (successMessage && !quiet) {
          showToast({
            body: redact(displayText(successMessage)),
            type: next.operationNotice ? 'info' : undefined,
            uniqueID: command,
          })
        }
      } catch (error) {
        if (command === 'change_pin') {
          // A failed vault write may lock the service; mirror that state.
          setState(await invoke<AppState>('state'))
        }
        const message = redact(displayText(error instanceof Error ? error.message : 'That action could not be completed'))
        if (!quiet) showToast({body: message, type: 'error', isAutoHide: true, uniqueID: `error-${command}`})
        if (propagateError) {
          throw error instanceof Error ? error : new Error(message)
        }
      }
    }

    if (pausesAutoLock(command)) {
      await runWithAutoLockPaused(execute)
      return
    }
    await execute()
  }, [onRequestLock, redact, runWithAutoLockPaused, setState, showToast])

  const {connection, connect} = useAccountConnection({
    approve: accountId => action('connect_riot_client', {accountId}, true, true),
    onError: error => showToast({body: t(accountConnectionError(error)), type: 'error', uniqueID: 'account-connection', isAutoHide: true}),
  })

  const enableRiotMfa = (account: Account): Promise<TotpSetupResult> => {
    const pending = pendingMfa.current.get(account.id)
    if (pending) return pending
    setEnablingMfaAccounts(previous => new Set(previous).add(account.id))
    const operation = runWithAutoLockPaused(async () => {
      try {
        const result = await invoke<TotpSetupResult>('enable_riot_mfa', {accountId: account.id})
        setState(result.state)
        if (!result.seedSaved) throw new Error('MFA setup did not complete')
        const complete = result.seedSaved && result.verified && !result.warning
        showToast({
          body: t(complete ? 'MFA enabled' : MFA_VERIFICATION_WARNING),
          isAutoHide: complete,
          uniqueID: `mfa-${account.id}`,
        })
        return result
      } catch (error) {
        const message = t(riotMfaError(error))
        showToast({body: message, type: 'error', uniqueID: `mfa-${account.id}`})
        throw new Error(message, {cause: error})
      } finally {
        pendingMfa.current.delete(account.id)
        setEnablingMfaAccounts(previous => {
          const next = new Set(previous)
          next.delete(account.id)
          return next
        })
      }
    })
    pendingMfa.current.set(account.id, operation)
    return operation
  }

  const report = selectedMatch
    ? resolveMatchReport(selectedMatch, state.accounts, state.followed, selectedAccount?.id)
    : undefined
  const reportId = selectedPlayer ? undefined : selectedMatch?.match.id
  const reportAccountId = report?.account?.id
  const reportKey = reportId && reportAccountId ? `${reportAccountId}:${reportId}` : null
  const reportPending = Boolean(report && matchReportNeedsRefresh(report.match))
  const reportRefreshState = useRef({action, pending: reportPending})
  useEffect(() => {
    reportRefreshState.current = {action, pending: reportPending}
  }, [action, reportPending])
  useEffect(() => {
    setStoppedReport(null)
    if (!reportId || !reportAccountId || !reportKey) return
    return startMatchReportRefresh({
      refresh: () => reportRefreshState.current.action('refresh', {accountId: reportAccountId, priorityMatchId: reportId}, true, true),
      isPending: () => reportRefreshState.current.pending,
      onStopped: () => setStoppedReport(reportKey),
    })
  }, [reportAccountId, reportId, reportKey])
  const reportMatch = report && (!reportKey || stoppedReport === reportKey)
    ? clearMatchReportLoading(report.match)
    : report?.match

  const screen = riotProfile ? (
    <PlayerProfileScreen
      key={riotProfile.riotId}
      watched={playerIsWatched(riotProfile, state.followed)}
      isLoading={Boolean(profileRiotId) && (lookup?.loading ?? true)}
      onBack={() => onSelectPlayer(null)}
      onSelectMatch={match => {
        onSelectPlayer(null)
        onSelectMatch({match, region: riotProfile.region, source: 'player-profile'})
      }}
      onToggleWatchlist={() => action('toggle_watchlist', {player: riotProfile})}
      player={riotProfile}
    />
  ) : selectedMatch ? (
    <MatchDetailScreen
      match={reportMatch ?? selectedMatch.match}
      onBack={() => onSelectMatch(null)}
      onSelectPlayer={onSelectPlayer}
      region={selectedMatch.region}
    />
  ) : selectedAccount ? (
    <AccountDetailScreen
      account={selectedAccount}
      onBack={onClearAccount}
      onConnect={() => onConnectAccount(selectedAccount.id)}
      onEnableMfa={async () => { await enableRiotMfa(selectedAccount) }}
      isEnablingMfa={enablingMfaAccounts.has(selectedAccount.id)}
      onCopy={() => action('copy_totp', {accountId: selectedAccount.id})}
      onDelete={async () => {
        await action('remove_account', {accountId: selectedAccount.id}, true)
        onClearAccount()
      }}
      onRefresh={() => action('refresh', {accountId: selectedAccount.id})}
      onPasteQr={payload => action(
        'connect_riot_qr_image',
        {accountId: selectedAccount.id, ...payload},
        true,
      )}
      onSelectMatch={match => onSelectMatch({match, region: selectedAccount.region, accountId: selectedAccount.id})}
    />
  ) : page === 'overview' ? (
    <OverviewScreen
      onAdd={() => onAddOpen(true)}
      onSelect={onSelectAccount}
      onUse={account => void connect(account.id)}
      onEdit={account => setEditingAccountId(account.id)}
      connection={connection}
      onView={onView}
      state={state}
      view={view}
    />
  ) : page === 'search' ? (
    <SearchScreen action={action} invoke={invoke} onSelectPlayer={onSelectPlayer} state={state} />
  ) : page === 'watchlist' ? (
    <WatchlistScreen action={action} onSelectPlayer={onSelectPlayer} state={state} />
  ) : page === 'current' ? (
    <CurrentMatchScreen onSelectPlayer={onSelectPlayer} state={state} />
  ) : (
    <SettingsScreen action={action} state={state} />
  )

  return (
    <>
      <VStack
        className="screen-transition"
        height="100%"
        key={selectedPlayer?.id ?? selectedMatch?.match.id ?? selectedAccount?.id ?? page}>
        {screen}
      </VStack>

      <AddAccountDialog
        isOpen={isAddOpen}
        onOpenChange={onAddOpen}
        onConnect={() => action('add_account', {}, true)}
      />
      {editingAccount && <EditAccountDialog key={editingAccount.id} account={editingAccount}
        onClose={() => setEditingAccountId(null)}
        onSave={async preferences => { await action('set_account_icon', {accountId: editingAccount.id, ...preferences}, true) }}
        onDelete={async () => { await action('remove_account', {accountId: editingAccount.id}, true) }} />}
      <ConnectDialog
        account={connectAccount}
        isOpen={Boolean(connectAccount)}
        onConnectQr={account => action('connect_riot_client', {accountId: account.id}, true)}
        onCopyTotp={account => action('copy_totp', {accountId: account.id})}
        onAction={(command, account) => action(command, {accountId: account.id, forceSignIn: true}, true)}
        onEnableMfa={enableRiotMfa}
        onOpenChange={isOpen => !isOpen && onConnectAccount(null)}
      />
    </>
  )
}
