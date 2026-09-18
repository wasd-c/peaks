import {t, useLocale, displayText} from '../i18n'
import {useEffect, useRef, useState} from 'react'
import {AlertDialog} from '@astryxdesign/core/AlertDialog'
import {Button} from '@astryxdesign/core/Button'
import {Center} from '@astryxdesign/core/Center'
import {Heading} from '@astryxdesign/core/Heading'
import {HStack} from '@astryxdesign/core/HStack'
import {Icon} from '@astryxdesign/core/Icon'
import {RadioIndicator} from '@astryxdesign/core/Indicator'
import {Text} from '@astryxdesign/core/Text'
import {TextInput} from '@astryxdesign/core/TextInput'
import {VStack} from '@astryxdesign/core/VStack'
import {LockKeyhole, Mountain} from 'lucide-react'
import {passcodeErrorMessage} from '../passcodeMessages'
import {LanguageSelector} from './LanguageSelector'
import type {AppState} from '../types'

type Feedback = 'idle' | 'invalid' | 'wrong'
type ResetStep = 'closed' | 'warning' | 'confirmation'

interface LockScreenProps {
  mode: AppState['pinMode']
  onReset: () => Promise<void>
  onSubmit: (pin: string) => Promise<void>
  reduceMotion?: boolean
}

export const FORGOT_CODE_LABEL = 'Forgot your code?'

export const RESET_PROMPTS = {
  warning: {
    title: 'Your passcode can’t be recovered',
    description: 'Peaks cannot recover your passcode. The only way to reset it is to permanently erase all Peaks data saved on this device.',
    actionLabel: 'I understand — continue',
    cancelLabel: 'Keep my data',
  },
  confirmation: {
    title: 'Clear all local data?',
    description: 'Are you sure? This cannot be undone. Every account, credential, authenticator secret, search, watchlist entry, and setting stored by Peaks on this device will be erased. You’ll return to onboarding.',
    actionLabel: 'Clear all local data',
    cancelLabel: 'Keep my data',
  },
} as const

const copy = {
  create: {
    title: 'Create a passcode',
    body: 'Choose four digits to unlock Peaks.',
  },
  confirm: {
    title: 'Confirm your passcode',
    body: 'Enter the same four digits again.',
  },
  unlock: {
    title: 'Peaks is locked',
    body: 'Enter your four-digit passcode to continue.',
  },
} as const

export function LockScreen({mode, onReset, onSubmit, reduceMotion = false}: LockScreenProps) {
  useLocale()
  const [pin, setPin] = useState('')
  const [feedback, setFeedback] = useState<Feedback>('idle')
  const [message, setMessage] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [resetStep, setResetStep] = useState<ResetStep>('closed')
  const [isResetting, setIsResetting] = useState(false)
  const [resetError, setResetError] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)
  const submittingRef = useRef(false)
  const mountedRef = useRef(true)
  const resetTimer = useRef<number | undefined>(undefined)
  const content = copy[mode]

  const clearTimer = () => {
    if (resetTimer.current !== undefined) window.clearTimeout(resetTimer.current)
  }

  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
      clearTimer()
    }
  }, [])

  useEffect(() => {
    setPin('')
    setFeedback('idle')
    setMessage('')
    setResetStep('closed')
    setResetError('')
    inputRef.current?.focus()
  }, [mode])

  const submit = async (candidate: string) => {
    if (submittingRef.current) return
    submittingRef.current = true
    setIsSubmitting(true)
    try {
      await onSubmit(candidate)
      if (mountedRef.current) {
        setPin('')
        setFeedback('idle')
        setMessage('')
      }
    } catch (error) {
      if (mountedRef.current) {
        setFeedback('wrong')
        setMessage(passcodeErrorMessage(error, 'Could not check the password. Try again.'))
        clearTimer()
        resetTimer.current = window.setTimeout(() => {
          setPin('')
          setFeedback('idle')
          inputRef.current?.focus()
        }, 520)
      }
    } finally {
      submittingRef.current = false
      if (mountedRef.current) setIsSubmitting(false)
    }
  }

  const handleChange = (value: string) => {
    if (isSubmitting || resetStep !== 'closed') return
    clearTimer()
    const digits = value.replace(/\D/g, '').slice(0, 4)
    if (value !== digits) {
      setFeedback('invalid')
      setMessage('Use four numbers')
      resetTimer.current = window.setTimeout(() => {
        setFeedback('idle')
        setMessage('')
      }, 360)
    } else {
      setFeedback('idle')
      setMessage('')
    }
    setPin(digits)
    if (digits.length === 4) void submit(digits)
  }

  const resetApplication = async () => {
    if (isResetting) return
    setIsResetting(true)
    setResetError('')
    try {
      await onReset()
    } catch (error) {
      if (mountedRef.current) {
        setResetError(error instanceof Error ? error.message : 'Peaks could not clear the local data')
      }
    } finally {
      if (mountedRef.current) setIsResetting(false)
    }
  }

  const resetPrompt = resetStep === 'confirmation'
    ? RESET_PROMPTS.confirmation
    : RESET_PROMPTS.warning
  const resetDescription = resetError
    ? `${t(RESET_PROMPTS.confirmation.description)} ${t('Reset failed: {{error}}', {error: displayText(resetError)})}`
    : t(resetPrompt.description)

  return (
    <Center
      className={`pd-entry pd-entry--lock lock-screen lock-screen--${feedback}`}
      data-reduce-motion={reduceMotion || undefined}
      minHeight="100dvh"
      padding={6}
      onPointerDown={() => inputRef.current?.focus()}>
      <HStack className="pd-entry-brand" align="center" gap={2}><Icon icon={Mountain} size="lg" /><Text weight="semibold">PEAKS</Text></HStack>
      <HStack className="pd-entry-language" onPointerDown={event => event.stopPropagation()}>
        <LanguageSelector isLabelHidden />
      </HStack>
      <VStack className="lock-content pd-entry-lock-content" gap={6} align="center" maxWidth="calc(var(--spacing-10) * 12)">
        <Center className="lock-icon pd-entry-lock-icon" width="calc(var(--spacing-10) * 2)" height="calc(var(--spacing-10) * 2)">
          <Icon icon={LockKeyhole} size="lg" label={t("Passcode")} />
        </Center>

        <VStack gap={2} align="center">
          <Heading level={1} type="display-2" justify="center">
            {t(content.title)}
          </Heading>
          <Text className="lock-copy" type="body" color="secondary" justify="center">
            {t(content.body)}
          </Text>
        </VStack>

        <HStack className="passcode-dots" data-feedback={feedback} gap={5} align="center" aria-label={t("{{length}} of 4 digits entered", {length: pin.length})}>
          {[0, 1, 2, 3].map(index => (
            <RadioIndicator
              className="passcode-dot"
              key={index}
              data-passcode-dot={index}
              data-filled={index < pin.length || undefined}
              size="md"
              state={index < pin.length ? 'checked' : 'unchecked'}
            />
          ))}
        </HStack>

        <TextInput
          ref={inputRef}
          className="passcode-input"
          label={t("Four-digit passcode")}
          isLabelHidden
          type="password"
          value={pin}
          onChange={handleChange}
          isDisabled={isSubmitting || resetStep !== 'closed'}
          hasAutoFocus
        />

        <VStack className="lock-status" gap={1} align="center">
          <Text role="status" type="supporting" color={message ? 'primary' : 'secondary'}>
            {displayText(message || (isSubmitting ? 'Checking…' : 'Type anywhere to enter'))}
          </Text>
          {typeof window !== 'undefined' && !window.peaks && mode === 'unlock' && (
            <Text type="supporting" color="secondary">{t("Demo passcode · 2580")}</Text>
          )}
        </VStack>

      </VStack>

      {mode === 'unlock' && (
        <Button
          className="forgot-code-button"
          label={t(FORGOT_CODE_LABEL)}
          size="sm"
          variant="ghost"
          isDisabled={isSubmitting}
          onPointerDown={event => event.stopPropagation()}
          onClick={() => {
            setResetError('')
            setResetStep('warning')
          }}
        />
      )}

      <AlertDialog
        key={resetStep}
        isOpen={resetStep !== 'closed'}
        onOpenChange={isOpen => {
          if (!isOpen && !isResetting) {
            setResetError('')
            setResetStep('closed')
          }
        }}
        title={t(resetPrompt.title)}
        description={resetDescription}
        actionLabel={t(resetPrompt.actionLabel)}
        actionVariant={resetStep === 'confirmation' ? 'destructive' : 'secondary'}
        cancelLabel={t(resetPrompt.cancelLabel)}
        isActionLoading={isResetting}
        onAction={resetStep === 'confirmation'
          ? () => void resetApplication()
          : () => setResetStep('confirmation')}
      />
    </Center>
  )
}
