/** Bundled with the app: these notes describe this build and work offline.
 * Update this content as part of preparing a release, before changing its version.
 */
export const releaseNotes = {
  summary: 'A redesigned account picker, unified Riot profiles and clearer live matches, in English, French and Korean.',
  added: [
    'Personalize accounts with nicknames and VALORANT agent or League champion icons.',
    'Choose English, French or Korean during onboarding, on the lock screen or in Settings.',
    'Read the changelog after each update or reopen it from Settings.',
  ],
  fixed: [
    'Discord activity keeps its elapsed time when match statistics change.',
    'Refresh Riot sign-in now opens a fresh sign-in instead of reusing the saved session.',
    'Account nicknames and chosen icons survive Riot session renewal.',
    'Account hover transitions are smooth, and Settings is centered in the sidebar.',
  ],
  changed: [
    'Accounts focus on selection, with compact editing and animated sign-in feedback.',
    'Profiles bring Riot games together, with neutral profile and current-match headers.',
    'VALORANT rosters adapt to the window to keep all ten agents visible, with team-colored scores.',
    'Peaks uses your device language by default, falling back to English.',
    'Updated dependencies and stricter filtering of technical diagnostics.',
  ],
  removed: ['Account summary tiles and redundant live-match labels.'],
  knownIssues: ['Enabling MFA directly from Peaks is not yet functional. Configure MFA through your Riot account for now.'],
} satisfies {summary: string; added: string[]; fixed: string[]; changed: string[]; removed: string[]; knownIssues: string[]}

export const releaseNoteSections = [
  {key: 'added', label: 'New features'},
  {key: 'fixed', label: 'Bug fixes'},
  {key: 'changed', label: 'Changes'},
  {key: 'removed', label: 'Removed'},
  {key: 'knownIssues', label: 'Known issues'},
] as const
