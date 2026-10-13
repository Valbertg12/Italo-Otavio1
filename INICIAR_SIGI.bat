@echo off
title SIGI - Gabinete Italo Otavio
cd /d "%~dp0"
echo ========================================================
echo  SIGI - Sistema Inteligente de Geracao de Indicacoes
echo  Gabinete Parlamentar: Italo Otavio
echo  Criador do Programa: Valbert Breno
echo ========================================================
echo.
echo Iniciando o servidor local...
start http://localhost:8501
python -m streamlit run app.py --server.port 8501
pause
