@echo off
if not "%~1"=="" (
  echo Use codexpi without arguments, then /rename ^<Projektname^>.
  exit /b 2
)
ssh -t -o ServerAliveInterval=20 -o ServerAliveCountMax=3 raspberry@192.168.2.105 /home/raspberry/CodexPi/bin/codexpi
