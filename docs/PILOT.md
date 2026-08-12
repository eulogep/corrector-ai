# Protocole de pilote préproduction

Ce protocole transforme Corrector AI en assistant de correction **supervisé**. Il ne doit pas être utilisé pour communiquer automatiquement une note à un élève. La décision finale appartient toujours à l’enseignant.

## Objectif du premier pilote

Le pilote doit répondre à trois questions concrètes : le système lit-il suffisamment bien les copies du contexte choisi, ses propositions réduisent-elles le temps de correction, et l’enseignant conserve-t-il une compréhension et une maîtrise complètes de la note finale ?

Commencez avec une seule matière, un seul niveau et un type d’évaluation homogène. Ne mélangez pas, par exemple, dissertation de français, exercices de calcul et questions à choix court dans la même première mesure.

| Phase | Corpus | Décision autorisée | Sortie attendue |
|---|---:|---|---|
| Vérification technique | 3 à 5 copies fictives ou très anonymisées | Aucune communication de note | OCR, barème, revue, PDF et alertes fonctionnent |
| Calibration | 30 à 50 copies historiques déjà corrigées | Note finale humaine uniquement | MAE, biais, taux à ±1 / ±2 points et taux de reprises |
| Pilote fermé | 1 à 2 correcteurs, 10 à 20 copies chacun | Validation humaine de 100 % des copies | Gain de temps et retours utilisateurs documentés |
| Extension | Une nouvelle matière ou un nouveau niveau à la fois | Selon la politique de l’établissement | Décision fondée sur les métriques du pilote précédent |

## 1. Préparer la préproduction

Déployez une instance distincte de la production, avec une base, un volume et des clés IA dédiés. Utilisez la configuration Docker du projet et activez Prometheus, Grafana, Redis et Alertmanager comme décrit dans [DEPLOYMENT.md](DEPLOYMENT.md).

Avant de charger des données, vérifiez la santé et protégez les accès :

```bash
curl -fsS http://127.0.0.1:8000/healthz
python -m pytest backend/tests/ -q
```

N’utilisez au début que des copies fictives, anonymisées ou des copies pour lesquelles le traitement est explicitement autorisé. Ne placez ni nom d’élève, ni contenu de copie, ni clé API dans un ticket, un journal ou une capture d’écran de support.

## 2. Parcours correcteur

Le parcours d’interface prévu pour chaque copie est le suivant :

1. Importer le sujet et **corriger puis valider** le barème proposé.
2. Créer ou sélectionner l’élève, importer la copie et contrôler le texte OCR.
3. Lancer la correction ; la copie apparaît avec le statut **À relire par l’enseignant**.
4. Vérifier les exercices, modifier la note et l’appréciation si nécessaire, puis choisir **Valider comme note finale** ou **À corriger / revoir**.
5. N’envoyer le rapport par email qu’après le statut **Validée par l’enseignant**.
6. Enregistrer une référence humaine indépendante dans **Pilote & revue** pour les copies de calibration.

La validation est enregistrée avec la date, la décision, le commentaire, la note avant et la note après. La proposition IA initiale est conservée séparément afin que les indicateurs de qualité restent interprétables après une correction manuelle.

## 3. API de pilote

| Endpoint | Usage |
|---|---|
| `GET /api/grading/reviews/queue` | File de copies `pending_review`, `needs_revision` ou `approved` |
| `POST /api/grading/exams/{id}/review` | Décision finale, commentaire, note et appréciation corrigées |
| `POST /api/grading/reviews/bulk` | Approbation ou demande de relecture de 1 à 100 copies possédées par le professeur |
| `GET /api/grading/exams/{id}/review-history` | Historique d’audit de la copie |
| `POST /api/grading/pilot/calibration` | Référence humaine sur une copie déjà corrigée indépendamment |
| `GET /api/grading/pilot/metrics` | Indicateurs de revue et de calibration du professeur connecté |

Exemple de validation avec note ajustée :

```json
POST /api/grading/exams/42/review
{
  "status": "approved",
  "comment": "Exercice 2 revalorisé après relecture.",
  "final_note": 15.5,
  "final_appreciation": "Bon raisonnement ; rédaction à préciser."
}
```

## 4. Lire les métriques de calibration

Les métriques API du pilote normalisent les notes sur 20, y compris lorsqu’une évaluation utilise un autre barème. Elles ne disent pas si le système est « bon » dans l’absolu : elles décrivent l’écart observé sur votre corpus et doivent être lues par matière, niveau et type de copie.

| Indicateur | Définition | Signal utile |
|---|---|---|
| `mae_sur_20` | Écart absolu moyen entre proposition IA initiale et référence humaine | Diminue à mesure que le barème, les prompts et le contexte se stabilisent |
| `biais_moyen_sur_20` | Tendance moyenne à sur- ou sous-noter | Un biais durable appelle une correction de barème ou de prompt |
| `within_one_point` | Part des copies à ±1 point de la référence | Indicateur d’utilité pour une première revue rapide |
| `within_two_points` | Part des copies à ±2 points de la référence | Détecte les écarts importants restant fréquents |
| `manual_note_change_rate` | Part des copies validées dont la note a été modifiée | Mesure le niveau réel de contrôle humain nécessaire |

Évitez de définir un seuil institutionnel avant d’avoir un corpus suffisamment large et comparé à au moins deux corrections humaines lorsque c’est possible. Documentez également les cas difficiles : écriture peu lisible, question ambiguë, réponse hors sujet, calcul partiellement juste ou mauvaise segmentation OCR.

## 5. Critères d’arrêt et de progression

Arrêtez temporairement le pilote si le système renvoie une note sans statut de revue, si un rapport non validé peut être envoyé, si les données sont exposées dans les logs, ou si la qualité se dégrade fortement sur un sous-groupe de copies. Corrigez la cause, rejouez des cas contrôlés, puis reprenez avec une nouvelle fenêtre de mesure.

Passez de la calibration au pilote fermé lorsque le parcours est compris par les correcteurs, que tous les résultats sont validés manuellement et que les métriques ne révèlent pas de dérive majeure inexpliquée. Une extension ne doit pas être une simple augmentation de volume : elle doit rester limitée à un contexte pédagogique que vous pouvez analyser.

## 6. Ce que cette version ne fait pas encore

La version pilote ne traite pas encore l’import et la correction asynchrones de lots de fichiers, la distribution de copies entre plusieurs correcteurs, les rôles administrateur d’établissement, l’authentification institutionnelle, le second fournisseur OCR ni une validation statistique sur corpus représentatif. Les opérations groupées livrées concernent la **décision de revue**, pas l’exécution massive d’OCR/LLM.

Ces limites sont intentionnelles pour le premier pilote : elles évitent de transformer une expérience non calibrée en processus de notation à grande échelle.
