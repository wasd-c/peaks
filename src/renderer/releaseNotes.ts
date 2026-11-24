/** Bundled with the app: these notes describe this build and work offline.
 * Update this content as part of preparing a release, before changing its version.
 */
export const releaseNotes = {
  summary: "A new interface built on Ant Design, and support for the standalone Teamfight Tactics client.",
  added: [
    "Detect Teamfight Tactics lobbies, queues and live games from the standalone TFT client, and save finished games to your history.",
    "See the Riot account Peaks follows next to the wordmark, one click from its profile.",
    "Switch game profiles with their logos, and open a game from its rank card.",
  ],
  fixed: [
    "Show the party size once in Discord activity.",
    "Recognize Double Up from its queue type, so event modes keep the right layout.",
  ],
  changed: [
    "Rebuild the interface on Ant Design, with one header per page and icons with tooltips instead of repeated text.",
    "Group settings into tabs, and show each game breakdown once with a 7, 30 and 90-day switch.",
    "Launch Teamfight Tactics as its own game.",
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
