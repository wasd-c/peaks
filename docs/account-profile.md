# Riot account profile

The Account tab sits above Accounts. An unlocked Peaks instance opens it over
the previous workspace with a fade when a verified local Riot identity changes,
or immediately after a successful account onboarding, session import, or QR
approval. Routine activity polls do not redirect the user back to the same
account. Like account selection, this fade follows Peaks' explicit Reduce
motion setting, which disables the transition.

Local discovery verifies Riot's lockfile and reads the entitlement subject.
For a previously unknown account, onboarding independently verifies the subject
against Riot userinfo before storing its profile. Automatic recognition neither
opens a login browser nor imports reusable credentials. Removing that account
suppresses recognition until the local identity changes. Renderer account IDs
are opaque handles; subjects and tokens remain in the backend.

## Data and scope

The initial view is a neutral Riot profile with equally available icon buttons
for VALORANT, League of Legends, and TFT. Switching games crossfades the profile
and applies a scoped Astryx theme. VALORANT uses the most-played available
agent's body artwork; League uses the most-played available champion's splash;
TFT uses a generic arena. Favorites are determined from loaded history, with
recent play breaking ties; they are not lifetime mastery claims.

Detailed game views load **20 matches per game** during refresh. The accumulated
activity view reads up to **10,000** lightweight match records already retained
in SQLite; the actual total and cap are reported when coverage is truncated.
No game's newer matches evict another game's history. Each report uses
its game's authoritative account region. VALORANT and League levels remain
separate; a legacy shared level is not evidence of either game's level.

### VALORANT

The view uses the authenticated owner's history. It offers overview, matches, agents, maps, weapons and roles,
with queue, act, agent and map filters. Aggregates always describe that loaded
selection, rather than lifetime or complete-act totals. Available detail counts
are displayed; metric tooltips show their evidence coverage.

- Level comes from VALORANT account XP, never the shared League level.
- Current and peak ranks use MMR and season metadata. Recent competitive updates
  can recover the current rank, but cannot establish a career peak or peak RR.
- ACS and ADR divide summed score/damage by the corresponding rounds played.
- HS% uses head hits divided by all recorded head/body/leg hits.
- K/D and (K+A)/D use complete KDA rows; a missing/zero denominator is unavailable.
- Round win rate excludes respawn modes and requires two known team scores.
- DDA per round uses outgoing minus received damage over the same known rounds.
- KAST uses rounds with a kill, assist, survival, or a teammate trading the death
  within five seconds. Round events must reconcile with player kill/death totals;
  missing assists prevent a KAST value. This is Peaks' calculation.
- First kills/deaths, flawless rounds and aces use complete round events.
- Weapon usage measures recorded killing weapons, not equip time or accuracy.

Missing/conflicting evidence stays unavailable. Peaks does not manufacture
Tracker Score, percentiles, weapon accuracy or clutch classification.

Riot's content catalogue supplies act labels. When unavailable, a separate,
credential-free, bounded request to [VALORANT API seasons](https://valorant-api.com/v1/seasons)
resolves names by explicit parent IDs and dates. No Riot identifiers or session
headers reach that provider. Unknown or expired dates do not invent a current act.
Agent roles use the public playable-agent metadata in `src/renderer/valorantRoles.json`.

Detail enrichment is cached and bounded. Opening the page starts one refresh
and up to two further passes while data is pending. A loading indicator ends
when those passes stop; manual refresh remains available. Reading fresh private
VALORANT statistics requires the matching active VALORANT session. A successful
Riot sign-in still opens the profile immediately when those statistics are not
yet available.

### League of Legends and TFT

The verified League client supplies the current summoner and ranks. Each owned
history request rechecks the exact signed-in PUUID; each returned match must
also contain that PUUID. LoL and TFT requests fail independently and do not
require a developer key. An optional configured Riot API provider remains
supported, including unranked TFT history.

The native TFT product endpoint rejects League pagination arguments. Its page
is bounded locally. Native `json`/`metadata`, legacy `participantIdentities`, and
documented Riot match payloads are normalized before persistence. Numeric-string
TFT dates, fractional match lengths, and snake-case combat fields are supported.
Raw authentication fields and PUUIDs never enter match presentation data.

League provides champion history, wins, KDA, CS/min, damage/min, average gold,
damage and vision. Per-minute metrics use matched duration evidence; kill
participation requires a complete five-player team with recorded kills.

TFT provides placement distribution, mean placement, first-place and top-four
rates, and final compositions with units, stars, equipped items, active traits,
and augments when recorded. Double Up uses its own selection; positive results
follow the placement scale proven by each recorded roster.
Composition arrays and identifiers are bounded and allowlisted. Hidden players
do not expose compositions. Missing boards and unknown static unit IDs remain
explicit; Peaks never reconstructs a board from guessed champion identities.

TFT's primary profile section shows the latest 20 dated results across all queues
in two rows of ten, independently from the composition filter. Compact placement
labels use metallic gold and silver. The signed streak uses top-four / bottom-four
results; Double Up uses top-two only when the complete roster proves a four-team
placement scale. Eight-place source reports keep their original placements and
top-four threshold. Ambiguous scales and missing placements interrupt the streak.
Fire starts at two wins and frost at two losses. These effects follow Peaks'
explicit Reduce motion setting, including when Windows disables other animation.
Unit stars sit on the portrait's top border: one bronze, two silver, or a gold
triangle. Equipped items stack over the left border. Completed solo TFT
reports are individual standings, including older cached reports; only verified
Double Up partners are grouped into pairs.

The neutral profile and account histories use compact match rows: game icon,
an agent or champion portrait, outcome and game-specific score, then any
historical rank and actual reward supplied for a ranked match. TFT uses the
same placement rectangles as its results grid, without a tactician portrait.
Normal matches omit rank and reward; absent rewards and historical ranks are
not reconstructed from current ranks or outcome. Character names appear only
in the icon tooltip. Queue IDs, map names, durations and relative dates are
omitted from these rows; selecting a row still opens its full report.

`scripts/fetch_profile_assets.py` bundles champion splashes and localized TFT
labels/icons from [Riot Data Dragon](https://developer.riotgames.com/docs/tft#data-dragon).
If a sprite sheet is unpublished, it is rebuilt from the same catalog's official
individual icons and coordinates. Runtime rendering makes no CDN requests.

`scripts/fetch_tft_set_assets.py` additionally bundles original, uncropped
portraits, localized names and costs for the latest two numeric sets from the
[CommunityDragon game catalog](https://raw.communitydragon.org/latest/cdragon/tft/).
This includes set 18's `DA_Sentinel18`. The manifest records source URLs and
hashes. Cost borders use colors sampled from Riot's 1–5 cost unit frames in its
team-planner atlas, rather than the profile's accent color. Missing unit artwork keeps an
explicit fallback. TFT duration uses the requested player's `time_eliminated`
when available. A finished lobby whose recorded player-damage values are all
zero is treated as missing damage telemetry, including previously saved reports.
A zero for one player remains valid when another player's damage is positive.
Unavailable damage is never reconstructed from an unrelated mission score.

Completed TFT reports also come directly from the game's local
`PostEogStatsBlock` journal event. The activity poll imports them every 15 seconds,
without a Riot request, and the rotated journals allow recovery after restart
or after the next game overwrites `TFTEoGStats.json`. That periodically updated
JSON file alone never establishes a final placement. Reads are bounded to the
last 2 MiB of 20 recent logs and cached by file revision; only reports containing
the exact owned PUUID and a known account platform are accepted. Raw logs,
headers, PUUIDs and client credentials are not copied into the report.

The owner's placement, personal duration and final composition are available
immediately. Opponents still alive at that moment keep their final placement
and composition unavailable. Missing damage, traits, level and LP are not
invented. Canonical platform/match IDs let a later Riot report replace the local
record without duplication; a local capture or ID-only remote stub cannot
overwrite a completed Riot report. Local start time is the EOG event time minus
the observed duration. Native history prefers explicit `gameStartTimestamp` or
`gameCreation` over `game_datetime`, which can describe publication at lobby end.
Owned League and TFT matches now also trigger the bounded post-match refresh
previously used only for VALORANT.

## Accumulated activity

Schema 5 adds local connection-day, identity and rank observations. Polling the
same value does not create duplicate observations. A verified active owned
identity records a connection day only while Peaks is unlocked. Imported match
dates do not create login days or retroactive rank observations. Removing an
account also removes its observations; resetting Peaks deletes this database.

The neutral profile shows recorded playtime, match count, active days and daily
connection streak, game mix, weekly stacked playtime, a red activity calendar,
weekday/hour heatmap, session histogram, 7/30/90-day game balance,
and observed Riot IDs. These describe the saved sample, not total lifetime use.
Timestamps are required; durations are never parsed from relative date labels.
Sessions join recorded matches with gaps of at most 45 minutes. Session duration
includes these gaps, while total playtime only sums recorded match durations.
Midnight-spanning matches appear on both active days without double-counting
their duration. The calendar sits directly below the Riot ID and opens its
timeline when a day is selected. It uses local time, with an enlarged 24-hour
canvas and one lane per game; arrows shift the view by six hours. A blue line
marks the current time, and white lines mark local midnights with the incoming
date. The clock updates every minute; midnight positions account for daylight
saving transitions. Selecting
an older block retrieves its complete owned report from SQLite. The game
switching section is temporarily commented out.

Each game has a rank progression chart. Actual owner VALORANT RR deltas come
from its bounded competitive-updates page. When match deltas are unavailable,
the chart shows timestamped rank observations, explicitly labeled as changes
that can cover multiple games. Missing rewards are never inferred from wins.
The hit silhouette uses head/body/leg hit counts and proportionate red intensity.
Chart transitions respect both Peaks' Reduce motion option and the OS setting.

## Navigation and refresh

Reports and player profiles retain the path that opened them. Back restores the
previous game, filters, selected calendar day and both scroll axes. Leaving that
path through the sidebar releases the retained screens; locking releases them
all. Reports opened directly from a post-match notification still return to the
owning account.

A failed manual refresh keeps the current profile visible and exposes Retry.
Rejected bridge requests are handled before they reach React's transition action;
only a successful refresh reloads activity. Duplicate clicks share the in-flight
request, and a late response from a previous identity cannot update the new one.

## Consulted profiles

Clicked and watched players use the same neutral and per-game views as owned
accounts. Public League/TFT histories are requested only after exact Riot ID
resolution through the validated local client, and every match must contain
that resolved PUUID. The separate owned-history method still rechecks the
signed-in identity. VALORANT public history is bounded to 20 matches, 36 requests
and an 18-second scheduling budget; no opponent-owned competitive-updates
endpoint is queried. Provider privacy/availability restrictions remain in force.

Sanitized public profiles are cached independently from credentials: at most
200 profiles, 20 reports per game, 200 rank observations and 90 days without a
refresh. A lookup failure can show the exact Riot ID's saved profile with its
fetch date. Resolving a reused Riot ID to a different PUUID discards old data.
Local analytics and public match contents are never added to optional telemetry.
The two new history commands use existing `account`/`match` telemetry categories
for compatibility with already deployed schema-1 relays.
