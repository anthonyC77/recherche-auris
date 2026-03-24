@echo off
:: ============================================================
::  Lance la recherche voitures DIRECTEMENT depuis ce PC
::  Branche : lancementLocal — pas de GitHub Actions
::
::  Fonctionnement :
::    1. Attendre 60 s (réseau disponible au démarrage)
::    2. git pull  (pour récupérer les éventuels changements)
::    3. Lancer recherche_auris.py et ATTENDRE la fin
::    4. git commit + git push  (sauvegarder CSV et logs)
::
::  Pour démarrage automatique : créer une tâche dans le
::  Planificateur de tâches Windows pointant sur ce fichier,
::  déclencheur = "Ouverture de session" ou "Au démarrage".
:: ============================================================

chcp 65001 > nul

:: ── 1. Pause réseau ───────────────────────────────────────
timeout /t 60 /nobreak > nul

:: ── 2. Se placer dans le dossier du projet ────────────────
set DOSSIER=C:\Users\antho\RechercheVoiture
cd /d "%DOSSIER%"

echo [%date% %time%] Demarrage lancement local >> "%DOSSIER%\toyota_auris_log.txt"

:: ── 3. Récupérer les mises à jour distantes ───────────────
git pull --rebase origin lancementLocal >> "%DOSSIER%\toyota_auris_log.txt" 2>&1

:: ── 4. Lancer la recherche et ATTENDRE la fin ────────────
::    start /wait garantit que cmd attend que pythonw se
::    termine avant de passer aux commandes git ci-dessous.
start /wait "" pythonw "%DOSSIER%\recherche_auris.py"

echo [%date% %time%] Recherche terminee, push en cours... >> "%DOSSIER%\toyota_auris_log.txt"

:: ── 5. Commit et push des résultats ──────────────────────
::    git add -u : ajoute uniquement les fichiers déjà suivis
::    (CSV et logs modifiés), sans risque d'ajouter des fichiers
::    temporaires ou sensibles.
git add -u
git diff --cached --quiet || git commit -m "Mise a jour annonces locale"
git push origin lancementLocal >> "%DOSSIER%\toyota_auris_log.txt" 2>&1

echo [%date% %time%] Push termine. >> "%DOSSIER%\toyota_auris_log.txt"

exit
