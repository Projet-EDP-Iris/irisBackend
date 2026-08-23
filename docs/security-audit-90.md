# Audit de securite - issue #90

Date : 23 aout 2026. Perimetre : irisBackend et irisFrontendApp.

## Synthese

| Severite | Constat | Statut |
| --- | --- | --- |
| Critique | Une cle JWT de test peut demarrer le service en production. | Corrige dans la PR de durcissement associee. |
| Elevee | La connexion et l inscription ne sont pas limitees ; seul le reset de mot de passe l etait. | Corrige dans la PR de durcissement associee. |
| Elevee | L origine CORS null est acceptee y compris en production. | Corrige dans la PR de durcissement associee. |
| Moyenne | HTTPS n est pas redirige explicitement par l application en production. | Corrige dans la PR de durcissement associee. |
| Moyenne | Le scanning de secrets GitHub est desactive. | Action d organisation requise. |
| Moyenne | Aucun CAPTCHA n est en place pour inscription/connexion. | A planifier apres choix Turnstile ou hCaptcha. |
| Faible | Aucun mecanisme de rotation/revocation de JWT d acces n est present. | A traiter avec un cycle refresh-token si la duree de session augmente. |

## Verifications realisees

- Les fichiers .env, les credentials Google et les tokens sont ignores par Git ; aucun secret backend n est expose dans le frontend (seule VITE_API_URL est utilisee).
- Les mots de passe sont haches avec Argon2 via Passlib.
- Les erreurs email inconnu et mot de passe incorrect ont le meme message.
- Les JWT sont signes en HS256 et expirent ; les jetons invalides sont rejetes.
- Une limitation en memoire existe pour la recuperation de mot de passe, mais elle ne protegeait ni inscription ni login.
- L API GitHub indique que Secret Scanning est desactive. Une revue des noms de fichiers de l historique ne revele pas de fichier de secrets suivi, mais elle ne remplace pas un scan de contenu.

## Correctifs appliques separement

La PR de durcissement associee ajoute :

1. un garde-fou qui interdit la cle JWT par defaut ou trop courte en production ;
2. une redirection HTTPS en production ;
3. le retrait de CORS null en production tout en le conservant uniquement pour Electron en developpement ;
4. une limite de cinq tentatives de connexion par couple IP/compte sur quinze minutes ;
5. une limite de cinq inscriptions par IP et par heure.

> La limite actuelle est en memoire et protege un processus unique. Pour un deploiement multi-instance, elle doit etre remplacee par un stockage partage (Redis par exemple).

## Actions de production requises

- Activer GitHub Secret Scanning et lancer un scan d historique (Gitleaks ou equivalent) sans afficher ni recopier de secrets.
- Definir une SECRET_KEY aleatoire d au moins 32 caracteres, ainsi que les secrets OAuth, uniquement dans le gestionnaire de secrets du deploiement.
- Mettre ENVIRONMENT=production et utiliser des URL https pour le frontend et les redirections OAuth.
- Placer l API derriere un proxy TLS de confiance et configurer les en-tetes proxy avant de deployer la redirection HTTPS.
- Choisir Turnstile ou hCaptcha ; la verification doit etre realisee cote backend avant inscription et connexion.