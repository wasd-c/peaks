# Third-party notices

Peaks is an independent project and is not endorsed by Riot Games. Riot Games,
League of Legends, Teamfight Tactics, VALORANT, and their associated marks and
artwork are trademarks or registered trademarks of Riot Games, Inc.

## Adapted and reference source

The headed browser sign-in, account/factor inspection, and fixed Riot Mobile
enable/verify requests are narrow adaptations of [Riot Games Mobile 2FA
Bypass](https://github.com/Askin242/RiotGames-Mobile-2FA-Bypass). Peaks adds an
explicit read-only preparation and confirmation boundary, exact selected-account
binding, refusal to rotate an existing factor, encrypted seed persistence
before verification, and redacted diagnostics. Peaks does not adapt that
project's push-approval/device registration, plaintext credential storage,
TLS-unpinning, unauthenticated LAN server, or unsigned self-updater features.

The verified Windows Riot lockfile discovery and local VALORANT identity path
were informed by
[VALORANT-rank-yoinker](https://github.com/zayKenyon/VALORANT-rank-yoinker).
Peaks additionally binds the lockfile PID to the expected live Riot executable,
keeps lockfile credentials inside the Python service, and does not reveal
identities hidden by streamer/incognito protections.

The complete notices required by those projects' licenses follow.

The onboarding visual effects adapt the SpecularButton, CRTWarp, and ASCIIText
components from [React Bits](https://github.com/DavidHDev/react-bits).

### React Bits — MIT + Commons Clause License Condition v1.0

Copyright (c) 2026 David Haz

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, and distribute the Software **as part of
an application, website, or product**, subject to the following conditions:
The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

#### Commons Clause Restriction

You may use this Software, including for any commercial purpose, **so long as
you do not sell, sublicense, or redistribute the components themselves-whether
alone, in a bundle, or as a ported version.**

#### No Warranty

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

### Riot Games Mobile 2FA Bypass — MIT License

Copyright (c) 2026 Sysy's

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

### VALORANT-rank-yoinker — ISC License

Copyright (c) 2021–2023 Zay Kenyon and Contributors

Permission to use, copy, modify, and/or distribute this software for any
purpose with or without fee is hereby granted, provided that the above
copyright notice and this permission notice appear in all copies.

THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY
SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER
RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT,
NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF OR IN CONNECTION WITH THE
USE OR PERFORMANCE OF THIS SOFTWARE.

## Runtime and artwork

[Patchright Python](https://github.com/Kaliiiiiiiiii-Vinyzu/patchright-python)
is distributed under the Apache License 2.0 and is based on Microsoft
Playwright. Peaks pins Patchright and packages its Python modules and driver;
the frozen onedir artifact also retains Patchright's complete license in its
package metadata. Electron builds stage the exact Chrome for Testing revision
declared by the pinned Patchright package. Its upstream attribution and license
notices are retained in the browser distribution's `ABOUT` file. Patchright's
staged FFmpeg helper is distributed under LGPL 2.1; its complete
`COPYING.LGPLv2.1` is retained beside the executable.

Artwork in `src/peaks/ui/assets/riot/` is downloaded from Riot's developer
asset bundle or the community-run valorant-api.com media service. The manifest
beside those files records each source URL. Do not imply Riot endorsement when
redistributing the app.

QR decoding uses zxing-cpp under the Apache License 2.0.
