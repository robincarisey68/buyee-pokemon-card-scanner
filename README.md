# Scanner Buyee → France (cartes Pokémon japonaises)

Ce robot cherche sur Mercari Japon (le site que Buyee revend) des cartes Pokémon japonaises **revendables avec au moins 35 % de bénéfice net** en France, et t'envoie l'annonce sur Discord avec le lien Buyee pour l'acheter. **Il n'achète jamais rien** : c'est toi qui décides.

## Ce qu'il fait à chaque passage (toutes les 2 heures)

1. **Recherche large** sur Mercari (`ポケカ SAR`, `SR`, `AR`, `UR`, `CHR`...), sur les 3 premières pages des annonces les plus récentes.
2. **Exclusion** des lots, boosters, cartes gradées (PSA, BGS...), versions étrangères, cartes abîmées (`ジャンク`, `傷あり`).
3. **Identification** de chaque carte à partir du titre japonais : nom + numéro (`201/165`) + set (`SV2a`, `ポケモンカード151`), ou nom + rareté + set. En cas de doute, la carte est ignorée plutôt que mal identifiée.
4. **Prix de revente en France** : prix Cardmarket de la **version japonaise** (API gratuite TCGdex, mise à jour chaque jour). Le robot garde le prix le plus prudent entre la tendance, la moyenne 7 jours et la moyenne 30 jours, et exige des ventes récentes.
5. **Comparaison** : pour chaque carte prometteuse, il lit jusqu'à **10 pages** d'annonces de cette carte précise, garde seulement le **bon état** (neuf, quasi neuf, sans rayures visibles), écarte les descriptions qui signalent un défaut (`白欠け`, `折れ`...) et prend la **moins chère**.
6. **Calcul du bénéfice net**, tous frais compris : prix, frais Buyee, port au Japon, port international, taxe UE de 3 €, TVA 20 %, commission Cardmarket, envoi à l'acheteur.
7. **Vérification des photos par IA** (Claude Haiku, facultatif) : bonne carte, une seule carte, pas de défaut visible.
8. **Alerte Discord** avec la photo, le lien Buyee, le lien Cardmarket et le détail des frais. Une même annonce n'est jamais envoyée deux fois.

## Mise en route (10 minutes)

### 1. Créer le webhook Discord
Dans ton serveur Discord : **Paramètres du salon → Intégrations → Webhooks → Nouveau webhook → Copier l'URL du webhook**.

### 2. Donner l'URL au robot
Sur GitHub, dans ce dépôt : **Settings → Secrets and variables → Actions → New repository secret**
- Nom : `DISCORD_WEBHOOK_URL`
- Valeur : l'URL copiée

### 3. (Facultatif) Vérification des photos par IA
Crée une clé sur [console.anthropic.com](https://console.anthropic.com), puis ajoute un second secret :
- Nom : `ANTHROPIC_API_KEY`
- Valeur : ta clé

Sans cette clé, le robot fonctionne quand même, mais sans regarder les photos. Avec la clé, chaque photo coûte environ un demi-centime, et seules les annonces déjà rentables sont vérifiées (10 au maximum par passage).

### 4. Lancer un premier essai
Onglet **Actions → Scan Buyee → Run workflow**. Coche « Mode test » pour voir le résultat dans les journaux sans rien recevoir sur Discord.

Ensuite, le robot tourne seul toutes les 2 heures.

## Régler le robot

Tout se règle dans [`config.yaml`](config.yaml), sans toucher au code :

| Réglage | Valeur actuelle | Rôle |
|---|---|---|
| `min_margin` | `0.35` | Marge nette minimale (35 %) |
| `min_resale_eur` | `25` | Ignore les cartes qui valent moins de 25 € en France |
| `search_queries` | SAR, SR, AR, UR, CHR | Recherches larges sur Mercari |
| `pages_per_card` | `10` | Pages comparées pour une carte précise |
| `accepted_conditions` | `[1, 2, 3]` | États Mercari acceptés |
| `costs` | voir le fichier | Frais Buyee, port, taxes : **ajuste-les avec tes vraies factures** |

## Limites à connaître

- **Prix de revente** : c'est le prix Cardmarket de la carte japonaise, pas une garantie de vente. Il faut toujours vérifier la page Cardmarket avant d'acheter.
- **Frais Buyee et port** : ce sont des estimations par défaut. Après ta première commande, mets tes vrais chiffres dans `config.yaml`.
- **Mercari seulement** pour l'instant. Yahoo Enchères pourra être ajouté ensuite.
- **Cartes gradées (PSA...)** exclues, car le prix Cardmarket correspond à une carte non gradée.
- **Source des annonces** : Buyee bloque les robots, donc le scanner lit Mercari directement grâce à la bibliothèque libre `mercapi` (la même que ton robot `buyee-robot-annonce`). Ce n'est pas une API officielle : elle peut casser si Mercari change son site. Chaque annonce Mercari a exactement la même référence sur Buyee, le lien envoyé est donc le bon.
- **Taux de change** : taux du jour de la BCE, plus 3 % de marge de change (réglable avec `fx_markup`).
- **Fréquence** : toutes les 2 heures, pour rester dans les 2 000 minutes gratuites par mois de GitHub (dépôt privé).

## Pour les développeurs

```bash
pip install -r requirements.txt
python -m pytest -q                 # tests
python -m scanner --dry-run         # scan complet sans envoi Discord
python -m scanner --quick --dry-run # essai rapide (1 recherche)
python -m scanner --test-discord    # envoie un message de test sur Discord
```
