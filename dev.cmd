@echo off
cd /d "%~dp0"
npm --workspace apps/desktop run dev:cuda
