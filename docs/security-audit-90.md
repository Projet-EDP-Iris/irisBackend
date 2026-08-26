# Audit de sécurité — issue #90

Date : 23 août 2026. Périmètre : irisBackend et irisFrontendApp.

## Synthèse

| Sévérité | Constat | Statut |
| --- | --- | --- |
| Critique | Une clé JWT de test peut démarrer le service en production. | Corrigé dans la PR de durcissement associée (#111). |
| Elevee | La connexion et l’inscription ne sont pas limitées ; seul le reset de mot de passe l’était. | Corrige dans la PR de durcissement associee. |
| Elevee | L’origine CORS null est acceptée y compris en production. | Corrige dans la PR de durcissement associee. |
| Moyenne | HTTPS n’est pas redirigé explicitement par l’application en production. | Corrige dans la PR de durcissement associee. |
| Critique | Un fichier .env apparaît dans l’historique Git et GitHub Secret Scanning est désactivé. | Assainissement et rotation des secrets requis. |
| Moyenne | Aucun CAPTCHA n’est en place pour l’inscription/la connexion. | À planifier après choix de Turnstile ou hCaptcha. |
| Faible | Aucun mécanisme de rotation/révocation de JWT d’accès n’est présent. | À traiter avec un cycle refresh-token si la durée de session augmente. |

## Verifications realisees

- Les fichiers .env, les credentials Google et les tokens sont ignores par Git ; aucun secret backend n est expose dans le frontend (seule VITE_API_URL est utilisee).
- Les mots de passe sont haches avec Argon2 via Passlib.
- Les erreurs email inconnu et mot de passe incorrect ont le meme message.
- Les JWT sont signes en HS256 et expirent ; les jetons invalides sont rejetes.
- Une limitation en memoire existe pour la recuperation de mot de passe, mais elle ne protegeait ni inscription ni login.
- L’API GitHub indique que Secret Scanning est désactivé. La revue des noms de fichiers de l’historique révèle un fichier .env ; son contenu n’a pas été affiché. Il doit être considéré comme potentiellement exposé jusqu’à la rotation de tous les secrets.

## Correctifs appliques separement

La PR de durcissement associée (#111) ajoute :

1. un garde-fou qui interdit la cle JWT par defaut ou trop courte en production ;
2. une redirection HTTPS en production ;
3. le retrait de CORS null en production tout en le conservant uniquement pour Electron en developpement ;
4. une limite de cinq tentatives de connexion par couple IP/compte sur quinze minutes ;
5. une limite de cinq inscriptions par IP et par heure.

> La limite actuelle est en memoire et protege un processus unique. Pour un deploiement multi-instance, elle doit etre remplacee par un stockage partage (Redis par exemple).

## Actions de production requises

- Révoquer et remplacer immédiatement chaque secret qui a pu figurer dans le .env historique, puis purger l’historique avec git-filter-repo et coordonner le force-push. Activer ensuite GitHub Secret Scanning et lancer Gitleaks sans afficher ni recopier de secrets.
- Définir une SECRET_KEY aleatoire d’au moins 32 caractères, ainsi que les secrets OAuth, uniquement dans le gestionnaire de secrets du deploiement.
- Mettre ENVIRONMENT=production et utiliser des URL HTTPS pour le frontend et les redirections OAuth.
- Placer l API derrière un proxy TLS de confiance et configurer les en-tetes proxy avant de deployer la redirection HTTPS.
- Choisir Turnstile ou hCaptcha ; la vérification doit être réalisée côté backend avant inscription et connexion.