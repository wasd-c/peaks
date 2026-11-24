import {Fragment, useEffect, useState} from 'react'
import {Heading, HStack, Icon, Text, VStack} from '../ui'
import {Shapes, Sparkles} from 'lucide-react'
import {formatNumber, localeTags, t, useLocale} from '../i18n'
import {tftAssetLabel, tftChampionTraitStyle, tftProfileImage, tftUnitPortrait} from '../profileAssets'
import {loadTftChampion, tftChampionEntry, type TftChampion, type TftScaling} from '../tftCatalog'
import {tftSpellParts, type TftSpellPart} from '../tftSpell'

const number = (value: number | null | undefined) => value == null ? '—' : formatNumber(value, {maximumFractionDigits: 2})
const labels = {ap: 'Ability power', ad: 'Attack damage', health: 'Health', armor: 'Armor', mr: 'Magic resist', speed: 'Attack speed', mana: 'Mana', range: 'Range', gold: 'gold'}

function ScalingIcon({scaling}: {scaling: TftScaling | 'range' | 'gold'}) {
  const source = tftProfileImage(`tft-stats/${scaling === 'speed' ? 'attack-speed' : scaling}.png`)
  return <img className="pd-tft-scaling-icon" data-scaling={scaling} src={source} alt={t(labels[scaling])} title={t(labels[scaling])} />
}

export function TftSpellDescription({parts, stars}: {parts: TftSpellPart[]; stars: number}) {
  return <Text as="p" className="pd-tft-spell-description">{parts.map((part, index) => {
    if (part.kind === 'break') return <br key={index} />
    if (part.kind === 'icon') return <ScalingIcon key={index} scaling={part.scaling} />
    if (part.kind === 'text') return <Text key={index} type="inherit" color="inherit" data-scaling={part.scaling} weight={part.emphasis ? 'semibold' : undefined}>{part.text}</Text>
    if (part.kind === 'unavailable') return <Text key={index} type="inherit" color="secondary" aria-label={t(part.reason === 'live' ? 'This value changes during combat.' : 'This value is missing from the set data.')}>{t(part.reason === 'live' ? 'variable' : 'n/a')}</Text>
    const values = part.values.slice(0, stars === 4 ? 4 : 3)
    const varies = new Set(values).size > 1
    if (!varies) return <Text key={index} type="inherit" weight="semibold" className="pd-tft-spell-value" data-active="true" data-scaling={part.scaling}>{number(values[0])}</Text>
    return <Text key={index} type="inherit" className="pd-tft-spell-values" hasTabularNumbers>
      {'[ '}{values.map((value, level) => <Fragment key={level}>
        {level ? ' / ' : null}<Text type="inherit" className="pd-tft-spell-value" data-active={stars === level + 1} data-scaling={part.scaling}
          weight={stars === level + 1 ? 'bold' : 'normal'} aria-label={t('{{stars}} stars: {{value}}', {stars: level + 1, value: number(value)})}>{number(value)}</Text>
      </Fragment>)}{' ]'}
    </Text>
  })}</Text>
}

export function TftChampionDetails({champion, id, stars, setNumber}: {champion: TftChampion; id: string; stars: number; setNumber?: number}) {
  const language = useLocale()
  const entry = tftChampionEntry(id, setNumber)
  const parts = tftSpellParts(champion, language)
  const scalings = new Set(parts.flatMap(part => part.kind === 'icon' ? [part.scaling] : []))
  const type = scalings.has('ap') && scalings.has('ad') ? 'Mixed ability'
    : scalings.has('ap') || champion.role?.startsWith('AP') ? 'Magic ability'
      : scalings.has('ad') || champion.role?.startsWith('AD') ? 'Physical ability' : 'Ability'
  const abilityIcon = tftProfileImage(champion.ability.icon)
  const portrait = tftUnitPortrait(id, setNumber)
  const stats = champion.stats
  return <VStack gap={4} className="pd-tft-champion-card__body" data-champion={id} data-set={entry?.set} data-stars={stars}>
    <HStack gap={3} align="center" justify="between">
      <HStack gap={3} align="center">
        {portrait ? <img className="pd-tft-champion-card__portrait" src={portrait} alt="" /> : null}
        <VStack gap={0.5}>
          <Heading level={3}>{champion.names[language] || champion.names.en || id}</Heading>
          <Text type="supporting">{t('Set {{set}}', {set: entry?.set ?? '—'})} · {t('{{stars}} stars', {stars})}</Text>
        </VStack>
      </HStack>
      <HStack gap={1} align="center" className="pd-tft-champion-card__cost"><ScalingIcon scaling="gold" /><Text weight="semibold">{champion.cost ?? '—'}</Text></HStack>
    </HStack>
    <VStack gap={2} aria-label={t('Traits')}>
      {(champion.traits[language] ?? champion.traits.en ?? []).map((name, index) => {
        const style = tftChampionTraitStyle(Object.values(champion.traits).flatMap(names => names[index] ? [names[index]] : []), entry?.set)
        return <HStack key={name} gap={2} align="center">
          {style ? <HStack className="pd-tft-icon pd-tft-icon--small" style={style} aria-hidden /> : <Icon icon={Shapes} />}
          <Text weight="bold">{name}</Text>
        </HStack>
      })}
    </VStack>
    <VStack gap={3} className="pd-tft-champion-card__ability">
      <HStack gap={3} align="center">
        {abilityIcon ? <img className="pd-tft-champion-card__spell-icon" src={abilityIcon} alt="" /> : <Icon icon={Sparkles} size="lg" />}
        <VStack gap={0.5}>
          <Heading level={4}>{champion.ability.names[language] || champion.ability.names.en || t('Ability')}</Heading>
          <Text type="supporting" className="pd-tft-ability-type" data-scaling={type === 'Magic ability' ? 'ap' : type === 'Physical ability' ? 'ad' : undefined}>{t(type)}</Text>
          <HStack gap={1} align="center" className="pd-tft-mana"><ScalingIcon scaling="mana" /><Text type="supporting" color="inherit">{stats.mana === 0 ? t('Passive · no mana cost') : t('Mana: {{initial}} / {{cost}}', {initial: number(stats.initialMana), cost: number(stats.mana)})}</Text></HStack>
        </VStack>
      </HStack>
      {parts.length ? <TftSpellDescription parts={parts} stars={stars} /> : <Text color="secondary">{t('Ability details unavailable for this unit.')}</Text>}
    </VStack>
    <VStack gap={2}>
      <Text type="supporting">{t('Base stats · 1 star')}</Text>
      <HStack gap={4} wrap="wrap" className="pd-tft-champion-card__stats">
        {([['health', 'hp'], ['ad', 'damage'], ['speed', 'attackSpeed'], ['armor', 'armor'], ['mr', 'magicResist']] as const).map(([scaling, stat]) =>
          <HStack key={stat} gap={1} align="center" className="pd-tft-stat" data-scaling={scaling}><ScalingIcon scaling={scaling} /><Text type="supporting" color="inherit">{number(stats[stat])}</Text></HStack>)}
        <HStack gap={1} align="center"><ScalingIcon scaling="range" /><Text type="supporting" color="primary">{number(stats.range)}</Text></HStack>
      </HStack>
    </VStack>
    <Text type="supporting">{t('Base ability values · before items and traits.')}{parts.some(part => part.kind === 'unavailable' && part.reason !== 'live') ? ` ${t('n/a: value missing from the set data.')}` : ''}{parts.some(part => part.kind === 'unavailable' && part.reason === 'live') ? ` ${t('Variable values depend on combat.')}` : ''}</Text>
    {champion.ability.source ? <Text type="supporting">{t('Spell data: {{source}} · {{patch}} · {{date}}', {source: champion.ability.source.provider, patch: champion.ability.source.patch.toUpperCase(), date: new Intl.DateTimeFormat(localeTags[language], {dateStyle: 'medium'}).format(new Date(champion.ability.source.generated))})}</Text> : null}
  </VStack>
}

export function TftChampionCard({id, stars, setNumber, variant}: {id: string; stars: number; setNumber?: number; variant?: string}) {
  useLocale()
  const [result, setResult] = useState<{key: string; champion?: TftChampion} | null>(null)
  const key = `${setNumber ?? ''}:${variant ?? ''}:${id}`
  useEffect(() => {
    let current = true
    void loadTftChampion(id, setNumber, variant).then(champion => { if (current) setResult({key, champion}) }, () => { if (current) setResult({key}) })
    return () => { current = false }
  }, [id, setNumber, variant, key])
  if (result?.key === key && result.champion) return <TftChampionDetails champion={result.champion} id={id} stars={stars} setNumber={setNumber} />
  return <VStack gap={2}><Heading level={3}>{tftAssetLabel('champion', id, setNumber)}</Heading><Text color="secondary">{result?.key === key ? t('Ability details unavailable for this unit.') : t('Loading ability…')}</Text></VStack>
}
