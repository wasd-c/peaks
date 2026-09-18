import {isValidElement, type ComponentProps, type ReactElement} from 'react'
import {Button} from '@astryxdesign/core/Button'
import {EmptyState} from '@astryxdesign/core/EmptyState'
import {ListItem} from '@astryxdesign/core/List'
import {Text} from '@astryxdesign/core/Text'
import {TextInput} from '@astryxdesign/core/TextInput'
import {beforeEach, describe, expect, it, vi} from 'vitest'
import type {AppState, Player} from '../types'
import {SearchScreen, type SearchScreenProps} from './SearchScreen'
import {PlayerList, PlayerListItem} from './shared'

// Exercise the screen's real callbacks without adding a DOM runtime. State
// setters do not rerender automatically, so same-tick submissions deliberately
// see the same closure, as they would before React commits a state update.
const hooks = vi.hoisted(() => ({cells: [] as unknown[], cursor: 0, private: false}))
vi.mock('react', async importOriginal => ({
  ...await importOriginal<typeof import('react')>(),
  useState: <T,>(initial: T | (() => T)) => {
    const slot = hooks.cursor++
    if (slot >= hooks.cells.length) hooks.cells[slot] = typeof initial === 'function' ? (initial as () => T)() : initial
    return [hooks.cells[slot] as T, (value: T | ((previous: T) => T)) => {
      hooks.cells[slot] = typeof value === 'function' ? (value as (previous: T) => T)(hooks.cells[slot] as T) : value
    }]
  },
  useRef: <T,>(initial: T) => {
    const slot = hooks.cursor++
    if (slot >= hooks.cells.length) hooks.cells[slot] = {current: initial}
    return hooks.cells[slot]
  },
}))
vi.mock('../components/PlayerPrivacy', () => ({
  usePlayerPrivacy: () => ({enabled: hooks.private, displayName: (name: string) => hooks.private ? 'Player 1' : name}),
}))
// This callback harness deliberately calls the component outside React.
// Locale subscriptions are exercised by the real renderer/localization tests.
vi.mock('../i18n', async importOriginal => ({
  ...await importOriginal<typeof import('../i18n')>(), useLocale: () => 'en',
}))

type Element = ReactElement<Record<string, unknown>>
function elements(node: unknown): Element[] {
  if (Array.isArray(node)) return node.flatMap(elements)
  if (!isValidElement<Record<string, unknown>>(node)) return []
  return [node, ...Object.values(node.props).flatMap(elements)]
}
function propsOf<T>(node: unknown, component: unknown, predicate: (props: T) => boolean = () => true): T {
  const found = elements(node).find(element => element.type === component && predicate(element.props as T))
  if (!found) throw new Error('Expected screen control was not rendered')
  return found.props as T
}
type QueryInput = {label: string; type: string; onChange: (query: string) => void; onEnter: () => void}
type SearchButton = {label: string; isDisabled: boolean; isLoading: boolean; onClick: () => void}
const flush = async () => { for (let index = 0; index < 4; index++) await Promise.resolve() }
const player: Player = {id: 'result-1', riotId: 'Example#EUW', region: 'EUW', game: 'VALORANT'}
function setup() {
  const state: AppState = {
    locked: false, hasPasscode: true, pinMode: 'unlock', pinError: '',
    accounts: [], followed: [], searchHistory: ['Recent#EUW'], currentMatch: {}, gameDetected: false,
    settings: {autoLockMinutes: 0, lockOnBlur: false, streamerMode: false, reduceMotion: true, riotApiConfigured: false, clipboardClearSeconds: 15},
    riotClient: {detected: false, label: 'Offline'},
  }
  const invoke = vi.fn<(command: string, payload?: unknown) => Promise<unknown>>().mockResolvedValue([])
  const action = vi.fn<() => Promise<void>>().mockResolvedValue(undefined)
  const onSelectPlayer = vi.fn()
  const props: SearchScreenProps = {state, invoke: <T,>(command: string, payload?: unknown) => invoke(command, payload) as Promise<T>, action, onSelectPlayer}
  const render = () => { hooks.cursor = 0; return SearchScreen(props) }
  const enterQuery = (query = 'Example#EUW') => {
    propsOf<QueryInput>(render(), TextInput).onChange(query)
    return render()
  }
  const submit = (tree: unknown) => propsOf<SearchButton>(tree, Button, button => button.label === 'Search').onClick()
  return {state, invoke, action, onSelectPlayer, render, enterQuery, submit}
}
beforeEach(() => { hooks.cells = []; hooks.cursor = 0; hooks.private = false })

describe('simplified player search', () => {
  it('offers only Riot ID input, with no game, region, or API configuration control', () => {
    const {render} = setup()
    const tree = render()
    const inputs = elements(tree).filter(element => element.type === TextInput)
    expect(inputs).toHaveLength(1)
    expect(inputs[0].props.label).toBe('Riot ID')
    const labels = elements(tree).map(element => element.props.label).filter(label => typeof label === 'string')
    expect(labels.join(' ')).not.toMatch(/game|region|api key|developer/i)
    expect(propsOf<SearchButton>(tree, Button, button => button.label === 'Search').isDisabled).toBe(true)
  })

  it('requires a #tag before submitting from the keyboard', () => {
    const {enterQuery, invoke} = setup()
    const tree = enterQuery('IncompleteName')
    propsOf<QueryInput>(tree, TextInput).onEnter()
    expect(invoke).not.toHaveBeenCalled()
  })

  it('sends only the trimmed query and suppresses same-tick click, Enter, and history submissions', async () => {
    const {enterQuery, submit, render, invoke, action} = setup()
    let finish!: (players: Player[]) => void
    invoke.mockReturnValueOnce(new Promise<Player[]>(resolve => { finish = resolve }))
    const tree = enterQuery('  Example#EUW  ')
    submit(tree)
    propsOf<QueryInput>(tree, TextInput).onEnter()
    propsOf<{onClick: () => void}>(tree, ListItem).onClick()
    expect(invoke).toHaveBeenCalledExactlyOnceWith('search', {query: 'Example#EUW'})
    expect(propsOf<SearchButton>(render(), Button, button => button.label === 'Search').isLoading).toBe(true)
    finish([player])
    await flush()
    expect(action).toHaveBeenCalledWith('state')
    expect(propsOf<ComponentProps<typeof PlayerList>>(render(), PlayerList).players).toEqual([{...player, followed: false}])
    expect(propsOf<SearchButton>(render(), Button, button => button.label === 'Search').isLoading).toBe(false)
  })

  it('keeps duplicate protection until the refreshed app state has finished', async () => {
    const {enterQuery, submit, invoke, action} = setup()
    let finish!: () => void
    action.mockReturnValueOnce(new Promise<void>(resolve => { finish = resolve }))
    const tree = enterQuery()
    submit(tree)
    await flush()
    submit(tree)
    expect(invoke).toHaveBeenCalledOnce()
    finish()
    await flush()
    submit(tree)
    expect(invoke).toHaveBeenCalledTimes(2)
    await flush()
  })

  it('retains profile opening and follow/unfollow actions based on the current watchlist', async () => {
    const {state, enterQuery, submit, invoke, render, action, onSelectPlayer} = setup()
    state.followed = [{...player, id: 'older-result-id', riotId: 'example#euw'}]
    invoke.mockResolvedValue([player])
    submit(enterQuery())
    await flush()
    let results = propsOf<ComponentProps<typeof PlayerList>>(render(), PlayerList)
    expect(results.players[0].followed).toBe(true)
    let row = PlayerListItem({player: results.players[0], action: results.action, onSelect: results.onSelect})
    propsOf<{onClick: () => void}>(row, ListItem).onClick()
    expect(onSelectPlayer).toHaveBeenCalledWith({...player, followed: true})
    await propsOf<{label: string; clickAction: () => Promise<void>}>(row, Button, button => button.label === 'Unwatch Example#EUW').clickAction()
    expect(action).toHaveBeenLastCalledWith('toggle_watchlist', {player: {...player, followed: true}})
    state.followed = []
    results = propsOf<ComponentProps<typeof PlayerList>>(render(), PlayerList)
    row = PlayerListItem({player: results.players[0], action: results.action, onSelect: results.onSelect})
    expect(propsOf<{label: string}>(row, Button).label).toBe('Watch Example#EUW')
  })

  it.each([
    ['LOCAL_RIOT_CLIENT_UNAVAILABLE', 'Open Riot Client and sign in, then try again.'],
    ['Unexpected provider failure', 'Unable to search right now. Try again in a moment.'],
  ])('shows an actionable failure and allows retry after %s', async (failure, message) => {
    const {invoke, enterQuery, submit, render} = setup()
    invoke.mockRejectedValueOnce(new Error(failure)).mockResolvedValue([])
    submit(enterQuery())
    await flush()
    expect(propsOf<{role: string; children: string}>(render(), Text, text => text.role === 'alert').children).toBe(message)
    expect(elements(render()).some(element => element.type === PlayerList)).toBe(false)
    submit(render())
    await flush()
    expect(invoke).toHaveBeenCalledTimes(2)
    expect(elements(render()).some(element => element.props.role === 'alert')).toBe(false)
    expect(propsOf<{title: string}>(render(), EmptyState).title).toBe('No matching players')
  })

  it('keeps private history labels while searching the original Riot ID immediately', async () => {
    hooks.private = true
    const {render, invoke} = setup()
    const tree = render()
    expect(propsOf<QueryInput>(tree, TextInput).type).toBe('password')
    const history = propsOf<{label: string; onClick: () => void}>(tree, ListItem)
    expect(history.label).toBe('Player 1')
    history.onClick()
    expect(invoke).toHaveBeenCalledExactlyOnceWith('search', {query: 'Recent#EUW'})
    await flush()
  })
})
