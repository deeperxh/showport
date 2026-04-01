"""
ShowPort - Windows 端口可视化管理工具
一个本地桌面应用，查看端口占用、搜索过滤、一键Kill进程。
"""

import os
import subprocess
import re
import json
import webbrowser
from urllib.request import urlopen, Request

import psutil
import webview


CURRENT_VERSION = "1.2.0"
GITHUB_REPO = "deeperxh/showport"


def get_connections():
    """通过 netstat -ano 获取所有网络连接，再用 psutil 查进程名"""
    results = []
    try:
        output = subprocess.check_output(
            ['netstat', '-ano'], encoding='gbk', errors='replace'
        )
    except Exception as e:
        return [{'error': str(e)}]

    pid_name_cache = {}

    for line in output.splitlines():
        line = line.strip()
        # 匹配 TCP / UDP 行
        m = re.match(
            r'(TCP|UDP)\s+'           # 协议
            r'(\S+):(\d+)\s+'         # 本地地址:端口
            r'(\S+):(\S+)\s*'         # 远程地址:端口
            r'(\S*)\s*'               # 状态 (UDP 无状态)
            r'(\d+)',                  # PID
            line
        )
        if not m:
            continue

        proto = m.group(1)
        local_addr = m.group(2)
        local_port = int(m.group(3))
        remote_addr = m.group(4)
        remote_port_str = m.group(5)
        status = m.group(6).strip() if m.group(6) else ''
        pid = int(m.group(7))

        remote_port = int(remote_port_str) if remote_port_str.isdigit() else 0

        # netstat 输出状态名与 psutil 不同，统一一下
        status_map = {
            'LISTENING': 'LISTEN',
            'ESTABLISHED': 'ESTABLISHED',
            'TIME_WAIT': 'TIME_WAIT',
            'CLOSE_WAIT': 'CLOSE_WAIT',
            'FIN_WAIT_2': 'FIN_WAIT2',
            'SYN_SENT': 'SYN_SENT',
            'SYN_RECEIVED': 'SYN_RECV',
            'LAST_ACK': 'LAST_ACK',
            'CLOSING': 'CLOSING',
        }
        status = status_map.get(status, status)

        # 获取进程名（带缓存）
        proc_name = ''
        if pid > 0:
            if pid in pid_name_cache:
                proc_name = pid_name_cache[pid]
            else:
                try:
                    proc_name = psutil.Process(pid).name()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    proc_name = '-'
                pid_name_cache[pid] = proc_name

        results.append({
            'proto': proto,
            'localAddr': local_addr,
            'localPort': local_port,
            'remoteAddr': remote_addr,
            'remotePort': remote_port,
            'status': status,
            'pid': pid,
            'procName': proc_name,
        })

    return results


def kill_process(pid, lang='zh'):
    """终止指定PID的进程"""
    en = lang == 'en'
    try:
        pid = int(pid)
        if pid <= 0:
            return {'success': False, 'message': 'Invalid PID' if en else '无效的 PID'}
        if pid == os.getpid():
            return {'success': False, 'message': 'Cannot kill self' if en else '不能终止自身进程'}
        proc = psutil.Process(pid)
        proc_name = proc.name()
        proc.kill()
        proc.wait(timeout=3)
        msg = f'Killed {proc_name} (PID: {pid})' if en else f'已终止进程 {proc_name} (PID: {pid})'
        return {'success': True, 'message': msg}
    except psutil.NoSuchProcess:
        msg = f'Process {pid} not found' if en else f'进程 {pid} 不存在'
        return {'success': False, 'message': msg}
    except psutil.AccessDenied:
        try:
            subprocess.check_output(
                ['taskkill', '/F', '/PID', str(pid)],
                encoding='gbk', errors='replace'
            )
            msg = f'Killed process (PID: {pid})' if en else f'已终止进程 (PID: {pid})'
            return {'success': True, 'message': msg}
        except Exception:
            msg = f'Access denied for PID {pid}, run as admin' if en else f'无权限终止进程 {pid}，请以管理员身份运行'
            return {'success': False, 'message': msg}
    except Exception as e:
        msg = f'Kill failed: {str(e)}' if en else f'终止失败: {str(e)}'
        return {'success': False, 'message': msg}


def check_for_update():
    """检查 GitHub Releases 是否有新版本"""
    try:
        url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
        req = Request(url, headers={"User-Agent": "ShowPort-Updater"})
        with urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        tag = data.get("tag_name", "")
        remote_ver = tag.lstrip("v")
        if remote_ver > CURRENT_VERSION:
            return {
                "hasUpdate": True,
                "currentVersion": CURRENT_VERSION,
                "latestVersion": remote_ver,
                "url": data.get("html_url", ""),
                "body": data.get("body", ""),
            }
    except Exception:
        pass
    return {"hasUpdate": False, "currentVersion": CURRENT_VERSION}


class Api:
    """暴露给前端 JS 调用的 Python API"""

    def get_ports(self):
        return get_connections()

    def kill_pid(self, pid, lang='zh'):
        return kill_process(pid, lang)

    def check_update(self):
        return check_for_update()

    def open_url(self, url):
        webbrowser.open(url)


HTML = r"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>ShowPort</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }

  :root {
    --bg-primary: #f5f6fa;
    --bg-surface: #ffffff;
    --bg-toolbar: #ffffff;
    --bg-input: #f0f1f5;
    --bg-row-hover: #eef0ff;
    --bg-row-stripe: #fafbfd;
    --border: #e2e4ea;
    --border-light: #f0f1f5;
    --border-focus: #5b6ef5;
    --text-primary: #1a1d2e;
    --text-secondary: #5a5e72;
    --text-muted: #6b6f82;
    --accent: #5b6ef5;
    --accent-light: #eef0ff;
    --danger: #e5354b;
    --danger-hover: #ff4d63;
    --danger-bg: #fef2f2;
    --danger-border: #fecaca;
    --danger-hover-bg: #fee2e2;
    --success: #10b981;
    --success-bg: #ecfdf5;
    --success-text: #065f46;
    --error-text: #991b1b;
    --info-text: #3730a3;
    --listening: #10b981;
    --established: #3b82f6;
    --time-wait: #f59e0b;
    --close-wait: #f97316;
    --status-listen-bg: #ecfdf5;
    --status-established-bg: #eff6ff;
    --status-time-wait-bg: #fffbeb;
    --status-close-wait-bg: #fff7ed;
    --shadow-sm: 0 1px 3px rgba(0,0,0,0.06);
    --shadow-md: 0 4px 12px rgba(0,0,0,0.08);
    --scrollbar-thumb: #cccfda;
    --scrollbar-thumb-hover: #b0b4c2;
    --mark-bg: rgba(91,110,245,0.18);
    --focus-ring: 0 0 0 3px rgba(91,110,245,0.12);
    --overlay-bg: rgba(0,0,0,0.25);
    --modal-shadow: 0 12px 40px rgba(0,0,0,0.12);
    --toast-success-border: #a7f3d0;
    --toast-error-border: #fecaca;
    --toast-info-border: #c7d2fe;
    --toggle-knob: #ffffff;
    --danger-shadow: 0 2px 6px rgba(229,53,75,0.15);
    --accent-shadow: 0 2px 8px rgba(91,110,245,0.3);
  }

  [data-theme="dark"] {
      --bg-primary: #1a1b2e;
      --bg-surface: #242538;
      --bg-toolbar: #242538;
      --bg-input: #2d2e42;
      --bg-row-hover: #2d2e52;
      --bg-row-stripe: #1e1f34;
      --border: #3a3b52;
      --border-light: #2d2e42;
      --border-focus: #7b8af7;
      --text-primary: #e8e9f0;
      --text-secondary: #a8abba;
      --text-muted: #8a8e9f;
      --accent: #7b8af7;
      --accent-light: #2a2b52;
      --danger: #f06070;
      --danger-hover: #ff7080;
      --danger-bg: #2e1a1e;
      --danger-border: #5a2a30;
      --danger-hover-bg: #3e2228;
      --success: #34d399;
      --success-bg: #1a2e24;
      --success-text: #6ee7b7;
      --error-text: #fca5a5;
      --info-text: #a5b4fc;
      --listening: #34d399;
      --established: #60a5fa;
      --time-wait: #fbbf24;
      --close-wait: #fb923c;
      --status-listen-bg: #1a2e24;
      --status-established-bg: #1a2232;
      --status-time-wait-bg: #2e2a1a;
      --status-close-wait-bg: #2e241a;
      --shadow-sm: 0 1px 3px rgba(0,0,0,0.3);
      --shadow-md: 0 4px 12px rgba(0,0,0,0.4);
      --scrollbar-thumb: #4a4b62;
      --scrollbar-thumb-hover: #5a5b72;
      --mark-bg: rgba(123,138,247,0.25);
      --focus-ring: 0 0 0 3px rgba(123,138,247,0.25);
      --overlay-bg: rgba(0,0,0,0.5);
      --modal-shadow: 0 12px 40px rgba(0,0,0,0.4);
      --toast-success-border: #065f46;
      --toast-error-border: #7f1d1d;
      --toast-info-border: #3730a3;
      --toggle-knob: #e8e9f0;
      --danger-shadow: 0 2px 6px rgba(240,96,112,0.25);
      --accent-shadow: 0 2px 8px rgba(123,138,247,0.35);
  }

  html, body {
    height: 100%;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Microsoft YaHei', sans-serif;
    background: var(--bg-primary);
    color: var(--text-primary);
    overflow: hidden;
    -webkit-font-smoothing: antialiased;
  }

  .sr-only {
    position: absolute;
    width: 1px;
    height: 1px;
    padding: 0;
    margin: -1px;
    overflow: hidden;
    clip: rect(0,0,0,0);
    white-space: nowrap;
    border: 0;
  }

  .app {
    display: flex;
    flex-direction: column;
    height: 100vh;
  }

  /* ---- Toolbar ---- */
  .toolbar {
    display: flex;
    align-items: center;
    gap: 12px 14px;
    padding: 12px 20px;
    background: var(--bg-toolbar);
    border-bottom: 1px solid var(--border);
    flex-shrink: 0;
    box-shadow: var(--shadow-sm);
    position: relative;
    z-index: 20;
    flex-wrap: wrap;
  }

  .toolbar .logo {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-right: 6px;
    flex-shrink: 0;
  }

  .toolbar .logo svg { width: 22px; height: 22px; color: var(--accent); }

  .toolbar .logo span {
    font-family: 'Cascadia Code', 'Consolas', 'SF Mono', monospace;
    font-weight: 700;
    font-size: 14px;
    letter-spacing: 0.5px;
    color: var(--text-primary);
  }

  .search-box {
    flex: 1;
    position: relative;
    max-width: 480px;
  }

  .search-box svg {
    position: absolute;
    left: 12px;
    top: 50%;
    transform: translateY(-50%);
    width: 16px; height: 16px;
    color: var(--text-muted);
    pointer-events: none;
    transition: color 0.15s;
  }

  .search-box input {
    width: 100%;
    padding: 9px 12px 9px 36px;
    background: var(--bg-input);
    border: 1.5px solid transparent;
    border-radius: 10px;
    color: var(--text-primary);
    font-family: 'Cascadia Code', 'Consolas', 'SF Mono', monospace;
    font-size: 13px;
    outline: none;
    transition: border-color 0.2s, background 0.2s, box-shadow 0.2s;
  }

  .search-box input:focus {
    border-color: var(--border-focus);
    background: var(--bg-surface);
    box-shadow: var(--focus-ring);
  }

  .search-box input:focus + svg { color: var(--accent); }

  .search-box input::placeholder { color: var(--text-muted); }

  .toolbar-actions {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-left: auto;
    flex-shrink: 0;
  }

  .btn {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 8px 14px;
    border: 1.5px solid var(--border);
    border-radius: 8px;
    background: var(--bg-surface);
    color: var(--text-secondary);
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Microsoft YaHei', sans-serif;
    font-size: 12px;
    font-weight: 500;
    cursor: pointer;
    transition: border-color 0.15s, color 0.15s, background 0.15s, transform 0.15s;
    white-space: nowrap;
  }

  .btn:hover {
    border-color: var(--accent);
    color: var(--accent);
    background: var(--accent-light);
  }

  .btn:active { transform: scale(0.97); }
  .btn:focus-visible { box-shadow: var(--focus-ring); outline: none; }

  .btn svg { width: 14px; height: 14px; }

  .auto-refresh {
    display: flex;
    align-items: center;
    gap: 6px;
    color: var(--text-muted);
    font-size: 12px;
  }

  .toggle {
    position: relative;
    width: 40px; height: 24px;
    appearance: none;
    background: var(--bg-input);
    border: 1.5px solid var(--border);
    border-radius: 12px;
    cursor: pointer;
    transition: background 0.25s, border-color 0.25s;
    flex-shrink: 0;
  }

  .toggle::after {
    content: '';
    position: absolute;
    top: 3px; left: 3px;
    width: 16px; height: 16px;
    background: var(--text-muted);
    border-radius: 50%;
    transition: left 0.25s, background 0.25s;
  }

  .toggle:checked { background: var(--accent); border-color: var(--accent); }
  .toggle:checked::after { left: 19px; background: var(--toggle-knob); }
  .toggle:focus-visible { box-shadow: var(--focus-ring); outline: none; }

  /* ---- Stats Bar ---- */
  .stats-bar {
    display: flex;
    align-items: center;
    gap: 22px;
    padding: 8px 20px;
    border-bottom: 1px solid var(--border);
    font-family: 'Cascadia Code', 'Consolas', 'SF Mono', monospace;
    font-size: 11px;
    color: var(--text-muted);
    flex-shrink: 0;
    background: var(--bg-surface);
  }

  .stats-bar .stat { display: flex; align-items: center; gap: 6px; }
  .stats-bar .stat .dot { width: 7px; height: 7px; border-radius: 50%; }
  .stat-total .dot { background: var(--accent); }
  .stat-listening .dot { background: var(--listening); }
  .stat-established .dot { background: var(--established); }
  .stat-other .dot { background: var(--text-muted); }
  .stats-bar .stat-val { color: var(--text-primary); font-weight: 600; }

  /* ---- Table ---- */
  .table-wrap {
    flex: 1;
    overflow: auto;
    background: var(--bg-surface);
  }

  .table-wrap::-webkit-scrollbar { width: 8px; height: 8px; }
  .table-wrap::-webkit-scrollbar-track { background: var(--bg-primary); }
  .table-wrap::-webkit-scrollbar-thumb { background: var(--scrollbar-thumb); border-radius: 4px; }
  .table-wrap::-webkit-scrollbar-thumb:hover { background: var(--scrollbar-thumb-hover); }

  table {
    width: 100%;
    border-collapse: collapse;
    font-size: 12.5px;
    table-layout: fixed;
  }

  thead { position: sticky; top: 0; z-index: 10; }

  th {
    padding: 10px 14px;
    text-align: left;
    font-weight: 600;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.6px;
    color: var(--text-muted);
    background: var(--bg-primary);
    border-bottom: 1.5px solid var(--border);
    cursor: pointer;
    user-select: none;
    white-space: nowrap;
    transition: color 0.15s;
  }

  th:hover { color: var(--text-primary); }
  th:last-child { cursor: default; }

  th .sort-arrow {
    display: inline-block;
    margin-left: 3px;
    opacity: 0;
    transition: opacity 0.15s;
    font-size: 10px;
  }

  th.sorted .sort-arrow { opacity: 1; color: var(--accent); }
  th.sorted { color: var(--accent); }

  /* Column widths */
  th:nth-child(1), td:nth-child(1) { width: 5%; }
  th:nth-child(2), td:nth-child(2) { width: 13%; }
  th:nth-child(3), td:nth-child(3) { width: 8%; }
  th:nth-child(4), td:nth-child(4) { width: 13%; }
  th:nth-child(5), td:nth-child(5) { width: 8%; }
  th:nth-child(6), td:nth-child(6) { width: 12%; }
  th:nth-child(7), td:nth-child(7) { width: 6%; }
  th:nth-child(8), td:nth-child(8) { width: auto; }
  th:nth-child(9), td:nth-child(9) { width: 8%; text-align: center; }

  td {
    padding: 7px 14px;
    border-bottom: 1px solid var(--border-light);
    font-family: 'Cascadia Code', 'Consolas', 'SF Mono', monospace;
    font-size: 12px;
    color: var(--text-secondary);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  tr:nth-child(even) td { background: var(--bg-row-stripe); }
  tr:hover td { background: var(--bg-row-hover); color: var(--text-primary); }

  /* Status badges */
  .status-badge {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 5px;
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.4px;
  }

  .status-LISTEN { background: var(--status-listen-bg); color: var(--listening); }
  .status-ESTABLISHED { background: var(--status-established-bg); color: var(--established); }
  .status-TIME_WAIT { background: var(--status-time-wait-bg); color: var(--time-wait); }
  .status-CLOSE_WAIT { background: var(--status-close-wait-bg); color: var(--close-wait); }
  .status-NONE, .status-other { background: var(--bg-input); color: var(--text-muted); }

  .proc-name { color: var(--text-primary); font-weight: 500; }
  .port-highlight { color: var(--accent); font-weight: 700; }

  /* Kill button */
  .btn-kill {
    display: inline-flex;
    align-items: center;
    gap: 3px;
    padding: 6px 12px;
    border: 1px solid var(--danger-border);
    border-radius: 6px;
    background: var(--danger-bg);
    color: var(--danger);
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Microsoft YaHei', sans-serif;
    font-size: 11px;
    font-weight: 500;
    cursor: pointer;
    transition: background 0.15s, border-color 0.15s, transform 0.15s, box-shadow 0.15s;
    min-height: 30px;
  }

  .btn-kill:hover {
    background: var(--danger-hover-bg);
    border-color: var(--danger);
    transform: translateY(-1px);
    box-shadow: var(--shadow-md);
  }

  .btn-kill:focus-visible { box-shadow: var(--focus-ring); outline: none; }

  .btn-kill svg { width: 12px; height: 12px; }
  .btn-kill:disabled { opacity: 0.3; cursor: not-allowed; transform: none; box-shadow: none; }

  /* ---- Toast ---- */
  .toast-container {
    position: fixed;
    top: 16px;
    right: 16px;
    z-index: 1000;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .toast {
    padding: 10px 16px;
    border-radius: 10px;
    font-size: 12px;
    font-weight: 500;
    animation: toastIn 0.25s ease-out;
    max-width: 360px;
    box-shadow: var(--shadow-md);
    transition: opacity 0.25s ease-in;
  }

  .toast.toast-exit { opacity: 0; }

  .toast-success { background: var(--success-bg); color: var(--success-text); border: 1px solid var(--toast-success-border); }
  .toast-error { background: var(--danger-bg); color: var(--error-text); border: 1px solid var(--toast-error-border); }
  .toast-info { background: var(--accent-light); color: var(--info-text); border: 1px solid var(--toast-info-border); }

  @keyframes toastIn { from { opacity: 0; transform: translateX(20px); } to { opacity: 1; transform: translateX(0); } }

  /* ---- Modal ---- */
  .modal-overlay {
    display: none;
    position: fixed;
    inset: 0;
    background: var(--overlay-bg);
    backdrop-filter: blur(3px);
    z-index: 900;
    align-items: center;
    justify-content: center;
    opacity: 0;
    transition: opacity 0.2s ease-out;
  }

  .modal-overlay.active { display: flex; opacity: 1; }
  .modal-overlay.closing { opacity: 0; }

  .modal {
    background: var(--bg-surface);
    border: 1px solid var(--border);
    border-radius: 14px;
    padding: 24px;
    min-width: 380px;
    box-shadow: var(--modal-shadow);
    animation: modalIn 0.2s ease-out;
    transition: opacity 0.15s, transform 0.15s;
  }

  .modal-overlay.closing .modal { opacity: 0; transform: scale(0.95); }

  @keyframes modalIn { from { opacity: 0; transform: scale(0.95); } to { opacity: 1; transform: scale(1); } }

  .modal h3 { font-size: 15px; font-weight: 600; margin-bottom: 8px; }
  .modal p { font-size: 13px; color: var(--text-secondary); margin-bottom: 20px; line-height: 1.6; }
  .modal p strong { color: var(--danger); }

  .modal-actions { display: flex; gap: 10px; justify-content: flex-end; }

  .modal-actions .btn-cancel {
    padding: 8px 18px;
    border: 1.5px solid var(--border);
    border-radius: 8px;
    background: var(--bg-surface);
    color: var(--text-secondary);
    font-size: 13px;
    cursor: pointer;
    transition: border-color 0.15s, color 0.15s;
  }

  .modal-actions .btn-cancel:hover { border-color: var(--text-muted); color: var(--text-primary); }
  .modal-actions .btn-cancel:focus-visible { box-shadow: var(--focus-ring); outline: none; }

  .modal-actions .btn-confirm-kill {
    padding: 8px 18px;
    border: none;
    border-radius: 8px;
    background: var(--danger);
    color: var(--toggle-knob);
    font-size: 13px;
    font-weight: 600;
    cursor: pointer;
    transition: background 0.15s;
  }

  .modal-actions .btn-confirm-kill:hover { background: var(--danger-hover); }
  .modal-actions .btn-confirm-kill:focus-visible { box-shadow: var(--focus-ring); outline: none; }

  /* ---- Empty ---- */
  .empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 60px 20px;
    color: var(--text-muted);
  }

  .empty-state svg { width: 48px; height: 48px; margin-bottom: 16px; opacity: 0.35; }
  .empty-state p { font-size: 14px; }

  /* ---- Loading ---- */
  .loading-bar {
    height: 2.5px;
    background: linear-gradient(90deg, transparent, var(--accent), transparent);
    position: absolute;
    top: 0; left: 0; right: 0;
    animation: loadSlide 0.9s ease-in-out infinite;
    display: none;
    z-index: 30;
    will-change: transform;
  }

  .loading-bar.active { display: block; }

  @keyframes loadSlide { 0% { transform: translateX(-100%); } 100% { transform: translateX(100%); } }

  mark {
    background: var(--mark-bg);
    color: var(--text-primary);
    border-radius: 2px;
    padding: 0 2px;
  }

  .lang-btn {
    padding: 7px 12px;
    border: 1.5px solid var(--border);
    border-radius: 6px;
    background: var(--bg-surface);
    color: var(--text-muted);
    font-family: 'Cascadia Code', 'Consolas', 'SF Mono', monospace;
    font-size: 11px;
    font-weight: 600;
    cursor: pointer;
    transition: border-color 0.15s, color 0.15s, background 0.15s;
    letter-spacing: 0.3px;
    min-height: 32px;
  }
  .lang-btn:hover { border-color: var(--accent); color: var(--accent); background: var(--accent-light); }
  .lang-btn:focus-visible { box-shadow: var(--focus-ring); outline: none; }

  .theme-btn {
    padding: 7px 10px;
    border: 1.5px solid var(--border);
    border-radius: 6px;
    background: var(--bg-surface);
    color: var(--text-muted);
    font-size: 14px;
    cursor: pointer;
    transition: border-color 0.15s, color 0.15s, background 0.15s;
    line-height: 1;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: 34px;
    min-height: 32px;
  }
  .theme-btn:hover { border-color: var(--accent); color: var(--accent); background: var(--accent-light); }
  .theme-btn:focus-visible { box-shadow: var(--focus-ring); outline: none; }

  /* ---- Update Banner ---- */
  .update-banner {
    display: none;
    align-items: center;
    gap: 12px;
    padding: 10px 20px;
    background: linear-gradient(135deg, var(--accent-light), var(--status-established-bg));
    border-bottom: 1px solid var(--border);
    font-size: 13px;
    color: var(--text-primary);
    flex-shrink: 0;
    animation: bannerIn 0.3s ease-out;
  }
  .update-banner.active { display: flex; }
  .update-banner .update-icon { font-size: 16px; flex-shrink: 0; }
  .update-banner .update-text { flex: 1; }
  .update-banner .update-text strong { color: var(--accent); }
  .update-banner .btn-update {
    padding: 6px 14px;
    border: 1.5px solid var(--accent);
    border-radius: 8px;
    background: var(--accent);
    color: var(--toggle-knob);
    font-size: 12px;
    font-weight: 600;
    cursor: pointer;
    transition: opacity 0.15s, transform 0.15s, box-shadow 0.15s;
    white-space: nowrap;
  }
  .update-banner .btn-update:hover { opacity: 0.85; transform: translateY(-1px); box-shadow: var(--accent-shadow); }
  .update-banner .btn-dismiss {
    padding: 4px 8px;
    border: none;
    background: transparent;
    color: var(--text-muted);
    cursor: pointer;
    font-size: 16px;
    line-height: 1;
    border-radius: 4px;
    transition: background 0.15s, color 0.15s;
  }
  .update-banner .btn-dismiss:hover { background: var(--bg-input); color: var(--text-primary); }
  @keyframes bannerIn { from { opacity: 0; transform: translateY(-100%); } to { opacity: 1; transform: translateY(0); } }
</style>
</head>
<body>
<div class="app" role="main">
  <h1 class="sr-only">ShowPort</h1>
  <div class="loading-bar" id="loadingBar" role="progressbar" aria-label="Loading"></div>

  <div class="update-banner" id="updateBanner" role="alert">
    <span class="update-icon" aria-hidden="true">&#x1F680;</span>
    <span class="update-text" id="updateText"></span>
    <button class="btn-update" id="btnUpdate" onclick="downloadUpdate()"></button>
    <button class="btn-dismiss" onclick="dismissUpdate()" aria-label="Dismiss">&times;</button>
  </div>

  <nav class="toolbar" aria-label="Toolbar">
    <div class="logo" aria-hidden="true">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>
      </svg>
      <span>SHOW PORT</span>
    </div>

    <div class="search-box">
      <input type="text" id="searchInput" placeholder="搜索端口、PID、进程名 ..." aria-label="Search" autofocus />
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>
      </svg>
    </div>

    <div class="toolbar-actions">
      <button class="btn" onclick="refreshData()" title="Ctrl+R" aria-label="Refresh">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/>
          <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
        </svg>
        <span id="labelRefresh">刷新</span>
      </button>
      <div class="auto-refresh">
        <input type="checkbox" class="toggle" id="autoRefreshToggle" role="switch" aria-checked="false" aria-label="Auto refresh" />
        <label for="autoRefreshToggle" id="labelAutoRefresh" style="cursor:pointer;">自动刷新</label>
      </div>
      <button class="lang-btn" id="langBtn" onclick="toggleLang()" aria-label="Switch language">EN</button>
      <button class="theme-btn" id="themeBtn" onclick="toggleTheme()" aria-label="Toggle theme">&#x1F319;</button>
    </div>
  </nav>

  <div class="stats-bar" role="status" aria-live="polite">
    <div class="stat stat-total"><span class="dot" aria-hidden="true"></span><span id="labelTotal">总计</span> <span class="stat-val" id="statTotal">0</span></div>
    <div class="stat stat-listening"><span class="dot" aria-hidden="true"></span>LISTEN <span class="stat-val" id="statListening">0</span></div>
    <div class="stat stat-established"><span class="dot" aria-hidden="true"></span>ESTABLISHED <span class="stat-val" id="statEstablished">0</span></div>
    <div class="stat stat-other"><span class="dot" aria-hidden="true"></span><span id="labelOther">其他</span> <span class="stat-val" id="statOther">0</span></div>
    <div style="margin-left:auto;" id="lastRefresh"></div>
  </div>

  <div class="table-wrap" id="tableWrap">
    <table aria-label="Network connections">
      <thead>
        <tr>
          <th data-col="proto" data-type="str" aria-sort="none"><span class="th-label">协议</span> <span class="sort-arrow" aria-hidden="true"></span></th>
          <th data-col="localAddr" data-type="str" aria-sort="none"><span class="th-label">本地地址</span> <span class="sort-arrow" aria-hidden="true"></span></th>
          <th data-col="localPort" data-type="num" aria-sort="none"><span class="th-label">本地端口</span> <span class="sort-arrow" aria-hidden="true"></span></th>
          <th data-col="remoteAddr" data-type="str" aria-sort="none"><span class="th-label">远程地址</span> <span class="sort-arrow" aria-hidden="true"></span></th>
          <th data-col="remotePort" data-type="num" aria-sort="none"><span class="th-label">远程端口</span> <span class="sort-arrow" aria-hidden="true"></span></th>
          <th data-col="status" data-type="str" aria-sort="none"><span class="th-label">状态</span> <span class="sort-arrow" aria-hidden="true"></span></th>
          <th data-col="pid" data-type="num" aria-sort="none"><span class="th-label">PID</span> <span class="sort-arrow" aria-hidden="true"></span></th>
          <th data-col="procName" data-type="str" aria-sort="none"><span class="th-label">进程名</span> <span class="sort-arrow" aria-hidden="true"></span></th>
          <th aria-label="Actions"><span class="th-label">操作</span></th>
        </tr>
      </thead>
      <tbody id="tableBody"></tbody>
    </table>
  </div>
</div>

<div class="toast-container" id="toastContainer" aria-live="assertive" aria-atomic="true"></div>

<div class="modal-overlay" id="killModal" role="dialog" aria-modal="true" aria-labelledby="modalTitle">
  <div class="modal">
    <h3 id="modalTitle">确认终止进程</h3>
    <p id="killModalMsg"></p>
    <div class="modal-actions">
      <button class="btn-cancel" id="btnCancel" onclick="closeKillModal()">取消</button>
      <button class="btn-confirm-kill" id="btnConfirmKill">终止进程</button>
    </div>
  </div>
</div>

<script>
  const i18n = {
    zh: {
      search: '搜索端口、PID、进程名 ...',
      refresh: '刷新',
      autoRefresh: '自动刷新',
      total: '总计',
      other: '其他',
      th: ['协议','本地地址','本地端口','远程地址','远程端口','状态','PID','进程名','操作'],
      modalTitle: '确认终止进程',
      modalMsg: (name, pid) => '确定要终止进程 <strong>'+name+'</strong> (PID: <strong>'+pid+'</strong>) 吗？',
      cancel: '取消',
      confirmKill: '终止进程',
      updatedAt: t => '更新于 ' + t,
      fetchError: e => '获取数据失败: ' + e,
      autoOn: '已开启自动刷新 (3秒)',
      autoOff: '已关闭自动刷新',
      opError: e => '操作失败: ' + e,
      noMatch: t => '没有匹配 "' + t + '" 的结果',
      noConn: '没有活动连接',
      langBtn: 'EN',
      updateAvailable: (cur, latest) => '发现新版本 <strong>v' + latest + '</strong>（当前 v' + cur + '）',
      updateBtn: '前往下载',
    },
    en: {
      search: 'Search port, PID, process ...',
      refresh: 'Refresh',
      autoRefresh: 'Auto refresh',
      total: 'Total',
      other: 'Other',
      th: ['Proto','Local Addr','Local Port','Remote Addr','Remote Port','Status','PID','Process','Action'],
      modalTitle: 'Confirm Kill Process',
      modalMsg: (name, pid) => 'Kill process <strong>'+name+'</strong> (PID: <strong>'+pid+'</strong>) ?',
      cancel: 'Cancel',
      confirmKill: 'Kill',
      updatedAt: t => 'Updated ' + t,
      fetchError: e => 'Fetch failed: ' + e,
      autoOn: 'Auto refresh on (3s)',
      autoOff: 'Auto refresh off',
      opError: e => 'Operation failed: ' + e,
      noMatch: t => 'No results for "' + t + '"',
      noConn: 'No active connections',
      langBtn: '中文',
      updateAvailable: (cur, latest) => 'New version <strong>v' + latest + '</strong> available (current v' + cur + ')',
      updateBtn: 'Download',
    }
  };

  let lang = 'zh';
  try { lang = localStorage.getItem('showport-lang') || 'zh'; } catch(e) {}

  let theme = 'light';
  try {
    const saved = localStorage.getItem('showport-theme');
    if (saved) { theme = saved; }
    else if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) { theme = 'dark'; }
  } catch(e) {}

  function applyTheme() {
    document.documentElement.setAttribute('data-theme', theme);
    document.getElementById('themeBtn').innerHTML = theme === 'dark' ? '&#x2600;&#xFE0F;' : '&#x1F319;';
  }

  function toggleTheme() {
    theme = theme === 'dark' ? 'light' : 'dark';
    try { localStorage.setItem('showport-theme', theme); } catch(e) {}
    applyTheme();
  }
  let allData = [];
  let sortCol = 'localPort';
  let sortDir = 'asc';
  let autoRefreshTimer = null;
  let pendingKillPid = null;

  function debounce(fn, ms) {
    let timer;
    return function(...args) {
      clearTimeout(timer);
      timer = setTimeout(() => fn.apply(this, args), ms);
    };
  }

  function t(key) { return i18n[lang][key]; }

  function applyLang() {
    const L = i18n[lang];
    document.getElementById('searchInput').placeholder = L.search;
    document.getElementById('labelRefresh').textContent = L.refresh;
    document.getElementById('labelAutoRefresh').textContent = L.autoRefresh;
    document.getElementById('labelTotal').textContent = L.total;
    document.getElementById('labelOther').textContent = L.other;
    document.getElementById('modalTitle').textContent = L.modalTitle;
    document.getElementById('btnCancel').textContent = L.cancel;
    document.getElementById('btnConfirmKill').textContent = L.confirmKill;
    document.getElementById('langBtn').textContent = L.langBtn;
    document.querySelectorAll('.th-label').forEach((el, i) => { el.textContent = L.th[i]; });
    document.documentElement.lang = lang === 'zh' ? 'zh-CN' : 'en';
    if (updateInfo) showUpdateBanner();
  }

  function toggleLang() {
    lang = lang === 'zh' ? 'en' : 'zh';
    try { localStorage.setItem('showport-lang', lang); } catch(e) {}
    applyLang();
    renderTable();
  }

  async function fetchPorts() {
    return await window.pywebview.api.get_ports();
  }

  async function killPid(pid) {
    return await window.pywebview.api.kill_pid(pid, lang);
  }

  function showToast(msg, type) {
    const c = document.getElementById('toastContainer');
    const el = document.createElement('div');
    el.className = 'toast toast-' + (type || 'info');
    el.textContent = msg;
    c.appendChild(el);
    setTimeout(() => {
      el.classList.add('toast-exit');
      el.addEventListener('transitionend', () => el.remove(), { once: true });
    }, 2700);
  }

  async function refreshData() {
    document.getElementById('loadingBar').classList.add('active');
    try {
      allData = await fetchPorts();
      renderTable();
      document.getElementById('lastRefresh').textContent = t('updatedAt')(new Date().toLocaleTimeString(lang === 'zh' ? 'zh-CN' : 'en'));
    } catch (e) {
      showToast(t('fetchError')(e), 'error');
    } finally {
      document.getElementById('loadingBar').classList.remove('active');
    }
  }

  function updateStats(data) {
    const l = data.filter(r => r.status === 'LISTEN').length;
    const e = data.filter(r => r.status === 'ESTABLISHED').length;
    document.getElementById('statTotal').textContent = data.length;
    document.getElementById('statListening').textContent = l;
    document.getElementById('statEstablished').textContent = e;
    document.getElementById('statOther').textContent = data.length - l - e;
  }

  function getSearchTerm() { return document.getElementById('searchInput').value.trim().toLowerCase(); }

  function matchRow(row, term) {
    if (!term) return true;
    const f = [row.proto, row.localAddr, String(row.localPort), row.remoteAddr, String(row.remotePort), row.status, String(row.pid), row.procName];
    return f.some(v => v.toLowerCase().includes(term));
  }

  function getFilteredData() { return allData.filter(r => matchRow(r, getSearchTerm())); }

  function esc(s) { return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

  function hl(text, term) {
    if (!term || !text) return esc(String(text));
    const s = String(text), i = s.toLowerCase().indexOf(term);
    if (i === -1) return esc(s);
    return esc(s.substring(0, i)) + '<mark>' + esc(s.substring(i, i + term.length)) + '</mark>' + esc(s.substring(i + term.length));
  }

  function sortData(data) {
    const col = sortCol, dir = sortDir === 'asc' ? 1 : -1;
    const th = document.querySelector('th[data-col="' + col + '"]');
    const isNum = th && th.dataset.type === 'num';
    return [...data].sort((a, b) => {
      let va = a[col], vb = b[col];
      if (isNum) return ((Number(va)||0) - (Number(vb)||0)) * dir;
      return String(va).toLowerCase().localeCompare(String(vb).toLowerCase()) * dir;
    });
  }

  function renderTable() {
    const tbody = document.getElementById('tableBody');
    const term = getSearchTerm();
    const filtered = getFilteredData();
    let data = sortData(filtered);
    updateStats(filtered);

    if (!data.length) {
      tbody.innerHTML = '<tr><td colspan="9"><div class="empty-state"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg><p>' + (term ? t('noMatch')(esc(term)) : t('noConn')) + '</p></div></td></tr>';
      return;
    }

    tbody.innerHTML = data.map(r => {
      const sc = ['LISTEN','ESTABLISHED','TIME_WAIT','CLOSE_WAIT','NONE'].includes(r.status) ? 'status-'+r.status : 'status-other';
      const dis = r.pid <= 0 ? 'disabled' : '';
      const killLabel = r.pid > 0 ? ' aria-label="Kill '+esc(r.procName)+' (PID: '+r.pid+')"' : '';
      return '<tr>'
        + '<td>' + hl(r.proto, term) + '</td>'
        + '<td>' + hl(r.localAddr, term) + '</td>'
        + '<td class="port-highlight">' + hl(r.localPort, term) + '</td>'
        + '<td>' + hl(r.remoteAddr||'-', term) + '</td>'
        + '<td>' + hl(r.remotePort||'-', term) + '</td>'
        + '<td><span class="status-badge '+sc+'">' + hl(r.status||'-', term) + '</span></td>'
        + '<td>' + hl(r.pid, term) + '</td>'
        + '<td class="proc-name">' + hl(r.procName||'-', term) + '</td>'
        + '<td style="text-align:center"><button class="btn-kill" '+dis+killLabel+' onclick="confirmKill('+r.pid+',\''+esc(r.procName).replace(/'/g,"\\'")+'\')"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="12" cy="12" r="10"/><path d="m15 9-6 6"/><path d="m9 9 6 6"/></svg> Kill</button></td>'
        + '</tr>';
    }).join('');
  }

  function confirmKill(pid, name) {
    pendingKillPid = pid;
    document.getElementById('killModalMsg').innerHTML = t('modalMsg')(esc(name), pid);
    const modal = document.getElementById('killModal');
    modal.classList.remove('closing');
    modal.classList.add('active');
    document.getElementById('btnConfirmKill').focus();
  }

  function closeKillModal() {
    const modal = document.getElementById('killModal');
    modal.classList.add('closing');
    setTimeout(() => {
      modal.classList.remove('active', 'closing');
      pendingKillPid = null;
    }, 200);
  }

  /* Focus trap for modal */
  document.getElementById('killModal').addEventListener('keydown', function(e) {
    if (e.key === 'Tab') {
      const focusable = this.querySelectorAll('button:not([disabled])');
      const first = focusable[0], last = focusable[focusable.length - 1];
      if (e.shiftKey) {
        if (document.activeElement === first) { e.preventDefault(); last.focus(); }
      } else {
        if (document.activeElement === last) { e.preventDefault(); first.focus(); }
      }
    }
  });

  document.getElementById('btnConfirmKill').addEventListener('click', async () => {
    if (pendingKillPid === null) return;
    const pid = pendingKillPid;
    closeKillModal();
    try {
      const r = await killPid(pid);
      showToast(r.message, r.success ? 'success' : 'error');
      if (r.success) setTimeout(refreshData, 500);
    } catch (e) { showToast(t('opError')(e), 'error'); }
  });

  document.querySelectorAll('th[data-col]').forEach(th => {
    th.addEventListener('click', () => {
      const col = th.dataset.col;
      if (sortCol === col) sortDir = sortDir === 'asc' ? 'desc' : 'asc';
      else { sortCol = col; sortDir = 'asc'; }
      document.querySelectorAll('th[data-col]').forEach(h => {
        h.classList.remove('sorted');
        h.setAttribute('aria-sort', 'none');
      });
      th.classList.add('sorted');
      th.querySelector('.sort-arrow').textContent = sortDir === 'asc' ? '▲' : '▼';
      th.setAttribute('aria-sort', sortDir === 'asc' ? 'ascending' : 'descending');
      renderTable();
    });
  });

  document.getElementById('searchInput').addEventListener('input', debounce(renderTable, 150));

  document.getElementById('autoRefreshToggle').addEventListener('change', e => {
    e.target.setAttribute('aria-checked', e.target.checked);
    if (e.target.checked) {
      autoRefreshTimer = setInterval(refreshData, 3000);
      showToast(t('autoOn'), 'info');
    } else {
      clearInterval(autoRefreshTimer);
      showToast(t('autoOff'), 'info');
    }
  });

  document.addEventListener('keydown', e => {
    if ((e.ctrlKey && e.key === 'r') || e.key === 'F5') { e.preventDefault(); refreshData(); }
    if (e.ctrlKey && e.key === 'f') { e.preventDefault(); document.getElementById('searchInput').focus(); document.getElementById('searchInput').select(); }
    if (e.key === 'Escape') {
      if (document.getElementById('killModal').classList.contains('active')) closeKillModal();
      else { document.getElementById('searchInput').value = ''; renderTable(); }
    }
  });

  let updateInfo = null;

  async function checkUpdate() {
    try {
      const result = await window.pywebview.api.check_update();
      if (result.hasUpdate) {
        updateInfo = result;
        showUpdateBanner();
      }
    } catch (e) { /* silent fail */ }
  }

  function showUpdateBanner() {
    if (!updateInfo) return;
    document.getElementById('updateText').innerHTML = t('updateAvailable')(updateInfo.currentVersion, updateInfo.latestVersion);
    document.getElementById('btnUpdate').textContent = t('updateBtn');
    document.getElementById('updateBanner').classList.add('active');
  }

  function downloadUpdate() {
    if (updateInfo && updateInfo.url) {
      window.pywebview.api.open_url(updateInfo.url);
    }
  }

  function dismissUpdate() {
    document.getElementById('updateBanner').classList.remove('active');
  }

  window.addEventListener('pywebviewready', function() { applyTheme(); applyLang(); refreshData(); checkUpdate(); });
</script>
</body>
</html>
"""


def main():
    api = Api()
    window = webview.create_window(
        'ShowPort',
        html=HTML,
        js_api=api,
        width=1100,
        height=720,
        min_size=(800, 500),
        background_color='#1e1f2e',
    )
    webview.start(debug=False)


if __name__ == '__main__':
    main()
