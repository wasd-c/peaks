import {Button} from '@astryxdesign/core/Button'
import {Grid} from '@astryxdesign/core/Grid'
import {Heading} from '@astryxdesign/core/Heading'
import {HStack} from '@astryxdesign/core/HStack'
import {Icon} from '@astryxdesign/core/Icon'
import {Section} from '@astryxdesign/core/Section'
import {Text} from '@astryxdesign/core/Text'
import {VStack} from '@astryxdesign/core/VStack'
import {ArrowUpRight, ChartNoAxesCombined, Layers3, Mountain} from 'lucide-react'
import ascentUrl from '../../peaks/ui/assets/riot/artwork/valorant-ascent.png'

export const ONBOARDING_HEADING = 'Welcome to Peaks'
export const ONBOARDING_BODY = 'Add your Riot accounts to get started.'
export const ONBOARDING_ACTION = 'Get started'

interface OnboardingScreenProps {
  onGetStarted: () => void
  reduceMotion?: boolean
}

export function OnboardingScreen({onGetStarted, reduceMotion = false}: OnboardingScreenProps) {
  return (
    <VStack className="pd-entry pd-entry--welcome" data-reduce-motion={reduceMotion || undefined} as="main" gap={0}>
      <HStack className="pd-entry-brand" align="center" gap={2}>
        <Icon icon={Mountain} size="lg" />
        <Text weight="semibold">PEAKS</Text>
      </HStack>
      <Grid className="pd-entry-welcome-grid" columns={2} gap={0}>
        <VStack className="pd-entry-welcome-copy" gap={8} justify="center">
          <VStack gap={4}>
            <Heading className="pd-entry-title" level={1}>{ONBOARDING_HEADING}</Heading>
            <Text className="pd-entry-description" color="secondary">{ONBOARDING_BODY}</Text>
          </VStack>
          <VStack gap={4}>
            <HStack gap={3} align="center"><Icon icon={Layers3} color="secondary" /><Text>Manage your Riot accounts.</Text></HStack>
            <HStack gap={3} align="center"><Icon icon={ChartNoAxesCombined} color="secondary" /><Text>View ranks and recent matches.</Text></HStack>
          </VStack>
          <HStack><Button className="pd-entry-start" label={ONBOARDING_ACTION} variant="primary" size="lg" endContent={<Icon icon={ArrowUpRight} />} onClick={onGetStarted} /></HStack>
        </VStack>
        <Section className="pd-entry-world" padding={0}>
          <img className="pd-entry-world-art" src={ascentUrl} alt="" />
          <VStack className="pd-entry-world-copy" gap={3}>
            <HStack gap={3}><Text type="supporting">VALORANT</Text><Text type="supporting">/</Text><Text type="supporting">LEAGUE</Text><Text type="supporting">/</Text><Text type="supporting">TFT</Text></HStack>
          </VStack>
        </Section>
      </Grid>
    </VStack>
  )
}
