#!/bin/bash
# Script de configuração do ambiente local (sem Docker)

echo "Criando ambiente virtual..."
python3 -m venv venv

echo "Ativando ambiente virtual..."
source venv/Scripts/activate 2>/dev/null || source venv/bin/activate

echo "Atualizando pip..."
pip install --upgrade pip

echo "Instalando dependências..."
pip install -r requirements.txt

echo "Configuração completa!"
echo "Para ativar o ambiente: source venv/Scripts/activate (Windows) ou source venv/bin/activate (Linux/Mac)"