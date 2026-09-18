/** Fixed public Peaks application icon, verified through Discord's asset proxy. */
export const DISCORD_PEAKS_IMAGE = 'https://cdn.discordapp.com/app-icons/1549634813756178503/73d9f3fd3166763966ab9868db736ee1.png'

/**
 * The snake_case activity object accepted by Discord's native SET_ACTIVITY RPC.
 * No account identity, match ID, party ID, or credentials leave this boundary.
 */
export interface DiscordActivity {
  type: 0
  details: string
  state: string
  timestamps?: {start: number}
  assets: {
    large_image?: string
    large_text?: string
    small_image: typeof DISCORD_PEAKS_IMAGE
    small_text: 'Peaks'
  }
  party?: {size: [number, number]}
}

type RecordValue = Record<string, unknown>

// Generated from src/peaks/ui/assets/riot/valorant/index.json. Kept inside the
// Electron compilation root so packaged activity needs no renderer filesystem.
// The catalog parity test detects drift when bundled game metadata is updated.
const AGENT_CATALOG = [
  ["Iso","0e38b510-41a8-5780-5e8f-568b2a4f2d6c"],
  ["Cypher","117ed9e3-49f3-6512-3ccf-0cada7e3823b"],
  ["Clove","1dbf2edd-4729-0984-3115-daa5eed44993"],
  ["Killjoy","1e58de9c-4950-5125-93e9-a0aee9f98746"],
  ["Chamber","22697a3d-45bf-8dd7-4fec-84a9e28c69d7"],
  ["Sova","320b2a48-4d9b-a075-30f1-1f93a9b638fa"],
  ["Astra","41fb69c1-4189-7b37-f117-bcaf1e96f1bf"],
  ["Sage","569fdd95-4d10-43ab-ca70-79becc718b46"],
  ["Breach","5f8d3a7f-467b-97f3-062c-13acf203c006"],
  ["KAY/O","601dbbe7-43ce-be57-2a40-4abd24953621"],
  ["Skye","6f2a04ca-43e0-be17-7f36-b3908627744d"],
  ["Viper","707eab51-4836-f488-046a-cda6bf494859"],
  ["Miks","7c8a4701-4de6-9355-b254-e09bc2a34b72"],
  ["Yoru","7f94d92c-4234-0a36-9646-3a87eb8b5c89"],
  ["Omen","8e253930-4c05-31dd-1b6c-968525494517"],
  ["Veto","92eeef5d-43b5-1d4a-8d03-b3927a09034b"],
  ["Harbor","95b78ed7-4637-86d9-7e41-71ba8c293152"],
  ["Brimstone","9f0d8ba9-4140-b941-57d3-a7ad57c6b417"],
  ["Reyna","a3bfb853-43b2-7238-a4f1-ad90e9e46bcc"],
  ["Jett","add6443a-41bd-e414-f6ad-e58d267f4e95"],
  ["Tejo","b444168c-4e35-8076-db47-ef9bf368f384"],
  ["Neon","bb2a4828-46eb-8cd1-e765-15848195d751"],
  ["Deadlock","cc8b64c8-4b25-4ff9-6e7f-37b4da43d235"],
  ["Fade","dade69b4-4f5a-8528-247b-219e5a1facd6"],
  ["Waylay","df1cb487-4902-002e-5c17-d28e83e78588"],
  ["Gekko","e370fa57-4757-3604-3648-499e1f642d3f"],
  ["Phoenix","eb93336a-449b-9c1b-0a54-a891f7921d69"],
  ["Vyse","efba5359-4016-a1e5-7626-b1ae76895940"],
  ["Raze","f94c3b30-42be-e959-889c-5aa313dba261"],
] as const

const MAP_CATALOG = [
  ["Kasbah","12452a9d-48c3-0b02-e7eb-0381c3520404","/Game/Maps/HURM/HURM_Bowl/HURM_Bowl","valorant/maps/12452a9d-48c3-0b02-e7eb-0381c3520404.png"],
  ["Corrode","1c18ab1f-420d-0d8b-71d0-77ad3c439115","/Game/Maps/Rook/Rook","valorant/maps/1c18ab1f-420d-0d8b-71d0-77ad3c439115.png"],
  ["Skirmish D","1c7555fc-4bc6-3b98-9674-789d47ef6c50","/Game/Maps/Duel/Duel_Platform/Skirmish_D","valorant/maps/1c7555fc-4bc6-3b98-9674-789d47ef6c50.png"],
  ["Basic Training","1f10dab3-4294-3827-fa35-c2aa00213cf3","/Game/Maps/NPEV2/NPEV2","valorant/maps/1f10dab3-4294-3827-fa35-c2aa00213cf3.png"],
  ["Abyss","224b0a95-48b9-f703-1bd8-67aca101a61f","/Game/Maps/Infinity/Infinity","valorant/maps/224b0a95-48b9-f703-1bd8-67aca101a61f.png"],
  ["Haven","2bee0dc9-4ffe-519b-1cbd-7fbe763a6047","/Game/Maps/Triad/Triad","valorant/maps/2bee0dc9-4ffe-519b-1cbd-7fbe763a6047.png"],
  ["Drift","2c09d728-42d5-30d8-43dc-96a05cc7ee9d","/Game/Maps/HURM/HURM_Helix/HURM_Helix","valorant/maps/2c09d728-42d5-30d8-43dc-96a05cc7ee9d.png"],
  ["Bind","2c9d57ec-4431-9c5e-2939-8f9ef6dd5cba","/Game/Maps/Duality/Duality","valorant/maps/2c9d57ec-4431-9c5e-2939-8f9ef6dd5cba.png"],
  ["Breeze","2fb9a4fd-47b8-4e7d-a969-74b4046ebd53","/Game/Maps/Foxtrot/Foxtrot","valorant/maps/2fb9a4fd-47b8-4e7d-a969-74b4046ebd53.png"],
  ["Lotus","2fe4ed3a-450a-948b-6d6b-e89a78e680a9","/Game/Maps/Jam/Jam","valorant/maps/2fe4ed3a-450a-948b-6d6b-e89a78e680a9.png"],
  ["Skirmish E","4490f1d6-4818-bf5f-9b3a-9c9a8dbb52ed","/Game/Maps/Duel/Duel_Heady/Skirmish_E","valorant/maps/4490f1d6-4818-bf5f-9b3a-9c9a8dbb52ed.png"],
  ["The Range","5914d1e0-40c4-cfdd-6b88-eba06347686c","/Game/Maps/PovegliaV2/RangeV2","valorant/maps/5914d1e0-40c4-cfdd-6b88-eba06347686c.png"],
  ["District","690b3ed2-4dff-945b-8223-6da834e30d24","/Game/Maps/HURM/HURM_Alley/HURM_Alley","valorant/maps/690b3ed2-4dff-945b-8223-6da834e30d24.png"],
  ["Summit","756da597-416b-c0f2-f47b-afbdf28670bc","/Game/Maps/Plummet/Plummet","valorant/maps/756da597-416b-c0f2-f47b-afbdf28670bc.png"],
  ["Ascent","7eaecc1b-4337-bbf6-6ab9-04b8f06b3319","/Game/Maps/Ascent/Ascent","valorant/maps/7eaecc1b-4337-bbf6-6ab9-04b8f06b3319.png"],
  ["Sunset","92584fbe-486a-b1b2-9faa-39b0f486b498","/Game/Maps/Juliett/Juliett","valorant/maps/92584fbe-486a-b1b2-9faa-39b0f486b498.png"],
  ["Skirmish C","a264de0f-4a04-9c78-c97a-a6b192ce6e86","/Game/Maps/Duel/Duel_3/Skirmish_C","valorant/maps/a264de0f-4a04-9c78-c97a-a6b192ce6e86.png"],
  ["Skirmish B","a38a3f9a-4042-844c-8970-a3ac2f7ce93d","/Game/Maps/Duel/Duel_2/Skirmish_B","valorant/maps/a38a3f9a-4042-844c-8970-a3ac2f7ce93d.png"],
  ["Skirmish A","a9009649-421f-d5d5-f80c-0cbe02c125bb","/Game/Maps/Duel/Duel_1/Skirmish_A","valorant/maps/a9009649-421f-d5d5-f80c-0cbe02c125bb.png"],
  ["Fracture","b529448b-4d60-346e-e89e-00a4c527a405","/Game/Maps/Canyon/Canyon","valorant/maps/b529448b-4d60-346e-e89e-00a4c527a405.png"],
  ["Glitch","d6336a5a-428f-c591-98db-c8a291159134","/Game/Maps/HURM/HURM_HighTide/HURM_HighTide","valorant/maps/d6336a5a-428f-c591-98db-c8a291159134.png"],
  ["Split","d960549e-485c-e861-8d71-aa9d1aed12a2","/Game/Maps/Bonsai/Bonsai","valorant/maps/d960549e-485c-e861-8d71-aa9d1aed12a2.png"],
  ["Piazza","de28aa9b-4cbe-1003-320e-6cb3ec309557","/Game/Maps/HURM/HURM_Yard/HURM_Yard","valorant/maps/de28aa9b-4cbe-1003-320e-6cb3ec309557.png"],
  ["Icebox","e2ad5c54-4114-a870-9641-8ea21279579a","/Game/Maps/Port/Port","valorant/maps/e2ad5c54-4114-a870-9641-8ea21279579a.png"],
  ["The Range","ee613ee9-28b7-4beb-9666-08db13bb2244","/Game/Maps/Poveglia/Range","valorant/maps/ee613ee9-28b7-4beb-9666-08db13bb2244.png"],
  ["Pearl","fd267378-4d1d-484f-ff52-77821ed10dc2","/Game/Maps/Pitt/Pitt","valorant/maps/fd267378-4d1d-484f-ff52-77821ed10dc2.png"],
] as const

// Official Riot Data Dragon 16.18.1 catalog. Only these fixed champion IDs may
// form external artwork URLs; names and URLs from a snapshot never do.
const LEAGUE_CHAMPION_CATALOG = [
  ["Aatrox", "Aatrox"],
  ["Ahri", "Ahri"],
  ["Akali", "Akali"],
  ["Akshan", "Akshan"],
  ["Alistar", "Alistar"],
  ["Ambessa", "Ambessa"],
  ["Amumu", "Amumu"],
  ["Anivia", "Anivia"],
  ["Annie", "Annie"],
  ["Aphelios", "Aphelios"],
  ["Ashe", "Ashe"],
  ["Aurelion Sol", "AurelionSol"],
  ["Aurora", "Aurora"],
  ["Azir", "Azir"],
  ["Bard", "Bard"],
  ["Bel'Veth", "Belveth"],
  ["Blitzcrank", "Blitzcrank"],
  ["Brand", "Brand"],
  ["Braum", "Braum"],
  ["Briar", "Briar"],
  ["Caitlyn", "Caitlyn"],
  ["Camille", "Camille"],
  ["Cassiopeia", "Cassiopeia"],
  ["Cho'Gath", "Chogath"],
  ["Corki", "Corki"],
  ["Darius", "Darius"],
  ["Diana", "Diana"],
  ["Draven", "Draven"],
  ["Dr. Mundo", "DrMundo"],
  ["Ekko", "Ekko"],
  ["Elise", "Elise"],
  ["Evelynn", "Evelynn"],
  ["Ezreal", "Ezreal"],
  ["Fiddlesticks", "Fiddlesticks"],
  ["Fiora", "Fiora"],
  ["Fizz", "Fizz"],
  ["Galio", "Galio"],
  ["Gangplank", "Gangplank"],
  ["Garen", "Garen"],
  ["Gnar", "Gnar"],
  ["Gragas", "Gragas"],
  ["Graves", "Graves"],
  ["Gwen", "Gwen"],
  ["Hecarim", "Hecarim"],
  ["Heimerdinger", "Heimerdinger"],
  ["Hwei", "Hwei"],
  ["Illaoi", "Illaoi"],
  ["Irelia", "Irelia"],
  ["Ivern", "Ivern"],
  ["Janna", "Janna"],
  ["Jarvan IV", "JarvanIV"],
  ["Jax", "Jax"],
  ["Jayce", "Jayce"],
  ["Jhin", "Jhin"],
  ["Jinx", "Jinx"],
  ["Kai'Sa", "Kaisa"],
  ["Kalista", "Kalista"],
  ["Karma", "Karma"],
  ["Karthus", "Karthus"],
  ["Kassadin", "Kassadin"],
  ["Katarina", "Katarina"],
  ["Kayle", "Kayle"],
  ["Kayn", "Kayn"],
  ["Kennen", "Kennen"],
  ["Kha'Zix", "Khazix"],
  ["Kindred", "Kindred"],
  ["Kled", "Kled"],
  ["Kog'Maw", "KogMaw"],
  ["K'Sante", "KSante"],
  ["LeBlanc", "Leblanc"],
  ["Lee Sin", "LeeSin"],
  ["Leona", "Leona"],
  ["Lillia", "Lillia"],
  ["Lissandra", "Lissandra"],
  ["Locke", "Locke"],
  ["Lucian", "Lucian"],
  ["Lulu", "Lulu"],
  ["Lux", "Lux"],
  ["Malphite", "Malphite"],
  ["Malzahar", "Malzahar"],
  ["Maokai", "Maokai"],
  ["Master Yi", "MasterYi"],
  ["Mel", "Mel"],
  ["Milio", "Milio"],
  ["Miss Fortune", "MissFortune"],
  ["Wukong", "MonkeyKing"],
  ["Mordekaiser", "Mordekaiser"],
  ["Morgana", "Morgana"],
  ["Naafiri", "Naafiri"],
  ["Nami", "Nami"],
  ["Nasus", "Nasus"],
  ["Nautilus", "Nautilus"],
  ["Neeko", "Neeko"],
  ["Nidalee", "Nidalee"],
  ["Nilah", "Nilah"],
  ["Nocturne", "Nocturne"],
  ["Nunu & Willump", "Nunu"],
  ["Olaf", "Olaf"],
  ["Orianna", "Orianna"],
  ["Ornn", "Ornn"],
  ["Pantheon", "Pantheon"],
  ["Poppy", "Poppy"],
  ["Pyke", "Pyke"],
  ["Qiyana", "Qiyana"],
  ["Quinn", "Quinn"],
  ["Rakan", "Rakan"],
  ["Rammus", "Rammus"],
  ["Rek'Sai", "RekSai"],
  ["Rell", "Rell"],
  ["Renata Glasc", "Renata"],
  ["Renekton", "Renekton"],
  ["Rengar", "Rengar"],
  ["Riven", "Riven"],
  ["Rumble", "Rumble"],
  ["Ryze", "Ryze"],
  ["Samira", "Samira"],
  ["Sejuani", "Sejuani"],
  ["Senna", "Senna"],
  ["Seraphine", "Seraphine"],
  ["Sett", "Sett"],
  ["Shaco", "Shaco"],
  ["Shen", "Shen"],
  ["Shyvana", "Shyvana"],
  ["Singed", "Singed"],
  ["Sion", "Sion"],
  ["Sivir", "Sivir"],
  ["Skarner", "Skarner"],
  ["Smolder", "Smolder"],
  ["Sona", "Sona"],
  ["Soraka", "Soraka"],
  ["Swain", "Swain"],
  ["Sylas", "Sylas"],
  ["Syndra", "Syndra"],
  ["Tahm Kench", "TahmKench"],
  ["Taliyah", "Taliyah"],
  ["Talon", "Talon"],
  ["Taric", "Taric"],
  ["Teemo", "Teemo"],
  ["Thresh", "Thresh"],
  ["Tristana", "Tristana"],
  ["Trundle", "Trundle"],
  ["Tryndamere", "Tryndamere"],
  ["Twisted Fate", "TwistedFate"],
  ["Twitch", "Twitch"],
  ["Udyr", "Udyr"],
  ["Urgot", "Urgot"],
  ["Varus", "Varus"],
  ["Vayne", "Vayne"],
  ["Veigar", "Veigar"],
  ["Vel'Koz", "Velkoz"],
  ["Vex", "Vex"],
  ["Vi", "Vi"],
  ["Viego", "Viego"],
  ["Viktor", "Viktor"],
  ["Vladimir", "Vladimir"],
  ["Volibear", "Volibear"],
  ["Warwick", "Warwick"],
  ["Xayah", "Xayah"],
  ["Xerath", "Xerath"],
  ["Xin Zhao", "XinZhao"],
  ["Yasuo", "Yasuo"],
  ["Yone", "Yone"],
  ["Yorick", "Yorick"],
  ["Yunara", "Yunara"],
  ["Yuumi", "Yuumi"],
  ["Zaahen", "Zaahen"],
  ["Zac", "Zac"],
  ["Zed", "Zed"],
  ["Zeri", "Zeri"],
  ["Ziggs", "Ziggs"],
  ["Zilean", "Zilean"],
  ["Zoe", "Zoe"],
  ["Zyra", "Zyra"],
] as const

const RIOT_IMAGE_ROOT = 'https://ddragon.leagueoflegends.com/cdn/16.18.1/img'
export const DISCORD_TFT_IMAGE = `${RIOT_IMAGE_ROOT}/tft-arena/1.png`
const LEAGUE_DEFAULT_IMAGE = `${RIOT_IMAGE_ROOT}/map/map11.png`
const championLookup = new Map<string, {name: string; image: string}>()
for (const [name, id] of LEAGUE_CHAMPION_CATALOG) {
  for (const alias of [name, id]) championLookup.set(alias.toLowerCase(), {name, image: `${RIOT_IMAGE_ROOT}/champion/${id}.png`})
}

const assetKey = (name: string) => name.toLowerCase().replace(/[^a-z0-9]+/g, '')

/** Exact upload keys for the Discord application's Rich Presence art assets. */
export const DISCORD_AGENT_ASSETS = Object.freeze(AGENT_CATALOG.map(([name, uuid]) => Object.freeze({
  name,
  uuid,
  key: assetKey(name),
})))

const agentLookup = new Map<string, {name: string; image: string}>()
for (const agent of DISCORD_AGENT_ASSETS) {
  // Discord accepts external artwork. Resolve only bundled catalog UUIDs;
  // backend input can never choose a host, path, or arbitrary public URL.
  const image = `https://media.valorant-api.com/agents/${agent.uuid}/displayicon.png`
  for (const alias of [agent.name, agent.uuid, agent.key]) agentLookup.set(alias.toLowerCase(), {name: agent.name, image})
}

const mapLookup = new Map<string, string>()
for (const [name, uuid, mapUrl, path] of MAP_CATALOG) {
  for (const alias of [name, uuid, mapUrl, path, `riot/${path}`]) mapLookup.set(alias.toLowerCase(), name)
}

const modeLookup = new Map<string, string>([
  ['competitive', 'Competitive'],
  ['unrated', 'Unrated'],
  ['swiftplay', 'Swiftplay'],
  ['spike rush', 'Spike Rush'],
  ['spikerush', 'Spike Rush'],
  ['deathmatch', 'Deathmatch'],
  ['team deathmatch', 'Team Deathmatch'],
  ['teamdeathmatch', 'Team Deathmatch'],
  ['hurm', 'Team Deathmatch'],
  ['premier', 'Premier'],
  ['custom', 'Custom'],
  ['custom game', 'Custom'],
  ['escalation', 'Escalation'],
  ['ggteam', 'Escalation'],
  ['gggun', 'Escalation'],
  ['replication', 'Replication'],
  ['onefa', 'Replication'],
  ['retake', 'Retake'],
  ['skirmish', 'Skirmish'],
  ['gauntlet', 'Gauntlet'],
  ['gauntlet: glitched', 'Gauntlet: Glitched'],
  ['gauntlet glitched', 'Gauntlet: Glitched'],
  ['snowball', 'Snowball Fight'],
])

const FIVE_PLAYER_PARTY_MODES = new Set([
  'Competitive', 'Unrated', 'Swiftplay', 'Spike Rush', 'Team Deathmatch',
  'Premier', 'Escalation', 'Replication', 'Snowball Fight',
])

const LEAGUE_QUEUE_MODES = new Map<string, string>([
  ['0', 'Custom'], ['400', 'Draft Pick'], ['420', 'Ranked Solo/Duo'],
  ['430', 'Blind Pick'], ['440', 'Ranked Flex'], ['450', 'ARAM'],
  ['480', 'Swiftplay'], ['490', 'Quickplay'], ['700', 'Clash'],
  ['720', 'ARAM Clash'], ['830', 'Co-op vs. AI'], ['840', 'Co-op vs. AI'],
  ['850', 'Co-op vs. AI'], ['870', 'Co-op vs. AI'], ['880', 'Co-op vs. AI'],
  ['890', 'Co-op vs. AI'], ['900', 'ARURF'], ['1020', 'One for All'],
  ['1300', 'Nexus Blitz'], ['1700', 'Arena'], ['1710', 'Arena'],
  ['1900', 'URF'], ['2000', 'Tutorial'], ['2010', 'Tutorial'],
  ['2020', 'Tutorial'], ['2300', 'Brawl'], ['2400', 'ARAM: Mayhem'],
])

const TFT_QUEUE_MODES = new Map<string, string>([
  ['1090', 'Normal'], ['1100', 'Ranked'], ['1110', 'Tutorial'],
  ['1111', 'TFT'], ['1130', 'Hyper Roll'], ['1150', 'Double Up'], ['1160', 'Double Up'],
])

const leagueModeLookup = new Map<string, string>([
  ...[...LEAGUE_QUEUE_MODES.values()].map(mode => [mode.toLowerCase(), mode] as [string, string]),
  ['ranked solo', 'Ranked Solo/Duo'], ['ranked_solo_5x5', 'Ranked Solo/Duo'],
  ['ranked_flex_sr', 'Ranked Flex'], ['ranked flex 5v5', 'Ranked Flex'],
  ['normal', 'Normal'], ['classic', 'League of Legends'], ['cherry', 'Arena'],
  ['nexusblitz', 'Nexus Blitz'], ['oneforall', 'One for All'],
  ['kingporo', 'Poro King'], ['practice tool', 'Practice Tool'],
])

const tftModeLookup = new Map<string, string>([
  ...[...TFT_QUEUE_MODES.values()].map(mode => [mode.toLowerCase(), mode] as [string, string]),
  ['teamfight tactics', 'TFT'], ['ranked tft', 'Ranked'], ['ranked_tft', 'Ranked'],
  ['tft_tutorial', 'Tutorial'], ['tft_turbo', 'Hyper Roll'], ['hyperroll', 'Hyper Roll'],
  ['doubleup', 'Double Up'], ['double_up', 'Double Up'], ['pairs', 'Double Up'],
  ['tft_pairs', 'Double Up'], ['tft_double_up', 'Double Up'],
  ['ranked_tft_pairs', 'Double Up'], ['ranked_tft_double_up', 'Double Up'],
])

const leagueMapLookup = new Map<string, string>([
  ['summoner\'s rift', 'Summoner\'s Rift'], ['map11', 'Summoner\'s Rift'], ['11', 'Summoner\'s Rift'],
  ['howling abyss', 'Howling Abyss'], ['map12', 'Howling Abyss'], ['12', 'Howling Abyss'],
  ['rings of wrath', 'Rings of Wrath'], ['map30', 'Rings of Wrath'], ['30', 'Rings of Wrath'],
  ['nexus blitz', 'Nexus Blitz'], ['map21', 'Nexus Blitz'], ['21', 'Nexus Blitz'],
  ['the bandlewood', 'The Bandlewood'], ['map35', 'The Bandlewood'], ['35', 'The Bandlewood'],
])

const LEAGUE_PHASES = new Map<unknown, string>([
  ['lobby', 'In lobby'], ['matchmaking', 'Finding a match'], ['readycheck', 'Match found'],
  ['pregame', 'Champion select'], ['live', 'In game'],
])

const record = (value: unknown): RecordValue | undefined => (
  value !== null && typeof value === 'object' && !Array.isArray(value) ? value as RecordValue : undefined
)
const optionalFalse = (value: unknown) => value === undefined || value === false
const count = (value: unknown, maximum: number): value is number => (
  typeof value === 'number' && Number.isInteger(value) && value >= 0 && value <= maximum
)
function key(value: unknown) {
  if (typeof value !== 'string' || value.length > 256) return undefined
  for (const character of value) {
    const code = character.charCodeAt(0)
    if (code < 32 || (code >= 127 && code <= 159)) return undefined
  }
  return value.trim().toLowerCase()
}

function roundScore(value: unknown): number | undefined {
  const numeric = typeof value === 'string' && /^(0|[1-9][0-9]{0,2})$/.test(value) ? Number(value) : value
  return count(numeric, 100) ? numeric : undefined
}

function gameMode(value: unknown): string | undefined {
  const normalized = key(value)
  if (!normalized) return undefined
  if (modeLookup.has(normalized)) return modeLookup.get(normalized)
  // GLZ can provide an Unreal asset path instead of a queue identifier.
  if (!normalized.startsWith('/game/gamemodes/')) return undefined
  const asset = normalized.split('/').at(-1)?.split('.')[0].replace(/_gamemode$/, '')
  return modeLookup.get(asset ?? '')
}

function currentTeams(value: unknown): RecordValue[] {
  if (!Array.isArray(value) || value.length > 32) return []
  const teams: RecordValue[] = []
  let playerCount = 0
  for (const item of value) {
    const team = record(item)
    if (!team || !Array.isArray(team.players) || team.players.length > 64
      || team.players.some(player => !record(player))) return []
    playerCount += team.players.length
    if (playerCount > 64) return []
    teams.push(team)
  }
  return teams
}

function performance(statsValue: unknown) {
  const stats = record(statsValue)
  // Only actual in-match numeric counts qualify. A rendered score string or
  // overallStats cannot establish the player's current performance.
  if (!stats || !count(stats.kills, 1_000) || !count(stats.deaths, 1_000)) return 'Playing'
  const difference = stats.kills - stats.deaths
  if (difference <= -8) return 'Throwing'
  if (difference < 0) return 'Inting'
  return difference < 7 ? 'Trying' : 'Carrying'
}

function nativeQueue(value: unknown): string | undefined {
  if (count(value, 100_000)) return String(value)
  const normalized = key(value)
  return normalized && /^(0|[1-9][0-9]{0,5})$/.test(normalized) ? normalized : undefined
}

function leagueMode(match: RecordValue, tft: boolean): string {
  const queues = tft ? TFT_QUEUE_MODES : LEAGUE_QUEUE_MODES
  const fallback = tft ? 'TFT' : 'League of Legends'
  // A queue ID is authoritative. Do not reuse an older game's mode label when
  // the client introduces a new queue, or mistake solo TFT for Double Up.
  const queue = nativeQueue(match.queue) ?? nativeQueue(match.queueId)
  if (queue !== undefined) return queues.get(queue) ?? fallback
  if (tft && match.teamMode === 'duos') return 'Double Up'
  const modes = tft ? tftModeLookup : leagueModeLookup
  for (const value of [match.queue, match.queueId, match.modeId, match.mode]) {
    const mode = modes.get(key(value) ?? '')
    if (mode) return mode
  }
  return fallback
}

function leagueActivity(match: RecordValue, teams: RecordValue[]): DiscordActivity {
  const tft = match.game === 'Teamfight Tactics'
  const phase = LEAGUE_PHASES.get(match.phase)!
  const playing = match.phase === 'live'
  const choosing = playing || match.phase === 'pregame'
  const selves = teams.flatMap(team => (team.players as RecordValue[]).filter(player => player.self === true))
  const self = selves.length === 1 && optionalFalse(selves[0].hidden) ? selves[0] : undefined
  const champion = !tft && choosing && self ? championLookup.get(key(self.agent) ?? '') : undefined
  const map = !tft ? leagueMapLookup.get(key(match.map) ?? '') : undefined
  const details = tft ? 'Playing Teamfight Tactics'
    : champion ? `${champion.name}${map ? ` on ${map}` : ' in League of Legends'}`
      : map && choosing ? `Playing on ${map}` : 'Playing League of Legends'
  const parts = [leagueMode(match, tft)]
  if (!playing) parts.push(tft && match.phase === 'pregame' ? 'Getting ready' : phase)

  const stats = playing && self ? record(self.stats) : undefined
  const health = stats?.health
  if (tft && typeof health === 'number' && Number.isFinite(health) && health >= 0 && health <= 1_000) {
    parts.push(`${Math.round(health * 10) / 10} HP`)
  }
  if (!tft && stats && count(stats.kills, 1_000) && count(stats.deaths, 1_000) && count(stats.assists, 1_000)) {
    parts.push(`${stats.kills}/${stats.deaths}/${stats.assists} KDA`)
  }
  // Only the backend's bounded match duration is accepted, never timestamps or
  // account-controlled text. Lobby snapshots may still carry stale duration.
  if (playing && typeof match.elapsed === 'string' && /^(0|[1-9][0-9]{0,2}):[0-5][0-9]$/.test(match.elapsed)) {
    parts.push(match.elapsed)
  }
  if (playing && parts.length === 1) parts.push(phase)

  const partySize = count(match.partySize, 64) && match.partySize >= 1 ? match.partySize : undefined
  const partyMax = count(match.partyMax, 64) && match.partyMax >= (partySize ?? 1) ? match.partyMax : undefined
  if (partySize !== undefined) parts.push(partyMax === undefined ? `Party of ${partySize}` : `Party ${partySize}/${partyMax}`)

  return {
    type: 0,
    details,
    state: parts.join(' · '),
    assets: {
      large_image: tft ? DISCORD_TFT_IMAGE : champion?.image ?? LEAGUE_DEFAULT_IMAGE,
      large_text: tft ? 'Teamfight Tactics' : champion ? `${champion.name} · League of Legends` : 'League of Legends',
      small_image: DISCORD_PEAKS_IMAGE,
      small_text: 'Peaks',
    },
    ...(partySize !== undefined && partyMax !== undefined ? {party: {size: [partySize, partyMax] as [number, number]}} : {}),
  }
}

/** Pure projection of a backend snapshot into bounded, public game facts. */
export function buildDiscordActivity(snapshot: unknown): DiscordActivity | null {
  const state = record(snapshot)
  const settings = record(state?.settings)
  const match = record(state?.currentMatch)
  // Match streamerMode describes incognito players anywhere in the roster.
  // Only the user's global setting opts their entire activity out of sharing.
  if (!state || state.locked !== false || state.gameDetected !== true || !settings
    || !optionalFalse(settings.streamerMode) || !match
    || !optionalFalse(match.isStale)) return null

  const teams = currentTeams(match.teams)
  if (match.game === 'League of Legends' || match.game === 'Teamfight Tactics') {
    return LEAGUE_PHASES.has(match.phase) ? leagueActivity(match, teams) : null
  }
  if (match.game !== 'VALORANT' || (match.phase !== 'live' && match.phase !== 'pregame')) return null
  const selves = teams.flatMap(team => (team.players as RecordValue[])
    .filter(player => player.self === true)
    .map(player => ({player, team})))
  const self = selves.length === 1 && optionalFalse(selves[0].player.hidden) ? selves[0] : undefined
  const map = mapLookup.get(key(match.map) ?? '')
  const agent = self ? agentLookup.get(key(self.player.agent) ?? '') : undefined
  const verb = match.phase === 'live' && self ? performance(self.player.stats) : 'Playing'
  const details = map ? `${verb} on ${map}` : verb === 'Playing' ? 'Playing VALORANT' : `${verb} in VALORANT`
  const mode = gameMode(match.queue) ?? gameMode(match.queueId) ?? gameMode(match.modeId) ?? gameMode(match.mode) ?? 'VALORANT'
  const parts = [mode]

  if (match.phase === 'pregame') {
    parts.push('Agent select')
  } else if (self && teams.length === 2 && match.freeForAll !== true && mode !== 'Deathmatch') {
    const ownScore = roundScore(self.team.score)
    const opponent = teams.find(team => team !== self.team)
    const enemyScore = roundScore(opponent?.score)
    if (ownScore !== undefined && enemyScore !== undefined) parts.push(`${ownScore}:${enemyScore}`)
  }

  const partySize = count(match.partySize, 20) && match.partySize >= 1 ? match.partySize : undefined
  const nativeQueue = key(match.queue) || key(match.queueId)
  const partyMode = nativeQueue ? gameMode(nativeQueue) : mode
  const defaultPartyMax = match.partyMax === undefined && match.freeForAll !== true && teams.length <= 2
    && partySize !== undefined && partySize <= 5 && FIVE_PLAYER_PARTY_MODES.has(partyMode ?? '') ? 5 : undefined
  const partyMax = count(match.partyMax, 20) && match.partyMax >= (partySize ?? 1) ? match.partyMax : defaultPartyMax
  if (partySize !== undefined) parts.push(partyMax === undefined ? `Party of ${partySize}` : `Party ${partySize}/${partyMax}`)

  return {
    type: 0,
    details,
    state: parts.join(' · '),
    assets: {
      ...(agent ? {large_image: agent.image, large_text: agent.name} : {}),
      small_image: DISCORD_PEAKS_IMAGE,
      small_text: 'Peaks',
    },
    ...(partySize !== undefined && partyMax !== undefined ? {party: {size: [partySize, partyMax] as [number, number]}} : {}),
  }
}
