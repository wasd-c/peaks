import {useEffect, useMemo, useState} from 'react'
import {emptyActivity} from './activityAnalytics'
import {invoke} from './bridge'
import type {Account, ProfileActivity} from './types'

export function useProfileActivity(account: Account | undefined, owned: boolean, revision: number, provided?: ProfileActivity) {
  const [stored, setStored] = useState<{id: string; activity: ProfileActivity} | null>(null)
  const [failedId, setFailedId] = useState<string>()
  const id = account?.id
  // Polling replaces account objects, so depend on evidence changes rather than object identity.
  const evidence = JSON.stringify([account?.matches?.map(match => [
    match.id, match.game, match.playedAtTimestamp, match.durationSeconds,
    match.result, match.mode, match.map, match.delta,
  ]), account?.ranks])
  useEffect(() => {
    if (!id || !owned) return
    let cancelled = false
    void invoke<ProfileActivity>('account_activity', {accountId: id}).then(activity => {
      if (!Array.isArray(activity.matches) || !Array.isArray(activity.connectionDays) || !Array.isArray(activity.ranks) || !Array.isArray(activity.identities)) throw new Error('Invalid activity response')
      if (!cancelled) { setStored({id, activity}); setFailedId(undefined) }
    }).catch(() => { if (!cancelled) setFailedId(id) })
    return () => { cancelled = true }
  }, [id, owned, evidence, revision])
  const fallback = useMemo(() => emptyActivity(account?.matches), [account?.matches])
  return {activity: !owned ? provided ?? fallback : stored && stored.id === id ? stored.activity : fallback, failed: owned && Boolean(id) && failedId === id}
}
