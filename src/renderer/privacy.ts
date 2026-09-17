import type {AppState} from './types'

/** Presentation aliases only: never modify the identities used for Riot actions. */
export class PlayerAliases {
  private readonly aliases = new Map<string, string>()
  private readonly identities = new Set<string>()

  name(identity: string): string {
    const normalized = identity.trim().normalize('NFKC').toLocaleLowerCase()
    let alias = this.aliases.get(normalized)
    if (!alias) {
      alias = `Player ${this.aliases.size + 1}`
      this.aliases.set(normalized, alias)
    }
    if (identity.trim()) this.identities.add(identity.trim())
    return alias
  }

  seed(state: AppState): void {
    for (const account of state.accounts) this.name(account.riotId)
    for (const player of state.followed) this.name(player.riotId)
    for (const entry of state.searchHistory) this.name(entry)
  }

  redact(text: string): string {
    const identities = [...this.identities].sort((a, b) => b.length - a.length)
    if (!identities.length) return text
    const escaped = identities.map(value => value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))
    return text.replace(new RegExp(escaped.join('|'), 'giu'), identity => this.name(identity))
  }
}
