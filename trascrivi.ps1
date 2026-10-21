# Uso: .\trascrivi.ps1 "C:\percorso\riunione.mp4" [altri file] [--model large-v3-turbo] [--redo names] ...
$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
$env:PYTHONPATH = $PSScriptRoot
& $python -m meeting_transcriber @args
