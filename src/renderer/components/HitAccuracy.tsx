import {HStack} from '@astryxdesign/core/HStack'
import {Text} from '@astryxdesign/core/Text'
import {VStack} from '@astryxdesign/core/VStack'
import {formatNumber, t} from '../i18n'
import {ChartSection} from './RiotActivity'

export function HitAccuracy({head, body, legs}: {head?: number; body?: number; legs?: number}) {
  const total = head != null && body != null && legs != null ? head + body + legs : 0
  const parts = [{label: 'Head', hits: head, y: 38}, {label: 'Body', hits: body, y: 116}, {label: 'Legs', hits: legs, y: 191}].map(part => ({...part, share: total && part.hits != null ? part.hits / total * 100 : undefined}))
  return <ChartSection title={t('Accuracy')}>
    <HStack gap={6} align="center" wrap="wrap">
      <svg className="pd-hit-body" viewBox="0 0 180 250" role="img" aria-label={parts.map(part => `${t(part.label)} ${part.share == null ? '—' : `${formatNumber(part.share, {maximumFractionDigits: 1})}%`}`).join(' · ')}>
        {parts.map((part, index) => <g key={part.label} className="pd-hit-body__zone" fill={`color-mix(in srgb, var(--color-activity-heat) ${part.share ?? 0}%, var(--color-background-muted))`}>
          <title>{`${t(part.label)} · ${part.hits ?? '—'} ${t('hits')}`}</title>
          {index === 0 ? <circle cx="90" cy="31" r="24" /> : index === 1 ? <path d="M65 61 L115 61 Q126 61 131 77 L150 139 L132 146 L117 103 L116 153 L64 153 L63 103 L48 146 L30 139 L49 77 Q54 61 65 61Z" /> : <path d="M64 160 L116 160 L118 232 L98 232 L90 193 L82 232 L62 232Z" />}
          <text x="90" y={part.y} textAnchor="middle" className="pd-hit-body__value" fill={(part.share ?? 0) > 65 ? 'var(--color-background-body)' : 'var(--color-text-primary)'}>{part.share == null ? '—' : `${Math.round(part.share)}%`}</text>
        </g>)}
      </svg>
      <VStack gap={5}>{parts.map(part => <VStack key={part.label} gap={1}>
        <HStack gap={5} justify="between"><Text>{t(part.label)}</Text><Text weight="semibold" hasTabularNumbers>{part.share == null ? '—' : `${formatNumber(part.share, {maximumFractionDigits: 1})}%`}</Text></HStack>
        <Text type="supporting" color="secondary">{part.hits == null ? '—' : formatNumber(part.hits)} {t('hits')}</Text>
      </VStack>)}</VStack>
    </HStack>
  </ChartSection>
}
