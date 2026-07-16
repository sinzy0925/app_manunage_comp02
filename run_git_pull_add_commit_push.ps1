echo "`n---------------"
echo "git pull`n"
git pull
echo "`n---------------"
echo "git add commit push`n"
git add .
git commit -m "git pull add commit push $(Get-Date -Format 'yyyyMMdd HH:mm')"
git push -u origin main


