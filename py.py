from ddgs import DDGS
import os
import sys
import json
import uuid
import base64
import re
import threading
import webbrowser
import platform
import socket
import ipaddress
from datetime import datetime, timedelta
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse
import requests
import markdown2

DDGS_AVAILABLE = True
try:
    from ddgs import DDGS as _DDGSCheck
except ImportError:
    try:
        from duckduckgo_search import DDGS as _DDGSCheck
    except ImportError:
        DDGS_AVAILABLE = False

try:
    from g4f.client import Client as G4FClient
    G4F_AVAILABLE = True
except ImportError:
    G4F_AVAILABLE = False

SYSTEM = platform.system()
if SYSTEM == "Windows":
    BASE_DIR = r"C:\Omni"
else:
    BASE_DIR = "/home/oem/AppImages/ChatAI"

CHAT_DIR = os.path.join(BASE_DIR, "Message")
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
PORT = 8080
os.makedirs(CHAT_DIR, exist_ok=True)

DEFAULT_CONFIG = {
    "username": "",
    "openrouter_api_key": "",
    "theme": "dark",
    "g4f_warning_dismissed": False,
    "search_warning_dismissed": False,
    "system_prompt": "",
    "ddgs_max_results": 5,
    "ddgs_region": "wt-wt",
    "ddgs_safesearch": "moderate",
    "ddgs_format_context": True,
    "ddgs_parse_sites": False,
    "ddgs_parse_count": 3,
    "welcome_seen": False,
    "last_provider": "openrouter"
}

VPN_RANGES = [
    (ipaddress.IPv4Network('198.18.0.0/15'),),
    (ipaddress.IPv4Network('100.64.0.0/10'),),
    (ipaddress.IPv4Network('169.254.0.0/16'),),
]

def is_real_lan_ip(ip):
    try:
        addr = ipaddress.IPv4Address(ip)
        if addr.is_loopback:
            return False
        for (net,) in VPN_RANGES:
            if addr in net:
                return False
        if not addr.is_private:
            return False
        return True
    except Exception:
        return False

def get_local_ip():
    candidates = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.5)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        if ip and is_real_lan_ip(ip):
            return ip
        if ip and ip != "127.0.0.1":
            candidates.append(ip)
    except Exception:
        pass
    try:
        hostname = socket.gethostname()
        addrs = socket.getaddrinfo(hostname, None, socket.AF_INET)
        seen = set()
        for family, type_, proto, canonname, sockaddr in addrs:
            ip = sockaddr[0]
            if ip in seen:
                continue
            seen.add(ip)
            if is_real_lan_ip(ip):
                return ip
            if ip != "127.0.0.1":
                candidates.append(ip)
    except Exception:
        pass
    for ip in candidates:
        if not ip.startswith("127.") and not ip.startswith("169.254."):
            return ip
    return "127.0.0.1"

LOCAL_IP = get_local_ip()

def load_config():
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            for k, v in DEFAULT_CONFIG.items():
                if k not in cfg:
                    cfg[k] = v
            return cfg
        except Exception:
            pass
    return dict(DEFAULT_CONFIG)

def save_config(cfg):
    try:
        tmp = CONFIG_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        os.replace(tmp, CONFIG_PATH)
    except Exception:
        pass

_chat_locks = {}
_chat_locks_lock = threading.Lock()

def get_chat_lock(chat_id):
    with _chat_locks_lock:
        if chat_id not in _chat_locks:
            _chat_locks[chat_id] = threading.Lock()
        return _chat_locks[chat_id]

MD_EXTRAS = ["fenced-code-blocks", "tables", "code-friendly", "cuddled-lists"]

def render_md(text):
    try:
        html = markdown2.markdown(text, extras=MD_EXTRAS)
        html = re.sub(r'(<table[^>]*>)', r'<div style="overflow-x:auto;margin:10px 0">\n', html)
        html = re.sub(r'(</table>)', r'</div>', html)
        return html
    except Exception:
        return text

HTML_CONTENT = r"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>CIS AI Chat</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');
:root{
--bg:#09090b;--sidebar:#0c0c0e;--surface:#131316;--surface2:#1a1a1e;--input-bg:#141417;
--border:#1e1e22;--border-light:#2a2a2f;--text:#ececf0;--text-secondary:#8b8b95;--text-dim:#55555f;
--accent:#8b7cf7;--accent-hover:#7b6ce7;--accent-glow:rgba(139,124,247,.12);
--user-msg:#1a1830;--ai-msg:#111114;
--code-bg:#0a0a0c;--success:#34d399;--warn:#fbbf24;--danger:#fb7185;
--radius:12px;--radius-sm:8px;--transition:0.3s cubic-bezier(.4,0,.2,1);
--shadow:0 8px 32px rgba(0,0,0,.5);--glow:0 0 16px var(--accent-glow);
}
[data-theme="light"]{
--bg:#fafafa;--sidebar:#fff;--surface:#fff;--surface2:#f5f5f7;--input-bg:#f0f0f2;
--border:#e8e8ec;--border-light:#d4d4d8;--text:#18181b;--text-secondary:#71717a;--text-dim:#a1a1aa;
--user-msg:#ede9fe;--ai-msg:#f8f8fa;
--code-bg:#f4f4f5;--shadow:0 8px 32px rgba(0,0,0,.06);--glow:0 0 16px rgba(139,124,247,.06);
}
*{margin:0;padding:0;box-sizing:border-box;}
body{font-family:'Inter',system-ui,sans-serif;background:var(--bg);color:var(--text);height:100vh;height:100dvh;display:flex;overflow:hidden;transition:background var(--transition),color var(--transition);}
::-webkit-scrollbar{width:4px;}
::-webkit-scrollbar-track{background:transparent;}
::-webkit-scrollbar-thumb{background:var(--border-light);border-radius:4px;}
.welcome-overlay{position:fixed;inset:0;background:var(--bg);z-index:9999;display:flex;align-items:center;justify-content:center;flex-direction:column;transition:opacity .7s ease,visibility .7s ease;}
.welcome-overlay.hidden{opacity:0;visibility:hidden;pointer-events:none;}
.welcome-logo{font-size:48px;font-weight:700;background:linear-gradient(135deg,var(--accent),#c084fc);-webkit-background-clip:text;-webkit-text-fill-color:transparent;margin-bottom:12px;}
.welcome-sub{font-size:15px;color:var(--text-secondary);font-weight:300;letter-spacing:.8px;animation:welcomeFadeIn 1s ease .3s both;}
@keyframes welcomeFadeIn{from{opacity:0;transform:translateY(12px);}to{opacity:1;transform:translateY(0);}}
.sidebar{width:280px;background:var(--sidebar);border-right:1px solid var(--border);display:flex;flex-direction:column;flex-shrink:0;transition:background var(--transition),border-color var(--transition),transform .3s ease;}
.sidebar-section{padding:16px 18px;border-bottom:1px solid var(--border);}
.sidebar-section label{display:block;font-size:10px;text-transform:uppercase;letter-spacing:1.2px;color:var(--text-dim);margin-bottom:7px;font-weight:600;}
.sidebar-section input{width:100%;background:var(--input-bg);border:1px solid var(--border);color:var(--text);padding:9px 12px;border-radius:var(--radius-sm);font-size:13px;outline:none;transition:all .2s ease;font-family:'Inter',sans-serif;}
.sidebar-section input:focus{border-color:var(--accent);box-shadow:var(--glow);}
.chat-list{flex:1;overflow-y:auto;padding:4px 6px;}
.chat-date-group{padding:10px 12px 4px;font-size:10px;text-transform:uppercase;letter-spacing:1.2px;color:var(--text-dim);font-weight:600;}
.chat-item{padding:10px 12px;border-radius:8px;cursor:pointer;margin-bottom:1px;font-size:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;transition:all .15s ease;color:var(--text-secondary);border:1px solid transparent;}
.chat-item:hover{background:var(--surface2);color:var(--text);}
.chat-item.active{background:var(--accent);color:#fff;border-color:var(--accent);}
.new-chat-btn{margin:6px 8px;padding:11px;background:var(--accent);border:none;border-radius:var(--radius);color:#fff;cursor:pointer;font-size:13px;font-weight:600;transition:all .2s ease;}
.new-chat-btn:hover{background:var(--accent-hover);transform:translateY(-1px);}
.settings-btn{margin:4px 8px 8px;padding:10px;background:var(--surface2);border:1px solid var(--border);border-radius:var(--radius);color:var(--text-secondary);cursor:pointer;font-size:13px;font-weight:500;transition:all .2s ease;text-align:center;}
.settings-btn:hover{border-color:var(--accent);color:var(--text);}
.sidebar-footer{padding:12px 18px;border-top:1px solid var(--border);}
.sidebar-footer a{font-size:11px;color:var(--accent);text-decoration:none;transition:color .2s;}
.sidebar-footer a:hover{text-decoration:underline;}
.main{flex:1;display:flex;flex-direction:column;min-width:0;}
.top-bar{padding:10px 20px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:8px;flex-wrap:wrap;}
.mobile-menu-btn{display:none;background:var(--input-bg);border:1px solid var(--border);color:var(--text);width:34px;height:34px;border-radius:var(--radius-sm);cursor:pointer;align-items:center;justify-content:center;font-size:18px;transition:all .2s ease;flex-shrink:0;}
select{background:var(--input-bg);border:1px solid var(--border);color:var(--text);padding:7px 12px;border-radius:var(--radius-sm);font-size:13px;outline:none;cursor:pointer;transition:all .2s ease;font-family:'Inter',sans-serif;}
select:focus{border-color:var(--accent);}
.theme-toggle{margin-left:auto;background:var(--input-bg);border:1px solid var(--border);color:var(--text);width:34px;height:34px;border-radius:var(--radius-sm);cursor:pointer;display:flex;align-items:center;justify-content:center;font-size:14px;transition:all .2s ease;}
.theme-toggle:hover{border-color:var(--accent);color:var(--accent);}
.messages{flex:1;overflow-y:auto;padding:24px;display:flex;flex-direction:column;gap:14px;}
.msg{max-width:78%;padding:14px 18px;border-radius:var(--radius);font-size:14px;line-height:1.7;word-wrap:break-word;overflow-wrap:break-word;position:relative;animation:msgIn .35s cubic-bezier(.4,0,.2,1);}
@keyframes msgIn{from{opacity:0;transform:translateY(10px);}to{opacity:1;transform:translateY(0);}}
.msg.user{align-self:flex-end;background:var(--user-msg);border-bottom-right-radius:3px;border:1px solid var(--border);white-space:pre-wrap;}
.msg.ai{align-self:flex-start;background:var(--ai-msg);border-bottom-left-radius:3px;border:1px solid var(--border);}
.msg img{max-width:100%;max-height:60vh;border-radius:8px;margin-top:8px;border:1px solid var(--border);}
.msg table{border-collapse:collapse;width:100%;margin:10px 0;font-size:13px;}
.msg th,.msg td{border:1px solid var(--border);padding:8px 12px;text-align:left;}
.msg th{background:var(--surface2);font-weight:600;}
.msg tr:nth-child(even){background:var(--surface);}
.msg pre{background:var(--code-bg);padding:14px;border-radius:8px;overflow-x:auto;margin:10px 0;font-size:13px;position:relative;border:1px solid var(--border);}
.msg code{font-family:'JetBrains Mono',monospace;font-size:13px;}
.msg p{margin-bottom:8px;}
.msg>:last-child:not(.msg-footer){margin-bottom:0!important;}
.msg ul,.msg ol{margin:6px 0 6px 18px;}
.msg li{margin-bottom:3px;}
.msg blockquote{border-left:3px solid var(--accent);padding-left:12px;margin:8px 0;color:var(--text-secondary);font-style:italic;}
.msg h1,.msg h2,.msg h3{margin:12px 0 6px;font-weight:600;}
.msg hr{border:none;border-top:1px solid var(--border);margin:12px 0;}
.msg-content>*:first-child{margin-top:0;}
.copy-code-btn{position:absolute;top:6px;right:6px;background:var(--surface2);border:1px solid var(--border);color:var(--text-secondary);padding:4px 10px;border-radius:5px;font-size:10px;cursor:pointer;opacity:0;transition:all .15s ease;font-family:'Inter',sans-serif;font-weight:500;}
.msg pre:hover .copy-code-btn{opacity:1;}
.copy-code-btn:hover{color:var(--text);border-color:var(--accent);}
.msg-footer{display:flex;justify-content:flex-end;margin-top:10px;padding-top:8px;border-top:1px solid var(--border);}
.msg-copy-all{background:var(--surface2);border:1px solid var(--border);color:var(--text-secondary);padding:5px 14px;border-radius:6px;font-size:11px;cursor:pointer;transition:all .15s ease;font-family:'Inter',sans-serif;font-weight:500;}
.msg-copy-all:hover{color:var(--text);border-color:var(--accent);}
.search-indicator{align-self:flex-start;max-width:78%;padding:12px 16px;border-radius:var(--radius);border:1px solid var(--border);background:var(--surface);display:flex;flex-direction:column;gap:8px;font-size:13px;color:var(--text-secondary);}
.search-indicator.search-done{border-color:var(--success);}
.search-row{display:flex;align-items:center;gap:10px;}
.search-spinner{width:16px;height:16px;border:2px solid var(--border-light);border-top-color:var(--accent);border-radius:50%;animation:spin .7s linear infinite;flex-shrink:0;}
@keyframes spin{to{transform:rotate(360deg);}}
.search-results-preview{padding:8px 12px;background:var(--surface2);border-radius:var(--radius-sm);font-size:11px;line-height:1.5;color:var(--text-dim);max-height:150px;overflow-y:auto;border:1px solid var(--border);}
.sr-item{margin-bottom:5px;padding-bottom:5px;border-bottom:1px solid var(--border);}
.sr-item:last-child{margin-bottom:0;padding-bottom:0;border-bottom:none;}
.sr-title{color:var(--accent);font-weight:500;margin-bottom:1px;font-size:11px;}
.sr-highlight{color:var(--accent);font-weight:600;}
.input-area{padding:14px 20px 18px;border-top:1px solid var(--border);display:flex;gap:8px;align-items:flex-end;}
.input-wrapper{flex:1;display:flex;flex-direction:column;gap:6px;}
.attachments{display:flex;flex-wrap:wrap;gap:5px;padding:0 2px;}
.attachment-chip{display:flex;align-items:center;gap:5px;background:var(--surface2);border:1px solid var(--border);padding:4px 10px;border-radius:16px;font-size:11px;color:var(--text-secondary);animation:chipIn .25s ease;}
@keyframes chipIn{from{opacity:0;transform:scale(.9);}to{opacity:1;transform:scale(1);}}
.attachment-chip button{background:none;border:none;color:var(--text-dim);cursor:pointer;font-size:13px;line-height:1;padding:2px 0 2px 6px;transition:color .15s;min-width:20px;min-height:20px;display:flex;align-items:center;justify-content:center;}
.attachment-chip button:hover{color:var(--danger);}
.input-row{display:flex;gap:8px;align-items:flex-end;}
.plus-btn{background:var(--input-bg);border:1px solid var(--border);color:var(--text-secondary);width:46px;height:46px;border-radius:var(--radius);cursor:pointer;display:flex;align-items:center;justify-content:center;font-size:20px;transition:all .2s ease;flex-shrink:0;position:relative;}
.plus-btn:hover,.plus-btn.menu-open{border-color:var(--accent);color:var(--accent);}
.plus-menu{position:absolute;bottom:52px;left:0;background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:4px;min-width:190px;box-shadow:var(--shadow);display:none;z-index:100;animation:menuIn .15s ease;}
.plus-menu.open{display:block;}
@keyframes menuIn{from{opacity:0;transform:translateY(6px);}to{opacity:1;transform:translateY(0);}}
.plus-menu-item{display:flex;align-items:center;gap:8px;padding:9px 12px;border-radius:6px;cursor:pointer;font-size:13px;color:var(--text-secondary);transition:all .15s ease;border:none;background:none;width:100%;text-align:left;font-family:'Inter',sans-serif;}
.plus-menu-item:hover{background:var(--surface2);color:var(--text);}
.plus-menu-item.active{color:var(--accent);background:var(--accent-glow);}
.plus-menu-item svg{width:15px;height:15px;fill:currentColor;}
textarea.chat-input{flex:1;background:var(--input-bg);border:1px solid var(--border);color:var(--text);padding:12px 16px;border-radius:var(--radius);resize:none;font-size:14px;font-family:'Inter',sans-serif;outline:none;min-height:46px;max-height:160px;line-height:1.5;transition:all .2s ease;}
textarea.chat-input:focus{border-color:var(--accent);box-shadow:var(--glow);}
.send-btn{background:var(--accent);border:none;border-radius:var(--radius);width:46px;height:46px;cursor:pointer;display:flex;align-items:center;justify-content:center;transition:all .2s ease;flex-shrink:0;}
.send-btn:hover{background:var(--accent-hover);transform:translateY(-1px);}
.send-btn:active{transform:translateY(0);}
.send-btn svg{fill:#fff;width:18px;height:18px;}
.stop-btn{background:var(--danger);display:none;}
.toast-container{position:fixed;top:16px;right:16px;z-index:10001;display:flex;flex-direction:column;gap:6px;}
.toast{background:var(--surface);border:1px solid var(--border);color:var(--text);padding:12px 18px;border-radius:var(--radius);font-size:13px;box-shadow:var(--shadow);animation:toastIn .3s ease;max-width:340px;}
@keyframes toastIn{from{opacity:0;transform:translateX(30px);}to{opacity:1;transform:translateX(0);}}
.toast.out{animation:toastOut .25s ease forwards;}
@keyframes toastOut{to{opacity:0;transform:translateX(30px);}}
.toast-dismiss{display:flex;align-items:center;gap:6px;margin-top:8px;font-size:11px;color:var(--text-dim);}
.toast-dismiss input{accent-color:var(--accent);}
.cursor-blink::after{content:'|';animation:blink .7s step-end infinite;color:var(--accent);margin-left:1px;}
@keyframes blink{50%{opacity:0;}}
.file-input{display:none;}
.modal-overlay{position:fixed;inset:0;background:rgba(0,0,0,.5);z-index:5000;display:none;align-items:center;justify-content:center;backdrop-filter:blur(3px);}
.modal-overlay.open{display:flex;}
.modal{background:var(--surface);border:1px solid var(--border);border-radius:14px;width:500px;max-width:90vw;max-height:85vh;overflow-y:auto;box-shadow:var(--shadow);animation:modalIn .25s ease;}
@keyframes modalIn{from{opacity:0;transform:scale(.96) translateY(8px);}to{opacity:1;transform:scale(1) translateY(0);}}
.modal-header{padding:18px 22px;border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between;}
.modal-header h2{font-size:16px;font-weight:600;}
.modal-close{background:none;border:none;color:var(--text-secondary);font-size:20px;cursor:pointer;padding:4px 8px;border-radius:5px;transition:all .15s;min-width:32px;min-height:32px;display:flex;align-items:center;justify-content:center;}
.modal-close:hover,.modal-close:active{background:var(--surface2);color:var(--text);}
.modal-body{padding:22px;}
.setting-group{margin-bottom:18px;}
.setting-group label{display:block;font-size:10px;text-transform:uppercase;letter-spacing:1px;color:var(--text-dim);margin-bottom:6px;font-weight:600;}
.setting-group input,.setting-group textarea,.setting-group select{width:100%;background:var(--input-bg);border:1px solid var(--border);color:var(--text);padding:9px 12px;border-radius:var(--radius-sm);font-size:13px;outline:none;transition:all .2s ease;font-family:'Inter',sans-serif;}
.setting-group textarea{resize:vertical;min-height:70px;line-height:1.5;}
.setting-group input:focus,.setting-group textarea:focus,.setting-group select:focus{border-color:var(--accent);box-shadow:var(--glow);}
.setting-row{display:flex;gap:10px;}
.setting-row .setting-group{flex:1;}
.modal-footer{padding:14px 22px;border-top:1px solid var(--border);display:flex;gap:8px;justify-content:flex-end;}
.btn{padding:9px 18px;border-radius:var(--radius-sm);font-size:13px;font-weight:500;cursor:pointer;transition:all .2s ease;border:1px solid var(--border);font-family:'Inter',sans-serif;}
.btn-primary{background:var(--accent);border-color:var(--accent);color:#fff;}
.btn-primary:hover{background:var(--accent-hover);}
.btn-danger{background:transparent;border-color:var(--danger);color:var(--danger);}
.btn-danger:hover{background:var(--danger);color:#fff;}
.btn-secondary{background:var(--surface2);color:var(--text-secondary);}
.btn-secondary:hover{color:var(--text);border-color:var(--text-dim);}
.ddgs-status{font-size:11px;padding:5px 10px;border-radius:5px;margin-top:4px;display:inline-block;}
.ddgs-ok{background:rgba(52,211,153,.12);color:var(--success);}
.ddgs-fail{background:rgba(251,113,133,.12);color:var(--danger);}
@media(max-width:768px){
.sidebar{position:fixed;left:0;top:0;bottom:0;z-index:200;transform:translateX(-100%);}
.sidebar.open{transform:translateX(0);}
.mobile-menu-btn{display:flex;}
.sidebar-overlay{position:fixed;inset:0;background:rgba(0,0,0,.4);z-index:199;display:none;}
.sidebar-overlay.open{display:block;}
.msg{max-width:90%;}
.input-area{padding:10px 12px 14px;}
.messages{padding:16px;}
.top-bar{padding:8px 12px;}
}
</style>
</head>
<body data-theme="dark">
<div class="welcome-overlay hidden" id="welcomeOverlay">
<div class="welcome-logo">CIS</div>
<div class="welcome-sub">Добро пожаловать в проект CIS</div>
</div>
<div class="toast-container" id="toastContainer"></div>
<div class="sidebar-overlay" id="sidebarOverlay" onclick="toggleSidebar()"></div>
<div class="modal-overlay" id="settingsModal">
<div class="modal">
<div class="modal-header">
<h2>Настройки</h2>
<button class="modal-close" onclick="closeSettings()">x</button>
</div>
<div class="modal-body">
<div class="setting-group">
<label>Системный промпт</label>
<textarea id="settSystemPrompt" placeholder="Введите системный промпт..."></textarea>
</div>
<div class="setting-group">
<label>OpenRouter API Key</label>
<input type="password" id="settApiKey" placeholder="sk-or-v1-...">
</div>
<div class="setting-group">
<label>DuckDuckGo</label>
<div id="ddgsStatus"></div>
</div>
<div class="setting-row">
<div class="setting-group">
<label>Макс. результатов</label>
<input type="number" id="settDdgsMax" min="1" max="20" value="5">
</div>
<div class="setting-group">
<label>Регион</label>
<select id="settDdgsRegion">
<option value="wt-wt">Любой</option>
<option value="ru-ru">Россия</option>
<option value="us-en">США</option>
<option value="de-de">Германия</option>
<option value="fr-fr">Франция</option>
<option value="ua-uk">Украина</option>
<option value="kz-kz">Казахстан</option>
<option value="by-be">Беларусь</option>
</select>
</div>
</div>
<div class="setting-group">
<label>SafeSearch</label>
<select id="settDdgsSafe">
<option value="off">Выключен</option>
<option value="moderate">Умеренный</option>
<option value="strict">Строгий</option>
</select>
</div>
<div class="setting-group">
<label style="display:flex;align-items:center;gap:8px;cursor:pointer;">
<input type="checkbox" id="settDdgsFormat" style="width:auto;">
Форматировать контекст поиска
</label>
</div>
<div class="setting-group">
<label style="display:flex;align-items:center;gap:8px;cursor:pointer;">
<input type="checkbox" id="settDdgsParse" style="width:auto;">
Парсить содержимое сайтов
</label>
</div>
<div class="setting-group">
<label>Кол-во сайтов для парсинга</label>
<input type="number" id="settDdgsParseCount" min="1" max="10" value="3">
</div>
</div>
<div class="modal-footer">
<button class="btn btn-danger" onclick="resetConfig()">Сброс</button>
<button class="btn btn-secondary" onclick="closeSettings()">Отмена</button>
<button class="btn btn-primary" onclick="saveSettings()">Сохранить</button>
</div>
</div>
</div>
<div class="sidebar" id="sidebar">
<div class="sidebar-section">
<label>Имя пользователя</label>
<input type="text" id="usernameInput" placeholder="Введите имя..." oninput="saveConfigField('username',this.value)">
</div>
<div class="chat-list" id="chatList"></div>
<button class="new-chat-btn" onclick="newChat()">+ Новый чат</button>
<button class="settings-btn" onclick="openSettings()">Настройки</button>
<div class="sidebar-footer">
<a href="https://openrouter.ai/" target="_blank">Получить ключ на openrouter.ai</a>
</div>
</div>
<div class="main">
<div class="top-bar">
<button class="mobile-menu-btn" onclick="toggleSidebar()">&#9776;</button>
<select id="providerSelect" onchange="onProviderChange()">
<option value="openrouter">OpenRouter</option>
<option value="g4f">G4F</option>
<option value="flux">Flux (Image)</option>
</select>
<select id="modelSelect"></select>
<button class="theme-toggle" onclick="toggleTheme()" title="Сменить тему">&#9681;</button>
</div>
<div class="messages" id="messages"></div>
<div class="input-area">
<div class="input-wrapper">
<div class="attachments" id="attachments"></div>
<div class="input-row">
<div class="plus-btn" id="plusBtn" onclick="togglePlusMenu(event)">
+
<div class="plus-menu" id="plusMenu">
<button class="plus-menu-item" id="searchItem" onclick="toggleSearch(event)">
<svg viewBox="0 0 24 24"><path d="M15.5 14h-.79l-.28-.27A6.47 6.47 0 0016 9.5 6.5 6.5 0 109.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z"/></svg>
<span>DuckDuckGo Search</span>
</button>
<button class="plus-menu-item" onclick="triggerFileUpload(event)">
<svg viewBox="0 0 24 24"><path d="M16.5 6v11.5c0 2.21-1.79 4-4 4s-4-1.79-4-4V5a2.5 2.5 0 015 0v10.5c0 .83-.67 1.5-1.5 1.5s-1.5-.67-1.5-1.5V6H9v9.5a3 3 0 006 0V5c0-2.21-1.79-4-4-4S7 2.79 7 5v12.5c0 3.04 2.46 5.5 5.5 5.5s5.5-2.46 5.5-5.5V6h-1.5z"/></svg>
<span>Добавить файлы</span>
</button>
</div>
</div>
<textarea class="chat-input" id="input" placeholder="Напишите сообщение..." onkeydown="handleInputKey(event)" oninput="autoResize(this)"></textarea>
<button class="send-btn" id="sendBtn" onclick="send()"><svg viewBox="0 0 24 24"><path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/></svg></button>
<button class="send-btn stop-btn" id="stopBtn" onclick="stopGeneration()">&#9632;</button>
</div>
</div>
</div>
</div>
<input type="file" class="file-input" id="fileInput" multiple accept=".txt,.py,.java,.kt,.js,.ts,.cpp,.c,.h,.cs,.go,.rs,.rb,.php,.swift,.scala,.sh,.bash,.json,.xml,.yaml,.yml,.md,.html,.css,.sql,.r,.lua,.pl,.ex,.erl,.hs,.ml,.toml,.ini,.cfg,.conf,.log,.csv">
<script>
const MODELS={
openrouter:[
{id:"poolside/laguna-xs-2.1:free",name:"Laguna XS 2.1"},
{id:"google/gemma-4-31b-it:free",name:"Gemma 4 31B"},
{id:"openai/gpt-oss-20b:free",name:"GPT-OSS 20B"}
],
g4f:[
{id:"gpt-4o-mini",name:"GPT-4o Mini"},
{id:"srv_mp1v9cyha31b95fa8c9a:deepseek-ai/deepseek-v4-flash",name:"DeepSeek V4 Flash",provider:"default"},
{id:"srv_mkom688d57c76d8a3542:llama-3.3-70b-versatile",name:"Llama 3.3 70B",provider:"default"},
{id:"srv_mrgykg8eea645e7bb006:nemotron-3-super",name:"Nemotron 3 Super",provider:"default"},
{id:"claude-opus-4.5-rp",name:"Claude Opus 4.5",provider:"airforce"},
{id:"gemini-3.1-pro",name:"Gemini 3.1 Pro",provider:"airforce"},
{id:"models/gemini-3.5-flash",name:"Gemini 3.5 Flash",provider:"gemini"},
{id:"moonshotai/kimi-k2.6",name:"Kimi K2.6",provider:"openrouter"},
{id:"qwen/qwen3.7-max",name:"Qwen 3.7 Max",provider:"openrouter"}
],
flux:[
{id:"flux",name:"Flux Image Generation"}
]
};
let currentChatId=null,chats=[],abortController=null,isStreaming=false;
let attachedFiles=[],searchEnabled=false,currentConfig={};
let searchIndicatorCounter=0;
function escapeHtml(t){const d=document.createElement('div');d.textContent=t;return d.innerHTML;}
async function renderMd(text){try{const r=await fetch('/api/render-markdown',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:text})});const d=await r.json();return d.html||text;}catch(e){return text;}}
function isHtmlRendered(text){return /<(p|div|h[1-6]|table|pre|ul|ol|li|hr|br|blockquote|strong|em)\b/i.test(text);}
async function init(){
try{const r=await fetch('/api/config');currentConfig=await r.json();}catch(e){currentConfig={};}
document.body.setAttribute('data-theme',currentConfig.theme||'dark');
document.getElementById('usernameInput').value=currentConfig.username||'';
if(!currentConfig.welcome_seen){
document.getElementById('welcomeOverlay').classList.remove('hidden');
setTimeout(()=>{document.getElementById('welcomeOverlay').classList.add('hidden');saveConfigField('welcome_seen',true);},2000);
}
const savedProvider=currentConfig.last_provider||'openrouter';
document.getElementById('providerSelect').value=savedProvider;
onProviderChange(true);
await loadChats();
const lastId=localStorage.getItem('lastChatId');
if(chats.length>0){
const found=lastId?chats.find(c=>c.id===lastId):null;
await loadChat(found?found.id:chats[0].id);
}else{
await newChat();
}
}
async function saveConfigField(key,val){await fetch('/api/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({[key]:val})});}
async function toggleTheme(){const cur=document.body.getAttribute('data-theme');const next=cur==='dark'?'light':'dark';document.body.setAttribute('data-theme',next);await saveConfigField('theme',next);}
function toggleSidebar(){document.getElementById('sidebar').classList.toggle('open');document.getElementById('sidebarOverlay').classList.toggle('open');}
async function loadChats(){const r=await fetch('/api/chats');chats=await r.json();renderChatList();}
function renderChatList(){
const el=document.getElementById('chatList');el.innerHTML='';let lastGroup='';
chats.forEach(c=>{const group=c.dateGroup||'';if(group!==lastGroup){const gd=document.createElement('div');gd.className='chat-date-group';gd.textContent=group;el.appendChild(gd);lastGroup=group;}
const d=document.createElement('div');d.className='chat-item'+(c.id===currentChatId?' active':'');d.textContent=c.title||'Новый чат';d.onclick=()=>{loadChat(c.id);if(window.innerWidth<=768)toggleSidebar();};el.appendChild(d);});
}
async function newChat(){const r=await fetch('/api/chats',{method:'POST'});const c=await r.json();currentChatId=c.id;localStorage.setItem('lastChatId',c.id);document.getElementById('messages').innerHTML='';await loadChats();}
async function loadChat(id){
if(isStreaming)return;
currentChatId=id;
localStorage.setItem('lastChatId',id);
const r=await fetch('/api/chats/'+id);
if(!r.ok)return;
const data=await r.json();
const el=document.getElementById('messages');el.innerHTML='';
for(const m of data.messages){
if(m.searchResults&&m.searchResults.length>0){
appendSearchIndicatorDone(m.searchResults,m.searchQuery||'');
}
if(m.role==='user'){
const display=m.displayContent||m.content;
appendMsg('user',display,false);
}else if(m.role==='assistant'){
let content=m.content||'';
let html=content;
if(!isHtmlRendered(content)){
html=await renderMd(content);
}
appendMsg('ai','',false,html);
}
}
renderChatList();
addCopyButtons();
}
function appendMsg(role,text,animate=true,rawHtml=null){
const el=document.getElementById('messages');
const d=document.createElement('div');
d.className='msg '+role;
if(!animate)d.style.animation='none';
if(role==='ai'){
const html=rawHtml||escapeHtml(text||'');
d.innerHTML='<div class="msg-content">'+html+'</div><div class="msg-footer"><button class="msg-copy-all" onclick="copyFullResponse(this)">Копировать ответ</button></div>';
}else{
d.textContent=text||'';
}
el.appendChild(d);el.scrollTop=el.scrollHeight;return d;
}
function appendSearchIndicatorDone(results,query){
const el=document.getElementById('messages');
const d=document.createElement('div');
d.className='search-indicator search-done';
d.style.animation='none';
let html='<div class="search-row"><span>Найдено: '+results.length+' результатов</span></div>';
if(results.length>0){
html+='<div class="search-results-preview">';
results.forEach(r=>{html+='<div class="sr-item"><div class="sr-title">'+escapeHtml(r.title||'')+'</div><div>'+escapeHtml((r.body||'').substring(0,120))+'</div></div>';});
html+='</div>';
}
d.innerHTML=html;el.appendChild(d);
}
function copyFullResponse(btn){const msgDiv=btn.closest('.msg');const contentDiv=msgDiv.querySelector('.msg-content');const text=contentDiv?contentDiv.innerText.trim():msgDiv.innerText.trim();navigator.clipboard.writeText(text).then(()=>showToast('Ответ скопирован')).catch(()=>showToast('Ошибка копирования'));}
function showSearchIndicator(){searchIndicatorCounter++;const el=document.getElementById('messages');const d=document.createElement('div');d.className='search-indicator';d.id='si_'+searchIndicatorCounter+'_'+Date.now();d.innerHTML='<div class="search-row"><div class="search-spinner"></div><span>Поиск в DuckDuckGo...</span></div>';el.appendChild(d);el.scrollTop=el.scrollHeight;return d;}
function highlightText(text,query){if(!query||!text)return escapeHtml(text||'');const escaped=escapeHtml(text);const words=query.toLowerCase().split(/\s+/).filter(w=>w.length>2);if(words.length===0)return escaped;let result=escaped;words.forEach(w=>{const regex=new RegExp('('+w.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')+')','gi');result=result.replace(regex,'<span class="sr-highlight">$1</span>');});return result;}
function updateSearchIndicator(indicatorId,results,query){const d=document.getElementById(indicatorId);if(!d)return;d.classList.add('search-done');let html='<div class="search-row"><span>Найдено: '+results.length+' результатов</span></div>';if(results.length>0){html+='<div class="search-results-preview">';results.forEach(r=>{html+='<div class="sr-item"><div class="sr-title">'+highlightText(r.title||'',query)+'</div><div>'+highlightText((r.body||'').substring(0,120),query)+'</div></div>';});html+='</div>';}d.innerHTML=html;document.getElementById('messages').scrollTop=document.getElementById('messages').scrollHeight;}
function addCopyButtons(){document.querySelectorAll('.msg.ai pre').forEach(pre=>{if(pre.querySelector('.copy-code-btn'))return;const btn=document.createElement('button');btn.className='copy-code-btn';btn.textContent='Копировать';btn.onclick=(e)=>{e.stopPropagation();navigator.clipboard.writeText(pre.querySelector('code')?.textContent||pre.textContent).then(()=>showToast('Код скопирован'));};pre.style.position='relative';pre.appendChild(btn);});}
function showToast(msg,duration=2500){const container=document.getElementById('toastContainer');const t=document.createElement('div');t.className='toast';t.textContent=msg;container.appendChild(t);setTimeout(()=>{t.classList.add('out');setTimeout(()=>t.remove(),250);},duration);}
function showWarningToast(text,cfgKey){fetch('/api/config').then(r=>r.json()).then(cfg=>{if(cfg[cfgKey])return;const container=document.getElementById('toastContainer');const t=document.createElement('div');t.className='toast';t.innerHTML='<div>'+escapeHtml(text)+'</div><div class="toast-dismiss"><label><input type="checkbox" data-cfg-key="'+cfgKey+'"> Не показывать снова</label></div>';container.appendChild(t);setTimeout(()=>{const chk=t.querySelector('input[type=checkbox]');if(chk&&chk.checked)saveConfigField(chk.dataset.cfgKey,true);t.classList.add('out');setTimeout(()=>t.remove(),250);},10000);});}
function onProviderChange(silent){const p=document.getElementById('providerSelect').value;const ms=document.getElementById('modelSelect');ms.innerHTML='';const list=MODELS[p]||[];list.forEach(m=>{const o=document.createElement('option');o.value=m.id;o.textContent=m.name;if(m.provider)o.dataset.provider=m.provider;ms.appendChild(o);});saveConfigField('last_provider',p);if(!silent&&p==='g4f')showWarningToast('G4F: бесплатные провайдеры. Ответ может быть медленным.','g4f_warning_dismissed');document.getElementById('searchItem').style.display=p==='flux'?'none':'flex';}
function togglePlusMenu(e){e.stopPropagation();const menu=document.getElementById('plusMenu');const btn=document.getElementById('plusBtn');menu.classList.toggle('open');btn.classList.toggle('menu-open');}
document.addEventListener('click',(e)=>{const menu=document.getElementById('plusMenu');const btn=document.getElementById('plusBtn');if(menu.classList.contains('open')&&!btn.contains(e.target)){menu.classList.remove('open');btn.classList.remove('menu-open');}});
function toggleSearch(e){e.stopPropagation();const provider=document.getElementById('providerSelect').value;if(provider==='flux')return;searchEnabled=!searchEnabled;document.getElementById('searchItem').classList.toggle('active',searchEnabled);if(searchEnabled)showWarningToast('DuckDuckGo поиск выполняется перед отправкой сообщения.','search_warning_dismissed');}
function triggerFileUpload(e){e.stopPropagation();document.getElementById('fileInput').click();}
document.getElementById('fileInput').addEventListener('change',async function(){const files=Array.from(this.files);if(attachedFiles.length+files.length>10){showToast('Максимум 10 файлов');this.value='';return;}for(const file of files){if(attachedFiles.length>=10)break;if(file.size>5*1024*1024){showToast('Файл '+file.name+' слишком большой (макс. 5MB)');continue;}const text=await file.text();attachedFiles.push({name:file.name,content:text});}renderAttachments();this.value='';});
function renderAttachments(){const el=document.getElementById('attachments');el.innerHTML='';attachedFiles.forEach((f,i)=>{const chip=document.createElement('div');chip.className='attachment-chip';chip.innerHTML='<span>'+escapeHtml(f.name)+'</span><button onclick="removeAttachment('+i+')">x</button>';el.appendChild(chip);});}
function removeAttachment(i){attachedFiles.splice(i,1);renderAttachments();}
function autoResize(el){el.style.height='auto';el.style.height=Math.min(el.scrollHeight,160)+'px';}
function handleInputKey(e){if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();send();}}
function resetUIState(){isStreaming=false;abortController=null;document.getElementById('sendBtn').style.display='flex';document.getElementById('stopBtn').style.display='none';document.querySelectorAll('.cursor-blink').forEach(el=>el.classList.remove('cursor-blink'));}
function stopGeneration(){if(abortController){try{abortController.abort();}catch(ex){}}resetUIState();document.getElementById('input').focus();}
async function openSettings(){try{const r=await fetch('/api/config');currentConfig=await r.json();}catch(e){currentConfig={};}document.getElementById('settSystemPrompt').value=currentConfig.system_prompt||'';document.getElementById('settApiKey').value=currentConfig.openrouter_api_key||'';document.getElementById('settDdgsMax').value=currentConfig.ddgs_max_results||5;document.getElementById('settDdgsRegion').value=currentConfig.ddgs_region||'wt-wt';document.getElementById('settDdgsSafe').value=currentConfig.ddgs_safesearch||'moderate';document.getElementById('settDdgsFormat').checked=currentConfig.ddgs_format_context!==false;document.getElementById('settDdgsParse').checked=currentConfig.ddgs_parse_sites===true;document.getElementById('settDdgsParseCount').value=currentConfig.ddgs_parse_count||3;const statusEl=document.getElementById('ddgsStatus');try{const sr=await fetch('/api/ddgs/status');const sd=await sr.json();statusEl.innerHTML=sd.available?'<span class="ddgs-status ddgs-ok">DDGS доступен</span>':'<span class="ddgs-status ddgs-fail">DDGS не установлен</span>';}catch(e){statusEl.innerHTML='<span class="ddgs-status ddgs-fail">Ошибка проверки</span>';}document.getElementById('settingsModal').classList.add('open');}
function closeSettings(){document.getElementById('settingsModal').classList.remove('open');}
async function saveSettings(){const data={system_prompt:document.getElementById('settSystemPrompt').value,openrouter_api_key:document.getElementById('settApiKey').value,ddgs_max_results:parseInt(document.getElementById('settDdgsMax').value)||5,ddgs_region:document.getElementById('settDdgsRegion').value,ddgs_safesearch:document.getElementById('settDdgsSafe').value,ddgs_format_context:document.getElementById('settDdgsFormat').checked,ddgs_parse_sites:document.getElementById('settDdgsParse').checked,ddgs_parse_count:parseInt(document.getElementById('settDdgsParseCount').value)||3};await fetch('/api/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});currentConfig={...currentConfig,...data};closeSettings();showToast('Настройки сохранены');}
async function resetConfig(){if(!confirm('Сбросить все настройки?'))return;await fetch('/api/config/reset',{method:'POST'});const r=await fetch('/api/config');currentConfig=await r.json();document.getElementById('settSystemPrompt').value='';document.getElementById('settApiKey').value='';document.getElementById('settDdgsMax').value=5;document.getElementById('settDdgsRegion').value='wt-wt';document.getElementById('settDdgsSafe').value='moderate';document.getElementById('settDdgsFormat').checked=true;document.getElementById('settDdgsParse').checked=false;document.getElementById('settDdgsParseCount').value=3;document.getElementById('usernameInput').value='';showToast('Конфиг сброшен');}
async function send(){
const input=document.getElementById('input');
const text=input.value.trim();
if((!text&&attachedFiles.length===0)||isStreaming)return;
let fullMessage=text;let totalFileChars=0;
if(attachedFiles.length>0){const fileParts=attachedFiles.map(f=>{totalFileChars+=f.content.length;return '### Файл: '+f.name+'\n```\n'+f.content+'\n```';}).join('\n\n');fullMessage=fullMessage?fullMessage+'\n\n'+fileParts:fileParts;}
const displayNames=attachedFiles.map(f=>f.name);
input.value='';input.style.height='auto';
attachedFiles=[];renderAttachments();
let userDisplay=text;
if(displayNames.length>0){userDisplay=userDisplay?(userDisplay+'\n\n'):'';userDisplay+='Файлы: '+displayNames.join(', ');}
appendMsg('user',userDisplay||fullMessage);
if(!currentChatId)await newChat();
const provider=document.getElementById('providerSelect').value;
const modelEl=document.getElementById('modelSelect');
const model=modelEl.value;
const g4fProvider=modelEl.selectedOptions[0]?.dataset?.provider||null;
const useSearch=searchEnabled&&(totalFileChars<=100)&&(provider!=='flux');
let indicatorId=null;
if(useSearch){const ind=showSearchIndicator();indicatorId=ind.id;}
const aiDiv=appendMsg('ai','<span class="cursor-blink"></span>');
isStreaming=true;
document.getElementById('sendBtn').style.display='none';
document.getElementById('stopBtn').style.display='flex';
abortController=new AbortController();
let streamFinished=false;
try{
const r=await fetch('/api/chat/stream',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({chatId:currentChatId,message:fullMessage,provider,model,g4fProvider,webSearch:useSearch,indicatorId:indicatorId,originalQuery:text,userDisplay:userDisplay||fullMessage}),signal:abortController.signal});
if(!r.ok)throw new Error('HTTP '+r.status);
const reader=r.body.getReader();
const decoder=new TextDecoder('utf-8');
let buffer='',fullContent='',isImage=false;
while(true){
let done,value;
try{const result=await reader.read();done=result.done;value=result.value;}catch(readErr){break;}
if(done)break;
buffer+=decoder.decode(value,{stream:true});
const lines=buffer.split('\n');
buffer=lines.pop()||'';
for(const line of lines){
const trimmed=line.trim();
if(!trimmed.startsWith('data:'))continue;
const payload=trimmed.slice(5).trim();
if(payload==='[DONE]'){streamFinished=true;break;}
try{
const evt=JSON.parse(payload);
if(evt.type==='search_results'&&evt.indicatorId){updateSearchIndicator(evt.indicatorId,evt.results||[],evt.query||'');}
if(evt.type==='image'){isImage=true;const safeUrl=escapeHtml(evt.url||'');aiDiv.innerHTML='<img src="'+safeUrl+'" alt="Generated"><div class="msg-footer"><button class="msg-copy-all" onclick="copyFullResponse(this)">Копировать ответ</button></div>';streamFinished=true;break;}
if(evt.type==='chunk'){fullContent+=evt.data;aiDiv.innerHTML='<div class="msg-content">'+fullContent+'</div><span class="cursor-blink"></span><div class="msg-footer"><button class="msg-copy-all" onclick="copyFullResponse(this)">Копировать ответ</button></div>';document.getElementById('messages').scrollTop=document.getElementById('messages').scrollHeight;}
if(evt.type==='error'){aiDiv.innerHTML='<span style="color:var(--danger)">'+escapeHtml(evt.data||'Ошибка')+'</span><div class="msg-footer"><button class="msg-copy-all" onclick="copyFullResponse(this)">Копировать ответ</button></div>';streamFinished=true;break;}
}catch(ex){}
}
if(streamFinished)break;
}
try{reader.releaseLock();}catch(ex){}
if(!isImage&&fullContent){const rendered=await renderMd(fullContent);aiDiv.innerHTML='<div class="msg-content">'+rendered+'</div><div class="msg-footer"><button class="msg-copy-all" onclick="copyFullResponse(this)">Копировать ответ</button></div>';}
else if(!isImage&&!fullContent){aiDiv.innerHTML='<span style="color:var(--text-dim)">Пустой ответ</span><div class="msg-footer"><button class="msg-copy-all" onclick="copyFullResponse(this)">Копировать ответ</button></div>';}
addCopyButtons();await loadChats();
}catch(err){
if(err.name==='AbortError'){aiDiv.innerHTML='<span style="color:var(--warn)">Остановлено</span><div class="msg-footer"><button class="msg-copy-all" onclick="copyFullResponse(this)">Копировать ответ</button></div>';}
else{aiDiv.innerHTML='<span style="color:var(--danger)">Ошибка: '+escapeHtml(err.message)+'</span><div class="msg-footer"><button class="msg-copy-all" onclick="copyFullResponse(this)">Копировать ответ</button></div>';}
}
resetUIState();document.getElementById('input').focus();
}
init();
</script>
</body>
</html>"""

def get_chat_files():
    files = []
    if not os.path.exists(CHAT_DIR):
        return files
    now = datetime.now()
    today = now.date()
    yesterday = today - timedelta(days=1)
    entries = []
    for f in os.listdir(CHAT_DIR):
        if f.endswith(".json"):
            path = os.path.join(CHAT_DIR, f)
            try:
                mtime = os.path.getmtime(path)
                entries.append((f, path, mtime))
            except Exception:
                pass
    entries.sort(key=lambda x: x[2], reverse=True)
    for f, path, mtime in entries:
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            created_str = data.get("created_at", "")
            date_group = "Ранее"
            if created_str:
                try:
                    created_dt = datetime.fromisoformat(created_str)
                    cd = created_dt.date()
                    if cd == today:
                        date_group = "Сегодня"
                    elif cd == yesterday:
                        date_group = "Вчера"
                    else:
                        date_group = created_dt.strftime("%d.%m.%Y")
                except Exception:
                    pass
            files.append({
                "id": f.replace(".json", ""),
                "title": data.get("title", "Новый чат"),
                "messages": data.get("messages", []),
                "dateGroup": date_group,
                "createdAt": created_str
            })
        except Exception:
            pass
    return files

def save_chat(chat_id, messages, title=None, created_at=None):
    lock = get_chat_lock(chat_id)
    with lock:
        path = os.path.join(CHAT_DIR, f"{chat_id}.json")
        if created_at is None:
            existing_created = None
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        existing_created = json.load(f).get("created_at")
                except Exception:
                    pass
            created_at = existing_created or datetime.now().isoformat()
        data = {
            "title": title or "Новый чат",
            "messages": messages,
            "created_at": created_at
        }
        try:
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, path)
        except Exception:
            pass

def generate_title(message):
    try:
        if G4F_AVAILABLE:
            client = G4FClient()
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": f"Заголовок чата (2-4 слова): \"{message[:200]}\". Только заголовок."}],
                web_search=False
            )
            title = resp.choices[0].message.content.strip().strip('"').strip("'").strip(".")[:50]
            if title:
                return title
    except Exception:
        pass
    return message[:40].replace("\n", " ")

def safe_write(wfile, data):
    try:
        wfile.write(data)
        wfile.flush()
        return True
    except (BrokenPipeError, ConnectionResetError, OSError):
        return False

def extract_keywords(query):
    stopwords = {'и','в','на','с','по','о','к','а','но','не','что','как','это','то','да','нет','ну','бы','ли','же','за','от','до','из','у','для','ты','я','он','она','мы','вы','они','мне','тебя','его','ее','нас','вас','их','мой','твой','свой','этот','тот','так','там','тут','еще','уже','очень','просто','тоже','или','если','когда','где','кто','чем','без','под','над','перед','через','про','при','можно','надо','нужно','хочу','можешь','скажи','расскажи','покажи','напиши','сделай','дай','будь','будет','был','была','было','были','есть','будут','стал','стала','стало','стали','также','более','менее','сам','себе','сюда','туда','здесь','потом','сейчас','сегодня','вчера','завтра','дарова','привет','здорово','здарова','абоба','лять','сука','блять','нахуй','пожалуйста','спасибо','короче','типа','блин','ладно','ок','окей','слушай','смотри','знаешь','понимаешь','короч','вообще','конечно','может','наверное','точно','прямо','совсем','чуть','вроде','типо','подробнее','последнее','последний','последняя','новости','новость','сводку','таблицу','код','калькулятор','пайтон','python','сво','об','обо','насчет'}
    words = re.findall(r'[а-яёa-z0-9]+', query.lower())
    keywords = [w for w in words if w not in stopwords and len(w) > 2]
    seen = set()
    unique = []
    for w in keywords:
        if w not in seen:
            seen.add(w)
            unique.append(w)
    return unique[:8]

def parse_site_content(url, max_chars=4000):
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7"
        }
        resp = requests.get(url, timeout=15, headers=headers, allow_redirects=True)
        resp.raise_for_status()
        text = resp.text
        text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<nav[^>]*>.*?</nav>', '', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<footer[^>]*>.*?</footer>', '', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<header[^>]*>.*?</header>', '', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<!--.*?-->', '', text, flags=re.DOTALL)
        text = re.sub(r'<[^>]+>', ' ', text)
        text = re.sub(r'&nbsp;', ' ', text)
        text = re.sub(r'&[a-z]+;', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()
        return text[:max_chars]
    except Exception:
        return ""

def ddgs_search(query, cfg):
    max_results = cfg.get("ddgs_max_results", 5)
    region = cfg.get("ddgs_region", "wt-wt")
    safesearch = cfg.get("ddgs_safesearch", "moderate")
    parse_sites = cfg.get("ddgs_parse_sites", False)
    parse_count = cfg.get("ddgs_parse_count", 3)
    keywords = extract_keywords(query)
    optimized_query = " ".join(keywords) if keywords else query
    try:
        ddgs = DDGS()
        results = list(ddgs.text(optimized_query, region=region, safesearch=safesearch, max_results=max_results))
        if not results:
            return [], "", optimized_query
        parts = []
        for i, r in enumerate(results, 1):
            title = r.get("title", "")
            body = r.get("body", "")
            href = r.get("href", "")
            entry = f"[Источник {i}] {title}\n{body}"
            if parse_sites and i <= parse_count and href:
                site_text = parse_site_content(href)
                if site_text:
                    entry += f"\n[Содержимое сайта]: {site_text}"
            if href:
                entry += f"\nURL: {href}"
            parts.append(entry)
        context = "\n\n".join(parts)
        return results, context, optimized_query
    except Exception as e:
        return [], f"[Ошибка поиска: {str(e)}]", optimized_query

def call_openrouter_stream(messages, model, api_key):
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    body = {"model": model, "messages": messages, "stream": True}
    resp = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers=headers,
        json=body,
        stream=True,
        timeout=120
    )
    resp.raise_for_status()
    for raw_line in resp.iter_lines():
        if not raw_line:
            continue
        line = raw_line.decode("utf-8", errors="replace")
        if line.startswith("data:"):
            payload = line[5:].strip()
            if payload == "[DONE]":
                yield None
                return
            try:
                chunk = json.loads(payload)
                choices = chunk.get("choices", [])
                if not choices:
                    continue
                delta = choices[0].get("delta", {})
                content = delta.get("content", "")
                if content:
                    yield content
            except Exception:
                pass

def call_g4f_sync(messages, model, provider):
    if not G4F_AVAILABLE:
        raise RuntimeError("g4f не установлен")
    client = G4FClient()
    kwargs = {"model": model, "messages": messages, "web_search": False}
    if provider and provider != "default":
        kwargs["provider"] = provider
    response = client.chat.completions.create(**kwargs)
    msg = response.choices[0].message
    if hasattr(msg, "image") and msg.image:
        img = msg.image
        if isinstance(img, bytes):
            b64 = base64.b64encode(img).decode("utf-8")
            return None, f"data:image/png;base64,{b64}"
        return None, str(img)
    content = msg.content if hasattr(msg, "content") else str(msg)
    return content, None

class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path in ("/", "/index.html"):
            data = HTML_CONTENT.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        elif parsed.path == "/api/config":
            data = json.dumps(load_config(), ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        elif parsed.path == "/api/ddgs/status":
            status = {"available": DDGS_AVAILABLE}
            data = json.dumps(status).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        elif parsed.path == "/api/chats":
            result = [
                {"id": c["id"], "title": c["title"], "dateGroup": c["dateGroup"], "createdAt": c["createdAt"]}
                for c in get_chat_files()
            ]
            data = json.dumps(result, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        elif parsed.path.startswith("/api/chats/"):
            chat_id = parsed.path.split("/")[-1]
            if not re.match(r'^[a-f0-9-]+$', chat_id):
                self.send_response(400)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            path = os.path.join(CHAT_DIR, f"{chat_id}.json")
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    raw = f.read()
                data = raw.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            else:
                self.send_response(404)
                self.send_header("Content-Length", "0")
                self.end_headers()
        else:
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()

    def do_POST(self):
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8") if length else "{}"
        if parsed.path == "/api/config":
            try:
                data = json.loads(body)
                cfg = load_config()
                cfg.update(data)
                save_config(cfg)
            except Exception:
                pass
            resp = b'{"ok":true}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(resp)))
            self.end_headers()
            self.wfile.write(resp)
        elif parsed.path == "/api/config/reset":
            save_config(dict(DEFAULT_CONFIG))
            resp = b'{"ok":true}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(resp)))
            self.end_headers()
            self.wfile.write(resp)
        elif parsed.path == "/api/render-markdown":
            try:
                data = json.loads(body)
                text = data.get("text", "")
                rendered = render_md(text)
                resp = json.dumps({"html": rendered}, ensure_ascii=False).encode("utf-8")
            except Exception:
                resp = b'{"html":""}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(resp)))
            self.end_headers()
            self.wfile.write(resp)
        elif parsed.path == "/api/chats":
            chat_id = str(uuid.uuid4())[:8]
            created_at = datetime.now().isoformat()
            save_chat(chat_id, [], created_at=created_at)
            resp = json.dumps({"id": chat_id}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(resp)))
            self.end_headers()
            self.wfile.write(resp)
        elif parsed.path == "/api/chat/stream":
            try:
                data = json.loads(body)
            except Exception:
                self.send_response(400)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            chat_id = data.get("chatId", "")
            message = data.get("message", "")
            provider = data.get("provider", "openrouter")
            model = data.get("model", "")
            g4f_provider = data.get("g4fProvider")
            web_search = data.get("webSearch", False)
            indicator_id = data.get("indicatorId", "")
            original_query = data.get("originalQuery", "")
            user_display = data.get("userDisplay", "")
            cfg = load_config()
            path = os.path.join(CHAT_DIR, f"{chat_id}.json")
            messages = []
            title = None
            created_at = None
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        existing = json.load(f)
                    messages = [m for m in existing.get("messages", []) if m.get("role") != "system"]
                    title = existing.get("title")
                    created_at = existing.get("created_at")
                except Exception:
                    pass
            system_prompt = cfg.get("system_prompt", "").strip()
            api_messages = list(messages)
            if system_prompt:
                api_messages.insert(0, {"role": "system", "content": system_prompt})
            optimized_query_used = ""
            search_results_saved = []
            if web_search and message and provider != "flux":
                search_query = original_query if original_query else message[:300]
                search_results_list, search_context, optimized_query_used = ddgs_search(search_query, cfg)
                search_results_saved = search_results_list
                evt = json.dumps({"type": "search_results", "results": search_results_list, "indicatorId": indicator_id, "query": optimized_query_used}, ensure_ascii=False)
                safe_write(self.wfile, f"data: {evt}\n\n".encode("utf-8"))
                if search_results_list:
                    current_date = datetime.now().strftime("%d %B %Y года")
                    formatted = f"[Контекст из DuckDuckGo (запрос: \"{optimized_query_used}\", дата: {current_date})]\n{search_context}\n\n[Запрос пользователя]\n{message}"
                    api_messages.append({"role": "user", "content": formatted})
                else:
                    api_messages.append({"role": "user", "content": message})
            else:
                api_messages.append({"role": "user", "content": message})
            if not title or title == "Новый чат":
                title = generate_title(original_query if original_query else message)
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            full_reply = ""
            is_image = False
            try:
                if provider == "flux":
                    reply_text, img = call_g4f_sync(api_messages, "flux", None)
                    if img:
                        is_image = True
                        evt = json.dumps({"type": "image", "url": img}, ensure_ascii=False)
                        safe_write(self.wfile, f"data: {evt}\n\n".encode("utf-8"))
                        full_reply = "[IMAGE]"
                    else:
                        rendered = render_md(reply_text or "Не удалось сгенерировать изображение")
                        evt = json.dumps({"type": "chunk", "data": rendered}, ensure_ascii=False)
                        safe_write(self.wfile, f"data: {evt}\n\n".encode("utf-8"))
                        full_reply = rendered
                    safe_write(self.wfile, b"data: [DONE]\n\n")
                elif provider == "openrouter":
                    api_key = cfg.get("openrouter_api_key", "")
                    for chunk in call_openrouter_stream(api_messages, model, api_key):
                        if chunk is None:
                            safe_write(self.wfile, b"data: [DONE]\n\n")
                            break
                        evt = json.dumps({"type": "chunk", "data": chunk}, ensure_ascii=False)
                        encoded = f"data: {evt}\n\n".encode("utf-8")
                        if not safe_write(self.wfile, encoded):
                            break
                        full_reply += chunk
                    else:
                        safe_write(self.wfile, b"data: [DONE]\n\n")
                else:
                    reply_text, img = call_g4f_sync(api_messages, model, g4f_provider)
                    if img:
                        is_image = True
                        evt = json.dumps({"type": "image", "url": img}, ensure_ascii=False)
                        safe_write(self.wfile, f"data: {evt}\n\n".encode("utf-8"))
                        full_reply = "[IMAGE]"
                    else:
                        rendered = render_md(reply_text or "")
                        evt = json.dumps({"type": "chunk", "data": rendered}, ensure_ascii=False)
                        safe_write(self.wfile, f"data: {evt}\n\n".encode("utf-8"))
                        full_reply = rendered
                    safe_write(self.wfile, b"data: [DONE]\n\n")
            except Exception as e:
                err_msg = str(e)
                evt = json.dumps({"type": "error", "data": err_msg}, ensure_ascii=False)
                safe_write(self.wfile, f"data: {evt}\n\n".encode("utf-8"))
                safe_write(self.wfile, b"data: [DONE]\n\n")
                full_reply = f"Ошибка: {err_msg}"
            if provider == "openrouter" and full_reply and not is_image:
                full_reply = render_md(full_reply)
            save_messages = list(messages)
            user_msg = {"role": "user", "content": message}
            if user_display and user_display != message:
                user_msg["displayContent"] = user_display
            if search_results_saved:
                user_msg["searchResults"] = search_results_saved
                user_msg["searchQuery"] = optimized_query_used
            save_messages.append(user_msg)
            if is_image:
                msg_entry = {"role": "assistant", "content": "[IMAGE]"}
                save_messages.append(msg_entry)
            else:
                msg_entry = {"role": "assistant", "content": full_reply}
                save_messages.append(msg_entry)
            save_chat(chat_id, save_messages, title, created_at)
        else:
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()

def main():
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"CIS AI Chat Server:")
    print(f"  Local:   http://127.0.0.1:{PORT}")
    print(f"  Network: http://{LOCAL_IP}:{PORT}")
    threading.Timer(1.5, lambda: webbrowser.open(f"http://127.0.0.1:{PORT}")).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()

if __name__ == "__main__":
    main()