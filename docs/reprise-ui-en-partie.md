# Reprendre les trois écrans Peaks

Le travail se trouve sur `antd-ui`, dans `C:\Users\Anis\Desktop\peaks-antd`. Ce dossier utilise Ant Design 6. Lire son `AGENTS.md` avant de modifier le rendu.

| Écran | Point d’entrée | Comportement à préserver |
| --- | --- | --- |
| VALORANT en direct | `src/renderer/components/ValorantLiveScoreboard.tsx` | Comparer les deux équipes, basculer entre la partie et l’historique récent, ouvrir le détail par le chevron. |
| TFT en direct | `src/renderer/components/TftLiveStandings.tsx` | Classer selon la position observée, distinguer zéro PV d’une valeur absente, ouvrir le panneau du tacticien. Double Up respecte les paires déclarées. |
| Fiche de compte enregistré | `src/renderer/screens/AccountDetailScreen.tsx` et `src/renderer/components/AccountMatchHistory.tsx` | Entrer par Comptes, puis le portrait. Le tableau trie les parties des trois jeux par date et conserve l’ordre source pour les anciennes parties sans date. |

`CurrentMatchScreen.tsx` choisit la vue selon la phase. `LiveRoster.tsx` et `useMatchRoster.tsx` centralisent l’ordre, les déplacements clavier/souris et les identités affichées. Les dictionnaires français, anglais et coréen se trouvent dans `src/renderer/i18n/locales`.

L’utilisateur veut des interfaces sobres en texte. Garder les logos de jeu, les onglets de la fiche compte et les résultats sous forme d’icônes nommées pour les lecteurs d’écran. Les infobulles donnent les précisions à la demande.

## Revoir le rendu sans compte Riot

Dans ce dossier, lancer `npx vite --host 127.0.0.1 --port 5839`. Ouvrir le serveur local et déverrouiller **la démo navigateur** avec `2580`.

- Ouvrir **Partie en cours** depuis `/` pour VALORANT, `/?matchLayout=tft` pour TFT et `/?matchLayout=tft-double-up` pour les duos.
- Ouvrir **Comptes**, puis le portrait d’un compte pour la fiche. Les onglets Parties, Analyse et Sécurité restent disponibles.
- Les captures de démo de ce poste se trouvent dans `artifacts/ui-review/`.

## Vérifications effectuées

`npm run build:web`, `npm run lint` et 118 tests ciblés passent. Le parcours en français a été vérifié dans Chromium à 1440 × 900 et 1080 × 680, avec ouverture de profil, réorganisation clavier/souris et ouverture de partie. Vérification en client Riot réel encore à faire si une validation native est demandée.

Pour un changement ciblé, relancer `npx vitest run AccountMatchHistory TftLiveStandings ValorantLiveScoreboard CurrentMatchScreen PlayerMatchCards`. Indépendamment du rendu, `electron/telemetry.test.ts` échoue sur le diagnostic de la commande `cancel_connection`.
