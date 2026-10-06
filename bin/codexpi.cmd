@echo off
if "%~1"=="--all" if "%~2"=="" (
  ssh -t -o ServerAliveInterval=20 -o ServerAliveCountMax=3 raspberry@192.168.2.105 env TERM=xterm-256color /home/raspberry/CodexPi/bin/codexpi --all
  exit /b
)
if not "%~1"=="" (
  echo Use codexpi, then /rename ^<Projektname^>, or codexpi --all.
  exit /b 2
)
ssh -t -o ServerAliveInterval=20 -o ServerAliveCountMax=3 raspberry@192.168.2.105 env TERM=xterm-256color /home/raspberry/CodexPi/bin/codexpi
