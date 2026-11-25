# Reprendre les écrans de partie Peaks

Le travail se trouve sur `antd-ui`, dans `C:\Users\Anis\Desktop\peaks-antd`. Ce dossier utilise Ant Design 6. Lire son `AGENTS.md` avant de modifier le rendu.

| Écran | Point d’entrée | Comportement à préserver |
| --- | --- | --- |
| VALORANT en direct | `src/renderer/components/ValorantLiveScoreboard.tsx` | Comparer les deux équipes, basculer entre la partie et l’historique récent, ouvrir le détail par le chevron. |
| TFT en direct | `src/renderer/components/TftLiveStandings.tsx` | Classer selon la position observée, distinguer zéro PV d’une valeur absente, cliquer sur le nom pour le profil ou déplier les données supplémentaires avec le chevron. Double Up respecte les paires déclarées. |
| Fiche de compte enregistré | `src/renderer/screens/AccountDetailScreen.tsx` et `src/renderer/components/AccountMatchHistory.tsx` | Entrer par Comptes, puis le portrait. L’historique trie les parties par date. Le score VALORANT ou la place TFT porte le résultat. Les anciens rapports sans date gardent leur ordre source. |
| Résumé de fin de partie | `src/renderer/components/PostMatchReviewDialog.tsx` | Score orienté côté joueur ou place finale, composition TFT et variation historique de RR/LP. Le rapport complet et le partage restent accessibles. |

`CurrentMatchScreen.tsx` choisit la vue selon la phase. `LiveRoster.tsx` et `useMatchRoster.tsx` centralisent l’ordre, les déplacements clavier/souris et les identités affichées. Les dictionnaires français, anglais et coréen se trouvent dans `src/renderer/i18n/locales`.

Pour chaque partie, partir de la donnée que le joueur reconnaît en jeu. Utiliser l’emblème officiel de la division enregistrée et le delta de cette partie. Pour LoL et TFT, l’emblème représente le palier et le chiffre précise la division. Le nom complet reste accessible. Une défaite par abandon ou un K/D/A peuvent demander un verdict explicite.

## Revoir le rendu sans compte Riot

Dans ce dossier, lancer `npx vite --host 127.0.0.1 --port 5839`. Ouvrir le serveur local et déverrouiller **la démo navigateur** avec `2580`.

- Ouvrir **Partie en cours** depuis `/` pour VALORANT, `/?matchLayout=tft` pour TFT et `/?matchLayout=tft-double-up` pour les duos.
- Pour rejouer la fin de partie, utiliser `/?postMatch=1` en VALORANT ou `/?postMatch=1&matchLayout=tft` en TFT. Le résumé apparaît après la détection du résultat par la démo.
- Ouvrir **Comptes**, puis le portrait d’un compte pour la fiche. Les onglets Parties, Analyse et Sécurité restent disponibles.
- Les captures de la fiche compte se trouvent dans `artifacts/ui-review/account-games-1440.png` et `account-games-1080.png`. La démo utilisée pour ces captures contient sept matchs synthétiques et un compte Or 1 à 97 RR.

## Vérifications effectuées

La passe initiale sur les trois écrans a couvert 118 tests ciblés, l’ouverture de profil et la réorganisation clavier/souris. La passe sur l’historique et les emblèmes a vérifié 58 tests ciblés, `npm run build:web` et `npm run lint`. Le parcours de la fiche compte a été vérifié en français dans Chromium à 1440 × 900 et 1080 × 680, avec ouverture de partie au clavier. La validation avec un client Riot réel reste à effectuer si elle est demandée.

Cette passe a validé 100 tests ciblés, le lint et le build web. Les nouvelles captures sont dans `artifacts/ui-review/{valorant,tft}-{live,recap}-{1440,1080}.png`. Pour vérifier le parcours, ouvrir le partage, revenir par Échap, puis ouvrir le rapport. Tester aussi avec la réduction des animations activée.

Pour un changement ciblé, relancer `npx vitest run PostMatchReviewDialog postMatch AccountMatchHistory TftLiveStandings ValorantLiveScoreboard CurrentMatchScreen PlayerMatchCards`. Indépendamment du rendu, `electron/telemetry.test.ts` échoue sur le diagnostic de la commande `cancel_connection`.
