/** Bundled with the app: these notes describe this build and work offline.
 * Update this content as part of preparing a release, before changing its version.
 */
export const releaseNotes = {
  summary: 'Detailed Riot profiles, local activity history and one-click favorite-game launching.',
  added: [
    'Explore dedicated VALORANT, League of Legends and TFT profiles with statistics from your available match history.',
    'Track recorded playtime, activity calendars, sessions and rank changes across Riot games.',
    'Inspect TFT results and recorded compositions, including units, items, traits and augments.',
    'Choose and launch your favorite game from the top bar, with optional automatic launch after sign-in.',
  ],
  fixed: [
    'Prevent repeated JavaScript error dialogs when the launcher console closes.',
    'Keep cached profiles available when a background refresh has no active game session.',
    'Restore immediate passcode typing after switching back to Peaks.',
    'Keep activity timestamps and TFT Double Up results consistent across profile views.',
  ],
  changed: [
    'Open the active Riot account profile after a verified account change or successful sign-in.',
    'Browse compact match rows with game-specific results and recorded ranked rewards.',
  ],
  removed: [],
  knownIssues: ['Enabling MFA directly from Peaks is not yet functional. Configure MFA through your Riot account for now.'],
} satisfies {summary: string; added: string[]; fixed: string[]; changed: string[]; removed: string[]; knownIssues: string[]}

export const releaseNoteSections = [
  {key: 'added', label: 'New features'},
  {key: 'fixed', label: 'Bug fixes'},
  {key: 'changed', label: 'Changes'},
  {key: 'removed', label: 'Removed'},
  {key: 'knownIssues', label: 'Known issues'},
] as const
