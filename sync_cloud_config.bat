@echo off
echo JARVIS // Syncing config.json to GitHub...
git add config.json
git commit -m "Update report configuration"
git push
echo.
echo JARVIS // Cloud configuration sync complete.
pause
