/** Bundled with the app: these notes describe this build and work offline.
 * Update this content as part of preparing a release, before changing its version.
 */
export const releaseNotes = {
  summary: 'Peaks now speaks your language, with a changelog after each update and a steadier Discord activity timer.',
  added: [
    'English, French and Korean throughout Peaks.',
    'Language selection on the welcome screen, lock screen and in Settings.',
    'A changelog after updates, available again from Settings.',
  ],
  fixed: [
    'Discord activity keeps its elapsed time when match statistics change.',
    'The Settings button is centered in the sidebar.',
    'Incorrect passcodes show a clear, simple message.',
  ],
  changed: [
    'Peaks starts in your device language when supported, with English as the fallback.',
    'Match cards, statistics, tags and shared images follow your chosen language.',
  ],
  removed: [],
} satisfies {summary: string; added: string[]; fixed: string[]; changed: string[]; removed: string[]}

export const releaseNoteSections = [
  {key: 'added', label: 'New features'},
  {key: 'fixed', label: 'Bug fixes'},
  {key: 'changed', label: 'Changes'},
  {key: 'removed', label: 'Removed'},
] as const
