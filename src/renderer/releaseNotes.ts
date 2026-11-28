/** Bundled with the app: these notes describe this build and work offline.
 * Update this content as part of preparing a release, before changing its version.
 */
export const releaseNotes = {
  summary: "Sign out of Riot from Peaks, choose a game at each sign-in, and play League and TFT on PBE.",
  added: [
    "Sign out of the Riot account Peaks follows from the sidebar, closing a running game only after you confirm.",
    "Choose what signing in does: launch your favorite game, pick a game each time, or launch none.",
    "Sign in to your three most recent accounts from the Windows taskbar.",
    "Launch League of Legends and Teamfight Tactics on PBE when the signed-in account belongs to PBE.",
    "Show VALORANT lobbies, queues and found matches in Discord activity, with Skirmish and map art.",
    "Add Hush and the Gauntlet map to the VALORANT catalog.",
  ],
  fixed: [
    "Show TFT and League matches after a finished VALORANT match, instead of hiding them until Peaks restarts.",
    "Keep the map name and art in Discord activity for maps Riot reports by codename.",
    "Keep waiting when Riot Client delays quitting during a game launch, instead of reporting it as not ready.",
  ],
  changed: [
    "Redesign live TFT and VALORANT rosters, the saved account detail and each game’s post-match recap.",
    "Show match outcomes through scores and the recorded rank emblems.",
    "Move the followed Riot account from the header to the sidebar.",
    "Ship a smaller package with only the runtime modules and WebP art.",
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
