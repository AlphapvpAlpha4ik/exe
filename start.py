import subprocess
import sys
import os
import platform
import tempfile
import shutil

def resource_path(relative_path):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), relative_path)

py_path = resource_path("py.py")

banner = """
=============================================
  CIS AI Chat Server
  Перейдите на: http://127.0.0.1:8080
  Не закрывайте это окно!
=============================================
"""

if platform.system() == "Windows":
    bat_content = f'@echo off\ntitle CIS AI Chat Server\necho.\necho {banner.strip()}\necho.\n"{sys.executable}" "{py_path}"\npause'
    bat_path = os.path.join(tempfile.gettempdir(), "_cis_run.bat")
    with open(bat_path, "w", encoding="utf-8") as f:
        f.write(bat_content)
    os.system(f'start "CIS AI Chat Server" cmd /k "{bat_path}"')
else:
    sh_content = f'''#!/bin/bash
echo ""
echo "============================================="
echo "  CIS AI Chat Server"
echo "  Перейдите на: http://127.0.0.1:8080"
echo "  Не закрывайте это окно!"
echo "============================================="
echo ""
"{sys.executable}" "{py_path}"
exec bash'''
    sh_path = os.path.join(tempfile.gettempdir(), "_cis_run.sh")
    with open(sh_path, "w", encoding="utf-8") as f:
        f.write(sh_content)
    os.chmod(sh_path, 0o755)

    terminals = [
        ["gnome-terminal", "--", "bash", "-c"],
        ["konsole", "-e", "bash", "-c"],
        ["xfce4-terminal", "-e", "bash", "-c"],
        ["mate-terminal", "-e", "bash", "-c"],
        ["lxterminal", "-e", "bash", "-c"],
        ["xterm", "-e", "bash", "-c"]
    ]
    launched = False
    for term in terminals:
        try:
            subprocess.Popen(term + [f'{sh_path}; exec bash'])
            launched = True
            break
        except FileNotFoundError:
            continue
    if not launched:
        print("Не найден поддерживаемый терминал.")
        print(banner)
        print("Запустите вручную: python py.py")