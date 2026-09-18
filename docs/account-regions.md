# Account regions

Peaks records regions per game. The existing `accounts.region` field remains
League/TFT's platform for compatibility; `accounts.valorant_region` is separate.
Existing profiles upgrade to schema 3 without changing accounts, ranks or secrets.
The UI labels known regions with the game and displays “Region not detected” when
none is known. A League region is never used to route a VALORANT match.

## Detection and renewal

- After authenticated `/userinfo`, read the explicit `cpid` or `lol.cpid` platform.
  Unknown values and conflicting platforms are ignored; country, locale, IP and
  Riot ID tags are never used to infer a region.
- When the same authorization supplies an ID token, query Riot Geo's fixed
  VALORANT product endpoint and read only `affinities.live`. The ID token is bound
  to the access token and checked against the authenticated userinfo subject.
  ID and geo tokens stay in memory and never enter the account database or vault.
- Region enrichment is optional. Timeouts, missing permissions, missing ID tokens,
  redirects, malformed responses and unsupported values leave known regions intact.
  A verified active VALORANT client's PD route can fill an unknown VALORANT region.
- Onboarding, imported sessions, background session renewal and QR renewal persist
  metadata only after account identity binding. Existing saved accounts update on
  their normal renewal while Peaks is unlocked; no account re-add is necessary.
  Expired or rejected sessions still require the existing sign-in recovery.

Riot documents CPID for approved RSO clients in its
[OAuth client documentation](https://support-developer.riotgames.com/hc/en-us/articles/22897607341075-OAuth-Client-Documentation).
Peaks' current private Riot Client authorization flow already requests `lol`;
this change does not alter its authorization scopes. Availability of optional
metadata depends on the actual Riot response. The private VALORANT endpoint
contract is described in the [Riot Geo reference](https://valapidocs.techchrism.me/endpoint/riot-geo).
