# Politique de sécurité

## Versions prises en charge

La branche `main` reçoit les corrections de sécurité. Les déploiements de production doivent utiliser un commit ou un tag validé, et non une branche de travail.

## Signaler une vulnérabilité

Ne publiez pas de vulnérabilité exploitable, de clé API, de jeton JWT, de copie d’élève ou de donnée personnelle dans une issue publique. Utilisez les **GitHub Security Advisories** du dépôt lorsqu’ils sont disponibles. Si ce canal n’est pas accessible, ouvrez une issue publique ne contenant que la mention `security-contact-request` afin qu’un canal privé soit établi.

Indiquez le périmètre concerné, les prérequis, une reproduction minimale sans données réelles, l’impact estimé et, si possible, une proposition de correctif. Les mainteneurs accuseront réception, évalueront le risque, prépareront un correctif et coordonneront la divulgation.

## Mesures attendues en production

Conservez les clés des fournisseurs IA, les secrets JWT, Redis, SMTP, métriques et Alertmanager hors Git. Limitez l’exposition réseau aux services nécessaires, activez HTTPS, sauvegardez les volumes chiffrés et appliquez les mises à jour de dépendances après validation en préproduction.
