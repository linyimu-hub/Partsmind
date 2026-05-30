@echo off
ruff check . --ignore ANN,B904,N8,N818,S105,E501,UP038 --extend-ignore F401,F841
